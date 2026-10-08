"""Candidate communication: drafts, server-enforced approval, double-confirmed
send, and the complete audit trail.

No test in this file ever reaches a real mail provider: the mailer factory is
always replaced with a stub, and the tests that exercise the provider gates do
so with an explicitly faked connection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import comms
from app.sources.gmail import GmailSendError

from tests.conftest import create_profile, sample_resume_text, upload_and_process

FAKE_ACCOUNT = "hr.team@example.com"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def make_candidate(env, *, name="Test Candidate", email="test.candidate@example.com") -> int:
    profile_id = create_profile(env.client, title="Software Engineering Intern")
    upload_and_process(env.client, profile_id, [("resume.txt", sample_resume_text(name, email).encode())])
    items = env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"]
    assert items, "candidate was not created"
    return items[0]["id"]


def emails_url(candidate_id: int) -> str:
    return f"/api/candidates/{candidate_id}/emails"


def make_draft(env, candidate_id: int, email_type="interview_invitation", actor="Local Reviewer") -> dict:
    response = env.client.post(emails_url(candidate_id), json={"email_type": email_type, "actor": actor})
    assert response.status_code == 201, response.text
    return response.json()


def approve(env, email: dict, *, actor="Local Reviewer", revision=None) -> dict:
    response = env.client.post(
        f"/api/emails/{email['id']}/approve",
        json={"revision": revision or email["revision"], "actor": actor},
    )
    assert response.status_code == 200, response.text
    return response.json()


def update(env, email: dict, **changes) -> dict:
    payload = {
        "recipient": changes.get("recipient", email["recipient"]),
        "subject": changes.get("subject", email["subject"]),
        "body": changes.get("body", email["body"]),
        "actor": changes.get("actor", "Local Reviewer"),
    }
    response = env.client.post(f"/api/emails/{email['id']}/update", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def send(env, email: dict, *, confirm=True, revision=None, content_hash=None, recipient=None, actor="Local Reviewer"):
    response = env.client.post(
        f"/api/emails/{email['id']}/send",
        json={
            "revision": revision if revision is not None else email["revision"],
            "content_hash": content_hash if content_hash is not None else email["content_hash"],
            "recipient": recipient if recipient is not None else email["recipient"],
            "confirm": confirm,
            "actor": actor,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def connect_gmail(env, monkeypatch, *, account=FAKE_ACCOUNT):
    tokens = {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "account": account,
    }
    monkeypatch.setattr("app.sources.gmail.get_tokens", lambda ctx: dict(tokens))
    return tokens


def stub_mailer(monkeypatch, *, error: Exception | None = None, result=None):
    calls: list[dict] = []

    def factory(ctx):
        def send(recipient, subject, body):
            calls.append({"recipient": recipient, "subject": subject, "body": body})
            if error is not None:
                raise error
            return result or {"id": "stub-message-1"}

        return send

    monkeypatch.setattr(comms, "gmail_mailer", factory)
    return calls


def audit_events(env, event_type: str) -> list[dict]:
    rows = env.client.get("/api/audit?limit=200").json()["items"]
    return [row for row in rows if row["event_type"] == event_type]


def log_outcomes(env, email_id: int) -> list[str]:
    detail = env.client.get(f"/api/emails/{email_id}").json()
    return [entry["outcome"] for entry in detail["log"]]


# --------------------------------------------------------------------------
# drafts
# --------------------------------------------------------------------------


def test_list_and_draft_generation(env):
    candidate_id = make_candidate(env)
    listing = env.client.get(emails_url(candidate_id)).json()
    assert listing["items"] == []
    assert listing["provider"]["connected"] is False
    assert listing["provider"]["provider"] == "gmail"
    assert "not connected" in listing["provider"]["detail"]
    assert listing["approval_ttl_hours"] == comms.APPROVAL_TTL_HOURS
    assert [option["value"] for option in listing["types"]] == list(comms.EMAIL_TYPES)
    assert "never sends itself" in listing["send_policy"]
    assert listing["candidate"]["is_demo"] is False

    email = make_draft(env, candidate_id)
    assert email["email_type"] == "interview_invitation"
    assert email["status"] == "DRAFT"
    assert email["display_state"] == "DRAFT"
    assert email["revision"] == 1
    assert email["recipient"] == "test.candidate@example.com"
    assert "Software Engineering Intern" in email["subject"]
    assert "Test Candidate" in email["body"]
    assert email["content_hash"] == ""
    assert email["sent_at"] is None
    assert email["log"] == []

    events = audit_events(env, "email_draft_created")
    assert len(events) == 1
    assert events[0]["candidate_id"] == candidate_id

    # every type can be generated and each one describes itself honestly
    for email_type in comms.EMAIL_TYPES:
        created = make_draft(env, candidate_id, email_type=email_type)
        assert created["type_label"] == comms.EMAIL_TYPE_INFO[email_type]["label"]


def test_edit_bumps_revision_and_validates(env):
    candidate_id = make_candidate(env)
    email = make_draft(env, candidate_id)

    revised = update(env, email, subject="Interview invitation — updated")
    assert revised["revision"] == 2
    assert revised["subject"] == "Interview invitation — updated"
    assert revised["status"] == "DRAFT"

    # saving identical content is a no-op, not a revision
    same = update(env, revised)
    assert same["revision"] == 2

    bad_recipient = env.client.post(
        f"/api/emails/{email['id']}/update",
        json={"recipient": "not-an-email", "subject": "s", "body": "b"},
    )
    assert bad_recipient.status_code == 400
    assert "valid email" in bad_recipient.json()["detail"]

    newline_subject = env.client.post(
        f"/api/emails/{email['id']}/update",
        json={"recipient": email["recipient"], "subject": "line\r\nbreak", "body": "b"},
    )
    assert newline_subject.status_code == 400
    assert "single line" in newline_subject.json()["detail"]

    empty_body = env.client.post(
        f"/api/emails/{email['id']}/update",
        json={"recipient": email["recipient"], "subject": "s", "body": ""},
    )
    assert empty_body.status_code == 400


def test_approval_binds_exact_revision(env):
    candidate_id = make_candidate(env)
    email = make_draft(env, candidate_id)
    revised = update(env, email, body=email["body"] + "\nExtra line.")

    stale = env.client.post(f"/api/emails/{email['id']}/approve", json={"revision": 1})
    assert stale.status_code == 400
    assert "v2" in stale.json()["detail"]

    approved = approve(env, revised, actor="HR Lead")
    assert approved["status"] == "APPROVED"
    assert approved["display_state"] == "APPROVED"
    assert approved["approved_revision"] == approved["revision"] == 2
    assert approved["approved_by"] == "HR Lead"
    assert approved["approved_at"]
    assert approved["approval_expires_at"]
    assert approved["approved_expired"] is False
    assert approved["content_hash"] == comms.content_hash(
        approved["recipient"], approved["subject"], approved["body"]
    )

    events = audit_events(env, "email_approved")
    assert len(events) == 1
    assert "HR Lead" in events[0]["message"]


def test_edit_after_approval_invalidates_it(env):
    candidate_id = make_candidate(env)
    email = approve(env, make_draft(env, candidate_id))

    revised = update(env, email, body=email["body"] + "\nOne more paragraph.")
    assert revised["status"] == "DRAFT"
    assert revised["display_state"] == "DRAFT"
    assert revised["approved_by"] == ""
    assert revised["approved_at"] is None
    assert revised["approved_revision"] is None
    assert revised["content_hash"] == ""
    assert revised["revision"] == 2

    invalidations = audit_events(env, "email_approval_invalidated")
    assert len(invalidations) == 1
    assert "Approve the new revision" in invalidations[0]["message"]

    # the (now unapproved) email cannot be sent
    outcome = send(env, revised)
    assert outcome["outcome"] == "BLOCKED_NOT_APPROVED"
    assert outcome["sent"] is False


def test_recipient_required_before_approval(env):
    profile_id = create_profile(env.client, title="No-Email Role")
    text = sample_resume_text("No Email", "placeholder@example.com").replace(
        "placeholder@example.com", ""
    )
    upload_and_process(env.client, profile_id, [("resume.txt", text.encode())])
    candidate = env.client.get(f"/api/candidates?profile_id={profile_id}").json()["items"][0]
    assert not candidate["email"]

    draft = make_draft(env, candidate["id"])
    assert draft["recipient"] == ""
    blocked = env.client.post(f"/api/emails/{draft['id']}/approve", json={"revision": 1})
    assert blocked.status_code == 400
    assert "recipient" in blocked.json()["detail"].lower()

    fixed = update(env, draft, recipient="now.valid@example.com")
    approved = approve(env, fixed)
    assert approved["status"] == "APPROVED"


# --------------------------------------------------------------------------
# send gates (every blocked attempt is recorded)
# --------------------------------------------------------------------------


def test_send_requires_the_final_confirmation(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)))

    outcome = send(env, email, confirm=False)
    assert outcome["outcome"] == "BLOCKED_CONFIRMATION_REQUIRED"
    assert outcome["sent"] is False
    assert "Nothing was sent" in outcome["message"]
    assert calls == []
    assert outcome["email"]["sent_at"] is None
    assert log_outcomes(env, email["id"]) == ["BLOCKED_CONFIRMATION_REQUIRED"]
    assert len(audit_events(env, "email_send_blocked")) == 1


def test_send_blocked_without_approval(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    email = make_draft(env, make_candidate(env))
    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_NOT_APPROVED"
    assert calls == []


def test_send_blocked_when_gmail_is_not_connected(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)))

    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_NOT_CONNECTED"
    assert "not connected" in outcome["message"]
    assert outcome["sent"] is False
    assert calls == []
    assert outcome["email"]["sent_at"] is None


def test_send_blocked_on_stale_revision_hash_or_recipient(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    connect_gmail(env, monkeypatch)
    email = make_draft(env, make_candidate(env))
    revised = update(env, email, body=email["body"] + "\nEdited line.")  # v2
    approved = approve(env, revised)

    stale_revision = send(env, approved, revision=1)
    assert stale_revision["outcome"] == "BLOCKED_STATUS_MISMATCH"

    wrong_hash = send(env, approved, content_hash="0" * 64)
    assert wrong_hash["outcome"] == "BLOCKED_STATUS_MISMATCH"

    wrong_recipient = send(env, approved, recipient="someone.else@example.com")
    assert wrong_recipient["outcome"] == "BLOCKED_RECIPIENT_MISMATCH"

    assert calls == []
    assert set(log_outcomes(env, email["id"])) == {
        "BLOCKED_STATUS_MISMATCH",
        "BLOCKED_RECIPIENT_MISMATCH",
    }


def test_expired_approval_is_refused(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    connect_gmail(env, monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)))

    stale_time = (datetime.now(timezone.utc) - timedelta(hours=comms.APPROVAL_TTL_HOURS + 1)).isoformat(
        timespec="seconds"
    )
    conn = env.ctx.connect()
    try:
        conn.execute(
            "UPDATE candidate_emails SET approved_at = ? WHERE id = ?", (stale_time, email["id"])
        )
    finally:
        conn.close()

    detail = env.client.get(f"/api/emails/{email['id']}").json()
    assert detail["approved_expired"] is True

    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_APPROVAL_EXPIRED"
    assert "expired" in outcome["message"]
    assert calls == []


def test_demo_records_are_never_sent(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    connect_gmail(env, monkeypatch)
    candidate_id = make_candidate(env)
    conn = env.ctx.connect()
    try:
        conn.execute("UPDATE candidates SET is_demo = 1 WHERE id = ?", (candidate_id,))
    finally:
        conn.close()

    email = approve(env, make_draft(env, candidate_id))
    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_DEMO_RECORD"
    assert "demo" in outcome["message"].lower()
    assert calls == []
    assert outcome["email"]["sent_at"] is None


def test_stale_attempt_is_never_silently_retried(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    connect_gmail(env, monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)))

    conn = env.ctx.connect()
    try:
        conn.execute(
            """INSERT INTO email_send_log
               (email_id, candidate_id, outcome, recipient, subject, actor, detail, created_at)
               VALUES (?, ?, 'SENDING', ?, ?, 'Local Reviewer', 'crashed mid-send', ?)""",
            (email["id"], email["candidate_id"], email["recipient"], email["subject"], "2026-10-01T00:00:00+00:00"),
        )
    finally:
        conn.close()

    detail = env.client.get(f"/api/emails/{email['id']}").json()
    assert detail["display_state"] == "SENDING"

    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_UNRESOLVED_ATTEMPT"
    assert "Sent folder" in outcome["message"]
    assert calls == []


# --------------------------------------------------------------------------
# the happy path and provider outcomes
# --------------------------------------------------------------------------


def test_full_send_success_then_duplicate_blocked(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    connect_gmail(env, monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)), actor="HR Lead")

    outcome = send(env, email, confirm=True)
    assert outcome["outcome"] == "SENT"
    assert outcome["sent"] is True
    assert outcome["email"]["sent_at"]
    assert outcome["email"]["display_state"] == "SENT"
    assert outcome["email"]["sender_account"] == "h***@example.com"
    assert calls == [
        {"recipient": email["recipient"], "subject": email["subject"], "body": email["body"]}
    ]
    assert log_outcomes(env, email["id"]) == ["SENDING", "SENT"]
    assert len(audit_events(env, "email_sent")) == 1

    duplicate = send(env, email)
    assert duplicate["outcome"] == "BLOCKED_DUPLICATE_SEND"
    assert "already sent" in duplicate["message"]
    assert len(calls) == 1

    # a sent email cannot be edited or cancelled
    assert env.client.post(
        f"/api/emails/{email['id']}/update",
        json={"recipient": email["recipient"], "subject": "x", "body": "y"},
    ).status_code == 400
    assert env.client.post(
        f"/api/emails/{email['id']}/cancel", json={"actor": "Local Reviewer"}
    ).status_code == 400


def test_failed_attempt_can_be_retried_then_uncertain_blocks_retry(env, monkeypatch):
    connect_gmail(env, monkeypatch)
    email = approve(env, make_draft(env, make_candidate(env)))

    # A definitive failure (provider rejected) keeps the approval and allows an
    # explicit, user-driven retry.
    stub_mailer(monkeypatch, error=GmailSendError("Gmail rejected the message (HTTP 422). Nothing was sent."))
    failed = send(env, email)
    assert failed["outcome"] == "FAILED"
    assert failed["sent"] is False
    assert failed["email"]["sent_at"] is None
    assert failed["email"]["display_state"] == "FAILED"
    assert failed["email"]["status"] == "APPROVED"
    assert len(audit_events(env, "email_send_failed")) == 1

    calls = stub_mailer(monkeypatch, result={"id": "stub-message-2"})
    retried = send(env, email)
    assert retried["outcome"] == "SENT"
    assert calls and calls[0]["recipient"] == email["recipient"]

    # An uncertain outcome can never be retried on the same draft — a retry
    # could double-deliver to a real person. Cancel is the resolution path.
    other = approve(env, make_draft(env, make_candidate(env, name="Second Person", email="second@example.com")))
    stub_mailer(
        monkeypatch,
        error=GmailSendError("No definitive answer from Gmail (connection problem).", uncertain=True),
    )
    uncertain = send(env, other)
    assert uncertain["outcome"] == "UNKNOWN"
    assert uncertain["email"]["display_state"] == "UNKNOWN"
    assert uncertain["email"]["sent_at"] is None
    assert len(audit_events(env, "email_send_unknown")) == 1

    calls = stub_mailer(monkeypatch)
    blocked = send(env, other)
    assert blocked["outcome"] == "BLOCKED_UNRESOLVED_ATTEMPT"
    assert "no definitive outcome" in blocked["message"]
    assert calls == []

    cancelled = env.client.post(
        f"/api/emails/{other['id']}/cancel", json={"actor": "Local Reviewer", "reason": "Resolved: verify in Sent."}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["display_state"] == "CANCELLED"


def test_cancel_flow(env, monkeypatch):
    calls = stub_mailer(monkeypatch)
    email = make_draft(env, make_candidate(env))

    cancelled = env.client.post(
        f"/api/emails/{email['id']}/cancel", json={"actor": "HR Lead", "reason": "Role closed."}
    ).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["display_state"] == "CANCELLED"
    assert cancelled["log"][-1]["outcome"] == "CANCELLED"
    assert "Role closed." in cancelled["log"][-1]["detail"]
    assert len(audit_events(env, "email_cancelled")) == 1

    again = env.client.post(f"/api/emails/{email['id']}/cancel", json={"actor": "HR Lead"})
    assert again.status_code == 200  # idempotent

    blocked = send(env, email)
    assert blocked["outcome"] == "BLOCKED_NOT_APPROVED"
    assert calls == []

    edit = env.client.post(
        f"/api/emails/{email['id']}/update",
        json={"recipient": email["recipient"], "subject": "x", "body": "y"},
    )
    assert edit.status_code == 400


# --------------------------------------------------------------------------
# scoping, 404s and secret hygiene
# --------------------------------------------------------------------------


def test_not_found_errors(env):
    candidate_id = make_candidate(env)
    assert env.client.get(emails_url(999999)).status_code == 404
    assert env.client.post(emails_url(999999), json={"email_type": "general"}).status_code == 404
    assert env.client.get("/api/emails/999999").status_code == 404
    assert env.client.post("/api/emails/999999/approve", json={"revision": 1}).status_code == 404
    assert env.client.post("/api/emails/999999/cancel", json={}).status_code == 404

    other = make_candidate(env, name="Other Person", email="other.person@example.com")
    email = make_draft(env, candidate_id)
    assert env.client.get(emails_url(other)).json()["items"] == []
    detail = env.client.get(f"/api/emails/{email['id']}").json()
    assert detail["candidate_id"] == candidate_id


def test_tokens_never_appear_in_responses(env, monkeypatch):
    secret_token = "SEKRET-ACCESS-TOKEN-XYZ"
    secret_refresh = "SEKRET-REFRESH-TOKEN-XYZ"
    tokens = {
        "access_token": secret_token,
        "refresh_token": secret_refresh,
        "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "account": FAKE_ACCOUNT,
    }
    monkeypatch.setattr("app.sources.gmail.get_tokens", lambda ctx: dict(tokens))
    stub_mailer(monkeypatch)

    candidate_id = make_candidate(env)
    email = approve(env, make_draft(env, candidate_id))
    outcome = send(env, email)
    assert outcome["outcome"] == "SENT"
    assert outcome["email"]["sender_account"] == "h***@example.com"

    for url in (
        emails_url(candidate_id),
        f"/api/emails/{email['id']}",
        "/api/audit?limit=200",
        f"/api/candidates/{candidate_id}",
    ):
        body = env.client.get(url).text
        assert secret_token not in body
        assert secret_refresh not in body
        assert FAKE_ACCOUNT not in body  # the account is only ever shown masked


def test_status_endpoint_reports_provider_policy_and_attempt_log(env, monkeypatch):
    stub_mailer(monkeypatch)
    status = env.client.get("/api/comms/status").json()
    assert status["provider"]["connected"] is False
    assert status["provider"]["account"] is None
    assert "never sends itself" in status["send_policy"]
    assert status["approval_ttl_hours"] == comms.APPROVAL_TTL_HOURS
    assert status["recent_attempts"] == []

    email = make_draft(env, make_candidate(env))  # no approval on purpose
    outcome = send(env, email)
    assert outcome["outcome"] == "BLOCKED_NOT_APPROVED"

    status = env.client.get("/api/comms/status").json()
    assert status["recent_attempts"], "the blocked attempt must be visible in the log tail"
    entry = status["recent_attempts"][0]
    assert entry["outcome"] == "BLOCKED_NOT_APPROVED"
    assert entry["outcome_label"] == "Blocked — not approved"

    # the status payload itself never exposes tokens or the raw account
    connect_gmail(env, monkeypatch)
    body = env.client.get("/api/comms/status").text
    assert "fake-access-token" not in body
    assert "fake-refresh-token" not in body
    assert FAKE_ACCOUNT not in body
    assert "h***@example.com" in body

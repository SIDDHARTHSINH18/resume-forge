"""Resume intake sources: connectors, filtering, preview/import, audit, security.

All Gmail interactions in these tests use deterministic mocked HTTP transport
with synthetic fixtures. No real credentials, accounts or network calls.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.sources import gmail as gmail_module
from app.sources.base import (
    SearchCriteria,
    SourceError,
    SourceNotConfiguredError,
    SourceUnavailableError,
    classify_attachment,
)
from app.sources.gmail import (
    GMAIL_SCOPE,
    GmailSource,
    build_gmail_query,
    sanitize_keyword,
    sanitize_sender,
)
from app.sources.linkedin import LINKEDIN_MESSAGE, LinkedInSource
from app.sources.manual import MANUAL_MESSAGE, ManualUploadSource
from app.sources.mock import FIXTURE_MESSAGES
from app.sources.service import _INSTANCES
from tests.conftest import create_profile, sample_resume_text, wait_for_job

MOCK_CRITERIA = {
    "date_from": "2026-09-01",
    "date_to": "2026-09-30",
    "sender": "",
    "keywords": ["resume", "cv", "application"],
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def cards(client) -> dict[str, dict]:
    return {card["kind"]: card for card in client.get("/api/sources").json()["items"]}


def mock_preview(client, source_id: int, profile_id: int, **overrides) -> dict:
    payload = {"profile_id": profile_id, **MOCK_CRITERIA, **overrides}
    response = client.post(f"/api/sources/{source_id}/preview", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def mock_import(client, source_id: int, sync_id: int) -> tuple[int, dict]:
    response = client.post(f"/api/sources/{source_id}/import", json={"sync_id": sync_id})
    return response.status_code, response.json()


def audit_events(client, limit: int = 300) -> list[dict]:
    return client.get(f"/api/audit?limit={limit}").json()["items"]


def db_rows(env, sql: str, params: tuple = ()) -> list[dict]:
    conn = env.ctx.connect()
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def gmail_fixture_bytes() -> bytes:
    return sample_resume_text("Gmail Candidate", "gmail.candidate@example.com").encode("utf-8")


def _internal_date(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


GMAIL_MESSAGE_ID = "mock-gmail-msg-1"
GMAIL_ATTACHMENT_ID = "mock-gmail-att-1"


def gmail_message_payload() -> dict:
    return {
        "id": GMAIL_MESSAGE_ID,
        "internalDate": _internal_date(datetime(2026, 9, 10, 9, 30, tzinfo=timezone.utc)),
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "jobs@company-demo.com"},
                {"name": "Subject", "value": "Application - Gmail test resume"},
            ],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "filename": "", "body": {"size": 12}},
                    ],
                },
                {
                    "filename": "gmail_candidate.txt",
                    "mimeType": "text/plain",
                    "body": {"attachmentId": GMAIL_ATTACHMENT_ID, "size": len(gmail_fixture_bytes())},
                },
                {
                    "filename": "unrelated_archive.zip",
                    "mimeType": "application/zip",
                    "body": {"attachmentId": "mock-gmail-att-zip", "size": 40},
                },
            ],
        },
    }


def gmail_transport_handler(seen: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if path.endswith("/users/me/messages"):
            return httpx.Response(200, json={"messages": [{"id": GMAIL_MESSAGE_ID}]})
        if "/attachments/" in path:
            data = base64.urlsafe_b64encode(gmail_fixture_bytes()).decode()
            return httpx.Response(200, json={"data": data})
        if path.endswith(f"/messages/{GMAIL_MESSAGE_ID}"):
            return httpx.Response(200, json=gmail_message_payload())
        if path.endswith("/users/me/profile"):
            return httpx.Response(200, json={"emailAddress": "demo.inbox@example-demo.com"})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return handler


def install_gmail_mock(monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request] | None = None) -> None:
    """Route the Gmail singleton's API calls to the deterministic mock transport."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(gmail_transport_handler(seen)), base_url=gmail_module.API_BASE)

    monkeypatch.setattr(_INSTANCES["gmail"], "_client_factory", factory)
    monkeypatch.setattr(_INSTANCES["gmail"], "_http", None)


def configure_gmail(env, *, client_id: str = "demo-client-id.apps.googleusercontent.com", client_secret: str = "demo-client-secret") -> None:
    gmail_module.save_client_config(
        env.ctx,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=gmail_module.DEFAULT_REDIRECT_URI,
    )


def connect_gmail_tokens(env, *, account: str = "demo.inbox@example-demo.com") -> None:
    gmail_module.save_tokens(
        env.ctx,
        {
            "access_token": "mock-access-token",
            "refresh_token": "mock-refresh-token",
            "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "account": account,
        },
    )


# --------------------------------------------------------------------------
# source listing / honest states
# --------------------------------------------------------------------------


def test_source_cards_show_honest_states(env):
    listing = cards(env.client)
    assert set(listing) == {"manual", "gmail", "mock", "linkedin"}

    assert listing["manual"]["state"] == "AVAILABLE"
    assert listing["manual"]["message"] == MANUAL_MESSAGE
    assert listing["manual"]["connectable"] is False
    assert listing["manual"]["id"] is None

    assert listing["gmail"]["state"] == "NOT_CONNECTED"
    assert listing["gmail"]["is_test_source"] is False
    assert listing["gmail"]["id"] is not None

    assert listing["mock"]["state"] == "AVAILABLE"
    assert listing["mock"]["display_name"] == "Mock source (testing only)"
    assert listing["mock"]["is_test_source"] is True
    assert "MOCK SOURCE" in listing["mock"]["message"]

    assert listing["linkedin"]["state"] == "UNAVAILABLE"
    assert listing["linkedin"]["message"] == LINKEDIN_MESSAGE
    assert listing["linkedin"]["connectable"] is False


def test_linkedin_has_no_scraping_path(env):
    source = LinkedInSource()
    with pytest.raises(SourceUnavailableError) as connect_error:
        source.connect(env.ctx, {})
    assert connect_error.value.reason == LINKEDIN_MESSAGE
    with pytest.raises(SourceUnavailableError):
        source.search(env.ctx, SearchCriteria())


def test_only_stateful_sources_persist_rows(env):
    cards(env.client)
    kinds = {row["kind"] for row in db_rows(env, "SELECT kind FROM resume_sources")}
    assert kinds == {"gmail", "mock"}


# --------------------------------------------------------------------------
# Gmail query construction and criteria validation
# --------------------------------------------------------------------------


def test_gmail_search_requires_explicit_privacy_window(env):
    source = GmailSource()
    with pytest.raises(SourceError, match="Choose both a start date and an end date"):
        source.search(env.ctx, SearchCriteria())


def test_gmail_query_range_is_inclusive_of_end_date():
    query = build_gmail_query(SearchCriteria(date_from="2026-09-01", date_to="2026-09-30"))
    assert query == "after:2026/09/01 before:2026/10/01"


def test_gmail_query_sender_and_keywords():
    query = build_gmail_query(
        SearchCriteria(sender="jobs@company-demo.com", keywords=["resume", "cv"])
    )
    assert query == 'from:jobs@company-demo.com subject:("resume" OR "cv")'


def test_gmail_sender_injection_is_rejected():
    with pytest.raises(SourceError, match="Sender filter may only contain"):
        sanitize_sender('x" OR from:ceo@evil.example')
    with pytest.raises(SourceError):
        build_gmail_query(SearchCriteria(sender="a b"))


def test_gmail_keyword_syntax_is_stripped():
    assert sanitize_keyword('resume" OR has:attachment') == "resume OR has attachment"
    assert sanitize_keyword("cv (urgent)") == "cv urgent"
    with pytest.raises(SourceError):
        sanitize_keyword('"()"')


def test_criteria_validation_messages():
    with pytest.raises(SourceError, match="End date must be on or after start date."):
        SearchCriteria(date_from="2026-09-30", date_to="2026-09-01").validate()
    with pytest.raises(SourceError, match="Start date must be a valid date"):
        SearchCriteria(date_from="30-09-2026").validate()
    with pytest.raises(SourceError, match="At most 8 keywords"):
        SearchCriteria(keywords=[f"k{index}" for index in range(9)]).validate()
    with pytest.raises(SourceError, match="A keyword is too long"):
        SearchCriteria(keywords=["x" * 61]).validate()
    with pytest.raises(SourceError, match="Sender filter is too long"):
        SearchCriteria(sender="a" * 121).validate()


def test_attachment_classification():
    assert classify_attachment("resume.pdf") == "supported"
    assert classify_attachment("RESUME.DOCX") == "supported"
    assert classify_attachment("notes.txt") == "supported"
    assert classify_attachment("photo.png") == "unsupported"
    assert classify_attachment("archive.zip") == "dangerous"
    assert classify_attachment("setup.exe") == "dangerous"
    assert classify_attachment("run.bat") == "dangerous"
    assert classify_attachment("noextension") == "unsupported"


# --------------------------------------------------------------------------
# mock source: preview classification
# --------------------------------------------------------------------------


def test_mock_preview_classifies_duplicates_and_unsupported(env):
    profile_id = create_profile(env.client)
    mock_id = cards(env.client)["mock"]["id"]
    body = mock_preview(env.client, mock_id, profile_id)

    counts = body["counts"]
    assert counts["messages_scanned"] == len(FIXTURE_MESSAGES) == 9
    assert counts["messages_matched"] == 7
    assert counts["attachments_found"] == 8
    assert counts["new_resumes"] == 6
    assert counts["duplicates"] == 1
    assert counts["duplicates_total"] == 1
    assert counts["unsupported"] == 1
    assert counts["failed"] == 0
    assert counts["already_imported"] == 0
    assert body["status"] == "PREVIEWED"
    assert body["source"]["kind"] == "mock"
    assert body["source"]["display_name"] == "Mock source (testing only)"

    items = {item["attachment_name"]: item for item in body["items"]}
    assert len(items) == 8
    duplicate = items["aarav_patel_resume_copy.txt"]
    assert duplicate["status"] == "DUPLICATE"
    assert "already appeared in this scan" in duplicate["detail"]
    assert "mock-msg-0001" in duplicate["detail"]

    unsupported = items["kabir_portfolio.zip"]
    assert unsupported["status"] == "UNSUPPORTED"
    assert unsupported["detail"].startswith("IGNORED_UNSUPPORTED_TYPE")

    assert items["aarav_patel_resume.txt"]["status"] == "NEW"
    assert items["priya_menon_resume.docx"]["status"] == "NEW"


def test_mock_preview_respects_date_and_keyword_filters(env):
    profile_id = create_profile(env.client)
    mock_id = cards(env.client)["mock"]["id"]

    # August only: just the one older message.
    august = mock_preview(
        env.client,
        mock_id,
        profile_id,
        date_from="2026-08-01",
        date_to="2026-08-31",
        keywords=[],
    )
    assert august["counts"]["messages_matched"] == 1
    assert [item["attachment_name"] for item in august["items"]] == ["devansh_joshi_cv.txt"]

    # Keyword that matches no subject.
    none = mock_preview(env.client, mock_id, profile_id, keywords=["payroll"])
    assert none["counts"]["messages_matched"] == 0
    assert none["counts"]["attachments_found"] == 0
    assert none["messages"]["no_matches"] is True

    # Sender filter.
    careers = mock_preview(env.client, mock_id, profile_id, sender="careers@company-demo.com", keywords=[])
    assert careers["counts"]["messages_matched"] == 4


def test_preview_rejects_invalid_range_without_creating_sync(env):
    profile_id = create_profile(env.client)
    mock_id = cards(env.client)["mock"]["id"]
    response = env.client.post(
        f"/api/sources/{mock_id}/preview",
        json={"profile_id": profile_id, "date_from": "2026-09-30", "date_to": "2026-09-01"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "End date must be on or after start date."
    assert db_rows(env, "SELECT id FROM source_syncs") == []


# --------------------------------------------------------------------------
# mock source: import → candidates (the canonical pipeline)
# --------------------------------------------------------------------------


def run_mock_import(env, profile_id: int) -> tuple[int, dict, dict]:
    mock_id = cards(env.client)["mock"]["id"]
    preview = mock_preview(env.client, mock_id, profile_id)
    status, summary = mock_import(env.client, mock_id, preview["sync_id"])
    assert status == 200, summary
    job = wait_for_job(env.client, summary["job_id"])
    return mock_id, summary, job


def test_mock_import_runs_the_existing_pipeline(env):
    profile_id = create_profile(env.client)
    mock_id, summary, job = run_mock_import(env, profile_id)

    assert summary["imported"] == 6
    assert summary["failed"] == 0
    assert summary["message"] == "6 imported."
    assert summary["duplicates"] == 1
    assert summary["unsupported"] == 1
    assert summary["total_attachments"] == 8

    assert job["status"] == "COMPLETED_WITH_ERRORS"
    assert job["completed"] == 5
    assert job["failed"] == 1
    assert job["label"] == "Mock source (testing only) import — 6 file(s)"

    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert listing["total"] == 5
    names = sorted(item["name"] for item in listing["items"])
    assert names == ["Aarav Patel", "Kabir Mehta", "Nikhil Reddy", "Priya Menon", "Riya Shah"]

    # The deliberately corrupted PDF fails honestly inside the pipeline.
    failed = db_rows(env, "SELECT filename, status, error_reason FROM resumes WHERE status = 'FAILED'")
    assert len(failed) == 1
    assert "scanned_resume.pdf" in failed[0]["filename"]
    assert failed[0]["error_reason"]

    # Imported items link back to the created candidates.
    imported_items = db_rows(
        env, "SELECT attachment_name, status, resume_id FROM source_items WHERE status = 'IMPORTED'"
    )
    assert len(imported_items) == 6
    assert all(row["resume_id"] for row in imported_items)


def test_source_sync_history_and_detail(env):
    profile_id = create_profile(env.client)
    mock_id, summary, _ = run_mock_import(env, profile_id)

    history = env.client.get(f"/api/sources/{mock_id}/syncs").json()
    assert history["source"]["kind"] == "mock"
    assert len(history["items"]) == 1
    row = history["items"][0]
    assert row["status"] == "COMPLETED"
    assert row["messages_scanned"] == 9
    assert row["messages_matched"] == 7
    assert row["attachments_found"] == 8
    assert row["resumes_imported"] == 6
    assert row["duplicates_found"] == 1
    assert row["unsupported"] == 1
    assert row["failures"] == 0
    assert row["profile_title"] == "Software Engineering Intern"
    assert row["criteria"]["date_from"] == "2026-09-01"
    assert row["completed_at"]

    detail = env.client.get(f"/api/sources/{mock_id}/syncs/{summary['sync_id']}").json()
    assert len(detail["items"]) == 8
    assert any(item["candidate_name"] == "Aarav Patel" for item in detail["items"])

    missing = env.client.get(f"/api/sources/{mock_id}/syncs/9999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Sync not found for this source."


def test_source_card_tracks_last_successful_sync(env):
    profile_id = create_profile(env.client)
    mock_id, _, _ = run_mock_import(env, profile_id)
    card = cards(env.client)["mock"]
    assert card["last_successful_sync_at"]
    assert card["sync_count"] == 1


# --------------------------------------------------------------------------
# idempotent refetch and re-import
# --------------------------------------------------------------------------


def test_refetch_is_idempotent_and_never_reimports(env):
    profile_id = create_profile(env.client)
    mock_id, summary, _ = run_mock_import(env, profile_id)
    resumes_before = db_rows(env, "SELECT COUNT(*) AS n FROM resumes WHERE profile_id = ?", (profile_id,))[0]["n"]

    second = mock_preview(env.client, mock_id, profile_id)
    assert second["counts"]["new_resumes"] == 0
    assert second["counts"]["already_imported"] == 6
    assert second["counts"]["duplicates"] == 1
    assert second["counts"]["duplicates_total"] == 7

    status, body = mock_import(env.client, mock_id, second["sync_id"])
    assert status == 400
    assert body["detail"] == (
        "There are no new resumes in this scan to import. "
        "Duplicates and unsupported files are never re-imported."
    )

    status, repeat = mock_import(env.client, mock_id, summary["sync_id"])
    assert status == 200
    assert repeat["already_imported"] is True
    assert repeat["imported"] == 6
    assert repeat["message"].startswith("Already imported on")

    resumes_after = db_rows(env, "SELECT COUNT(*) AS n FROM resumes WHERE profile_id = ?", (profile_id,))[0]["n"]
    assert resumes_after == resumes_before == 6
    candidates = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert candidates["total"] == 5


def test_rescan_history_reports_duplicates_and_already_imported_separately(env):
    """History counts must not blur duplicates and already-imported files."""
    profile_id = create_profile(env.client)
    mock_id, _, _ = run_mock_import(env, profile_id)
    second = mock_preview(env.client, mock_id, profile_id)

    history = env.client.get(f"/api/sources/{mock_id}/syncs").json()["items"]
    row = next(item for item in history if item["id"] == second["sync_id"])
    assert row["duplicates_found"] == 1
    assert row["already_imported"] == second["counts"]["already_imported"]
    assert row["resumes_imported"] == 0
    # Every attachment is accounted for exactly once.
    assert (
        row["resumes_imported"]
        + row["duplicates_found"]
        + row["already_imported"]
        + row["unsupported"]
        == row["attachments_found"]
    )

    stored = db_rows(
        env,
        "SELECT duplicates_found FROM source_syncs WHERE id = ?",
        (second["sync_id"],),
    )
    assert stored[0]["duplicates_found"] == 1

    detail = env.client.get(f"/api/sources/{mock_id}/syncs/{second['sync_id']}").json()
    assert detail["duplicates_found"] == 1
    assert detail["already_imported"] == second["counts"]["already_imported"]


def test_repeated_scans_keep_prior_imports_stable(env):
    """A third scan must not degrade earlier classifications or re-offer imported files.

    Regression: the item upsert overwrites status on every scan, so a scan after
    the 'already imported' one used to fall back to content checks — mislabelling
    the failed-parse PDF as NEW and previously-imported files as duplicates.
    """
    profile_id = create_profile(env.client)
    mock_id, _, _ = run_mock_import(env, profile_id)

    second = mock_preview(env.client, mock_id, profile_id)
    second_items = {item["attachment_name"]: item for item in second["items"]}
    failed_pdf = second_items["scanned_resume.pdf"]
    assert failed_pdf["status"] == "ALREADY_IMPORTED"
    assert "parsing failed" in failed_pdf["detail"]

    third = mock_preview(env.client, mock_id, profile_id)
    counts = third["counts"]
    assert counts["new_resumes"] == 0
    assert counts["already_imported"] == 6
    assert counts["duplicates"] == 1
    assert counts["unsupported"] == 1
    assert counts["duplicates_total"] == 7

    third_items = {item["attachment_name"]: item for item in third["items"]}
    assert third_items["scanned_resume.pdf"]["status"] == "ALREADY_IMPORTED"
    assert "parsing failed" in third_items["scanned_resume.pdf"]["detail"]
    assert third_items["aarav_patel_resume.txt"]["status"] == "ALREADY_IMPORTED"
    assert "Already imported from this source on" in third_items["aarav_patel_resume.txt"]["detail"]

    history = env.client.get(f"/api/sources/{mock_id}/syncs").json()["items"]
    row = next(item for item in history if item["id"] == third["sync_id"])
    assert row["resumes_imported"] == 0
    assert row["already_imported"] == 6

    resumes_before = db_rows(
        env, "SELECT COUNT(*) AS n FROM resumes WHERE profile_id = ?", (profile_id,)
    )[0]["n"]
    status, body = mock_import(env.client, mock_id, third["sync_id"])
    assert status == 400
    assert "no new resumes" in body["detail"]
    resumes_after = db_rows(
        env, "SELECT COUNT(*) AS n FROM resumes WHERE profile_id = ?", (profile_id,)
    )[0]["n"]
    assert resumes_after == resumes_before


def test_duplicate_after_import_matches_existing_candidate(env):
    profile_id = create_profile(env.client)
    mock_id, _, _ = run_mock_import(env, profile_id)

    second = mock_preview(env.client, mock_id, profile_id, keywords=["resend"])
    items = second["items"]
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "DUPLICATE"
    assert "matched existing candidate: Aarav Patel" in item["detail"]
    assert item["candidate_name"] == "Aarav Patel"


def test_sync_now_requires_first_fetch_then_uses_last_sync(env):
    profile_id = create_profile(env.client)
    mock_id = cards(env.client)["mock"]["id"]

    response = env.client.post(f"/api/sources/{mock_id}/sync-now", json={"profile_id": profile_id})
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "This source has no successful sync yet — choose a date range for the first fetch."
    )

    run_mock_import(env, profile_id)
    last_sync = cards(env.client)["mock"]["last_successful_sync_at"]
    assert last_sync
    incremental = env.client.post(
        f"/api/sources/{mock_id}/sync-now",
        json={"profile_id": profile_id, "keywords": ["resume", "cv", "application"]},
    )
    assert incremental.status_code == 200
    body = incremental.json()
    assert body["criteria"]["date_from"] == last_sync[:10]
    assert body["counts"]["new_resumes"] == 0


# --------------------------------------------------------------------------
# audit trail
# --------------------------------------------------------------------------


def test_audit_trail_records_intake_events(env):
    profile_id = create_profile(env.client)
    run_mock_import(env, profile_id)
    events = audit_events(env.client)
    kinds = [event["event_type"] for event in events]

    assert "source_sync_started" in kinds
    assert "source_message_matched" in kinds
    assert "resume_attachment_found" in kinds
    assert "resume_import_started" in kinds
    assert "resume_imported" in kinds
    assert "source_sync_completed" in kinds
    assert kinds.count("resume_imported") == 6

    started = next(event for event in events if event["event_type"] == "source_sync_started")
    assert started["data"]["criteria"]["date_from"] == "2026-09-01"

    imported = [event for event in events if event["event_type"] == "resume_imported"]
    assert all("Mock source (testing only)" in event["message"] for event in imported)

    completed = next(event for event in events if event["event_type"] == "source_sync_completed")
    assert completed["data"]["imported"] == 6
    assert completed["data"]["failed"] == 0


# --------------------------------------------------------------------------
# Gmail: configuration, OAuth state, connect URL
# --------------------------------------------------------------------------


def test_gmail_preview_before_connection_is_honest(env):
    profile_id = create_profile(env.client)
    gmail_id = cards(env.client)["gmail"]["id"]
    response = env.client.post(
        f"/api/sources/{gmail_id}/preview", json={"profile_id": profile_id, **MOCK_CRITERIA}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Gmail is not connected. Connect the account first."


def test_gmail_config_connect_url_and_masking(env):
    gmail_id = cards(env.client)["gmail"]["id"]
    secret = "demo-client-secret-value"

    response = env.client.put(
        f"/api/sources/{gmail_id}/config",
        json={
            "client_id": "demo-client.apps.googleusercontent.com",
            "client_secret": secret,
            "redirect_uri": gmail_module.DEFAULT_REDIRECT_URI,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_client_secret"] is True
    assert body["secret_source"] == "config file"
    assert body["client_id_masked"] != body["client_id"]
    assert secret not in response.text

    card = cards(env.client)["gmail"]
    assert card["state"] == "NOT_CONNECTED"
    assert card["message"] == "Gmail OAuth client is configured. Connect the account to start fetching resumes."
    assert card["configured"] is True

    connect = env.client.post(f"/api/sources/{gmail_id}/connect")
    assert connect.status_code == 200, connect.text
    auth_url = connect.json()["auth_url"]
    params = parse_qs(urlparse(auth_url).query)
    assert params["scope"] == [GMAIL_SCOPE]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["client_id"] == ["demo-client.apps.googleusercontent.com"]
    assert params["state"][0]
    assert params["redirect_uri"] == [gmail_module.DEFAULT_REDIRECT_URI]

    events = audit_events(env.client)
    configured = next(event for event in events if event["event_type"] == "source_configured")
    assert configured["data"]["client_id_masked"] != "demo-client.apps.googleusercontent.com"
    assert secret not in json.dumps(events)


def test_gmail_secret_never_reaches_sqlite(env):
    gmail_id = cards(env.client)["gmail"]["id"]
    secret = "sqlite-should-never-hold-this"
    env.client.put(
        f"/api/sources/{gmail_id}/config",
        json={"client_id": "demo-client.apps.googleusercontent.com", "client_secret": secret},
    )
    connect_gmail_tokens(env)

    for path in (env.ctx.db_path, env.ctx.db_path.with_name(env.ctx.db_path.name + "-wal")):
        if path.exists():
            assert secret.encode() not in path.read_bytes(), f"secret leaked into {path.name}"
    assert secret not in env.client.get("/api/sources").text

    config_text = (env.ctx.config_path).read_text(encoding="utf-8")
    assert secret in config_text  # documented limitation: local git-ignored file, plaintext


def test_gmail_disconnect_clears_tokens(env):
    configure_gmail(env)
    connect_gmail_tokens(env)
    gmail_id = cards(env.client)["gmail"]["id"]
    assert cards(env.client)["gmail"]["state"] == "CONNECTED"
    assert cards(env.client)["gmail"]["account"] == "d***@example-demo.com"

    response = env.client.post(f"/api/sources/{gmail_id}/disconnect")
    assert response.status_code == 200
    assert gmail_module.get_tokens(env.ctx) is None

    card = cards(env.client)["gmail"]
    assert card["state"] == "NOT_CONNECTED"
    assert card["message"] == "Gmail OAuth client is configured. Connect the account to start fetching resumes."
    assert "source_disconnected" in [event["event_type"] for event in audit_events(env.client)]


def test_oauth_state_is_single_use(env):
    payload = gmail_module.start_oauth_state(env.ctx, redirect_uri=gmail_module.DEFAULT_REDIRECT_URI)
    assert payload["challenge"] and payload["verifier"]

    with pytest.raises(SourceError, match="Gmail connection failed"):
        gmail_module.consume_oauth_state(env.ctx, "not-the-state")
    # The mismatched attempt consumed the state.
    with pytest.raises(SourceError, match="Gmail connection failed"):
        gmail_module.consume_oauth_state(env.ctx, payload["state"])

    fresh = gmail_module.start_oauth_state(env.ctx, redirect_uri=gmail_module.DEFAULT_REDIRECT_URI)
    consumed = gmail_module.consume_oauth_state(env.ctx, fresh["state"])
    assert consumed["verifier"] == fresh["verifier"]

    with pytest.raises(SourceError, match="Gmail connection failed"):
        gmail_module.consume_oauth_state(env.ctx, fresh["state"])


def test_oauth_state_expires(env):
    payload = gmail_module.start_oauth_state(env.ctx, redirect_uri=gmail_module.DEFAULT_REDIRECT_URI)
    stale = dict(payload)
    stale["created_at"] = (datetime.now(timezone.utc) - timedelta(seconds=gmail_module.STATE_TTL_SECONDS + 30)).isoformat()
    conn = env.ctx.connect()
    try:
        conn.execute(
            "UPDATE settings SET value = ? WHERE key = ?",
            (gmail_module._json_dumps(stale), gmail_module.STATE_SETTING),
        )
    finally:
        conn.close()
    with pytest.raises(SourceError, match="expired"):
        gmail_module.consume_oauth_state(env.ctx, payload["state"])


def test_gmail_exchange_failure_is_honest(env):
    configure_gmail(env)
    failing = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(400, json={"error": "invalid_grant"})),
        base_url=gmail_module.TOKEN_ENDPOINT,
    )
    with pytest.raises(SourceError) as error:
        gmail_module.exchange_code(
            env.ctx, code="code", verifier="verifier", redirect_uri="http://127.0.0.1:8100/cb", http=failing
        )
    assert error.value.reason == "Gmail connection failed. No resumes were imported."


# --------------------------------------------------------------------------
# Gmail API client against mocked transport
# --------------------------------------------------------------------------


def test_gmail_api_reports_expired_session(env):
    api = gmail_module.GmailApi(
        "token", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401)), base_url=gmail_module.API_BASE)
    )
    with pytest.raises(SourceNotConfiguredError) as error:
        api.list_message_ids("")
    assert error.value.reason == "Gmail session expired or was revoked. Reconnect the account."


def test_gmail_api_reports_unreachable_service(env):
    api = gmail_module.GmailApi(
        "token", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)), base_url=gmail_module.API_BASE)
    )
    with pytest.raises(SourceError) as error:
        api.get_message("msg")
    assert error.value.reason == "Unable to reach Gmail. No resumes were imported."


def test_gmail_search_extracts_messages_and_attachments(env):
    configure_gmail(env)
    connect_gmail_tokens(env)
    seen: list[httpx.Request] = []
    source = GmailSource(client_factory=lambda: httpx.Client(
        transport=httpx.MockTransport(gmail_transport_handler(seen)), base_url=gmail_module.API_BASE
    ))
    criteria = SearchCriteria(
        date_from="2026-09-01", date_to="2026-09-30", sender="jobs@company-demo.com", keywords=["application"]
    )
    scan = source.search(env.ctx, criteria)

    list_requests = [request for request in seen if request.url.path.endswith("/users/me/messages")]
    assert list_requests
    assert list_requests[0].url.params["q"] == (
        'after:2026/09/01 before:2026/10/01 from:jobs@company-demo.com subject:("application")'
    )

    assert scan.messages_scanned == 1
    assert scan.messages_matched == 1
    assert [item.attachment_name for item in scan.attachments] == [
        "gmail_candidate.txt",
        "unrelated_archive.zip",
    ]
    attachment = scan.attachments[0]
    assert attachment.sender == "jobs@company-demo.com"
    assert attachment.subject == "Application - Gmail test resume"
    assert attachment.timestamp.startswith("2026-09-10")

    raw = source.fetch_attachment(env.ctx, attachment)
    assert raw == gmail_fixture_bytes()


def test_gmail_preview_and_import_end_to_end(env, monkeypatch):
    profile_id = create_profile(env.client)
    configure_gmail(env)
    connect_gmail_tokens(env)
    seen: list[httpx.Request] = []
    install_gmail_mock(monkeypatch, seen)

    gmail_id = cards(env.client)["gmail"]["id"]
    assert cards(env.client)["gmail"]["state"] == "CONNECTED"

    response = env.client.post(
        f"/api/sources/{gmail_id}/preview",
        json={
            "profile_id": profile_id,
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "sender": "jobs@company-demo.com",
            "keywords": ["application"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["display_name"] == "Gmail"
    assert body["counts"]["messages_scanned"] == 1
    assert body["counts"]["attachments_found"] == 2
    assert body["counts"]["new_resumes"] == 1
    assert body["counts"]["unsupported"] == 1

    list_requests = [request for request in seen if request.url.path.endswith("/users/me/messages")]
    assert list_requests
    query = list_requests[0].url.params["q"]
    assert query == 'after:2026/09/01 before:2026/10/01 from:jobs@company-demo.com subject:("application")'

    sync_id = body["sync_id"]
    status, summary = mock_import(env.client, gmail_id, sync_id)
    assert status == 200, summary
    assert summary["imported"] == 1
    job = wait_for_job(env.client, summary["job_id"])
    assert job["status"] == "COMPLETED"
    assert job["label"] == "Gmail import — 1 file(s)"

    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert listing["total"] == 1
    candidate = listing["items"][0]
    assert candidate["name"] == "Gmail Candidate"

    imported_events = [event for event in audit_events(env.client) if event["event_type"] == "resume_imported"]
    assert len(imported_events) == 1
    assert imported_events[0]["message"].startswith("Gmail:")

    history = env.client.get(f"/api/sources/{gmail_id}/syncs").json()["items"]
    assert history[0]["status"] == "COMPLETED"
    assert history[0]["resumes_imported"] == 1


# --------------------------------------------------------------------------
# manual upload remains the original, fully functional source
# --------------------------------------------------------------------------


def test_manual_upload_path_still_creates_candidates(env):
    profile_id = create_profile(env.client)
    upload = env.client.post(
        f"/api/profiles/{profile_id}/upload",
        files=[("files", ("manual.txt", sample_resume_text("Manual Candidate", "manual@example.com").encode(), "text/plain"))],
    )
    assert upload.status_code == 202
    job = wait_for_job(env.client, upload.json()["job_id"])
    assert job["completed"] == 1
    listing = env.client.get(f"/api/candidates?profile_id={profile_id}").json()
    assert [item["name"] for item in listing["items"]] == ["Manual Candidate"]


def test_manual_source_has_no_fetch_step(env):
    source = ManualUploadSource()
    with pytest.raises(SourceUnavailableError, match="Manual upload has no fetch step"):
        source.search(env.ctx, SearchCriteria())
    with pytest.raises(SourceUnavailableError, match="Manual upload has no fetch step"):
        source.fetch_attachment(env.ctx, None)


def test_unknown_source_ids_are_refused(env):
    profile_id = create_profile(env.client)
    response = env.client.post("/api/sources/99999/preview", json={"profile_id": profile_id, **MOCK_CRITERIA})
    assert response.status_code == 404
    assert response.json()["detail"] == "Resume source not found."

    listing = env.client.get("/api/sources/99999")
    assert listing.status_code == 404

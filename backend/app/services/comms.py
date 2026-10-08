"""Candidate communication: professional email drafts with server-enforced
double approval, and a complete send audit.

Rules this module encodes:
- A draft never sends itself. The flow is: pick a type → generate → review and
  edit → approve the *exact* revision → final confirmation screen → an explicit
  send. Every step is a separate, deliberate call.
- Approval is bound to one revision and one content hash. Editing the draft
  after approval invalidates the approval (status returns to DRAFT).
- Sending is blocked unless: the draft is APPROVED, the approval is fresh
  (APPROVAL_TTL_HOURS), the revision/hash/recipient match exactly what was
  approved, no earlier attempt is unresolved, the email was never sent, the
  explicit confirmation flag is present, a provider is connected, and the
  candidate is not a demo record.
- Every attempt — sent, failed, unknown, or blocked — is written to
  email_send_log, and the important transitions go to the audit trail too.
- Demo records are synthetic by definition, so they are never emailed, even
  when a provider is connected.
- Tokens and client secrets never leave the local config store; this module
  only ever asks the Gmail connector to send.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..audit import record
from ..util import now_iso
from ..sources import gmail as gmail_module
from ..sources.base import SourceError
from ..sources.gmail import GmailSendError

APPROVAL_TTL_HOURS = 24

SUBJECT_MAX = 200
BODY_MAX = 20_000
RECIPIENT_MAX = 254
ACTOR_MAX = 120

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

EMAIL_TYPES = (
    "interview_invitation",
    "shortlist_confirmation",
    "rejection",
    "assignment",
    "follow_up",
    "general",
)

EMAIL_TYPE_INFO = {
    "interview_invitation": {
        "label": "Interview invitation",
        "hint": "Invites the candidate to an interview. Fill in the bracketed placeholders before approving.",
    },
    "shortlist_confirmation": {
        "label": "Shortlist confirmation",
        "hint": "Confirms the candidate is moving to the next stage and sets expectations.",
    },
    "rejection": {
        "label": "Rejection",
        "hint": "A respectful close. Add an optional personal note before approving.",
    },
    "assignment": {
        "label": "Assignment / assessment",
        "hint": "Sends a take-home task or assessment with a deadline and submission details.",
    },
    "follow_up": {
        "label": "Follow-up",
        "hint": "A polite follow-up on an application already in progress.",
    },
    "general": {
        "label": "General message",
        "hint": "A neutral skeleton for anything that does not fit the other types.",
    },
}

STATUS_LABELS = {
    "DRAFT": "Draft",
    "APPROVED": "Approved",
    "CANCELLED": "Cancelled",
}

DISPLAY_LABELS = {
    "DRAFT": "Draft",
    "APPROVED": "Approved",
    "SENDING": "Sending",
    "SENT": "Sent",
    "FAILED": "Send failed",
    "CANCELLED": "Cancelled",
    "UNKNOWN": "Outcome unknown",
}

OUTCOME_LABELS = {
    "SENDING": "Attempt started",
    "SENT": "Sent",
    "FAILED": "Failed",
    "UNKNOWN": "Outcome unknown",
    "BLOCKED_NOT_APPROVED": "Blocked — not approved",
    "BLOCKED_NOT_CONNECTED": "Blocked — Gmail not connected",
    "BLOCKED_STATUS_MISMATCH": "Blocked — changed since approval",
    "BLOCKED_CONFIRMATION_REQUIRED": "Blocked — confirmation not completed",
    "BLOCKED_RECIPIENT_MISMATCH": "Blocked — recipient mismatch",
    "BLOCKED_APPROVAL_EXPIRED": "Blocked — approval expired",
    "BLOCKED_DUPLICATE_SEND": "Blocked — already sent",
    "BLOCKED_UNRESOLVED_ATTEMPT": "Blocked — earlier attempt unresolved",
    "BLOCKED_DEMO_RECORD": "Blocked — demo record",
    "CANCELLED": "Cancelled",
}

SEND_POLICY = (
    "A draft never sends itself: generate → review and edit → approve the exact revision → "
    "confirm recipient, sender, subject and body on the final screen → send. Editing after "
    "approval invalidates the approval; approvals expire after "
    f"{APPROVAL_TTL_HOURS} hours; every attempt — including blocked ones — is written to the "
    "send log. Emails for demo records are never sent."
)

_PROVIDER_DISCONNECTED_DETAIL = (
    "Gmail is not connected. Connect the account on the Resume Sources page to enable sending — "
    "sends stay blocked until then."
)


class CommsError(Exception):
    """A communication request that cannot be carried out as asked."""

    def __init__(self, reason: str, *, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


# --------------------------------------------------------------------------
# content helpers
# --------------------------------------------------------------------------


def content_hash(recipient: str, subject: str, body: str) -> str:
    """Hash of the exact revision content an approval is bound to."""
    payload = f"{recipient}\n{subject}\n{body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def valid_recipient(value: str) -> bool:
    return bool(value) and len(value) <= RECIPIENT_MAX and bool(_EMAIL_RE.match(value))


def _clean_single_line(value: str, *, label: str, max_len: int) -> str:
    text = (value or "").strip()
    if "\r" in text or "\n" in text or _CONTROL_RE.search(text):
        raise CommsError(f"The {label} must be a single line without control characters.")
    if len(text) > max_len:
        raise CommsError(f"The {label} is longer than {max_len} characters.")
    return text


def _clean_body(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").strip()
    if len(text) > BODY_MAX:
        raise CommsError(f"The message body is longer than {BODY_MAX} characters.")
    return text


def _actor(value: str | None) -> str:
    return ((value or "").strip() or "Local Reviewer")[:ACTOR_MAX]


# --------------------------------------------------------------------------
# provider status
# --------------------------------------------------------------------------


def provider_status(ctx) -> dict:
    """Who would actually send an approved email, and are they connected?"""
    tokens = gmail_module.get_tokens(ctx)
    if not tokens:
        return {
            "provider": "gmail",
            "connected": False,
            "account": None,
            "detail": _PROVIDER_DISCONNECTED_DETAIL,
        }
    account = gmail_module.mask_email(tokens.get("account"))
    return {
        "provider": "gmail",
        "connected": True,
        "account": account,
        "detail": (
            f"Approved emails are sent through the connected Gmail account ({account or 'account'}). "
            "Nothing is ever sent without the explicit final confirmation."
        ),
    }


def gmail_mailer(ctx):
    """Return the production send callable.

    Contract: call(recipient, subject, body) -> provider payload; raises
    GmailSendError. `uncertain=True` means the outcome is unknown and must not
    be silently retried. Tests replace this factory with a stub.
    """

    def send(recipient: str, subject: str, body: str) -> dict:
        tokens = gmail_module.get_tokens(ctx)
        if not tokens:
            raise GmailSendError("Gmail is not connected. Nothing was sent.")
        try:
            token = gmail_module.access_token_for(ctx)
        except SourceError as exc:
            # no usable token: nothing was sent, so this failure is definitive
            raise GmailSendError(exc.reason)
        except httpx.HTTPError:
            raise GmailSendError("Could not refresh the Gmail session (connection problem). Nothing was sent.")
        sender = tokens.get("account") or "me"
        raw = build_raw_message(sender, recipient, subject, body)
        api = gmail_module.GmailApi(token)
        try:
            return api.send_raw(raw)
        except httpx.HTTPError:
            raise GmailSendError(
                "No definitive answer from Gmail (connection problem). The email may or may not have been sent.",
                uncertain=True,
            )

    return send


def build_raw_message(sender: str, recipient: str, subject: str, body: str) -> bytes:
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message.as_bytes()


# --------------------------------------------------------------------------
# draft templates
# --------------------------------------------------------------------------


def _candidate_name(candidate) -> str:
    name = (candidate["name"] or "").strip()
    return name if name and name != "Not found" else ""


def build_template(email_type: str, candidate, profile) -> tuple[str, str]:
    title = (profile["title"] if profile else "") or "the role"
    name = _candidate_name(candidate)
    greeting = f"Dear {name}," if name else "Hello,"
    signoff = "Kind regards,\n[Hiring team]"

    if email_type == "interview_invitation":
        subject = f"Interview invitation — {title}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your application for the {title} role. We would like to invite you "
            "to an interview.\n\n"
            "Proposed details (please edit before approving):\n"
            "- Date and time: [date, time, timezone]\n"
            "- Format: [video call / on-site]\n"
            "- Location or link: [link or address]\n"
            "- Interviewer(s): [names]\n\n"
            "If the proposed time does not suit you, just reply to this email and we will find "
            "an alternative.\n\n"
            f"{signoff}\n"
        )
    elif email_type == "shortlist_confirmation":
        subject = f"Your application — moving forward ({title})"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your application for the {title} role. We are pleased to let you know "
            "that you have been shortlisted for the next stage of our process.\n\n"
            "What happens next (please edit before approving):\n"
            "- [Next step and approximate timing]\n"
            "- [Anything the candidate should prepare]\n\n"
            "We will be in touch with the details shortly.\n\n"
            f"{signoff}\n"
        )
    elif email_type == "rejection":
        subject = f"Update on your application — {title}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for the time and effort you invested in your application for the {title} "
            "role. After careful review, we have decided not to move forward with your application "
            "at this time.\n\n"
            "- [Optional: one line of specific, respectful feedback]\n\n"
            "We appreciate your interest and wish you the very best in your search.\n\n"
            f"{signoff}\n"
        )
    elif email_type == "assignment":
        subject = f"Take-home assignment — {title}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your application for the {title} role. As the next step, we would like "
            "you to complete a short take-home assignment.\n\n"
            "Assignment details (please edit before approving):\n"
            "- Task: [what to build or answer]\n"
            "- Deliverable: [format]\n"
            "- Deadline: [date, time, timezone]\n"
            "- Submission: [link or email]\n\n"
            "Please reply if anything is unclear — we are happy to help.\n\n"
            f"{signoff}\n"
        )
    elif email_type == "follow_up":
        subject = f"Following up — your application for {title}"
        body = (
            f"{greeting}\n\n"
            f"We are following up on your application for the {title} role.\n\n"
            "- [What you are following up on and the next step]\n\n"
            "If you are still interested, just reply to this email and we will continue from there.\n\n"
            f"{signoff}\n"
        )
    else:  # general
        subject = f"Regarding your application — {title}"
        body = (
            f"{greeting}\n\n"
            f"We are writing about your application for the {title} role.\n\n"
            "[Write your message here — replace this placeholder before approving.]\n\n"
            f"{signoff}\n"
        )
    return subject, body


# --------------------------------------------------------------------------
# persistence helpers
# --------------------------------------------------------------------------


def _load_email(conn, email_id: int):
    return conn.execute("SELECT * FROM candidate_emails WHERE id = ?", (email_id,)).fetchone()


def _load_candidate(conn, candidate_id: int):
    return conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()


def _load_log(conn, email_id: int) -> list:
    return list(
        conn.execute(
            "SELECT * FROM email_send_log WHERE email_id = ? ORDER BY id", (email_id,)
        )
    )


def _approval_expired(row) -> bool:
    if row["status"] != "APPROVED" or not row["approved_at"]:
        return False
    try:
        approved = datetime.fromisoformat(row["approved_at"])
    except ValueError:
        return True
    return datetime.now(timezone.utc) > approved + timedelta(hours=APPROVAL_TTL_HOURS)


def _approval_expires_at(row) -> str | None:
    if row["status"] != "APPROVED" or not row["approved_at"]:
        return None
    try:
        approved = datetime.fromisoformat(row["approved_at"])
    except ValueError:
        return None
    return (approved + timedelta(hours=APPROVAL_TTL_HOURS)).isoformat(timespec="seconds")


def log_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "outcome": row["outcome"],
        "outcome_label": OUTCOME_LABELS.get(row["outcome"], row["outcome"]),
        "recipient": row["recipient"],
        "subject": row["subject"],
        "sender_account": gmail_module.mask_email(row["sender_account"]) if row["sender_account"] else "",
        "actor": row["actor"],
        "detail": row["detail"],
        "created_at": row["created_at"],
    }


def _display_state(row, logs: list) -> str:
    if row["status"] == "CANCELLED":
        return "CANCELLED"
    if row["sent_at"]:
        return "SENT"
    last_attempt = None
    for entry in logs:
        if entry["outcome"] in ("SENDING", "SENT", "FAILED", "UNKNOWN"):
            last_attempt = entry["outcome"]
    if last_attempt == "SENDING":
        return "SENDING"  # an attempt started and never recorded an outcome
    if last_attempt == "FAILED":
        return "FAILED"
    if last_attempt == "UNKNOWN":
        return "UNKNOWN"
    if row["status"] == "APPROVED":
        return "APPROVED"
    return "DRAFT"


def email_to_dict(conn, row, *, include_log: bool = False) -> dict:
    logs = _load_log(conn, row["id"])
    display = _display_state(row, logs)
    last = logs[-1] if logs else None
    payload = {
        "id": row["id"],
        "candidate_id": row["candidate_id"],
        "profile_id": row["profile_id"],
        "email_type": row["email_type"],
        "type_label": EMAIL_TYPE_INFO.get(row["email_type"], {}).get("label", row["email_type"]),
        "recipient": row["recipient"],
        "subject": row["subject"],
        "body": row["body"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "display_state": display,
        "display_label": DISPLAY_LABELS.get(display, display),
        "revision": int(row["revision"] or 1),
        "content_hash": row["content_hash"],
        "approved_revision": row["approved_revision"],
        "approved_by": row["approved_by"],
        "approved_at": row["approved_at"],
        "approval_expires_at": _approval_expires_at(row),
        "approved_expired": _approval_expired(row),
        "sent_at": row["sent_at"],
        "sender_account": (
            gmail_module.mask_email(row["sender_account"]) if row["sender_account"] else ""
        ),
        "drafted_by": row["drafted_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_send": log_row_to_dict(last) if last else None,
    }
    if include_log:
        payload["log"] = [log_row_to_dict(entry) for entry in logs]
    return payload


def _audit(conn, event_type: str, row, *, message: str, data: dict | None = None) -> None:
    record(
        conn,
        event_type,
        entity_type="candidate_email",
        entity_id=row["id"],
        candidate_id=row["candidate_id"],
        profile_id=row["profile_id"],
        message=message,
        data=data,
    )


def _append_log(conn, row, outcome: str, *, actor: str, detail: str, sender_account: str = "") -> None:
    conn.execute(
        """INSERT INTO email_send_log
           (email_id, candidate_id, outcome, sender_account, recipient, subject, actor, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["id"],
            row["candidate_id"],
            outcome,
            sender_account,
            row["recipient"],
            row["subject"],
            actor,
            detail[:2000],
            now_iso(),
        ),
    )


# --------------------------------------------------------------------------
# list / create
# --------------------------------------------------------------------------


def list_payload(ctx, conn, candidate_id: int) -> dict:
    candidate = _load_candidate(conn, candidate_id)
    if candidate is None:
        raise CommsError("Candidate not found.", status=404)
    rows = conn.execute(
        "SELECT * FROM candidate_emails WHERE candidate_id = ? ORDER BY id DESC", (candidate_id,)
    ).fetchall()
    return {
        "items": [email_to_dict(conn, row) for row in rows],
        "provider": provider_status(ctx),
        "types": [
            {"value": key, "label": EMAIL_TYPE_INFO[key]["label"], "hint": EMAIL_TYPE_INFO[key]["hint"]}
            for key in EMAIL_TYPES
        ],
        "approval_ttl_hours": APPROVAL_TTL_HOURS,
        "send_policy": SEND_POLICY,
        "candidate": {
            "id": candidate["id"],
            "name": candidate["name"],
            "email": candidate["email"],
            "is_demo": bool(candidate["is_demo"]),
        },
    }


def status_payload(ctx, conn) -> dict:
    """Global communication state for the Settings page: who would send, the
    policy that gates sending, and the tail of the attempt log (blocked
    attempts included). Read-only."""
    rows = conn.execute("SELECT * FROM email_send_log ORDER BY id DESC LIMIT 10").fetchall()
    return {
        "provider": provider_status(ctx),
        "send_policy": SEND_POLICY,
        "approval_ttl_hours": APPROVAL_TTL_HOURS,
        "types": [
            {"value": key, "label": EMAIL_TYPE_INFO[key]["label"]}
            for key in EMAIL_TYPES
        ],
        "recent_attempts": [log_row_to_dict(row) for row in rows],
    }


def create_draft(ctx, candidate_id: int, *, email_type: str, actor: str) -> dict:
    if email_type not in EMAIL_TYPES:
        raise CommsError(f"Unknown email type '{email_type}'.")
    conn = ctx.connect()
    try:
        candidate = _load_candidate(conn, candidate_id)
        if candidate is None:
            raise CommsError("Candidate not found.", status=404)
        profile = conn.execute(
            "SELECT * FROM screening_profiles WHERE id = ?", (candidate["profile_id"],)
        ).fetchone()
        subject, body = build_template(email_type, candidate, profile)
        candidate_email = (candidate["email"] or "").strip()
        recipient = candidate_email if valid_recipient(candidate_email) else ""
        now = now_iso()
        cursor = conn.execute(
            """INSERT INTO candidate_emails
               (candidate_id, profile_id, email_type, recipient, subject, body, status, revision,
                content_hash, drafted_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', 1, '', ?, ?, ?)""",
            (
                candidate_id,
                candidate["profile_id"],
                email_type,
                recipient,
                subject,
                body,
                _actor(actor),
                now,
                now,
            ),
        )
        email_id = int(cursor.lastrowid)
        row = _load_email(conn, email_id)
        _audit(
            conn,
            "email_draft_created",
            row,
            message=f"{EMAIL_TYPE_INFO[email_type]['label']} draft created by {_actor(actor)}",
            data={"email_type": email_type, "revision": 1},
        )
        return email_to_dict(conn, row, include_log=True)
    finally:
        conn.close()


def get_email(ctx, email_id: int) -> dict:
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        if row is None:
            raise CommsError("Email draft not found.", status=404)
        return email_to_dict(conn, row, include_log=True)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# edit / approve / cancel
# --------------------------------------------------------------------------


def update_email(ctx, email_id: int, *, actor: str, recipient: str, subject: str, body: str) -> dict:
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        if row is None:
            raise CommsError("Email draft not found.", status=404)
        if row["status"] == "CANCELLED":
            raise CommsError("This email was cancelled. Create a new draft instead.")
        if row["sent_at"]:
            raise CommsError("This email was already sent — its content is part of the record and cannot be edited.")

        clean_recipient = (recipient or "").strip()
        if clean_recipient and not valid_recipient(clean_recipient):
            raise CommsError("The recipient must be a single valid email address.")
        clean_subject = _clean_single_line(subject, label="subject", max_len=SUBJECT_MAX)
        if not clean_subject:
            raise CommsError("The subject cannot be empty.")
        clean_body = _clean_body(body)
        if not clean_body:
            raise CommsError("The message body cannot be empty.")

        changed = (
            clean_recipient != row["recipient"]
            or clean_subject != row["subject"]
            or clean_body != row["body"]
        )
        if not changed:
            return email_to_dict(conn, row, include_log=True)

        was_approved = row["status"] == "APPROVED"
        now = now_iso()
        conn.execute(
            """UPDATE candidate_emails
               SET recipient = ?, subject = ?, body = ?, revision = revision + 1,
                   status = 'DRAFT', content_hash = '', approved_revision = NULL,
                   approved_by = '', approved_at = NULL, updated_at = ?
               WHERE id = ?""",
            (clean_recipient, clean_subject, clean_body, now, email_id),
        )
        row = _load_email(conn, email_id)
        _audit(
            conn,
            "email_draft_updated",
            row,
            message=f"Draft revised to v{row['revision']} by {_actor(actor)}",
            data={"revision": row["revision"]},
        )
        if was_approved:
            _audit(
                conn,
                "email_approval_invalidated",
                row,
                message=(
                    f"Approval invalidated — the draft was edited after approval (now v{row['revision']}). "
                    "Approve the new revision before sending."
                ),
                data={"revision": row["revision"]},
            )
        return email_to_dict(conn, row, include_log=True)
    finally:
        conn.close()


def approve_email(ctx, email_id: int, *, actor: str, revision: int) -> dict:
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        if row is None:
            raise CommsError("Email draft not found.", status=404)
        if row["sent_at"]:
            raise CommsError("This email was already sent — sending is final and cannot be re-approved.")
        if row["status"] == "CANCELLED":
            raise CommsError("This email was cancelled. Create a new draft instead.")
        if int(revision or 0) != int(row["revision"]):
            raise CommsError(
                f"This draft is now v{row['revision']} — the approval you attempted was for v{revision}. "
                "Review the current revision and approve it explicitly."
            )
        if not valid_recipient(row["recipient"]):
            raise CommsError("A valid recipient is required before approval. Add the candidate's email address first.")
        if not (row["subject"] or "").strip():
            raise CommsError("A subject is required before approval.")

        digest = content_hash(row["recipient"], row["subject"], row["body"])
        now = now_iso()
        conn.execute(
            """UPDATE candidate_emails
               SET status = 'APPROVED', content_hash = ?, approved_revision = revision,
                   approved_by = ?, approved_at = ?, updated_at = ?
               WHERE id = ?""",
            (digest, _actor(actor), now, now, email_id),
        )
        row = _load_email(conn, email_id)
        _audit(
            conn,
            "email_approved",
            row,
            message=f"v{row['revision']} approved by {_actor(actor)} — approval is valid for {APPROVAL_TTL_HOURS} hours",
            data={"revision": row["revision"], "content_hash": digest[:16]},
        )
        return email_to_dict(conn, row, include_log=True)
    finally:
        conn.close()


def cancel_email(ctx, email_id: int, *, actor: str, reason: str = "") -> dict:
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        if row is None:
            raise CommsError("Email draft not found.", status=404)
        if row["sent_at"]:
            raise CommsError("A sent email cannot be cancelled — it is part of the correspondence record.")
        if row["status"] == "CANCELLED":
            return email_to_dict(conn, row, include_log=True)
        now = now_iso()
        conn.execute(
            "UPDATE candidate_emails SET status = 'CANCELLED', updated_at = ? WHERE id = ?",
            (now, email_id),
        )
        row = _load_email(conn, email_id)
        detail = (reason or "").strip() or "Cancelled by the reviewer."
        _append_log(conn, row, "CANCELLED", actor=_actor(actor), detail=detail)
        _audit(
            conn,
            "email_cancelled",
            row,
            message=f"Email cancelled by {_actor(actor)} — {detail}",
        )
        return email_to_dict(conn, row, include_log=True)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# send (double confirmation, every gate logged)
# --------------------------------------------------------------------------


def _terminal_payload(ctx, email_id: int, outcome: str, *, sent: bool, message: str) -> dict:
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        return {
            "outcome": outcome,
            "outcome_label": OUTCOME_LABELS.get(outcome, outcome),
            "sent": sent,
            "message": message,
            "email": email_to_dict(conn, row, include_log=False),
            "log": [log_row_to_dict(entry) for entry in _load_log(conn, email_id)],
        }
    finally:
        conn.close()


def send_approved_email(
    ctx,
    email_id: int,
    *,
    actor: str,
    revision: int,
    expected_hash: str,
    recipient: str,
    confirm: bool,
    mailer=None,
) -> dict:
    actor = _actor(actor)
    conn = ctx.connect()
    try:
        row = _load_email(conn, email_id)
        if row is None:
            raise CommsError("Email draft not found.", status=404)
        candidate = _load_candidate(conn, row["candidate_id"])
        logs = _load_log(conn, email_id)
        current_hash = content_hash(row["recipient"], row["subject"], row["body"])

        def blocked(outcome: str, detail: str) -> dict:
            _append_log(conn, row, outcome, actor=actor, detail=detail)
            _audit(
                conn,
                "email_send_blocked",
                row,
                message=f"Send blocked ({OUTCOME_LABELS.get(outcome, outcome)}): {detail}",
                data={"outcome": outcome},
            )
            return _terminal_payload(ctx, email_id, outcome, sent=False, message=detail)

        # An earlier attempt that never recorded an outcome must never be
        # silently retried — it may already have reached the candidate.
        if logs and logs[-1]["outcome"] == "SENDING":
            return blocked(
                "BLOCKED_UNRESOLVED_ATTEMPT",
                "A previous send attempt never recorded an outcome. It may already have been sent — "
                "check the sending account's Sent folder (and the recipient's inbox) before doing anything else. "
                "This draft cannot be re-sent; cancel it and create a new draft if needed.",
            )
        # UNKNOWN is terminal for this draft: the provider never gave a
        # definitive answer, so a retry could double-deliver to a real person.
        if logs and logs[-1]["outcome"] == "UNKNOWN":
            return blocked(
                "BLOCKED_UNRESOLVED_ATTEMPT",
                "The previous attempt has no definitive outcome — the email may already have been delivered. "
                "Verify in the sending account's Sent folder first. If it was not delivered, cancel this draft "
                "and create a new one; this draft cannot be re-sent.",
            )
        if row["sent_at"]:
            return blocked(
                "BLOCKED_DUPLICATE_SEND",
                f"This email was already sent on {row['sent_at'][:19].replace('T', ' ')} UTC. "
                "Duplicate sends are blocked by the server.",
            )
        if not confirm:
            return blocked(
                "BLOCKED_CONFIRMATION_REQUIRED",
                "The final confirmation screen was not completed. Nothing was sent.",
            )
        if row["status"] != "APPROVED":
            return blocked(
                "BLOCKED_NOT_APPROVED",
                "Only an approved email can be sent. Approve the exact revision first.",
            )
        if _approval_expired(row):
            return blocked(
                "BLOCKED_APPROVAL_EXPIRED",
                f"The approval expired after {APPROVAL_TTL_HOURS} hours. Review the current revision "
                "and approve it again before sending.",
            )
        if (
            int(revision or 0) != int(row["revision"])
            or (expected_hash or "") != current_hash
            or row["content_hash"] != current_hash
        ):
            return blocked(
                "BLOCKED_STATUS_MISMATCH",
                "The content no longer matches what was approved — it was edited after approval, or the "
                "confirmation screen was stale. Approve the current revision again and repeat the confirmation.",
            )
        if (recipient or "").strip() != row["recipient"]:
            return blocked(
                "BLOCKED_RECIPIENT_MISMATCH",
                "The recipient on the confirmation screen does not match the stored draft. "
                "Review the recipient, re-approve if it changed, and confirm again.",
            )
        if candidate is not None and candidate["is_demo"]:
            return blocked(
                "BLOCKED_DEMO_RECORD",
                "This candidate belongs to the demo workspace (synthetic data). MeritOS never sends email "
                "for demo records — the attempt was blocked and logged.",
            )
        status = provider_status(ctx)
        if not status["connected"]:
            return blocked("BLOCKED_NOT_CONNECTED", status["detail"])

        # All server-side gates passed: record the attempt before calling out.
        _append_log(
            conn,
            row,
            "SENDING",
            actor=actor,
            detail="Attempt confirmed on the final screen; calling the configured provider.",
        )
        _audit(
            conn,
            "email_send_attempted",
            row,
            message=f"Send attempt started by {actor} — v{row['revision']} to {row['recipient']}",
            data={"revision": row["revision"]},
        )
    finally:
        conn.close()

    if mailer is None:
        mailer = gmail_mailer(ctx)
    try:
        result = mailer(row["recipient"], row["subject"], row["body"])
        provider_id = (result or {}).get("id")
        outcome = "SENT"
        detail = f"Accepted by the provider ({provider_id})." if provider_id else "Accepted by the provider."
    except GmailSendError as exc:
        outcome = "UNKNOWN" if exc.uncertain else "FAILED"
        detail = exc.reason
    except Exception:
        outcome = "UNKNOWN"
        detail = (
            "The provider call did not return a definitive outcome. Do not blindly retry — verify in the "
            "sent folder first; this attempt is recorded as unknown."
        )

    conn = ctx.connect()
    try:
        if outcome == "SENT":
            now = now_iso()
            account = ""
            try:
                account = (gmail_module.get_tokens(ctx) or {}).get("account") or ""
            except Exception:
                account = ""
            conn.execute(
                "UPDATE candidate_emails SET sent_at = ?, sender_account = ?, updated_at = ? WHERE id = ?",
                (now, account, now, email_id),
            )
        row = _load_email(conn, email_id)
        _append_log(
            conn,
            row,
            outcome,
            actor=actor,
            detail=detail,
            sender_account=row["sender_account"] or "",
        )
        _audit(
            conn,
            {"SENT": "email_sent", "FAILED": "email_send_failed", "UNKNOWN": "email_send_unknown"}[outcome],
            row,
            message=f"Send result for {row['recipient']}: {OUTCOME_LABELS[outcome]} — {detail}",
            data={"outcome": outcome},
        )
    finally:
        conn.close()
    return _terminal_payload(ctx, email_id, outcome, sent=outcome == "SENT", message=detail)

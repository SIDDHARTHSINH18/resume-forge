"""Gmail connector — official Gmail API via OAuth 2.0.

Security model:
- OAuth 2.0 authorization-code flow with PKCE; scopes are gmail.readonly for
  resume intake plus gmail.send, which the communication service uses *only*
  for emails a reviewer explicitly approved and confirmed. Nothing is ever
  sent automatically.
- The connector never sees or stores a Google password.
- Client credentials and tokens live in the local config file (backend/data/
  config.json), the same local credential store the AI provider keys use.
  The file is git-ignored, never returned in full by the API, and tokens are
  never written to audit events, logs, exports or error messages.
- Attachment bytes are treated strictly as data: they are downloaded, hashed
  and handed to the existing pipeline; they are never executed or interpreted.

The user query is translated into an official Gmail search query. User input
is validated against conservative character allow-lists and can never inject
query syntax.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from ..util import now_iso
from .base import (
    AttachmentCandidate,
    ResumeSource,
    SearchCriteria,
    ScanResult,
    SourceError,
    SourceNotConfiguredError,
    SourceStatus,
    ranged_dates,
    day_after,
)

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
# One consent covers both: intake reads, and the communication service sends
# only explicitly approved emails. Status copy and docs must stay consistent
# with this split.
GMAIL_SCOPE = f"{GMAIL_READ_SCOPE} {GMAIL_SEND_SCOPE}"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8421/api/sources/gmail/oauth/callback"

STATE_TTL_SECONDS = 600
MAX_MESSAGES = 500

CONFIG_KEY = "gmail"
TOKENS_KEY = "gmail_oauth"
STATE_SETTING = "gmail_oauth_state"

_SENDER_RE = re.compile(r"^[A-Za-z0-9._%+\-@*]+$")
_KEYWORD_RE = re.compile(r'[^A-Za-z0-9 \-\+#.]')

GMAIL_MESSAGES = (
    "Gmail session expired or was revoked. Reconnect the account.",
    "Unable to reach Gmail. No resumes were imported.",
)

GMAIL_SEND_PERMISSION_MESSAGE = (
    "The Gmail connection does not grant sending permission. "
    "Reconnect the Gmail account and approve the send scope to enable candidate emails."
)


class GmailSendError(Exception):
    """A send attempt failed.

    `uncertain` is True when the provider never gave a definitive answer
    (timeout, connection drop, 5xx): the message may or may not have been
    accepted, so it must not be silently retried.
    """

    def __init__(self, reason: str, *, uncertain: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.uncertain = uncertain


# --------------------------------------------------------------------------
# query construction (unit-tested; user input never becomes raw syntax)
# --------------------------------------------------------------------------


def sanitize_sender(sender: str) -> str:
    value = (sender or "").strip()
    if not value:
        return ""
    if not _SENDER_RE.match(value):
        raise SourceError(
            "Sender filter may only contain letters, numbers and the characters . _ % + - @ *"
        )
    return value


def sanitize_keyword(keyword: str) -> str:
    value = _KEYWORD_RE.sub(" ", (keyword or "").strip())
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise SourceError("A keyword contained no usable characters.")
    return value


def build_gmail_query(criteria: SearchCriteria) -> str:
    """Translate validated criteria into an official Gmail search query."""
    parts: list[str] = []
    start, end = ranged_dates(criteria)
    if start:
        parts.append(f"after:{start:%Y/%m/%d}")
    if end:
        # Gmail's `before:` is exclusive; use the next day so the end date is inclusive
        parts.append(f"before:{day_after(end):%Y/%m/%d}")
    sender = sanitize_sender(criteria.sender)
    if sender:
        parts.append(f"from:{sender}")
    if criteria.keywords:
        terms = " OR ".join(f'"{sanitize_keyword(word)}"' for word in criteria.keywords)
        parts.append(f"subject:({terms})")
    return " ".join(parts)


# --------------------------------------------------------------------------
# credential storage (local config file, same store as the AI provider keys)
# --------------------------------------------------------------------------


def mask_email(address: str | None) -> str | None:
    if not address:
        return None
    if "@" not in address:
        return address[:1] + "***"
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _env_first(*names: str) -> str:
    """Return the first non-empty environment value among `names`."""
    import os

    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def get_client_config(ctx) -> dict:
    stored = (ctx.read_config() or {}).get(CONFIG_KEY, {}) or {}
    # AILISTER_GMAIL_* is the canonical prefix (matches AILISTER_AI_*);
    # GOOGLE_CLIENT_ID / _SECRET / _REDIRECT_URI are accepted aliases so
    # operators can reuse standard Google OAuth naming without editing
    # this file — the UI hint in Sources.tsx references the alias names.
    client_id = _env_first("AILISTER_GMAIL_CLIENT_ID", "GOOGLE_CLIENT_ID") or stored.get("client_id") or ""
    client_secret = (
        _env_first("AILISTER_GMAIL_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET")
        or stored.get("client_secret")
        or ""
    )
    redirect_uri = (
        _env_first("AILISTER_GMAIL_REDIRECT_URI", "GOOGLE_REDIRECT_URI")
        or stored.get("redirect_uri")
        or DEFAULT_REDIRECT_URI
    )
    secret_from_env = bool(
        _env_first("AILISTER_GMAIL_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET")
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "secret_source": (
            "environment"
            if secret_from_env
            else ("config file" if stored.get("client_secret") else "none")
        ),
    }


def save_client_config(ctx, *, client_id: str, client_secret: str | None, redirect_uri: str | None) -> dict:
    config = ctx.read_config() or {}
    section = config.setdefault(CONFIG_KEY, {})
    section["client_id"] = (client_id or "").strip()
    if client_secret:
        section["client_secret"] = client_secret.strip()
    if redirect_uri:
        section["redirect_uri"] = redirect_uri.strip()
    ctx.write_config(config)
    return get_client_config(ctx)


def clear_client_secret(ctx) -> None:
    config = ctx.read_config() or {}
    section = config.get(CONFIG_KEY) or {}
    section.pop("client_secret", None)
    config[CONFIG_KEY] = section
    ctx.write_config(config)


def get_tokens(ctx) -> dict | None:
    stored = (ctx.read_config() or {}).get(TOKENS_KEY)
    if not stored or not stored.get("refresh_token"):
        return None
    return stored


def save_tokens(ctx, tokens: dict) -> None:
    config = ctx.read_config() or {}
    config[TOKENS_KEY] = tokens
    ctx.write_config(config)


def clear_tokens(ctx) -> None:
    config = ctx.read_config() or {}
    config.pop(TOKENS_KEY, None)
    ctx.write_config(config)


# --------------------------------------------------------------------------
# OAuth state (single-use, short-lived, stored server-side)
# --------------------------------------------------------------------------


def _settings_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _settings_set(conn, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, value, now_iso()),
    )


def _settings_delete(conn, key: str) -> None:
    conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def start_oauth_state(ctx, *, redirect_uri: str) -> dict:
    """Create a single-use state value plus PKCE verifier; returns the payload."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    payload = {
        "state": state,
        "verifier": verifier,
        "challenge": challenge,
        "redirect_uri": redirect_uri,
        "created_at": now_iso(),
    }
    conn = ctx.connect()
    try:
        _settings_set(conn, STATE_SETTING, _json_dumps(payload))
    finally:
        conn.close()
    return payload


def _json_dumps(payload: dict) -> str:
    from ..util import jdumps

    return jdumps(payload)


def consume_oauth_state(ctx, state: str) -> dict:
    """Validate and consume a pending OAuth state. Raises SourceError when invalid."""
    from ..util import jloads

    conn = ctx.connect()
    try:
        raw = _settings_get(conn, STATE_SETTING)
        _settings_delete(conn, STATE_SETTING)  # single use: consumed even when invalid
    finally:
        conn.close()
    if not raw:
        raise SourceError("Gmail connection failed. No resumes were imported. Start the connection again.")
    payload = jloads(raw, {}) or {}
    if not state or payload.get("state") != state:
        raise SourceError("Gmail connection failed. No resumes were imported. Start the connection again.")
    created = payload.get("created_at") or ""
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(created)).total_seconds()
    except ValueError:
        age = STATE_TTL_SECONDS + 1
    if age > STATE_TTL_SECONDS:
        raise SourceError("The Gmail connection request expired. Start the connection again.")
    return payload


def authorization_url(ctx, *, state: str, challenge: str, redirect_uri: str) -> str:
    config = get_client_config(ctx)
    if not config["client_id"]:
        raise SourceNotConfiguredError(
            "Gmail OAuth client ID is not configured. Add your Google Cloud OAuth client in the Gmail card first."
        )
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


# --------------------------------------------------------------------------
# Gmail API client (httpx; a custom transport is injectable for tests)
# --------------------------------------------------------------------------


class GmailApi:
    def __init__(self, access_token: str, *, client: httpx.Client | None = None):
        self.access_token = access_token
        self._client = client or httpx.Client(base_url=API_BASE, timeout=30)

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._client.get(
            path, params=params, headers={"Authorization": f"Bearer {self.access_token}"}
        )
        if response.status_code == 401:
            raise SourceNotConfiguredError(GMAIL_MESSAGES[0])
        if response.status_code >= 400:
            raise SourceError(GMAIL_MESSAGES[1])
        return response.json()

    def list_message_ids(self, query: str, *, max_messages: int = MAX_MESSAGES) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < max_messages:
            params: dict = {"maxResults": min(100, max_messages - len(ids))}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("/users/me/messages", params)
            ids.extend(item["id"] for item in payload.get("messages", []) if item.get("id"))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return ids

    def get_message(self, message_id: str) -> dict:
        return self._get(f"/users/me/messages/{message_id}", {"format": "full"})

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        payload = self._get(f"/users/me/messages/{message_id}/attachments/{attachment_id}")
        data = payload.get("data") or ""
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    def profile_email(self) -> str | None:
        try:
            return self._get("/users/me/profile").get("emailAddress")
        except SourceError:
            return None

    def send_raw(self, raw: bytes) -> dict:
        """Send a fully-formed RFC 2822 message. Raises GmailSendError.

        Status semantics: 4xx means the provider definitively rejected the
        message; timeouts, transport errors and 5xx are ambiguous — the
        message may or may not have been accepted.
        """
        payload = {"raw": base64.urlsafe_b64encode(raw).decode("ascii")}
        try:
            response = self._client.post(
                "/users/me/messages/send",
                json=payload,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        except httpx.HTTPError:
            raise GmailSendError(
                "No definitive answer from Gmail (connection problem). The email may or may not have been sent.",
                uncertain=True,
            )
        if response.status_code == 401:
            raise GmailSendError(GMAIL_MESSAGES[0])
        if response.status_code == 403:
            raise GmailSendError(GMAIL_SEND_PERMISSION_MESSAGE)
        if response.status_code >= 500:
            raise GmailSendError(
                "Gmail reported a server error. The email may or may not have been sent.",
                uncertain=True,
            )
        if response.status_code >= 400:
            raise GmailSendError(f"Gmail rejected the message (HTTP {response.status_code}). Nothing was sent.")
        return response.json()


def extract_headers(message: dict) -> tuple[str, str, str]:
    headers = {
        header.get("name", "").lower(): header.get("value", "")
        for header in (message.get("payload", {}) or {}).get("headers", []) or []
    }
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    internal = message.get("internalDate")
    if internal:
        try:
            timestamp = datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            timestamp = now_iso()
    else:
        timestamp = headers.get("date", "") or now_iso()
    return sender, subject, timestamp


def extract_attachments(message: dict) -> list[dict]:
    """Walk the MIME tree and return downloadable parts with a filename."""
    found: list[dict] = []

    def walk(part: dict) -> None:
        filename = (part.get("filename") or "").strip()
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        if filename and attachment_id:
            found.append(
                {
                    "attachment_id": attachment_id,
                    "filename": filename,
                    "size_bytes": body.get("size"),
                }
            )
        for child in part.get("parts", []) or []:
            walk(child)

    walk(message.get("payload", {}) or {})
    return found


# --------------------------------------------------------------------------
# OAuth token exchange / refresh
# --------------------------------------------------------------------------


def exchange_code(ctx, *, code: str, verifier: str, redirect_uri: str, http: httpx.Client | None = None) -> dict:
    config = get_client_config(ctx)
    if not config["client_id"] or not config["client_secret"]:
        raise SourceNotConfiguredError("Gmail OAuth client credentials are not configured.")
    client = http or httpx.Client(timeout=30)
    response = client.post(
        TOKEN_ENDPOINT,
        data={
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
    )
    if response.status_code >= 400:
        # never surface raw provider payloads (they can echo request parameters)
        raise SourceError("Gmail connection failed. No resumes were imported.")
    return _token_payload(response.json(), previous=None)


def refresh_tokens(ctx, tokens: dict, *, http: httpx.Client | None = None) -> dict:
    config = get_client_config(ctx)
    client = http or httpx.Client(timeout=30)
    response = client.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "refresh_token": tokens.get("refresh_token", ""),
            "grant_type": "refresh_token",
        },
    )
    if response.status_code >= 400:
        raise SourceNotConfiguredError(GMAIL_MESSAGES[0])
    return _token_payload(response.json(), previous=tokens)


def _token_payload(payload: dict, *, previous: dict | None) -> dict:
    expires_in = int(payload.get("expires_in") or 3600)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))
    refresh_token = payload.get("refresh_token") or (previous or {}).get("refresh_token")
    return {
        "access_token": payload.get("access_token", ""),
        "refresh_token": refresh_token or "",
        "expiry": expiry.isoformat(),
        "account": payload.get("email") or (previous or {}).get("account"),
    }


def _token_is_fresh(tokens: dict) -> bool:
    expiry = tokens.get("expiry")
    if not expiry:
        return False
    try:
        return datetime.fromisoformat(expiry) > datetime.now(timezone.utc)
    except ValueError:
        return False


def access_token_for(ctx, *, http: httpx.Client | None = None) -> str:
    tokens = get_tokens(ctx)
    if not tokens:
        raise SourceNotConfiguredError("Gmail is not connected. Connect the account first.")
    if not _token_is_fresh(tokens):
        tokens = refresh_tokens(ctx, tokens, http=http)
        save_tokens(ctx, tokens)
    return tokens["access_token"]


# --------------------------------------------------------------------------
# the source
# --------------------------------------------------------------------------


class GmailSource(ResumeSource):
    kind = "gmail"
    display_name = "Gmail"
    connectable = True

    def __init__(self, client_factory=None, http: httpx.Client | None = None):
        """client_factory builds an httpx.Client for API calls (tests inject a mock transport)."""
        self._client_factory = client_factory
        self._http = http

    def _api(self, ctx) -> GmailApi:
        token = access_token_for(ctx, http=self._http)
        if self._client_factory:
            return GmailApi(token, client=self._client_factory())
        return GmailApi(token)

    def status(self, ctx) -> SourceStatus:
        config = get_client_config(ctx)
        tokens = get_tokens(ctx)
        if not config["client_id"]:
            return SourceStatus(
                state="NOT_CONNECTED",
                message="Add your Google Cloud OAuth client (client ID and secret) to connect Gmail.",
                detail=(
                    "Uses the official Gmail API with OAuth 2.0. Intake reads with read-only access; "
                    "sending is only used for candidate emails you explicitly approve and confirm. "
                    "No Google password is ever requested or stored."
                ),
            )
        if not tokens:
            return SourceStatus(
                state="NOT_CONNECTED",
                message="Gmail OAuth client is configured. Connect the account to start fetching resumes.",
            )
        account = mask_email(tokens.get("account"))
        if not _token_is_fresh(tokens):
            try:
                tokens = refresh_tokens(ctx, tokens, http=self._http)
                save_tokens(ctx, tokens)
            except SourceError as exc:
                return SourceStatus(state="ERROR", account=account, message=exc.reason)
        return SourceStatus(state="CONNECTED", account=account)

    def connect(self, ctx, payload: dict) -> dict:
        redirect_uri = get_client_config(ctx)["redirect_uri"]
        pending = start_oauth_state(ctx, redirect_uri=redirect_uri)
        url = authorization_url(
            ctx, state=pending["state"], challenge=pending["challenge"], redirect_uri=redirect_uri
        )
        return {"auth_url": url, "redirect_uri": redirect_uri}

    def disconnect(self, ctx) -> None:
        clear_tokens(ctx)

    def search(self, ctx, criteria: SearchCriteria) -> ScanResult:
        api = self._api(ctx)
        query = build_gmail_query(criteria)
        message_ids = api.list_message_ids(query)
        attachments: list[AttachmentCandidate] = []
        matched = 0
        for message_id in message_ids:
            message = api.get_message(message_id)
            sender, subject, timestamp = extract_headers(message)
            parts = extract_attachments(message)
            if not parts:
                continue
            matched += 1
            for part in parts:
                attachments.append(
                    AttachmentCandidate(
                        external_id=message_id,
                        attachment_id=part["attachment_id"],
                        attachment_name=part["filename"],
                        sender=sender,
                        subject=subject,
                        timestamp=timestamp,
                        size_bytes=part.get("size_bytes"),
                        handle={"message_id": message_id, "attachment_id": part["attachment_id"]},
                    )
                )
        return ScanResult(
            messages_scanned=len(message_ids),
            messages_matched=matched,
            attachments=attachments,
        )

    def fetch_attachment(self, ctx, attachment: AttachmentCandidate) -> bytes:
        api = self._api(ctx)
        handle = attachment.handle or {}
        return api.get_attachment(handle["message_id"], handle["attachment_id"])

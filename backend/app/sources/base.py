"""Source connector abstraction.

Every way a resume can enter the platform — manual upload, Gmail, a local
test source, a future job board — implements the same small contract. The
connector only *finds and downloads* candidate files; everything after that
goes through the one canonical ingestion path (services.pipeline.handle_upload).

Connectors must never fabricate results: a source that is not configured,
not reachable or not officially available reports that state explicitly.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..parsing import ALLOWED_EXTENSIONS

# Attachment types accepted from any source; everything else is ignored.
SUPPORTED_EXTENSIONS = set(ALLOWED_EXTENSIONS)

# Attachment types that are explicitly recognised as unsafe to touch at all.
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".vbs", ".js", ".jar",
    ".py", ".sh", ".scr", ".zip", ".rar", ".7z", ".tar", ".gz", ".iso",
}


class SourceError(Exception):
    """User-facing connector failure (message is safe to display)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SourceUnavailableError(SourceError):
    """The source exists but cannot be used in this installation."""


class SourceNotConfiguredError(SourceError):
    """The source needs credentials or a connection the user has not provided."""


@dataclass
class SearchCriteria:
    """User-supplied fetch filters. All optional; validated before use."""

    date_from: str | None = None  # YYYY-MM-DD, inclusive
    date_to: str | None = None    # YYYY-MM-DD, inclusive
    sender: str = ""
    keywords: list[str] = field(default_factory=list)

    def validate(self) -> None:
        start = _parse_date(self.date_from, "Start date")
        end = _parse_date(self.date_to, "End date")
        if start and end and end < start:
            raise SourceError("End date must be on or after start date.")
        if self.date_from and not start:
            raise SourceError("Start date must be a valid date (YYYY-MM-DD).")
        if self.date_to and not end:
            raise SourceError("End date must be a valid date (YYYY-MM-DD).")
        if len(self.sender) > 120:
            raise SourceError("Sender filter is too long (120 characters max).")
        if len(self.keywords) > 8:
            raise SourceError("At most 8 keywords are supported.")
        for keyword in self.keywords:
            if len(keyword) > 60:
                raise SourceError("A keyword is too long (60 characters max).")

    def to_dict(self) -> dict:
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sender": self.sender,
            "keywords": list(self.keywords),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "SearchCriteria":
        raw_keywords = payload.get("keywords") or []
        if isinstance(raw_keywords, str):
            raw_keywords = [part.strip() for part in raw_keywords.split(",")]
        keywords = [str(item).strip() for item in raw_keywords if str(item).strip()]
        return cls(
            date_from=(str(payload.get("date_from")).strip() or None) if payload.get("date_from") else None,
            date_to=(str(payload.get("date_to")).strip() or None) if payload.get("date_to") else None,
            sender=str(payload.get("sender") or "").strip(),
            keywords=keywords,
        )


def _parse_date(value: str | None, label: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class AttachmentCandidate:
    """One downloadable attachment found by a source search.

    ``handle`` is opaque and only meaningful to the source that produced it.
    """

    external_id: str
    attachment_id: str
    attachment_name: str
    sender: str
    subject: str
    timestamp: str
    size_bytes: int | None
    handle: object = None


@dataclass
class ScanResult:
    messages_scanned: int
    messages_matched: int
    attachments: list[AttachmentCandidate]


@dataclass
class SourceStatus:
    state: str  # CONNECTED | NOT_CONNECTED | ERROR | AVAILABLE | UNAVAILABLE
    account: str | None = None
    message: str | None = None
    detail: str | None = None


class SourceUpload:
    """Adapts validated source bytes to the interface handle_upload expects."""

    def __init__(self, filename: str, raw: bytes):
        self.filename = filename
        self.file = io.BytesIO(raw)


class ResumeSource(ABC):
    """Contract every resume source implements."""

    kind: str = ""
    display_name: str = ""
    connectable: bool = True

    @abstractmethod
    def status(self, ctx) -> SourceStatus:
        """Current connection state, never a fabricated one."""

    def connect(self, ctx, payload: dict) -> dict:
        raise SourceUnavailableError(f"{self.display_name} cannot be connected in this installation.")

    def disconnect(self, ctx) -> None:
        pass

    @abstractmethod
    def search(self, ctx, criteria: SearchCriteria) -> ScanResult:
        """Find candidate attachments matching the criteria."""

    @abstractmethod
    def fetch_attachment(self, ctx, attachment: AttachmentCandidate) -> bytes:
        """Download one attachment's bytes. Must not execute or interpret it."""


def attachment_extension(name: str) -> str:
    lowered = (name or "").strip().lower()
    dot = lowered.rfind(".")
    return lowered[dot:] if dot >= 0 else ""


def classify_attachment(name: str) -> str:
    """Return 'supported', 'unsupported' or 'dangerous' for an attachment name."""
    extension = attachment_extension(name)
    if extension in SUPPORTED_EXTENSIONS:
        return "supported"
    if extension in DANGEROUS_EXTENSIONS:
        return "dangerous"
    return "unsupported"


def within_range(timestamp: str, criteria: SearchCriteria) -> bool:
    """True when an ISO timestamp falls inside the criteria date range."""
    if not timestamp:
        return True
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if criteria.date_from:
        start = datetime.strptime(criteria.date_from, "%Y-%m-%d").date()
        if moment.date() < start:
            return False
    if criteria.date_to:
        end = datetime.strptime(criteria.date_to, "%Y-%m-%d").date()
        if moment.date() > end:
            return False
    return True


def matches_filters(sender: str, subject: str, criteria: SearchCriteria) -> bool:
    sender_l = (sender or "").lower()
    subject_l = (subject or "").lower()
    if criteria.sender:
        needle = criteria.sender.lower().strip()
        if needle and needle not in sender_l:
            return False
    if criteria.keywords:
        if not any(keyword.lower() in subject_l for keyword in criteria.keywords):
            return False
    return True


def ranged_dates(criteria: SearchCriteria) -> tuple[date | None, date | None]:
    return _parse_date(criteria.date_from, "Start date"), _parse_date(criteria.date_to, "End date")


def day_after(value: date) -> date:
    return value + timedelta(days=1)

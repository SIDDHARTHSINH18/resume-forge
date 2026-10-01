"""Local test source (MOCK SOURCE) — deterministic, clearly labelled.

This connector behaves exactly like a real intake source (search with real
date/sender/keyword filtering, downloadable attachments, unsupported files,
duplicates) but the "inbox" is a fixed local fixture set built from the demo
data files. It exists so the full fetch → preview → import flow can be
exercised end to end without any external account.

It is always presented as "Mock source (testing only)" — it is never
presented as Gmail.
"""

from __future__ import annotations

from pathlib import Path

from ..services.demo_data import generate_demo_resumes
from .base import (
    AttachmentCandidate,
    ResumeSource,
    SearchCriteria,
    ScanResult,
    SourceStatus,
    SourceError,
    matches_filters,
    within_range,
)

MOCK_DISPLAY_NAME = "Mock source (testing only)"

# Deterministic fixture inbox. Attachments reference generated demo files by
# name; "inline_bytes" attachments carry synthetic payloads (e.g. an unsafe
# archive the pipeline must ignore).
FIXTURE_MESSAGES: list[dict] = [
    {
        "id": "mock-msg-0001",
        "sender": "jobs@company-demo.com",
        "subject": "Application — Aarav Patel — Resume attached",
        "timestamp": "2026-09-03T09:15:00",
        "attachments": [{"id": "a1", "name": "aarav_patel_resume.txt", "file": "demo_01_aarav_patel.txt"}],
    },
    {
        "id": "mock-msg-0002",
        "sender": "careers@company-demo.com",
        "subject": "CV — Riya Shah for the Software Engineer role",
        "timestamp": "2026-09-07T14:02:00",
        "attachments": [{"id": "a1", "name": "riya_shah_cv.txt", "file": "demo_02_riya_shah.txt"}],
    },
    {
        "id": "mock-msg-0003",
        "sender": "careers@company-demo.com",
        "subject": "Resume — Priya Menon (Word format)",
        "timestamp": "2026-09-12T11:40:00",
        "attachments": [{"id": "a1", "name": "priya_menon_resume.docx", "file": "demo_12_priya_menon.docx"}],
    },
    {
        "id": "mock-msg-0004",
        "sender": "jobs@company-demo.com",
        "subject": "Application — Nikhil Reddy — Resume",
        "timestamp": "2026-09-18T16:25:00",
        "attachments": [{"id": "a1", "name": "nikhil_reddy_resume.pdf", "file": "demo_13_nikhil_reddy.pdf"}],
    },
    {
        "id": "mock-msg-0005",
        "sender": "jobs@company-demo.com",
        "subject": "Application — Aarav Patel — Resume (resend)",
        "timestamp": "2026-09-21T10:05:00",
        "attachments": [{"id": "a1", "name": "aarav_patel_resume_copy.txt", "file": "demo_01_aarav_patel.txt"}],
    },
    {
        "id": "mock-msg-0006",
        "sender": "careers@company-demo.com",
        "subject": "Application — Kabir Mehta — resume and portfolio",
        "timestamp": "2026-09-24T08:50:00",
        "attachments": [
            {"id": "a1", "name": "kabir_mehta_resume.txt", "file": "demo_03_kabir_mehta.txt"},
            {"id": "a2", "name": "kabir_portfolio.zip", "inline_bytes": b"PK\x03\x04mock-archive-not-a-resume"},
        ],
    },
    {
        "id": "mock-msg-0007",
        "sender": "careers@company-demo.com",
        "subject": "Resume — broken scan test",
        "timestamp": "2026-09-26T13:30:00",
        "attachments": [{"id": "a1", "name": "scanned_resume.pdf", "file": "demo_99_broken_resume.pdf"}],
    },
    {
        "id": "mock-msg-0008",
        "sender": "newsletter@example-demo.com",
        "subject": "Weekly industry newsletter",
        "timestamp": "2026-09-28T07:00:00",
        "attachments": [],
    },
    {
        "id": "mock-msg-0009",
        "sender": "jobs@company-demo.com",
        "subject": "Application — Devansh Joshi — CV",
        "timestamp": "2026-08-20T12:00:00",
        "attachments": [{"id": "a1", "name": "devansh_joshi_cv.txt", "file": "demo_05_devansh_joshi.txt"}],
    },
]


class MockSource(ResumeSource):
    kind = "mock"
    display_name = MOCK_DISPLAY_NAME
    connectable = False  # always available; nothing to connect

    def status(self, ctx) -> SourceStatus:
        return SourceStatus(
            state="AVAILABLE",
            message=(
                "Local test inbox with %d fixture messages. Clearly labelled MOCK SOURCE — "
                "not a real mailbox and never presented as Gmail." % len(FIXTURE_MESSAGES)
            ),
        )

    # -- fixture plumbing ---------------------------------------------------

    def _ensure_files(self, ctx) -> Path:
        directory = Path(ctx.demo_dir)
        expected = {entry["file"] for message in FIXTURE_MESSAGES for entry in message["attachments"] if entry.get("file")}
        missing = [name for name in expected if not (directory / name).exists()]
        if missing:
            generate_demo_resumes(directory)
        return directory

    # -- ResumeSource -------------------------------------------------------

    def search(self, ctx, criteria: SearchCriteria) -> ScanResult:
        self._ensure_files(ctx)
        matched: list[dict] = []
        for message in FIXTURE_MESSAGES:
            if not within_range(message["timestamp"], criteria):
                continue
            if not matches_filters(message["sender"], message["subject"], criteria):
                continue
            matched.append(message)

        attachments: list[AttachmentCandidate] = []
        for message in matched:
            for entry in message["attachments"]:
                attachments.append(
                    AttachmentCandidate(
                        external_id=message["id"],
                        attachment_id=entry["id"],
                        attachment_name=entry["name"],
                        sender=message["sender"],
                        subject=message["subject"],
                        timestamp=message["timestamp"],
                        size_bytes=len(entry.get("inline_bytes") or b"") or None,
                    )
                )
        return ScanResult(
            messages_scanned=len(FIXTURE_MESSAGES),
            messages_matched=len(matched),
            attachments=attachments,
        )

    def fetch_attachment(self, ctx, attachment: AttachmentCandidate) -> bytes:
        """Resolve the fixture by ids, like a real connector resolves remote state.

        Import re-fetches from the source using the ids persisted at scan time,
        so a stale in-memory handle is never relied upon.
        """
        entry = None
        for message in FIXTURE_MESSAGES:
            if message["id"] != attachment.external_id:
                continue
            entry = next(
                (item for item in message["attachments"] if item["id"] == attachment.attachment_id),
                None,
            )
            break
        if entry is None:
            handle = attachment.handle or {}
            entry = handle.get("entry")
        if entry is None:
            raise SourceError(
                f"Mock fixture message '{attachment.external_id}' has no attachment "
                f"'{attachment.attachment_id}'."
            )
        if "inline_bytes" in entry:
            return entry["inline_bytes"]
        filename = entry.get("file")
        if not filename:
            raise SourceError("Mock attachment has no file reference.")
        path = Path(ctx.demo_dir) / filename
        if not path.exists():
            self._ensure_files(ctx)
        if not path.exists():
            raise SourceError(f"Mock fixture file '{filename}' is missing.")
        return path.read_bytes()

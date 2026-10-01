"""Manual upload as a ResumeSource.

The original workflow (upload files straight to a screening profile) remains
fully functional and is presented as one of the sources. There is no fetch
step: files are handed to the profile directly on the profile page, which
feeds the same canonical ingestion pipeline.
"""

from __future__ import annotations

from .base import AttachmentCandidate, ResumeSource, SearchCriteria, ScanResult, SourceStatus, SourceUnavailableError

MANUAL_MESSAGE = (
    "Upload PDF, DOCX or TXT files directly to a screening profile. "
    "This is the original intake flow and stays fully functional."
)


class ManualUploadSource(ResumeSource):
    kind = "manual"
    display_name = "Manual upload"
    connectable = False

    def status(self, ctx) -> SourceStatus:
        return SourceStatus(state="AVAILABLE", message=MANUAL_MESSAGE)

    def search(self, ctx, criteria: SearchCriteria) -> ScanResult:
        raise SourceUnavailableError("Manual upload has no fetch step — files are uploaded on a screening profile.")

    def fetch_attachment(self, ctx, attachment: AttachmentCandidate) -> bytes:
        raise SourceUnavailableError("Manual upload has no fetch step — files are uploaded on a screening profile.")

"""LinkedIn connector placeholder — architecture only, no scraping.

LinkedIn is implemented behind the same ResumeSource interface so it can be
completed later against the *official* LinkedIn API. This build deliberately
does not automate LinkedIn's website, does not ask for LinkedIn credentials
and does not pretend the integration is functional.
"""

from __future__ import annotations

from .base import AttachmentCandidate, ResumeSource, SearchCriteria, ScanResult, SourceStatus, SourceUnavailableError

LINKEDIN_MESSAGE = (
    "LinkedIn integration requires an approved official API connection. No browser scraping is used."
)


class LinkedInSource(ResumeSource):
    kind = "linkedin"
    display_name = "LinkedIn"
    connectable = False

    def status(self, ctx) -> SourceStatus:
        return SourceStatus(
            state="UNAVAILABLE",
            message=LINKEDIN_MESSAGE,
            detail=(
                "Supply approved official API access (partner programme) to enable this connector. "
                "Meanwhile, profile URLs can be stored manually in the intake ledger on the Resume Sources page."
            ),
        )

    def connect(self, ctx, payload: dict) -> dict:
        raise SourceUnavailableError(LINKEDIN_MESSAGE)

    def search(self, ctx, criteria: SearchCriteria) -> ScanResult:
        raise SourceUnavailableError(LINKEDIN_MESSAGE)

    def fetch_attachment(self, ctx, attachment: AttachmentCandidate) -> bytes:
        raise SourceUnavailableError(LINKEDIN_MESSAGE)

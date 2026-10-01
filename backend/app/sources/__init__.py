"""Resume source connectors (Phase 1 of Resume Intake V2)."""

from .base import (
    SUPPORTED_EXTENSIONS,
    AttachmentCandidate,
    ResumeSource,
    SearchCriteria,
    ScanResult,
    SourceError,
    SourceNotConfiguredError,
    SourceStatus,
    SourceUnavailableError,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "AttachmentCandidate",
    "ResumeSource",
    "SearchCriteria",
    "ScanResult",
    "SourceError",
    "SourceNotConfiguredError",
    "SourceStatus",
    "SourceUnavailableError",
]

"""Resume file parsing: PDF / DOCX / TXT to plain text.

Untrusted input is only ever read with libraries, never executed. Failures
raise ResumeParseError with a short user-facing reason; detailed errors are
logged to the developer log.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..util import clean_text

logger = logging.getLogger("ailister.parsing")

MAX_TEXT_CHARS = 60_000
MIN_USEFUL_PDF_CHARS = 40

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class ResumeParseError(Exception):
    """User-facing parse failure (message is safe to display)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        logger.warning("pdf open failed for %s: %s", path.name, exc)
        raise ResumeParseError("PDF file is corrupted or unreadable.") from exc
    except Exception as exc:  # noqa: BLE001 - defensive: any parser crash is a parse failure
        logger.exception("unexpected pdf open error for %s", path.name)
        raise ResumeParseError("PDF could not be opened.") from exc

    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise ResumeParseError("PDF is password-protected.")
        except ResumeParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf decrypt failed for %s: %s", path.name, exc)
            raise ResumeParseError("PDF is password-protected.") from exc

    chunks: list[str] = []
    try:
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf text extraction failed for %s: %s", path.name, exc)
        raise ResumeParseError("PDF text extraction failed.") from exc

    text = "\n".join(chunks)
    if len(text.strip()) < MIN_USEFUL_PDF_CHARS:
        raise ResumeParseError(
            "No extractable text found — the PDF may be a scanned image without a text layer."
        )
    return text


def _read_docx(path: Path) -> str:
    import docx

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("docx open failed for %s: %s", path.name, exc)
        raise ResumeParseError("DOCX file is corrupted or not a valid Word document.") from exc

    parts: list[str] = []
    try:
        for paragraph in document.paragraphs:
            if paragraph.text:
                parts.append(paragraph.text)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
    except Exception as exc:  # noqa: BLE001
        logger.warning("docx extraction failed for %s: %s", path.name, exc)
        raise ResumeParseError("DOCX text extraction failed.") from exc

    text = "\n".join(parts)
    if len(text.strip()) < 20:
        raise ResumeParseError("The DOCX file contains no readable text.")
    return text


def _read_txt(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw[:4096] and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise ResumeParseError("File does not look like a plain text document.")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 never fails, kept for safety
        raise ResumeParseError("Unable to read text encoding.")
    if len(text.strip()) < 20:
        raise ResumeParseError("The text file is empty or too short.")
    return text


def detect_format(path: Path) -> str:
    """Return 'pdf' | 'docx' | 'txt' from magic bytes, falling back to extension."""
    head = path.open("rb").read(8)
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"
    return "txt"


def extract_text(path: Path) -> str:
    """Extract plain text from a resume file. Raises ResumeParseError."""
    if not path.exists():
        raise ResumeParseError("Uploaded file is missing on disk.")
    fmt = detect_format(path)
    if fmt == "pdf":
        text = _read_pdf(path)
    elif fmt == "docx":
        text = _read_docx(path)
    else:
        text = _read_txt(path)
    cleaned = clean_text(text)
    if not cleaned:
        raise ResumeParseError("No readable text could be extracted from this file.")
    return cleaned[:MAX_TEXT_CHARS]

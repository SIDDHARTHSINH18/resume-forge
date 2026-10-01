"""Small shared helpers (time, JSON, text sanitation)."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp, ISO-8601, second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def jloads(raw, default):
    """Tolerant JSON load for values coming from the database."""
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value if value is not None else default


def jdumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"[ \t\u00a0]+")


def clean_text(text: str) -> str:
    """Normalize whitespace/control chars from untrusted extracted text.

    Keeps meaning; removes control characters that could confuse log/UI output.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub(" ", text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            out.append(line)
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


def normalize_skill(skill: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]+", "", skill.strip().lower()).strip()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def sanitize_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe base name (no paths, no surprises)."""
    name = (name or "resume").replace("\\", "/").split("/")[-1]
    name = _CONTROL_RE.sub("", name)
    name = re.sub(r"[^A-Za-z0-9._ ()\-]+", "_", name).strip(" .")
    if not name:
        name = "resume"
    return name[:120]


def safe_join_under(root, candidate_path: str):
    """Return resolved path if it stays under root, else raise ValueError."""
    from pathlib import Path

    root = Path(root).resolve()
    target = (root / candidate_path).resolve()
    if root not in target.parents and target != root:
        raise ValueError("path escapes storage root")
    return target

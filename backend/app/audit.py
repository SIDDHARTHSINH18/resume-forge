"""Audit log: important events are recorded, secrets never are."""

from __future__ import annotations

from .util import jdumps, now_iso

SECRET_KEY_HINTS = ("key", "secret", "token", "password", "authorization")


def _strip_secrets(data: dict | None) -> dict:
    if not data:
        return {}
    out = {}
    for key, value in data.items():
        if any(hint in key.lower() for hint in SECRET_KEY_HINTS):
            out[key] = "[redacted]"
        else:
            out[key] = value
    return out


def record(
    conn,
    event_type: str,
    *,
    entity_type: str = "",
    entity_id: int | None = None,
    profile_id: int | None = None,
    candidate_id: int | None = None,
    message: str = "",
    data: dict | None = None,
) -> None:
    conn.execute(
        """INSERT INTO audit_events
           (event_type, entity_type, entity_id, profile_id, candidate_id, message, data, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_type,
            entity_type,
            entity_id,
            profile_id,
            candidate_id,
            message,
            jdumps(_strip_secrets(data)),
            now_iso(),
        ),
    )

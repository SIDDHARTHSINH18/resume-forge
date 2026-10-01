"""Persistence for resume sources, their syncs and scanned items."""

from __future__ import annotations

import sqlite3

from ..util import jdumps, jloads, now_iso

SYNC_STATUSES = ("PREVIEWED", "COMPLETED", "FAILED", "IMPORTING")

ITEM_STATUSES = (
    "NEW", "DUPLICATE", "ALREADY_IMPORTED", "UNSUPPORTED",
    "FAILED", "IMPORTED", "IMPORT_FAILED",
)


def ensure_source(conn: sqlite3.Connection, kind: str, display_name: str) -> sqlite3.Row:
    """Return the row for a source kind, creating it on first sight."""
    conn.execute(
        """INSERT INTO resume_sources (kind, display_name, status, created_at, updated_at)
           VALUES (?, ?, 'NOT_CONNECTED', ?, ?)
           ON CONFLICT(kind) DO NOTHING""",
        (kind, display_name, now_iso(), now_iso()),
    )
    return conn.execute("SELECT * FROM resume_sources WHERE kind = ?", (kind,)).fetchone()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM resume_sources ORDER BY id"))


def get_source(conn: sqlite3.Connection, source_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM resume_sources WHERE id = ?", (source_id,)).fetchone()


def update_source(conn: sqlite3.Connection, source_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(
        f"UPDATE resume_sources SET {columns}, updated_at = ? WHERE id = ?",
        (*fields.values(), now_iso(), source_id),
    )


def create_sync(
    conn: sqlite3.Connection, *, source_id: int, profile_id: int, criteria: dict
) -> int:
    cursor = conn.execute(
        """INSERT INTO source_syncs (source_id, profile_id, status, criteria, started_at)
           VALUES (?, ?, 'PREVIEWED', ?, ?)""",
        (source_id, profile_id, jdumps(criteria), now_iso()),
    )
    return int(cursor.lastrowid)


def update_sync(conn: sqlite3.Connection, sync_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE source_syncs SET {columns} WHERE id = ?", (*fields.values(), sync_id))


def get_sync(conn: sqlite3.Connection, sync_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_syncs WHERE id = ?", (sync_id,)).fetchone()


def list_syncs(conn: sqlite3.Connection, source_id: int, limit: int = 25) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM source_syncs WHERE source_id = ? ORDER BY id DESC LIMIT ?",
            (source_id, limit),
        )
    )


def upsert_item(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    sync_id: int,
    external_id: str,
    attachment_id: str,
    external_timestamp: str | None,
    sender: str,
    subject: str,
    attachment_name: str,
    size_bytes: int | None,
    content_hash: str | None,
    status: str,
    detail: str = "",
    matched_candidate: int | None = None,
) -> int:
    """Insert the scanned item, or refresh an existing (source, message, attachment) row."""
    conn.execute(
        """INSERT INTO source_items
           (source_id, sync_id, external_id, attachment_id, external_timestamp, sender, subject,
            attachment_name, size_bytes, content_hash, status, detail, matched_candidate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_id, external_id, attachment_id) DO UPDATE SET
             sync_id = excluded.sync_id,
             size_bytes = excluded.size_bytes,
             content_hash = excluded.content_hash,
             status = excluded.status,
             detail = excluded.detail,
             matched_candidate = excluded.matched_candidate""",
        (
            source_id, sync_id, external_id, attachment_id, external_timestamp, sender, subject,
            attachment_name, size_bytes, content_hash, status, detail, matched_candidate, now_iso(),
        ),
    )
    row = conn.execute(
        "SELECT id FROM source_items WHERE source_id = ? AND external_id = ? AND attachment_id = ?",
        (source_id, external_id, attachment_id),
    ).fetchone()
    return int(row["id"])


def get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_items WHERE id = ?", (item_id,)).fetchone()


def find_item(
    conn: sqlite3.Connection, source_id: int, external_id: str, attachment_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM source_items WHERE source_id = ? AND external_id = ? AND attachment_id = ?",
        (source_id, external_id, attachment_id),
    ).fetchone()


def list_items(conn: sqlite3.Connection, sync_id: int, limit: int = 500) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM source_items WHERE sync_id = ? ORDER BY id LIMIT ?",
            (sync_id, limit),
        )
    )


def update_item(conn: sqlite3.Connection, item_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE source_items SET {columns} WHERE id = ?", (*fields.values(), item_id))


# --------------------------------------------------------------------------
# serialization
# --------------------------------------------------------------------------


def sync_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    data = dict(row)
    data["criteria"] = jloads(data.get("criteria"), {})
    profile = conn.execute(
        "SELECT title FROM screening_profiles WHERE id = ?", (row["profile_id"],)
    ).fetchone()
    data["profile_title"] = profile["title"] if profile else None
    return data


def item_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    data = dict(row)
    name = None
    if data.get("matched_candidate"):
        candidate = conn.execute(
            "SELECT name FROM candidates WHERE id = ?", (data["matched_candidate"],)
        ).fetchone()
        name = candidate["name"] if candidate else None
    elif data.get("resume_id"):
        candidate = conn.execute(
            "SELECT id, name FROM candidates WHERE resume_id = ?", (data["resume_id"],)
        ).fetchone()
        if candidate:
            data["matched_candidate"] = candidate["id"]
            name = candidate["name"]
    data["candidate_name"] = name
    return data

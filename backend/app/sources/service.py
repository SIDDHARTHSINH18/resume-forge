"""Resume intake: everything a source fetch does before and around the
canonical ingestion pipeline.

Flow (Phase 5 of the milestone):
    source.search  → classify (unsupported / duplicate / already imported)
    → explicit user import → handle_upload (the ONE existing pipeline)
    → parsing, extraction, scoring, dedup, candidate creation, audit

Nothing here parses, scores or creates candidates by itself — it only
validates bytes, classifies them honestly and hands them over.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..audit import record
from ..extraction import extract_resume
from ..parsing import ResumeParseError, extract_text
from ..services.pipeline import UploadError, handle_upload
from ..util import now_iso, sanitize_filename
from . import store
from .base import (
    SourceError,
    SourceUpload,
    classify_attachment,
)
from .gmail import GmailSource
from .linkedin import LinkedInSource
from .manual import ManualUploadSource
from .mock import MockSource

# Every source kind the platform knows about. Manual and LinkedIn are
# stateless (no DB row); Gmail and the local test source persist state.
_INSTANCES = {
    "manual": ManualUploadSource(),
    "gmail": GmailSource(),
    "mock": MockSource(),
    "linkedin": LinkedInSource(),
}
DB_SOURCE_KINDS = ("gmail", "mock")


def instance_for(kind: str):
    instance = _INSTANCES.get(kind)
    if instance is None:
        raise SourceError(f"Unknown resume source '{kind}'.")
    return instance


# --------------------------------------------------------------------------
# source listing
# --------------------------------------------------------------------------


def source_cards(ctx) -> list[dict]:
    conn = ctx.connect()
    try:
        cards: list[dict] = []
        for kind, instance in _INSTANCES.items():
            row = store.ensure_source(conn, kind, instance.display_name) if kind in DB_SOURCE_KINDS else None
            status = instance.status(ctx)
            card = {
                "id": row["id"] if row else None,
                "kind": kind,
                "display_name": instance.display_name,
                "state": status.state,
                "account": status.account,
                "message": status.message,
                "detail": status.detail,
                "connectable": instance.connectable,
                "configured": _configured(ctx, kind),
                "last_successful_sync_at": row["last_successful_sync_at"] if row else None,
                "is_test_source": kind == "mock",
            }
            if row:
                card["sync_count"] = conn.execute(
                    "SELECT COUNT(*) AS n FROM source_syncs WHERE source_id = ? AND status = 'COMPLETED'",
                    (row["id"],),
                ).fetchone()["n"]
            else:
                card["sync_count"] = 0
            cards.append(card)
        return cards
    finally:
        conn.close()


def _configured(ctx, kind: str) -> bool:
    if kind == "gmail":
        from .gmail import get_client_config

        return bool(get_client_config(ctx)["client_id"])
    return kind == "mock"


def source_row_or_error(ctx, source_id: int):
    conn = ctx.connect()
    try:
        row = store.get_source(conn, source_id)
    finally:
        conn.close()
    if row is None:
        raise SourceError("Resume source not found.")
    return row


# --------------------------------------------------------------------------
# preview (scan + classify) — persists the sync and its items
# --------------------------------------------------------------------------


def preview(ctx, source_row, profile: dict, criteria) -> dict:
    criteria.validate()
    source = instance_for(source_row["kind"])
    label = source.display_name

    conn = ctx.connect()
    try:
        sync_id = store.create_sync(
            conn, source_id=source_row["id"], profile_id=profile["id"], criteria=criteria.to_dict()
        )
        record(
            conn,
            "source_sync_started",
            entity_type="source_sync",
            entity_id=sync_id,
            profile_id=profile["id"],
            message=f"{label} scan started for profile '{profile['title']}'",
            data={"criteria": criteria.to_dict()},
        )
    finally:
        conn.close()

    try:
        scan = source.search(ctx, criteria)
    except SourceError as exc:
        _fail_sync(ctx, sync_id, source_row, exc.reason)
        raise

    counters = {
        "messages_scanned": scan.messages_scanned,
        "messages_matched": scan.messages_matched,
        "attachments_found": len(scan.attachments),
        "unsupported": 0,
        "duplicates": 0,
        "already_imported": 0,
        "new_resumes": 0,
        "failed": 0,
    }
    seen_hashes: dict[str, str] = {}
    tmp_dir = Path(ctx.data_dir) / "source_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    conn = ctx.connect()
    try:
        for attachment in scan.attachments:
            kind = classify_attachment(attachment.attachment_name)
            if kind != "supported":
                counters["unsupported"] += 1
                store.upsert_item(
                    conn,
                    source_id=source_row["id"],
                    sync_id=sync_id,
                    external_id=attachment.external_id,
                    attachment_id=attachment.attachment_id,
                    external_timestamp=attachment.timestamp,
                    sender=attachment.sender,
                    subject=attachment.subject,
                    attachment_name=attachment.attachment_name,
                    size_bytes=attachment.size_bytes,
                    content_hash=None,
                    status="UNSUPPORTED",
                    detail="IGNORED_UNSUPPORTED_TYPE — only PDF, DOCX and TXT files enter the resume pipeline.",
                )
                continue

            try:
                raw = source.fetch_attachment(ctx, attachment)
            except SourceError as exc:
                counters["failed"] += 1
                store.upsert_item(
                    conn,
                    source_id=source_row["id"],
                    sync_id=sync_id,
                    external_id=attachment.external_id,
                    attachment_id=attachment.attachment_id,
                    external_timestamp=attachment.timestamp,
                    sender=attachment.sender,
                    subject=attachment.subject,
                    attachment_name=attachment.attachment_name,
                    size_bytes=attachment.size_bytes,
                    content_hash=None,
                    status="FAILED",
                    detail=f"Download failed: {exc.reason}",
                )
                continue

            digest = hashlib.sha256(raw).hexdigest()
            size = len(raw)

            previous = store.find_item(
                conn, source_row["id"], attachment.external_id, attachment.attachment_id
            )
            # ALREADY_IMPORTED must stay in this tuple: the upsert overwrites the
            # stored status on every scan, so without it a re-scan would degrade to
            # content checks and could re-offer a failed-parse file as "new".
            if previous is not None and previous["status"] in ("IMPORTED", "IMPORT_FAILED", "ALREADY_IMPORTED"):
                counters["already_imported"] += 1
                store.upsert_item(
                    conn,
                    source_id=source_row["id"],
                    sync_id=sync_id,
                    external_id=attachment.external_id,
                    attachment_id=attachment.attachment_id,
                    external_timestamp=attachment.timestamp,
                    sender=attachment.sender,
                    subject=attachment.subject,
                    attachment_name=attachment.attachment_name,
                    size_bytes=size,
                    content_hash=digest,
                    status="ALREADY_IMPORTED",
                    detail=_already_imported_detail(conn, previous),
                    matched_candidate=previous["matched_candidate"],
                )
                continue

            duplicate = _classify_duplicate(conn, profile["id"], digest, raw, attachment, seen_hashes)
            if duplicate:
                counters["duplicates"] += 1
                store.upsert_item(
                    conn,
                    source_id=source_row["id"],
                    sync_id=sync_id,
                    external_id=attachment.external_id,
                    attachment_id=attachment.attachment_id,
                    external_timestamp=attachment.timestamp,
                    sender=attachment.sender,
                    subject=attachment.subject,
                    attachment_name=attachment.attachment_name,
                    size_bytes=size,
                    content_hash=digest,
                    status="DUPLICATE",
                    detail=duplicate["detail"],
                    matched_candidate=duplicate["candidate_id"],
                )
                continue

            seen_hashes[digest] = attachment.external_id
            counters["new_resumes"] += 1
            store.upsert_item(
                conn,
                source_id=source_row["id"],
                sync_id=sync_id,
                external_id=attachment.external_id,
                attachment_id=attachment.attachment_id,
                external_timestamp=attachment.timestamp,
                sender=attachment.sender,
                subject=attachment.subject,
                attachment_name=attachment.attachment_name,
                size_bytes=size,
                content_hash=digest,
                status="NEW",
                detail="",
            )

        # source_syncs stores a subset of the counters; "new_resumes" stays payload-only.
        # Duplicates and already-imported files are stored as separate, exact counts.
        store.update_sync(
            conn,
            sync_id,
            messages_scanned=counters["messages_scanned"],
            messages_matched=counters["messages_matched"],
            attachments_found=counters["attachments_found"],
            duplicates_found=counters["duplicates"],
            already_imported=counters["already_imported"],
            unsupported=counters["unsupported"],
            failures=counters["failed"],
        )
        record(
            conn,
            "source_message_matched",
            entity_type="source_sync",
            entity_id=sync_id,
            profile_id=profile["id"],
            message=f"{label}: {scan.messages_matched} of {scan.messages_scanned} messages matched the filters",
            data={"matched": scan.messages_matched, "scanned": scan.messages_scanned},
        )
        record(
            conn,
            "resume_attachment_found",
            entity_type="source_sync",
            entity_id=sync_id,
            profile_id=profile["id"],
            message=(
                f"{label}: {counters['attachments_found']} attachments found — "
                f"{counters['new_resumes']} new, {counters['duplicates']} duplicates, "
                f"{counters['unsupported']} unsupported, {counters['failed']} failed"
            ),
            data=dict(counters),
        )
        payload = _preview_payload(conn, ctx, sync_id, source_row, profile, criteria, counters)
    finally:
        conn.close()
    return payload


def _already_imported_detail(conn, previous) -> str:
    """Honest reason for skipping an attachment this source already ingested."""
    stored_date = previous["created_at"][:10]
    if previous["resume_id"] is not None:
        resume = conn.execute(
            "SELECT status, error_reason, uploaded_at FROM resumes WHERE id = ?",
            (previous["resume_id"],),
        ).fetchone()
        if resume is not None:
            imported_on = str(resume["uploaded_at"] or previous["created_at"])[:10]
            if resume["status"] == "FAILED":
                reason = resume["error_reason"] or "no reason recorded"
                return (
                    f"Already ingested from this source on {imported_on} — parsing failed: {reason}"
                    " Not re-imported; retry it from the Processing page."
                )
            return f"Already imported from this source on {imported_on}."
    if previous["status"] == "IMPORT_FAILED":
        return (
            f"Already attempted from this source on {stored_date} — "
            f"{previous['detail'] or 'the import did not complete'}. Not re-imported."
        )
    return f"Already imported from this source on {stored_date}."


def _classify_duplicate(conn, profile_id: int, digest: str, raw: bytes, attachment, seen: dict) -> dict | None:
    """Real duplicate checks: same-scan file hash, stored file hash, email, phone."""
    if digest in seen:
        return {
            "candidate_id": None,
            "detail": f"Identical file content already appeared in this scan (message {seen[digest]}).",
        }

    row = conn.execute(
        """SELECT r.id AS resume_id, c.id AS candidate_id, c.name
           FROM resumes r LEFT JOIN candidates c ON c.resume_id = r.id
           WHERE r.profile_id = ? AND r.file_hash = ? AND r.status != 'FAILED'
           ORDER BY r.id LIMIT 1""",
        (profile_id, digest),
    ).fetchone()
    if row:
        name = row["name"] or "an existing candidate"
        return {
            "candidate_id": row["candidate_id"],
            "detail": f"Identical file already in this profile — matched existing candidate: {name} (resume #{row['resume_id']}).",
        }

    text = _parse_probe(raw, attachment)
    if text is None:
        return None
    facts = extract_resume(text)
    if facts.email:
        match = conn.execute(
            "SELECT id, name FROM candidates WHERE profile_id = ? AND LOWER(email) = LOWER(?) LIMIT 1",
            (profile_id, facts.email),
        ).fetchone()
        if match:
            return {
                "candidate_id": match["id"],
                "detail": f"Same email address as existing candidate: {match['name']}.",
            }
    if facts.phone:
        match = conn.execute(
            "SELECT id, name FROM candidates WHERE profile_id = ? AND phone = ? LIMIT 1",
            (profile_id, facts.phone),
        ).fetchone()
        if match:
            return {
                "candidate_id": match["id"],
                "detail": f"Same phone number as existing candidate: {match['name']}.",
            }
    return None


def _parse_probe(raw: bytes, attachment) -> str | None:
    """Parse an attachment for contact-detail dedup; returns None when unreadable."""
    import tempfile

    name = attachment.attachment_name or ""
    dot = name.rfind(".")
    suffix = name[dot:].lower() if dot >= 0 else ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(raw)
            temp_path = Path(handle.name)
    except OSError:
        return None
    try:
        return extract_text(temp_path)
    except ResumeParseError:
        return None
    finally:
        temp_path.unlink(missing_ok=True)


def _preview_payload(conn, ctx, sync_id: int, source_row, profile: dict, criteria, counters: dict) -> dict:
    items = [store.item_to_dict(conn, row) for row in store.list_items(conn, sync_id)]
    sync = store.get_sync(conn, sync_id)
    return {
        "sync_id": sync_id,
        "source": {"id": source_row["id"], "kind": source_row["kind"], "display_name": source_row["display_name"]},
        "profile": {"id": profile["id"], "title": profile["title"]},
        "criteria": criteria.to_dict(),
        "counts": {
            **counters,
            "duplicates_total": counters["duplicates"] + counters["already_imported"],
        },
        "messages": {
            "no_matches": counters["messages_matched"] == 0,
            "no_attachments": counters["messages_matched"] > 0 and counters["attachments_found"] == 0,
            "no_supported": counters["attachments_found"] > 0 and counters["new_resumes"] == 0
            and counters["duplicates"] == 0,
        },
        "status": sync["status"] if sync else "PREVIEWED",
        "items": items,
    }


def _fail_sync(ctx, sync_id: int, source_row, reason: str) -> None:
    conn = ctx.connect()
    try:
        store.update_sync(conn, sync_id, status="FAILED", error_message=reason, completed_at=now_iso())
        record(
            conn,
            "source_sync_failed",
            entity_type="source_sync",
            entity_id=sync_id,
            message=f"{source_row['display_name']} scan failed: {reason}",
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# import — explicit user action; hands bytes to the existing pipeline
# --------------------------------------------------------------------------


def import_sync(ctx, source_row, profile: dict, sync_id: int) -> dict:
    source = instance_for(source_row["kind"])
    conn = ctx.connect()
    try:
        sync = store.get_sync(conn, sync_id)
        if sync is None or sync["source_id"] != source_row["id"]:
            raise SourceError("Scan not found for this source.")
        if sync["status"] == "COMPLETED":
            # idempotent: a completed import is never re-executed
            summary = _import_payload(conn, sync_id, source_row, profile, already=True)
            return summary
        if sync["status"] != "PREVIEWED":
            raise SourceError("This scan is not ready to import. Run a new fetch first.")
        new_items = [row for row in store.list_items(conn, sync_id) if row["status"] == "NEW"]
        if not new_items:
            raise SourceError(
                "There are no new resumes in this scan to import. Duplicates and unsupported files are never re-imported."
            )
        store.update_sync(conn, sync_id, status="IMPORTING")
        record(
            conn,
            "resume_import_started",
            entity_type="source_sync",
            entity_id=sync_id,
            profile_id=profile["id"],
            message=f"{source.display_name}: importing {len(new_items)} resume(s) into profile '{profile['title']}'",
            data={"count": len(new_items)},
        )
    finally:
        conn.close()

    uploads: list[SourceUpload] = []
    item_ids: list[int] = []
    fetch_failures: list[tuple[int, str]] = []
    for item in new_items:
        try:
            attachment = _attachment_from_item(item)
            raw = source.fetch_attachment(ctx, attachment)
            uploads.append(SourceUpload(sanitize_filename(item["attachment_name"] or "resume"), raw))
            item_ids.append(int(item["id"]))
        except SourceError as exc:
            fetch_failures.append((int(item["id"]), exc.reason))

    result = {"job_id": None, "resumes": [], "failures": []}
    if uploads:
        try:
            result = handle_upload(
                ctx,
                profile,
                uploads,
                label=f"{source.display_name} import — {len(uploads)} file(s)",
            )
        except UploadError as exc:
            _mark_import_failed(ctx, sync_id, source_row, str(exc))
            raise

    mapping = _map_uploads(uploads, result)

    conn = ctx.connect()
    try:
        imported = 0
        failed = len(fetch_failures)
        for failure_id, reason in fetch_failures:
            store.update_item(
                conn, failure_id, status="IMPORT_FAILED", detail=f"Download failed: {reason}"
            )
            record(
                conn,
                "resume_import_failed",
                entity_type="source_item",
                entity_id=failure_id,
                profile_id=profile["id"],
                message=f"{source.display_name}: import failed — {reason}",
            )
        for index, item_id in enumerate(item_ids):
            outcome, value = mapping.get(index, ("IMPORT_FAILED", "Not queued."))
            row = store.get_item(conn, item_id)
            name = row["attachment_name"] if row else "attachment"
            if outcome == "IMPORTED":
                imported += 1
                store.update_item(conn, item_id, status="IMPORTED", resume_id=value, detail="")
                record(
                    conn,
                    "resume_imported",
                    entity_type="source_item",
                    entity_id=item_id,
                    profile_id=profile["id"],
                    message=f"{source.display_name}: '{name}' imported into profile '{profile['title']}'",
                    data={"resume_id": value},
                )
            else:
                failed += 1
                store.update_item(
                    conn, item_id, status="IMPORT_FAILED", detail=f"Rejected by the pipeline: {value}"
                )
                record(
                    conn,
                    "resume_import_failed",
                    entity_type="source_item",
                    entity_id=item_id,
                    profile_id=profile["id"],
                    message=f"{source.display_name}: '{name}' was rejected — {value}",
                )

        completed_at = now_iso()
        store.update_sync(
            conn,
            sync_id,
            status="COMPLETED",
            resumes_imported=imported,
            failures=failed,
            job_id=result.get("job_id"),
            completed_at=completed_at,
        )
        store.update_source(conn, source_row["id"], last_successful_sync_at=completed_at)
        record(
            conn,
            "source_sync_completed",
            entity_type="source_sync",
            entity_id=sync_id,
            profile_id=profile["id"],
            message=(
                f"{source.display_name} sync completed — {imported} imported, {failed} failed"
            ),
            data={"imported": imported, "failed": failed, "job_id": result.get("job_id")},
        )
        return _import_payload(conn, sync_id, source_row, profile, already=False)
    finally:
        conn.close()


def _attachment_from_item(item):
    from .base import AttachmentCandidate

    return AttachmentCandidate(
        external_id=item["external_id"],
        attachment_id=item["attachment_id"],
        attachment_name=item["attachment_name"],
        sender=item["sender"] or "",
        subject=item["subject"] or "",
        timestamp=item["external_timestamp"] or "",
        size_bytes=item["size_bytes"],
        handle={"message_id": item["external_id"], "attachment_id": item["attachment_id"]},
    )


def _map_uploads(uploads: list[SourceUpload], result: dict) -> dict[int, tuple[str, object]]:
    """Map upload order → pipeline outcome (handle_upload keeps input order)."""
    remaining = list(result.get("failures") or [])
    successes = iter(result.get("resumes") or [])
    mapping: dict[int, tuple[str, object]] = {}
    for index, upload in enumerate(uploads):
        rejected = next((item for item in remaining if item["filename"] == upload.filename), None)
        if rejected is not None:
            remaining.remove(rejected)
            mapping[index] = ("IMPORT_FAILED", rejected["reason"])
        else:
            resume = next(successes, None)
            mapping[index] = ("IMPORTED", resume["id"] if resume else None)
    return mapping


def _mark_import_failed(ctx, sync_id: int, source_row, reason: str) -> None:
    conn = ctx.connect()
    try:
        store.update_sync(conn, sync_id, status="FAILED", error_message=reason, completed_at=now_iso())
        record(
            conn,
            "source_sync_failed",
            entity_type="source_sync",
            entity_id=sync_id,
            message=f"{source_row['display_name']} import failed: {reason}",
        )
    finally:
        conn.close()


def _import_payload(conn, sync_id: int, source_row, profile: dict, *, already: bool) -> dict:
    sync = store.get_sync(conn, sync_id)
    counts = store.sync_to_dict(conn, sync)
    imported = counts["resumes_imported"]
    failed = counts["failures"]
    if already:
        message = f"Already imported on {sync['completed_at'][:19] if sync['completed_at'] else 'an earlier run'} — {imported} resume(s), {failed} failed."
    elif failed and imported:
        message = f"{imported} imported, {failed} failed."
    elif failed:
        message = f"0 imported, {failed} failed."
    else:
        message = f"{imported} imported."
    return {
        "sync_id": sync_id,
        "source": {"id": source_row["id"], "kind": source_row["kind"], "display_name": source_row["display_name"]},
        "profile": {"id": profile["id"], "title": profile["title"]},
        "job_id": sync["job_id"],
        "imported": imported,
        "failed": failed,
        "duplicates": counts["duplicates_found"],
        "unsupported": counts["unsupported"],
        "total_attachments": counts["attachments_found"],
        "already_imported": already,
        "message": message,
    }


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------


def sync_history(ctx, source_row, limit: int = 25) -> dict:
    conn = ctx.connect()
    try:
        syncs = [store.sync_to_dict(conn, row) for row in store.list_syncs(conn, source_row["id"], limit)]
        return {"source": {"id": source_row["id"], "kind": source_row["kind"], "display_name": source_row["display_name"]}, "items": syncs}
    finally:
        conn.close()


def sync_detail(ctx, source_row, sync_id: int) -> dict:
    conn = ctx.connect()
    try:
        sync = store.get_sync(conn, sync_id)
        if sync is None or sync["source_id"] != source_row["id"]:
            raise SourceError("Sync not found for this source.")
        payload = store.sync_to_dict(conn, sync)
        payload["items"] = [store.item_to_dict(conn, row) for row in store.list_items(conn, sync_id)]
        return payload
    finally:
        conn.close()

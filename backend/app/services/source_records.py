"""Manual intake records — the provenance ledger for non-fetched resumes.

Every resume that did not arrive through an automated connector, and every
lead that has not become a resume yet, gets one row in `source_records`:
referrals, LinkedIn / careers-page / job-board URLs, CSV rows and pasted
resume text. Nothing in this module fetches, crawls or scrapes anything — it
stores exactly what a human typed, imported or pasted, and says so.

Resume *text* (pasted directly or carried in a CSV row) always enters through
the one canonical ingestion path, services.pipeline.handle_upload. This module
only creates the ledger record that links back to the resume it produced.
"""

from __future__ import annotations

import csv
import io
import re

from ..audit import record as write_audit
from ..sources.base import SourceError, SourceUpload
from ..util import now_iso, normalize_email, sanitize_filename
from .pipeline import handle_upload

# Kinds a person can create directly from the UI. csv_import / pasted_text are
# written by the import flows below, not chosen by hand.
CREATABLE_KINDS = ("referral", "linkedin_profile", "company_page", "job_board")
SYSTEM_KINDS = ("csv_import", "pasted_text")
RECORD_KINDS = CREATABLE_KINDS + SYSTEM_KINDS

RECORD_KIND_INFO = [
    {
        "kind": "referral",
        "label": "Referral",
        "description": "A current employee recommended this person. The resume is added separately by upload.",
    },
    {
        "kind": "linkedin_profile",
        "label": "LinkedIn profile URL",
        "description": "Paste the profile URL yourself. MeritOS never scrapes LinkedIn; the URL is kept as a reference only.",
    },
    {
        "kind": "company_page",
        "label": "Company careers page",
        "description": "Application URL from your own careers page. Stored as a reference; nothing is fetched.",
    },
    {
        "kind": "job_board",
        "label": "Job board listing",
        "description": "Listing URL from a job board. Stored as a reference; automated import needs an official partner API.",
    },
]

# Honest availability of every intake method the platform knows about. The
# Resume Sources page renders this list verbatim instead of inventing labels.
#   AVAILABLE    — fully working in this build
#   MANUAL_ONLY  — works by recording a reference by hand; nothing is fetched
#   UNAVAILABLE  — needs an official API this build does not have
#   COMING_SOON  — planned, gated on an official integration
INTAKE_METHODS = [
    {
        "key": "manual_upload",
        "label": "Manual upload",
        "availability": "AVAILABLE",
        "note": "Upload PDF, DOCX or TXT files to a screening profile.",
    },
    {
        "key": "folder_upload",
        "label": "Batch folder upload",
        "availability": "AVAILABLE",
        "note": "Pick a folder on a screening profile — every resume file inside (including subfolders) is queued.",
    },
    {
        "key": "paste_text",
        "label": "Paste resume text",
        "availability": "AVAILABLE",
        "note": "Paste the text straight in; it enters the same parsing and scoring pipeline as a file.",
    },
    {
        "key": "csv_import",
        "label": "CSV import",
        "availability": "AVAILABLE",
        "note": "Import a CSV of candidate leads. Rows with resume text are queued through the pipeline; the rest become intake records.",
    },
    {
        "key": "referral",
        "label": "Referral",
        "availability": "MANUAL_ONLY",
        "note": "Record who referred the candidate and attach the resume by upload.",
    },
    {
        "key": "linkedin_url",
        "label": "LinkedIn profile URL",
        "availability": "MANUAL_ONLY",
        "note": "Store the profile URL as a reference. No scraping — automated import needs the approved official API.",
    },
    {
        "key": "company_page_url",
        "label": "Company careers page URL",
        "availability": "MANUAL_ONLY",
        "note": "Store the application URL from your own careers site as a reference.",
    },
    {
        "key": "linkedin_automated",
        "label": "LinkedIn automated import",
        "availability": "UNAVAILABLE",
        "note": "Requires an approved official LinkedIn API connection. This build never scrapes LinkedIn.",
    },
    {
        "key": "job_board_automated",
        "label": "Job board automated import",
        "availability": "COMING_SOON",
        "note": "Requires official partner APIs or a paid feed. Until then, record listing URLs manually.",
    },
]

MIN_PASTE_CHARS = 40
MAX_PASTE_CHARS = 200_000
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 500
MAX_URL_LEN = 500
MAX_NOTES_LEN = 2000
MAX_TITLE_LEN = 300

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_ALLOWED_TRANSITIONS = {
    "RECORDED": ("SCREENED", "DISCARDED"),
    "SCREENED": ("RECORDED", "DISCARDED"),
    "DISCARDED": ("RECORDED",),
}

STATUS_LABELS = {"RECORDED": "Recorded", "SCREENED": "Screened", "DISCARDED": "Discarded"}


# --------------------------------------------------------------------------
# create / list / status
# --------------------------------------------------------------------------


def create_record(conn, *, source_kind: str, profile_id: int | None = None, title: str = "",
                  url: str = "", notes: str = "", contact_name: str = "",
                  contact_email: str = "", referrer: str = "",
                  created_by: str = "", resume_id: int | None = None) -> dict:
    """Validate one manually recorded lead and store it. Raises SourceError."""
    fields = _validate(source_kind=source_kind, title=title, url=url, notes=notes,
                       contact_name=contact_name, contact_email=contact_email)
    duplicate = _check_duplicate(conn, profile_id=profile_id, url=fields["url"],
                                 contact_email=fields["contact_email"])
    if duplicate:
        raise SourceError(duplicate)
    record_id = _insert_record(
        conn,
        source_kind=source_kind,
        profile_id=profile_id,
        title=fields["title"],
        url=fields["url"],
        notes=fields["notes"][:MAX_NOTES_LEN],
        contact_name=contact_name.strip()[:MAX_TITLE_LEN],
        contact_email=fields["contact_email"],
        referrer=referrer.strip()[:MAX_TITLE_LEN],
        created_by=created_by.strip()[:120],
        resume_id=resume_id,
    )
    row = fetch_record(conn, record_id)
    write_audit(
        conn,
        "source_record_created",
        entity_type="source_record",
        entity_id=record_id,
        profile_id=profile_id,
        message=f"{_kind_label(source_kind)} recorded: {fields['title'] or fields['url'] or fields['contact_email']} (record #{record_id})",
        data={"source_kind": source_kind, "has_url": bool(fields["url"])},
    )
    return row


def list_records(conn, *, profile_id: int | None = None, status: str | None = None,
                 source_kind: str | None = None) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if profile_id is not None:
        clauses.append("sr.profile_id = ?")
        params.append(profile_id)
    if status:
        clauses.append("sr.status = ?")
        params.append(status.upper())
    if source_kind:
        clauses.append("sr.source_kind = ?")
        params.append(source_kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT sr.*,
                   sp.title AS profile_title,
                   r.filename AS resume_filename,
                   (SELECT id FROM candidates WHERE resume_id = sr.resume_id LIMIT 1) AS candidate_id,
                   (SELECT name FROM candidates WHERE resume_id = sr.resume_id LIMIT 1) AS candidate_name
            FROM source_records sr
            LEFT JOIN screening_profiles sp ON sp.id = sr.profile_id
            LEFT JOIN resumes r ON r.id = sr.resume_id
            {where}
            ORDER BY sr.created_at DESC, sr.id DESC""",
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def fetch_record(conn, record_id: int) -> dict | None:
    row = conn.execute(
        """SELECT sr.*,
                  sp.title AS profile_title,
                  r.filename AS resume_filename,
                  (SELECT id FROM candidates WHERE resume_id = sr.resume_id LIMIT 1) AS candidate_id,
                  (SELECT name FROM candidates WHERE resume_id = sr.resume_id LIMIT 1) AS candidate_name
           FROM source_records sr
           LEFT JOIN screening_profiles sp ON sp.id = sr.profile_id
           LEFT JOIN resumes r ON r.id = sr.resume_id
           WHERE sr.id = ?""",
        (record_id,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def set_status(conn, record_id: int, status: str, actor: str = "") -> dict:
    wanted = (status or "").strip().upper()
    if wanted not in _ALLOWED_TRANSITIONS:
        raise SourceError(f"Unknown record status '{status}'. Expected RECORDED, SCREENED or DISCARDED.")
    row = conn.execute("SELECT * FROM source_records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise SourceError("Intake record not found.")
    if row["status"] == wanted:
        return fetch_record(conn, record_id)
    if wanted not in _ALLOWED_TRANSITIONS[row["status"]]:
        raise SourceError(
            f"This record is {STATUS_LABELS[row['status']].lower()} and cannot be marked "
            f"{STATUS_LABELS[wanted].lower()}."
        )
    conn.execute(
        "UPDATE source_records SET status = ?, updated_at = ? WHERE id = ?",
        (wanted, now_iso(), record_id),
    )
    write_audit(
        conn,
        "source_record_status_changed",
        entity_type="source_record",
        entity_id=record_id,
        profile_id=row["profile_id"],
        message=f"Intake record #{record_id} marked {STATUS_LABELS[wanted].lower()}"
        + (f" by {actor}" if actor.strip() else ""),
        data={"from": row["status"], "to": wanted},
    )
    return fetch_record(conn, record_id)


def record_counts(conn, profile_id: int | None = None) -> dict:
    if profile_id is None:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM source_records GROUP BY status"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM source_records WHERE profile_id = ? GROUP BY status",
            (profile_id,),
        ).fetchall()
    counts = {status: 0 for status in _ALLOWED_TRANSITIONS}
    for row in rows:
        counts[row["status"]] = row["n"]
    counts["total"] = sum(counts[s] for s in _ALLOWED_TRANSITIONS)
    return counts


# --------------------------------------------------------------------------
# paste / CSV — text enters through the one canonical pipeline
# --------------------------------------------------------------------------


def import_pasted_text(ctx, profile: dict, *, text: str, label: str = "", actor: str = "") -> dict:
    """Ingest pasted resume text through handle_upload and link a record to it."""
    body = (text or "").strip()
    if len(body) < MIN_PASTE_CHARS:
        raise SourceError(f"Paste at least {MIN_PASTE_CHARS} characters of resume text.")
    if len(body) > MAX_PASTE_CHARS:
        raise SourceError(f"Pasted text is too large ({MAX_PASTE_CHARS:,} characters max).")
    clean_label = (label or "").strip()[:MAX_TITLE_LEN]

    filename = sanitize_filename(clean_label) if clean_label else "pasted-resume"
    if not filename.lower().endswith(".txt"):
        filename += ".txt"

    result = handle_upload(
        ctx, profile, [SourceUpload(filename, body.encode("utf-8"))],
        label=f"Pasted resume — {profile['title']}",
    )
    if result["queued"] == 0:
        reason = result["failures"][0]["reason"] if result["failures"] else "The pasted text was not accepted."
        raise SourceError(reason)
    resume_id = int(result["resumes"][0]["id"])

    conn = ctx.connect()
    try:
        record_id = _insert_record(
            conn,
            source_kind="pasted_text",
            profile_id=profile["id"],
            title=clean_label or "Pasted resume",
            url="",
            notes=f"{len(body):,} characters pasted; entered the pipeline as '{filename}'.",
            contact_name="",
            contact_email="",
            referrer="",
            created_by=(actor or "").strip()[:120],
            resume_id=resume_id,
        )
        write_audit(
            conn,
            "source_record_created",
            entity_type="source_record",
            entity_id=record_id,
            profile_id=profile["id"],
            message=f"Pasted resume text recorded (record #{record_id}) and queued as '{filename}'",
            data={"source_kind": "pasted_text", "chars": len(body), "resume_id": resume_id},
        )
    finally:
        conn.close()
    return {
        "record_id": record_id,
        "resume_id": resume_id,
        "job_id": result["job_id"],
        "filename": filename,
        "chars": len(body),
        "message": f"Pasted resume queued for processing ({len(body):,} characters).",
    }


def import_csv(ctx, profile: dict, raw: bytes, filename: str, actor: str = "") -> dict:
    """Import candidate leads from a UTF-8 CSV.

    Rows with a usable `resume_text` column are queued through the canonical
    pipeline; every other row becomes an intake record. Nothing is fabricated:
    the response reports exactly what was created, skipped and rejected.
    """
    if len(raw) > MAX_CSV_BYTES:
        raise SourceError(f"CSV file is larger than {MAX_CSV_BYTES // (1024 * 1024)} MB.")
    if not raw.strip():
        raise SourceError("The CSV file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceError("The CSV must be UTF-8 encoded — re-export the file and try again.") from None

    rows = _read_csv_rows(text)
    if not rows:
        raise SourceError("The CSV has no data rows.")
    header, data_rows = rows[0], rows[1:]
    if not data_rows:
        raise SourceError("The CSV only has a header row — there is nothing to import.")
    if len(data_rows) > MAX_CSV_ROWS:
        raise SourceError(f"The CSV has more than {MAX_CSV_ROWS} data rows — split it and import in parts.")

    columns, unrecognised = _map_columns(header)
    if "name" not in columns and "email" not in columns:
        found = ", ".join(header) if header else "none"
        raise SourceError(
            f"The CSV needs at least a 'name' or 'email' column. Columns found: {found}."
        )

    valid_rows: list[dict] = []
    invalid_rows: list[dict] = []
    empty_rows = 0
    for offset, data_row in enumerate(data_rows):
        spreadsheet_row = offset + 2  # 1-based + header row
        parsed = _parse_row(data_row, columns, spreadsheet_row)
        if parsed is None:
            empty_rows += 1
            continue
        if isinstance(parsed, str):
            invalid_rows.append({"row": spreadsheet_row, "reason": parsed})
            continue
        valid_rows.append(parsed)

    inserted: list[tuple[int, dict]] = []
    skipped_duplicates: list[dict] = []
    conn = ctx.connect()
    try:
        for row in valid_rows:
            duplicate = _check_duplicate(
                conn, profile_id=profile["id"], url=row["url"], contact_email=row["contact_email"]
            )
            if duplicate:
                skipped_duplicates.append({"row": row["row"], "reason": duplicate})
                continue
            record_id = _insert_record(
                conn,
                source_kind=row["source_kind"],
                profile_id=profile["id"],
                title=row["title"],
                url=row["url"],
                notes=row["notes"],
                contact_name=row["contact_name"],
                contact_email=row["contact_email"],
                referrer=row["referrer"],
                created_by=(actor or "").strip()[:120],
                resume_id=None,
            )
            inserted.append((record_id, row))
        uploads = [
            SourceUpload(row["upload_filename"], row["resume_text"].encode("utf-8"))
            for _record_id, row in inserted
            if row["resume_text"]
        ]
    finally:
        conn.close()

    upload_result = {"job_id": None, "resumes": [], "failures": []}
    if uploads:
        upload_result = handle_upload(
            ctx, profile, uploads,
            label=f"CSV import — {len(uploads)} resume(s) from '{filename}'",
        )

    by_filename = {item["filename"]: item["id"] for item in upload_result["resumes"]}
    conn = ctx.connect()
    try:
        linked = 0
        for record_id, row in inserted:
            resume_id = by_filename.get(row["upload_filename"]) if row["resume_text"] else None
            if resume_id:
                conn.execute(
                    "UPDATE source_records SET resume_id = ?, updated_at = ? WHERE id = ?",
                    (resume_id, now_iso(), record_id),
                )
                linked += 1
        write_audit(
            conn,
            "source_csv_imported",
            entity_type="resume_source",
            profile_id=profile["id"],
            message=(
                f"CSV '{filename}': {len(inserted)} record(s) added, {linked} resume(s) queued, "
                f"{len(skipped_duplicates)} duplicate(s) skipped, {len(invalid_rows)} row(s) rejected"
            ),
            data={
                "records": len(inserted),
                "resumes": linked,
                "duplicates": len(skipped_duplicates),
                "invalid": len(invalid_rows),
            },
        )
    finally:
        conn.close()

    rejected_uploads = len(upload_result.get("failures") or [])
    message = (
        f"{len(inserted)} record(s) added to the intake ledger, {linked} resume(s) queued for processing"
    )
    if skipped_duplicates:
        message += f", {len(skipped_duplicates)} duplicate(s) skipped"
    if invalid_rows or empty_rows or rejected_uploads:
        message += f", {len(invalid_rows) + rejected_uploads} row(s) rejected"
    message += "."
    return {
        "profile": {"id": profile["id"], "title": profile["title"]},
        "total_rows": len(data_rows),
        "records_created": len(inserted),
        "records_skipped_duplicates": len(skipped_duplicates),
        "resumes_queued": linked,
        "empty_rows": empty_rows,
        "job_id": upload_result.get("job_id"),
        "invalid_rows": invalid_rows + [
            {"row": None, "reason": failure["reason"] + f" (file '{failure['filename']}')"}
            for failure in upload_result.get("failures") or []
        ],
        "skipped_rows": skipped_duplicates,
        "unrecognised_columns": unrecognised,
        "note": (
            "Rows without resume text are saved as records only — attach their resume later by upload. "
            "Nothing was fetched from any website."
        ),
        "message": message,
    }


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _validate(*, source_kind: str, title: str, url: str, notes: str,
              contact_name: str, contact_email: str) -> dict:
    if source_kind not in CREATABLE_KINDS:
        raise SourceError(
            f"Unknown record type '{source_kind}'. Expected one of: {', '.join(CREATABLE_KINDS)}."
        )
    title = (title or "").strip()[:MAX_TITLE_LEN]
    url = (url or "").strip()
    notes = (notes or "").strip()
    contact_name = (contact_name or "").strip()
    contact_email = normalize_email(contact_email or "")
    if len(url) > MAX_URL_LEN:
        raise SourceError(f"URL is too long ({MAX_URL_LEN} characters max).")
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        raise SourceError("URL must start with http:// or https://.")
    if contact_email and not _EMAIL_RE.match(contact_email):
        raise SourceError("The contact email does not look like a valid address.")
    if len(notes) > MAX_NOTES_LEN:
        raise SourceError(f"Notes are too long ({MAX_NOTES_LEN} characters max).")
    if not (title or url or contact_name or contact_email):
        raise SourceError("Add at least a name, an email or a URL so the record is identifiable.")
    return {"title": title, "url": url, "notes": notes, "contact_email": contact_email}


def _check_duplicate(conn, *, profile_id: int | None, url: str, contact_email: str) -> str | None:
    """Honest duplicate message for the same URL or email scoped to a profile."""
    scope_sql = "profile_id IS NULL" if profile_id is None else "profile_id = ?"
    scope_params: list = [] if profile_id is None else [profile_id]
    if url:
        existing = conn.execute(
            f"SELECT id, created_at FROM source_records WHERE {scope_sql} AND url != '' AND LOWER(url) = LOWER(?) LIMIT 1",
            [*scope_params, url],
        ).fetchone()
        if existing:
            return (
                f"This URL is already on record (#{existing['id']}, added {existing['created_at'][:10]}). "
                "Duplicate records are not created."
            )
    if contact_email:
        existing = conn.execute(
            f"SELECT id, created_at FROM source_records WHERE {scope_sql} AND contact_email != '' AND LOWER(contact_email) = ? LIMIT 1",
            [*scope_params, contact_email],
        ).fetchone()
        if existing:
            return (
                f"This email is already on record (#{existing['id']}, added {existing['created_at'][:10]}). "
                "Duplicate records are not created."
            )
    return None


def _insert_record(conn, *, source_kind: str, profile_id: int | None, title: str, url: str,
                   notes: str, contact_name: str, contact_email: str, referrer: str,
                   created_by: str, resume_id: int | None) -> int:
    now = now_iso()
    cursor = conn.execute(
        """INSERT INTO source_records
           (source_kind, profile_id, title, url, notes, contact_name, contact_email, referrer,
            status, resume_id, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RECORDED', ?, ?, ?, ?)""",
        (source_kind, profile_id, title, url, notes, contact_name, contact_email, referrer,
         resume_id, created_by, now, now),
    )
    return int(cursor.lastrowid)


def _row_to_dict(row) -> dict:
    data = dict(row)
    data["status_label"] = STATUS_LABELS.get(data["status"], data["status"])
    return data


def _kind_label(kind: str) -> str:
    for info in RECORD_KIND_INFO:
        if info["kind"] == kind:
            return info["label"]
    return {"csv_import": "CSV import", "pasted_text": "Pasted text"}.get(kind, kind)


# --------------------------------------------------------------------------
# CSV parsing
# --------------------------------------------------------------------------

_COLUMN_ALIASES = {
    "name": {"name", "full_name", "fullname", "candidate", "candidate_name"},
    "email": {"email", "email_address", "e-mail", "mail"},
    "phone": {"phone", "mobile", "phone_number", "mobile_number"},
    "url": {"url", "link", "profile", "profile_url", "linkedin", "linkedin_url",
            "resume_url", "portfolio", "portfolio_url"},
    "notes": {"notes", "note", "comments", "comment", "remarks"},
    "referrer": {"referrer", "referred_by", "reference", "source_name"},
    "source_kind": {"source_kind", "source", "kind", "channel"},
    "resume_text": {"resume_text", "cv_text", "resume_content"},
}


def _read_csv_rows(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        rows.append([cell.strip() for cell in row])
        if len(rows) > MAX_CSV_ROWS + 1:
            raise SourceError(f"The CSV has more than {MAX_CSV_ROWS} data rows — split it and import in parts.")
    return rows


def _normalise_header(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", (value or "").strip().lower()).strip("_")


def _map_columns(header: list[str]) -> tuple[dict[str, int], list[str]]:
    columns: dict[str, int] = {}
    unrecognised: list[str] = []
    for index, cell in enumerate(header):
        key = _normalise_header(cell)
        matched = next((field for field, aliases in _COLUMN_ALIASES.items() if key in aliases), None)
        if matched and matched not in columns:
            columns[matched] = index
        elif not matched:
            unrecognised.append(cell)
    return columns, unrecognised


def _cell(row: list[str], columns: dict[str, int], field: str) -> str:
    index = columns.get(field)
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _parse_row(row: list[str], columns: dict[str, int], spreadsheet_row: int) -> dict | None | str:
    """Returns a parsed dict, None for an empty row, or a rejection reason."""
    name = _cell(row, columns, "name")[:MAX_TITLE_LEN]
    email = normalize_email(_cell(row, columns, "email"))
    url = _cell(row, columns, "url")
    notes = _cell(row, columns, "notes")
    referrer = _cell(row, columns, "referrer")
    phone = _cell(row, columns, "phone")
    kind_raw = _normalise_header(_cell(row, columns, "source_kind"))
    resume_text = _cell(row, columns, "resume_text")

    if not (name or email or url or resume_text):
        return None
    if email and not _EMAIL_RE.match(email):
        return f"Email '{email}' is not a valid address."
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        return f"URL '{url[:80]}' does not start with http:// or https://."
    if len(url) > MAX_URL_LEN:
        return "URL is too long (500 characters max)."

    source_kind = kind_raw if kind_raw in RECORD_KINDS else "csv_import"
    if phone:
        notes = (notes + f" Phone: {phone}.").strip() if notes else f"Phone: {phone}."
    if kind_raw and source_kind == "csv_import" and kind_raw != "csv_import":
        notes = (notes + f" Original source label: {kind_raw}.").strip()
    if resume_text and len(resume_text) < MIN_PASTE_CHARS:
        notes = (notes + f" Resume text kept out of the pipeline (under {MIN_PASTE_CHARS} characters).").strip()
        resume_text = ""

    slug = re.sub(r"[^a-z0-9]+", "-", (name or email or "resume").lower()).strip("-") or "resume"
    upload_filename = f"csv-{spreadsheet_row:03d}-{slug}.txt"

    return {
        "row": spreadsheet_row,
        "title": name or email or url,
        "url": url,
        "notes": notes[:MAX_NOTES_LEN],
        "contact_name": name,
        "contact_email": email,
        "referrer": referrer[:MAX_TITLE_LEN],
        "source_kind": source_kind,
        "resume_text": resume_text,
        "upload_filename": upload_filename,
    }

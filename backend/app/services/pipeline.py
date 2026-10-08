"""Upload handling and the background processing pipeline.

Uploads are validated, hashed and stored; a single background worker thread
processes one resume at a time (parsing → extraction → scoring → optional AI
analysis), writing real progress into the database after every step, so the
UI can poll true counts. The worker never fabricates states: a resume that
cannot be parsed becomes FAILED with a reason and a Retry action.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from pathlib import Path

from .. import similarity
from ..ai import AIUnavailableError, resolve_provider
from ..audit import record
from ..extraction import extract_resume
from ..parsing import ALLOWED_EXTENSIONS, ResumeParseError, extract_text
from ..scoring import CandidateFacts, score_candidate
from ..util import jdumps, jloads, now_iso, sanitize_filename
from .candidates import create_candidate, save_scores, status_for_recommendation
from .settings_store import get_ai_settings

logger = logging.getLogger("ailister.pipeline")

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per resume


# --------------------------------------------------------------------------
# upload
# --------------------------------------------------------------------------


class UploadError(Exception):
    pass


def handle_upload(ctx, profile: dict, uploads: list, label: str | None = None) -> dict:
    """Validate and store uploaded files, then queue a processing job.

    ``label`` lets non-manual sources name the job ("Gmail import — 41 file(s)")
    while the ingestion path itself stays exactly the same.
    """
    if not uploads:
        raise UploadError("No files were uploaded.")

    conn = ctx.connect()
    try:
        created: list[dict] = []
        failures: list[dict] = []
        max_total = 2000

        for upload in uploads[:max_total]:
            filename = sanitize_filename(upload.filename or "resume")
            extension = Path(filename).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                failures.append({"filename": filename, "reason": "Unsupported file type (only PDF, DOCX and TXT are accepted)."})
                continue
            raw = upload.file.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                failures.append({"filename": filename, "reason": "File exceeds the 10 MB limit."})
                continue
            if len(raw) == 0:
                failures.append({"filename": filename, "reason": "File is empty."})
                continue

            file_hash = hashlib.sha256(raw).hexdigest()
            profile_dir = ctx.uploads_dir / str(profile["id"])
            profile_dir.mkdir(parents=True, exist_ok=True)
            stored_name = f"{file_hash[:16]}_{filename}"
            stored_path = profile_dir / stored_name
            stored_path.write_bytes(raw)

            duplicate_hash = conn.execute(
                "SELECT id FROM resumes WHERE profile_id = ? AND file_hash = ? AND status != 'FAILED' LIMIT 1",
                (profile["id"], file_hash),
            ).fetchone()

            cursor = conn.execute(
                """INSERT INTO resumes
                   (profile_id, filename, stored_path, file_hash, size_bytes, status, duplicate_hash_of, uploaded_at)
                   VALUES (?, ?, ?, ?, ?, 'UPLOADED', ?, ?)""",
                (
                    profile["id"],
                    filename,
                    str(stored_path.relative_to(ctx.data_dir)),
                    file_hash,
                    len(raw),
                    duplicate_hash["id"] if duplicate_hash else None,
                    now_iso(),
                ),
            )
            resume_id = int(cursor.lastrowid)
            created.append({"id": resume_id, "filename": filename, "size_bytes": len(raw)})
            record(
                conn,
                "resume_uploaded",
                entity_type="resume",
                entity_id=resume_id,
                profile_id=profile["id"],
                message=f"Resume '{filename}' uploaded",
                data={"size_bytes": len(raw), "duplicate_hash_of": duplicate_hash["id"] if duplicate_hash else None},
            )

        if not created:
            return {"job_id": None, "resumes": [], "failures": failures, "queued": 0}

        cursor = conn.execute(
            """INSERT INTO processing_jobs (profile_id, label, status, total_resumes, created_at)
               VALUES (?, ?, 'QUEUED', ?, ?)""",
            (profile["id"], label or f"Upload batch — {len(created)} file(s)", len(created), now_iso()),
        )
        job_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO job_resumes (job_id, resume_id) VALUES (?, ?)",
            [(job_id, item["id"]) for item in created],
        )
        record(
            conn,
            "processing_job_created",
            entity_type="processing_job",
            entity_id=job_id,
            profile_id=profile["id"],
            message=f"Processing job queued for {len(created)} resume(s)",
            data={"resumes": len(created)},
        )
    finally:
        conn.close()

    ctx.jobs.enqueue(job_id)
    return {"job_id": job_id, "resumes": created, "failures": failures, "queued": len(created)}


def retry_resume(ctx, resume_id: int) -> dict:
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if row is None:
            raise UploadError("Resume not found.")
        if row["status"] != "FAILED":
            raise UploadError("Only failed resumes can be retried.")
        conn.execute(
            "UPDATE resumes SET status = 'UPLOADED', error_reason = NULL WHERE id = ?", (resume_id,)
        )
        cursor = conn.execute(
            """INSERT INTO processing_jobs (profile_id, label, status, total_resumes, created_at)
               VALUES (?, ?, 'QUEUED', 1, ?)""",
            (row["profile_id"], f"Retry — {row['filename']}", now_iso()),
        )
        job_id = int(cursor.lastrowid)
        conn.execute("INSERT INTO job_resumes (job_id, resume_id) VALUES (?, ?)", (job_id, resume_id))
        record(
            conn,
            "retry_requested",
            entity_type="resume",
            entity_id=resume_id,
            profile_id=row["profile_id"],
            message=f"Retry requested for '{row['filename']}'",
        )
    finally:
        conn.close()
    ctx.jobs.enqueue(job_id)
    return {"job_id": job_id, "resume_id": resume_id}


# --------------------------------------------------------------------------
# job runner
# --------------------------------------------------------------------------


class JobRunner:
    """A single background worker consuming a FIFO of job ids."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ailister-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.queue.put(-1)
        if self._thread:
            self._thread.join(timeout=10)

    def enqueue(self, job_id: int) -> None:
        self.queue.put(job_id)

    def wait_idle(self, timeout: float = 120.0) -> bool:
        """Block until the worker has finished every job handed to it.

        ``Queue.empty()``/``qsize()`` take the queue's own non-reentrant lock,
        so they must never be called while that lock is held — doing so
        deadlocks this thread and every worker waiting on the same lock.
        ``unfinished_tasks`` is a plain counter, which is all this needs.
        """
        if self._thread is None or self._stop.is_set():
            return True
        deadline = time.monotonic() + timeout
        while self.queue.unfinished_tasks > 0:
            if time.monotonic() >= deadline:
                return False
            self._stop.wait(0.05)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            job_id = self.queue.get()
            try:
                if job_id == -1:
                    return
                process_job(self.ctx, job_id)
            except Exception:  # noqa: BLE001 - the worker must never die
                logger.exception("job %s crashed", job_id)
                _mark_job_crashed(self.ctx, job_id)
            finally:
                self.queue.task_done()


def _mark_job_crashed(ctx, job_id: int) -> None:
    conn = ctx.connect()
    try:
        conn.execute(
            "UPDATE processing_jobs SET status = 'COMPLETED_WITH_ERRORS', finished_at = ? WHERE id = ?",
            (now_iso(), job_id),
        )
    finally:
        conn.close()


def process_job(ctx, job_id: int) -> None:
    conn = ctx.connect()
    try:
        job = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            return
        conn.execute(
            "UPDATE processing_jobs SET status = 'RUNNING', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now_iso(), job_id),
        )
        profile_row = conn.execute(
            "SELECT * FROM screening_profiles WHERE id = ?", (job["profile_id"],)
        ).fetchone()
        resume_ids = [
            row["resume_id"]
            for row in conn.execute(
                """SELECT jr.resume_id FROM job_resumes jr
                   JOIN resumes r ON r.id = jr.resume_id
                   WHERE jr.job_id = ? AND r.status IN ('UPLOADED', 'PARSING')
                   ORDER BY jr.resume_id""",
                (job_id,),
            )
        ]
    finally:
        conn.close()

    from .profiles import profile_to_dict

    profile = profile_to_dict(profile_row)
    for resume_id in resume_ids:
        try:
            process_resume(ctx, resume_id, profile)
        except Exception:  # noqa: BLE001
            logger.exception("resume %s processing crashed", resume_id)
            _fail_resume(ctx, resume_id, "Processing failed unexpectedly. See developer log.")

    conn = ctx.connect()
    try:
        counts = conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN r.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                 SUM(CASE WHEN r.status IN ('UPLOADED','PARSING','PARSED','ANALYZING') THEN 1 ELSE 0 END) AS remaining
               FROM job_resumes jr JOIN resumes r ON r.id = jr.resume_id
               WHERE jr.job_id = ?""",
            (job_id,),
        ).fetchone()
        failed = counts["failed"] or 0
        remaining = counts["remaining"] or 0
        status = "COMPLETED_WITH_ERRORS" if (failed and not remaining) else "COMPLETED"
        if remaining:
            status = "RUNNING"
        conn.execute(
            "UPDATE processing_jobs SET status = ?, finished_at = ? WHERE id = ?",
            (status, now_iso() if status != "RUNNING" else None, job_id),
        )
        record(
            conn,
            "processing_job_finished",
            entity_type="processing_job",
            entity_id=job_id,
            profile_id=job["profile_id"],
            message=f"Job finished: {counts['total'] - remaining - failed} processed, {failed} failed",
            data={"failed": failed},
        )
    finally:
        conn.close()


def _fail_resume(ctx, resume_id: int, reason: str) -> None:
    conn = ctx.connect()
    try:
        conn.execute(
            "UPDATE resumes SET status = 'FAILED', error_reason = ? WHERE id = ?", (reason, resume_id)
        )
        row = conn.execute("SELECT filename, profile_id FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        record(
            conn,
            "resume_parse_failed",
            entity_type="resume",
            entity_id=resume_id,
            profile_id=row["profile_id"] if row else None,
            message=f"Processing failed for '{row['filename'] if row else resume_id}': {reason}",
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# single resume processing
# --------------------------------------------------------------------------


def process_resume(ctx, resume_id: int, profile: dict) -> None:
    conn = ctx.connect()
    try:
        resume = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if resume is None:
            return
        conn.execute("UPDATE resumes SET status = 'PARSING' WHERE id = ?", (resume_id,))

        # idempotency: clear any partial candidate left by an earlier crash
        stale = conn.execute("SELECT id FROM candidates WHERE resume_id = ?", (resume_id,)).fetchall()
        for row in stale:
            conn.execute("DELETE FROM candidates WHERE id = ?", (row["id"],))

        stored_path = ctx.data_dir / resume["stored_path"]
        try:
            text = extract_text(stored_path)
        except ResumeParseError as exc:
            conn.execute(
                "UPDATE resumes SET status = 'FAILED', error_reason = ? WHERE id = ?",
                (exc.reason, resume_id),
            )
            record(
                conn,
                "resume_parse_failed",
                entity_type="resume",
                entity_id=resume_id,
                profile_id=resume["profile_id"],
                message=f"Parsing failed for '{resume['filename']}': {exc.reason}",
            )
            return

        conn.execute(
            """UPDATE resumes SET status = 'PARSED', extracted_text = ?, text_chars = ?, parsed_at = ?,
                                  error_reason = NULL
               WHERE id = ?""",
            (text, len(text), now_iso(), resume_id),
        )
        record(
            conn,
            "resume_parsed",
            entity_type="resume",
            entity_id=resume_id,
            profile_id=resume["profile_id"],
            message=f"Resume '{resume['filename']}' parsed ({len(text)} characters)",
        )

        extracted = extract_resume(text)
        facts = CandidateFacts(
            skills=[
                {
                    "skill": item.skill,
                    "normalized": item.skill,
                    "strength": item.strength,
                    "category": item.category,
                    "sources": item.sources,
                }
                for item in extracted.skills
            ],
            education=[
                {
                    "degree": item.degree,
                    "course": item.course,
                    "institution": item.institution,
                    "graduation_year": item.graduation_year,
                    "academic_value": item.academic_value,
                    "academic_type": item.academic_type,
                    "raw_line": item.raw_line,
                }
                for item in extracted.education
            ],
            experience=[
                {
                    "title": item.title,
                    "organization": item.organization,
                    "kind": item.kind,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "duration_months": item.duration_months,
                    "description": item.description,
                    "raw_text": item.raw_text,
                }
                for item in extracted.experience
            ],
            projects=[
                {
                    "name": item.name,
                    "technologies": item.technologies,
                    "description": item.description,
                    "raw_text": item.raw_text,
                }
                for item in extracted.projects
            ],
            certifications=[
                {"name": item.name, "issuer": item.issuer, "year": item.year}
                for item in extracted.certifications
            ],
            achievements=extracted.achievements,
            name=extracted.name,
            email=extracted.email,
            phone=extracted.phone,
            location=extracted.location,
            links=extracted.links,
            dob_text=extracted.dob_text,
            best_academic=extracted.best_academic(),
            raw_text=text,
        )

        result = score_candidate(profile, facts)

        signature = similarity.signature(text)
        duplicate_of, signals = detect_duplicates(
            conn,
            profile_id=resume["profile_id"],
            facts=facts,
            signature=signature,
            text=text,
            duplicate_hash_of=resume["duplicate_hash_of"],
        )

        is_demo = "DEMO DATA" in text[:400].upper()
        conn.execute("UPDATE resumes SET status = 'ANALYZING' WHERE id = ?", (resume_id,))
        candidate_id = create_candidate(
            conn,
            profile_id=resume["profile_id"],
            resume_id=resume_id,
            facts=facts,
            result=result,
            signature=signature,
            duplicate_of=duplicate_of,
            duplicate_signals=signals,
            is_demo=is_demo,
        )
        record(
            conn,
            "candidate_created",
            entity_type="candidate",
            entity_id=candidate_id,
            profile_id=resume["profile_id"],
            candidate_id=candidate_id,
            message=(
                f"Candidate '{facts.name or 'Not found'}' created from '{resume['filename']}' — "
                f"overall match {result.overall} ({result.recommendation})"
            ),
            data={"overall": result.overall, "recommendation": result.recommendation},
        )
        if duplicate_of:
            record(
                conn,
                "duplicate_flagged",
                entity_type="candidate",
                entity_id=candidate_id,
                profile_id=resume["profile_id"],
                candidate_id=candidate_id,
                message=f"Potential duplicate of candidate #{duplicate_of}",
                data={"signals": signals},
            )

        conn.execute("UPDATE resumes SET status = 'ANALYZED', processed_at = ? WHERE id = ?", (now_iso(), resume_id))
    finally:
        conn.close()

    # AI analysis is optional and never blocks the deterministic pipeline
    run_ai_analysis(ctx, candidate_id, profile)


def detect_duplicates(
    conn,
    *,
    profile_id: int,
    facts: CandidateFacts,
    signature: list[int],
    text: str,
    duplicate_hash_of: int | None,
) -> tuple[int | None, list[dict]]:
    signals: list[dict] = []
    duplicate_of: int | None = None

    rows = conn.execute(
        """SELECT c.id, c.name, c.email, c.phone, c.text_signature, r.extracted_text
           FROM candidates c JOIN resumes r ON r.id = c.resume_id
           WHERE c.profile_id = ?""",
        (profile_id,),
    ).fetchall()

    for row in rows:
        if facts.email and row["email"] and facts.email.lower() == row["email"].lower():
            signals.append({"kind": "email", "candidate_id": row["id"], "candidate_name": row["name"],
                            "detail": f"identical email address as candidate #{row['id']}"})
            duplicate_of = duplicate_of or row["id"]
            break
    if duplicate_of is None:
        for row in rows:
            if facts.phone and row["phone"] and facts.phone == row["phone"]:
                signals.append({"kind": "phone", "candidate_id": row["id"], "candidate_name": row["name"],
                                "detail": f"identical phone number as candidate #{row['id']}"})
                duplicate_of = row["id"]
                break
    if duplicate_of is None and signature:
        for row in rows:
            other_sig = jloads(row["text_signature"], [])
            other_text = row["extracted_text"] or ""
            if not other_sig or not other_text:
                continue
            is_dup, score = similarity.is_likely_duplicate(text, other_text, signature, other_sig)
            if is_dup:
                signals.append({"kind": "content", "candidate_id": row["id"], "candidate_name": row["name"],
                                "detail": f"near-identical resume text ({int(score * 100)}% similar to candidate #{row['id']})"})
                duplicate_of = row["id"]
                break
    if duplicate_hash_of:
        signals.append({"kind": "file_hash", "resume_id": duplicate_hash_of,
                        "detail": f"identical file content already uploaded (resume #{duplicate_hash_of})"})
        if duplicate_of is None:
            other = conn.execute(
                "SELECT id FROM candidates WHERE resume_id = ?", (duplicate_hash_of,)
            ).fetchone()
            if other:
                duplicate_of = other["id"]
    return duplicate_of, signals


# --------------------------------------------------------------------------
# AI analysis
# --------------------------------------------------------------------------


def scoring_digest_from_db(conn, candidate_id: int) -> dict:
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    components = [
        {"component": score["component"], "score": score["score"], "weight": score["weight"],
         "points": score["points"], "evidence": score["evidence"], "details": jloads(score["details"], {})}
        for score in conn.execute(
            "SELECT * FROM candidate_scores WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        )
    ]
    strengths: list[str] = []
    missing: list[str] = []
    for component in components:
        if component["component"] == "skills":
            for item in component["details"].get("required", []) + component["details"].get("preferred", []):
                if not item.get("found"):
                    missing.append(f"Skill not found: {item['skill']}")
                elif item.get("strength") == "strong":
                    strengths.append(f"Strong evidence for skill: {item['skill']}")
    return {
        "overall": row["overall_score"] if row else None,
        "recommendation": row["recommendation"] if row else None,
        "components": components,
        "strengths": strengths[:8],
        "missing_requirements": missing[:8],
    }


def run_ai_analysis(ctx, candidate_id: int, profile: dict | None = None) -> dict:
    """Run (or re-run) the AI analysis for one candidate.

    Returns {"status": ..., "analysis": ..., "reason": ...}. On failure the
    stored ai_status becomes FAILED with a reason and the UI offers Retry.
    """
    from .profiles import get_profile

    conn = ctx.connect()
    try:
        candidate = conn.execute(
            """SELECT c.*, r.extracted_text FROM candidates c
               JOIN resumes r ON r.id = c.resume_id WHERE c.id = ?""",
            (candidate_id,),
        ).fetchone()
        if candidate is None:
            return {"status": "NOT_FOUND", "reason": "Candidate not found."}
        if profile is None:
            profile = get_profile(conn, candidate["profile_id"])
        digest = scoring_digest_from_db(conn, candidate_id)
        resume_text = candidate["extracted_text"] or ""

        if not profile.get("ai_enabled", True):
            conn.execute("UPDATE candidates SET ai_status = 'DISABLED' WHERE id = ?", (candidate_id,))
            return {"status": "DISABLED", "reason": "AI analysis is disabled for this screening profile."}

        provider = resolve_provider(get_ai_settings(ctx))
        if provider is None:
            conn.execute("UPDATE candidates SET ai_status = 'NOT_CONFIGURED' WHERE id = ?", (candidate_id,))
            return {"status": "NOT_CONFIGURED", "reason": "No AI provider is configured."}

        conn.execute("UPDATE candidates SET ai_status = 'RUNNING' WHERE id = ?", (candidate_id,))
        record(
            conn,
            "ai_analysis_started",
            entity_type="candidate",
            entity_id=candidate_id,
            candidate_id=candidate_id,
            profile_id=candidate["profile_id"],
            message=f"AI analysis started ({provider.name})",
            data={"provider": provider.name, "model": provider.model_name()},
        )
    finally:
        conn.close()

    try:
        analysis = provider.analyze(profile, resume_text, digest)
    except AIUnavailableError as exc:
        conn = ctx.connect()
        try:
            conn.execute(
                "UPDATE candidates SET ai_status = 'FAILED', ai_analysis = ?, ai_updated_at = ? WHERE id = ?",
                (jdumps({"error": exc.reason}), now_iso(), candidate_id),
            )
            record(
                conn,
                "ai_analysis_failed",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                message=f"AI analysis unavailable: {exc.reason}",
                data={"provider": provider.name},
            )
        finally:
            conn.close()
        return {"status": "FAILED", "reason": exc.reason}
    except Exception as exc:  # noqa: BLE001 - provider bugs must not crash the pipeline
        logger.exception("ai provider %s crashed", provider.name)
        conn = ctx.connect()
        try:
            conn.execute(
                "UPDATE candidates SET ai_status = 'FAILED', ai_analysis = ?, ai_updated_at = ? WHERE id = ?",
                (jdumps({"error": "AI provider error."}), now_iso(), candidate_id),
            )
            record(
                conn,
                "ai_analysis_failed",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                message="AI analysis failed with an internal provider error",
                data={"provider": provider.name, "error": str(exc)[:200]},
            )
        finally:
            conn.close()
        return {"status": "FAILED", "reason": "AI provider error."}

    conn = ctx.connect()
    try:
        conn.execute(
            "UPDATE candidates SET ai_status = 'COMPLETED', ai_analysis = ?, ai_updated_at = ? WHERE id = ?",
            (jdumps(analysis.to_dict()), now_iso(), candidate_id),
        )
        record(
            conn,
            "ai_analysis_completed",
            entity_type="candidate",
            entity_id=candidate_id,
            candidate_id=candidate_id,
            message=f"AI analysis completed ({analysis.provider}"
                    + (f", {analysis.model}" if analysis.model else "") + ")",
            data={"provider": analysis.provider, "confidence": analysis.confidence},
        )
    finally:
        conn.close()
    return {"status": "COMPLETED", "analysis": analysis.to_dict()}

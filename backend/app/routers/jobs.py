"""Processing jobs, resume status and retry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..services.pipeline import UploadError, retry_resume
from ..util import safe_join_under

router = APIRouter(prefix="/api", tags=["processing"])

JOB_PROGRESS_SQL = """
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN r.status = 'UPLOADED' THEN 1 ELSE 0 END) AS queued,
        SUM(CASE WHEN r.status IN ('PARSING','PARSED','ANALYZING') THEN 1 ELSE 0 END) AS processing,
        SUM(CASE WHEN r.status = 'ANALYZED' THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN r.status = 'FAILED' THEN 1 ELSE 0 END) AS failed
    FROM job_resumes jr JOIN resumes r ON r.id = jr.resume_id
"""


def _job_dict(ctx, conn, row) -> dict:
    counts = conn.execute(JOB_PROGRESS_SQL + " WHERE jr.job_id = ?", (row["id"],)).fetchone()
    total = counts["total"] or 0
    completed = counts["completed"] or 0
    failed = counts["failed"] or 0
    processing = counts["processing"] or 0
    queued = counts["queued"] or 0
    profile = conn.execute(
        "SELECT id, title, type FROM screening_profiles WHERE id = ?", (row["profile_id"],)
    ).fetchone()
    return {
        "id": row["id"],
        "profile_id": row["profile_id"],
        "profile_title": profile["title"] if profile else None,
        "profile_type": profile["type"] if profile else None,
        "label": row["label"],
        "status": row["status"],
        "total": total,
        "queued": queued,
        "processing": processing,
        "completed": completed,
        "failed": failed,
        "remaining": queued + processing,
        "percent": round(completed / total * 100, 1) if total else 0.0,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _resume_dict(row) -> dict:
    return {
        "id": row["id"],
        "profile_id": row["profile_id"],
        "filename": row["filename"],
        "size_bytes": row["size_bytes"],
        "status": row["status"],
        "error_reason": row["error_reason"],
        "text_chars": row["text_chars"],
        "uploaded_at": row["uploaded_at"],
        "processed_at": row["processed_at"],
        "duplicate_hash_of": row["duplicate_hash_of"],
        "candidate_id": row["candidate_id"] if "candidate_id" in row.keys() else None,
    }


@router.get("/jobs")
def list_jobs(request: Request, profile_id: int | None = None, limit: int = 50):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        sql = "SELECT * FROM processing_jobs"
        args: list = []
        if profile_id:
            sql += " WHERE profile_id = ?"
            args.append(profile_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(min(200, max(1, limit)))
        return {"items": [_job_dict(ctx, conn, row) for row in conn.execute(sql, args)]}
    finally:
        conn.close()


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Processing job not found.")
        job = _job_dict(ctx, conn, row)
        resumes = conn.execute(
            """SELECT r.*, (SELECT id FROM candidates c WHERE c.resume_id = r.id) AS candidate_id
               FROM job_resumes jr JOIN resumes r ON r.id = jr.resume_id
               WHERE jr.job_id = ? ORDER BY r.id""",
            (job_id,),
        ).fetchall()
        job["resumes"] = [_resume_dict(resume) for resume in resumes]
        return job
    finally:
        conn.close()


@router.get("/resumes")
def list_resumes(request: Request, profile_id: int | None = None, status: str | None = None, limit: int = 100):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        sql = """SELECT r.*, (SELECT id FROM candidates c WHERE c.resume_id = r.id) AS candidate_id
                 FROM resumes r WHERE 1=1"""
        args: list = []
        if profile_id:
            sql += " AND r.profile_id = ?"
            args.append(profile_id)
        if status:
            sql += " AND r.status = ?"
            args.append(status)
        sql += " ORDER BY r.id DESC LIMIT ?"
        args.append(min(500, max(1, limit)))
        return {"items": [_resume_dict(row) for row in conn.execute(sql, args)]}
    finally:
        conn.close()


@router.post("/resumes/{resume_id}/retry", status_code=202)
def retry(request: Request, resume_id: int):
    ctx = request.app.state.ctx
    try:
        return retry_resume(ctx, resume_id)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/resumes/{resume_id}/file")
def download_original(request: Request, resume_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        path = safe_join_under(ctx.data_dir, row["stored_path"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid stored path.") from exc
    if not path.exists():
        raise HTTPException(status_code=410, detail="The stored file is missing on disk.")
    return FileResponse(path, filename=row["filename"], media_type="application/octet-stream")

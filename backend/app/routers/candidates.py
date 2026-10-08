"""Candidate listing, detail, review actions, re-analysis and export."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import DecisionIn, NoteIn
from ..services.candidates import (
    add_note,
    apply_decision,
    candidate_detail,
    filter_options,
    list_candidates,
)
from ..services.exporter import export_csv
from ..services.pipeline import run_ai_analysis

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

LIST_PARAM_KEYS = (
    "profile_id", "search", "degree", "skill", "recommendation", "status",
    "resume_status", "min_academic", "max_academic", "academic_type", "experience",
    "duplicates_only", "data_scope", "date_range", "sort", "order", "page", "page_size",
)


def _list_params(request: Request) -> dict:
    params = {key: request.query_params.get(key) for key in LIST_PARAM_KEYS}
    return {key: value for key, value in params.items() if value not in (None, "")}


@router.get("")
def list_all(request: Request):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        return list_candidates(conn, _list_params(request))
    finally:
        conn.close()


@router.get("/filter-options")
def options(request: Request, profile_id: int | None = None):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        return filter_options(conn, profile_id)
    finally:
        conn.close()


@router.post("/export")
def export(request: Request):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        filename, payload, count = export_csv(conn, _list_params(request))
    finally:
        conn.close()
    if count == 0:
        raise HTTPException(status_code=404, detail="No candidates match the current filters — nothing to export.")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Export-Count": str(count)},
    )


@router.get("/{candidate_id}")
def detail(request: Request, candidate_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        candidate = candidate_detail(conn, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        return candidate
    finally:
        conn.close()


@router.get("/{candidate_id}/resume-text")
def resume_text(request: Request, candidate_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        row = conn.execute(
            """SELECT r.extracted_text, r.filename, r.text_chars
               FROM candidates c JOIN resumes r ON r.id = c.resume_id WHERE c.id = ?""",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        return {
            "filename": row["filename"],
            "text": row["extracted_text"] or "",
            "text_chars": row["text_chars"] or 0,
        }
    finally:
        conn.close()


@router.post("/{candidate_id}/notes", status_code=201)
def add_note_endpoint(request: Request, candidate_id: int, payload: NoteIn):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        if candidate_detail_row(conn, candidate_id) is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        add_note(conn, candidate_id, payload.author, payload.note)
        return candidate_detail(conn, candidate_id)
    finally:
        conn.close()


def candidate_detail_row(conn, candidate_id: int):
    return conn.execute("SELECT id FROM candidates WHERE id = ?", (candidate_id,)).fetchone()


@router.post("/{candidate_id}/decision")
def decision_endpoint(request: Request, candidate_id: int, payload: DecisionIn):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        updated = apply_decision(conn, candidate_id, payload.decision, payload.reason, payload.author)
        if updated is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        return updated
    finally:
        conn.close()


@router.post("/{candidate_id}/reanalyze")
def reanalyze(request: Request, candidate_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        if candidate_detail_row(conn, candidate_id) is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
    finally:
        conn.close()
    result = run_ai_analysis(ctx, candidate_id)
    return result

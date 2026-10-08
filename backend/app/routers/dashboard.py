"""Dashboard, review queue, exports history and audit endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..services.candidates import (
    DECISION_LABELS,
    created_after,
    demo_scope_clause,
    primary_education,
)
from ..services.demo_workspace import workspace_summary
from ..util import jloads
from .jobs import JOB_PROGRESS_SQL, _job_dict

router = APIRouter(prefix="/api", tags=["dashboard"])

NEEDS_REVIEW_STATUSES = ("REVIEW_REQUIRED", "PRIORITY_REVIEW", "INTERVIEW_RECOMMENDED")


@router.get("/dashboard")
def dashboard(request: Request, data_scope: str | None = None, date_range: str | None = None):
    """Overview cards.

    ``data_scope`` (demo / real) and ``date_range`` (today / last_7_days) narrow
    the cards, the activity feed and the profile list. They never delete or
    archive anything, and the unfiltered demo/real split stays available under
    ``demo_workspace`` so the demo widget cannot be made to look empty by a
    filter.
    """
    ctx = request.app.state.ctx
    scope = demo_scope_clause(data_scope)
    want_demo = str(data_scope or "").strip().lower() == "demo"
    cutoff = created_after(date_range)
    conn = ctx.connect()
    try:
        where = ["1=1"]
        args: list = []
        if scope:
            where.append(scope)
        if cutoff:
            where.append("created_at >= ?")
            args.append(cutoff)
        scope_sql = " AND ".join(where)

        candidates = conn.execute(
            f"""SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN status IN ('REVIEW_REQUIRED','PRIORITY_REVIEW','INTERVIEW_RECOMMENDED') THEN 1 ELSE 0 END) AS needs_review,
                 SUM(CASE WHEN status = 'PRIORITY_REVIEW' THEN 1 ELSE 0 END) AS priority_review,
                 SUM(CASE WHEN status = 'INTERVIEW_RECOMMENDED' THEN 1 ELSE 0 END) AS interview_recommended,
                 SUM(CASE WHEN status = 'SHORTLISTED' THEN 1 ELSE 0 END) AS shortlisted,
                 SUM(CASE WHEN status = 'INTERVIEW_STAGE' THEN 1 ELSE 0 END) AS interview_stage,
                 SUM(CASE WHEN status = 'HIRED' THEN 1 ELSE 0 END) AS hired,
                 SUM(CASE WHEN status = 'ON_HOLD' THEN 1 ELSE 0 END) AS on_hold,
                 SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed,
                 SUM(CASE WHEN recommendation = 'PRIORITY_REVIEW' THEN 1 ELSE 0 END) AS rec_priority,
                 SUM(CASE WHEN recommendation = 'INTERVIEW_RECOMMENDATION' THEN 1 ELSE 0 END) AS rec_interview,
                 SUM(CASE WHEN recommendation = 'MANUAL_REVIEW' THEN 1 ELSE 0 END) AS rec_manual,
                 SUM(CASE WHEN recommendation = 'DOES_NOT_MEET' THEN 1 ELSE 0 END) AS rec_not_met,
                 SUM(CASE WHEN duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS duplicates,
                 SUM(CASE WHEN ai_status = 'FAILED' THEN 1 ELSE 0 END) AS ai_failed,
                 SUM(CASE WHEN is_demo = 1 THEN 1 ELSE 0 END) AS demo,
                 SUM(CASE WHEN is_demo = 0 THEN 1 ELSE 0 END) AS real
               FROM candidates WHERE {scope_sql}""",
            args,
        ).fetchone()
        resumes = conn.execute(
            f"""SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN status = 'ANALYZED' THEN 1 ELSE 0 END) AS processed,
                 SUM(CASE WHEN status IN ('UPLOADED','PARSING','PARSED','ANALYZING') THEN 1 ELSE 0 END) AS processing,
                 SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed
               FROM resumes
               WHERE {'1=1' if cutoff is None else 'uploaded_at >= ?'}""",
            () if cutoff is None else (cutoff,),
        ).fetchone()
        active_jobs = [
            _job_dict(ctx, conn, row)
            for row in conn.execute(
                "SELECT * FROM processing_jobs WHERE status IN ('QUEUED','RUNNING') ORDER BY id DESC LIMIT 10"
            )
        ]
        recent_profiles = []
        profile_sql = f"""SELECT p.*,
                      (SELECT COUNT(*) FROM candidates c WHERE c.profile_id = p.id AND {scope_sql}) AS candidate_count,
                      (SELECT COUNT(*) FROM candidates c WHERE c.profile_id = p.id AND c.is_demo = 1) AS demo_count,
                      (SELECT COUNT(*) FROM resumes r WHERE r.profile_id = p.id) AS resume_count,
                      (SELECT COUNT(*) FROM resumes r WHERE r.profile_id = p.id AND r.status = 'ANALYZED') AS processed_count
               FROM screening_profiles p
               WHERE p.archived = 0
                 AND {'1=1' if cutoff is None else 'p.updated_at >= ?'}
               ORDER BY p.updated_at DESC, p.id DESC LIMIT 5"""
        for row in conn.execute(profile_sql, args if cutoff is None else args + [cutoff]):
            recent_profiles.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "type": row["type"],
                    "candidate_count": row["candidate_count"],
                    "demo_count": row["demo_count"],
                    "resume_count": row["resume_count"],
                    "processed_count": row["processed_count"],
                    "updated_at": row["updated_at"],
                }
            )

        activity_sql = """SELECT * FROM audit_events
                   WHERE event_type NOT IN ('source_sync_started', 'source_message_matched')"""
        activity_args: list = []
        if cutoff:
            activity_sql += " AND created_at >= ?"
            activity_args.append(cutoff)
        activity_sql += " ORDER BY id DESC LIMIT 60"
        activity_rows = conn.execute(activity_sql, activity_args).fetchall()
        demo_flags: dict[int, bool] = {}
        candidate_ids = {row["candidate_id"] for row in activity_rows if row["candidate_id"]}
        if candidate_ids:
            placeholders = ",".join("?" for _ in candidate_ids)
            demo_flags = {
                int(flag_row["id"]): bool(flag_row["is_demo"])
                for flag_row in conn.execute(
                    f"SELECT id, is_demo FROM candidates WHERE id IN ({placeholders})",
                    tuple(sorted(int(i) for i in candidate_ids)),
                )
            }
        activity = []
        for row in activity_rows:
            is_demo = demo_flags.get(row["candidate_id"])
            # an event whose candidate we can identify is filtered by scope;
            # events with no candidate link stay visible rather than vanish.
            if scope and is_demo is not None and bool(is_demo) != want_demo:
                continue
            activity.append(
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "message": row["message"],
                    "candidate_id": row["candidate_id"],
                    "profile_id": row["profile_id"],
                    "is_demo": is_demo,
                    "created_at": row["created_at"],
                }
            )
            if len(activity) >= 12:
                break

        demo_workspace = workspace_summary(conn)

        # Recent human decisions — the workflow record, newest first. Read-only
        # here; the decision was made and audited on the candidate page.
        decisions_sql = """SELECT c.id, c.name, c.status, c.human_decision, c.human_decision_note,
                                  c.human_decided_by, c.human_decided_at, c.overall_score, c.is_demo,
                                  p.title AS profile_title
                           FROM candidates c JOIN screening_profiles p ON p.id = c.profile_id
                           WHERE c.human_decision IS NOT NULL"""
        decision_args: list = []
        decision_scope = demo_scope_clause(data_scope, "c.is_demo")
        if decision_scope:
            decisions_sql += f" AND {decision_scope}"
        if cutoff:
            decisions_sql += " AND c.human_decided_at >= ?"
            decision_args.append(cutoff)
        decisions_sql += " ORDER BY c.human_decided_at DESC, c.id DESC LIMIT 8"
        recent_decisions = [
            {
                "id": row["id"],
                "name": row["name"],
                "profile_title": row["profile_title"],
                "decision": row["human_decision"],
                "decision_label": DECISION_LABELS.get(row["human_decision"], row["human_decision"]),
                "reason": row["human_decision_note"],
                "decided_by": row["human_decided_by"],
                "decided_at": row["human_decided_at"],
                "overall_score": row["overall_score"],
                "status": row["status"],
                "is_demo": bool(row["is_demo"]),
            }
            for row in conn.execute(decisions_sql, decision_args)
        ]

        return {
            "filters": {"data_scope": data_scope or "all", "date_range": date_range or "all"},
            "candidates": {
                "total": candidates["total"] or 0,
                "needs_review": candidates["needs_review"] or 0,
                "priority_review": candidates["priority_review"] or 0,
                "interview_recommended": candidates["interview_recommended"] or 0,
                "shortlisted": candidates["shortlisted"] or 0,
                "interview_stage": candidates["interview_stage"] or 0,
                "hired": candidates["hired"] or 0,
                "on_hold": candidates["on_hold"] or 0,
                "closed": candidates["closed"] or 0,
                "duplicates": candidates["duplicates"] or 0,
                "ai_failed": candidates["ai_failed"] or 0,
                "demo": candidates["demo"] or 0,
                "real": candidates["real"] or 0,
            },
            "demo_workspace": {
                "demo_candidates": demo_workspace["demo_candidates"],
                "real_candidates": demo_workspace["real_candidates"],
                "demo_resumes": demo_workspace["demo_resumes"],
                "demo_jobs": demo_workspace["demo_jobs"],
                "demo_decisions": demo_workspace["demo_decisions"],
                "demo_profiles": demo_workspace["demo_profiles"],
            },
            "recommendations": {
                "priority_review": candidates["rec_priority"] or 0,
                "interview_recommendation": candidates["rec_interview"] or 0,
                "manual_review": candidates["rec_manual"] or 0,
                "does_not_meet": candidates["rec_not_met"] or 0,
            },
            "resumes": {
                "total": resumes["total"] or 0,
                "processed": resumes["processed"] or 0,
                "processing": resumes["processing"] or 0,
                "failed": resumes["failed"] or 0,
            },
            "active_jobs": active_jobs,
            "recent_profiles": recent_profiles,
            "recent_decisions": recent_decisions,
            "activity": activity,
        }
    finally:
        conn.close()


@router.get("/reviews/queue")
def review_queue(request: Request, profile_id: int | None = None, limit: int = 100):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        sql = """
            SELECT c.*, r.status AS resume_status, p.title AS profile_title,
                   (SELECT COUNT(*) FROM candidate_projects cp WHERE cp.candidate_id = c.id) AS projects_count
            FROM candidates c
            JOIN resumes r ON r.id = c.resume_id
            JOIN screening_profiles p ON p.id = c.profile_id
            WHERE c.status IN ('REVIEW_REQUIRED','PRIORITY_REVIEW','INTERVIEW_RECOMMENDED')
              AND c.human_decision IS NULL
        """
        args: list = []
        if profile_id:
            sql += " AND c.profile_id = ?"
            args.append(profile_id)
        sql += " ORDER BY c.overall_score DESC NULLS LAST, c.id LIMIT ?"
        args.append(min(500, max(1, limit)))
        items = []
        for row in conn.execute(sql, args):
            data = dict(row)
            data["duplicate_signals"] = jloads(data.get("duplicate_signals"), [])
            items.append(data)
        education_map = primary_education(conn, [item["id"] for item in items])
        for item in items:
            education = education_map.get(item["id"])
            item["education"] = education["course"] if education else None
            item["education_detail"] = education["degree"] if education else None
            item["institution"] = education["institution"] if education else None
        summary = conn.execute(
            """SELECT
                 SUM(CASE WHEN status = 'PRIORITY_REVIEW' THEN 1 ELSE 0 END) AS priority,
                 SUM(CASE WHEN status = 'INTERVIEW_RECOMMENDED' THEN 1 ELSE 0 END) AS interview,
                 SUM(CASE WHEN status = 'REVIEW_REQUIRED' THEN 1 ELSE 0 END) AS manual
               FROM candidates WHERE human_decision IS NULL"""
        ).fetchone()
        return {
            "items": items,
            "summary": {
                "priority": summary["priority"] or 0,
                "interview": summary["interview"] or 0,
                "manual": summary["manual"] or 0,
            },
        }
    finally:
        conn.close()


@router.get("/exports")
def export_history(request: Request, limit: int = 50):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        rows = conn.execute(
            """SELECT id, message, data, profile_id, created_at FROM audit_events
               WHERE event_type = 'export_generated' ORDER BY id DESC LIMIT ?""",
            (min(200, max(1, limit)),),
        ).fetchall()
        return {
            "items": [
                {
                    "id": row["id"],
                    "message": row["message"],
                    "data": jloads(row["data"], {}),
                    "profile_id": row["profile_id"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        }
    finally:
        conn.close()


@router.get("/audit")
def audit_feed(
    request: Request,
    profile_id: int | None = None,
    candidate_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        sql = "SELECT * FROM audit_events WHERE 1=1"
        args: list = []
        if profile_id:
            sql += " AND profile_id = ?"
            args.append(profile_id)
        if candidate_id:
            sql += " AND candidate_id = ?"
            args.append(candidate_id)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args.extend([min(500, max(1, limit)), max(0, offset)])
        items = []
        for row in conn.execute(sql, args):
            data = dict(row)
            data["data"] = jloads(data["data"], {})
            items.append(data)
        return {"items": items}
    finally:
        conn.close()

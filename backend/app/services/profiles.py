"""Screening profile persistence helpers."""

from __future__ import annotations

import sqlite3

from ..audit import record
from ..util import jdumps, jloads, now_iso


def profile_to_dict(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    for field_name in ("required_skills", "preferred_skills", "weights", "thresholds"):
        data[field_name] = jloads(data.get(field_name), [] if "skills" in field_name else {})
    data["ai_enabled"] = bool(data.get("ai_enabled"))
    data["archived"] = bool(data.get("archived"))
    return data


def create_profile(conn: sqlite3.Connection, payload: dict) -> int:
    now = now_iso()
    cursor = conn.execute(
        """INSERT INTO screening_profiles
           (type, title, description, required_skills, preferred_skills, min_academic,
            min_academic_type, education_requirement, experience_requirement,
            projects_requirement, certifications_requirement, communication_note,
            weights, thresholds, ai_enabled, archived, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            payload["type"],
            payload["title"],
            payload.get("description", ""),
            jdumps(payload.get("required_skills", [])),
            jdumps(payload.get("preferred_skills", [])),
            payload.get("min_academic"),
            payload.get("min_academic_type", "cgpa"),
            payload.get("education_requirement", ""),
            payload.get("experience_requirement", "preferred"),
            payload.get("projects_requirement", "preferred"),
            payload.get("certifications_requirement", "not_required"),
            payload.get("communication_note", "Manual review"),
            jdumps(payload["weights"]),
            jdumps(payload["thresholds"]),
            1 if payload.get("ai_enabled", True) else 0,
            now,
            now,
        ),
    )
    profile_id = int(cursor.lastrowid)
    record(
        conn,
        "profile_created",
        entity_type="screening_profile",
        entity_id=profile_id,
        profile_id=profile_id,
        message=f"Screening profile '{payload['title']}' created",
        data={"type": payload["type"]},
    )
    return profile_id


def update_profile(conn: sqlite3.Connection, profile_id: int, payload: dict) -> None:
    conn.execute(
        """UPDATE screening_profiles SET
             type = ?, title = ?, description = ?, required_skills = ?, preferred_skills = ?,
             min_academic = ?, min_academic_type = ?, education_requirement = ?,
             experience_requirement = ?, projects_requirement = ?, certifications_requirement = ?,
             communication_note = ?, weights = ?, thresholds = ?, ai_enabled = ?, updated_at = ?
           WHERE id = ?""",
        (
            payload["type"],
            payload["title"],
            payload.get("description", ""),
            jdumps(payload.get("required_skills", [])),
            jdumps(payload.get("preferred_skills", [])),
            payload.get("min_academic"),
            payload.get("min_academic_type", "cgpa"),
            payload.get("education_requirement", ""),
            payload.get("experience_requirement", "preferred"),
            payload.get("projects_requirement", "preferred"),
            payload.get("certifications_requirement", "not_required"),
            payload.get("communication_note", "Manual review"),
            jdumps(payload["weights"]),
            jdumps(payload["thresholds"]),
            1 if payload.get("ai_enabled", True) else 0,
            now_iso(),
            profile_id,
        ),
    )
    record(
        conn,
        "profile_updated",
        entity_type="screening_profile",
        entity_id=profile_id,
        profile_id=profile_id,
        message=f"Screening profile '{payload['title']}' updated",
    )


def get_profile(conn: sqlite3.Connection, profile_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM screening_profiles WHERE id = ?", (profile_id,)).fetchone()
    return profile_to_dict(row) if row else None


def profile_counts(conn: sqlite3.Connection, profile_id: int) -> dict:
    totals = conn.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'ANALYZED' THEN 1 ELSE 0 END) AS analyzed,
             SUM(CASE WHEN status IN ('UPLOADED','PARSING','PARSED','ANALYZING') THEN 1 ELSE 0 END) AS in_progress,
             SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed
           FROM resumes WHERE profile_id = ?""",
        (profile_id,),
    ).fetchone()
    candidates = conn.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status IN ('REVIEW_REQUIRED','PRIORITY_REVIEW','INTERVIEW_RECOMMENDED') THEN 1 ELSE 0 END) AS needs_review,
             SUM(CASE WHEN status = 'SHORTLISTED' THEN 1 ELSE 0 END) AS shortlisted,
             SUM(CASE WHEN status = 'INTERVIEW_STAGE' THEN 1 ELSE 0 END) AS interview_stage,
             SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed,
             SUM(CASE WHEN status = 'ON_HOLD' THEN 1 ELSE 0 END) AS on_hold,
             SUM(CASE WHEN status = 'PRIORITY_REVIEW' THEN 1 ELSE 0 END) AS priority,
             SUM(CASE WHEN status = 'INTERVIEW_RECOMMENDED' THEN 1 ELSE 0 END) AS interview_rec,
             SUM(CASE WHEN ai_status = 'FAILED' THEN 1 ELSE 0 END) AS ai_failed
           FROM candidates WHERE profile_id = ?""",
        (profile_id,),
    ).fetchone()
    return {
        "resumes": {
            "total": totals["total"] or 0,
            "analyzed": totals["analyzed"] or 0,
            "in_progress": totals["in_progress"] or 0,
            "failed": totals["failed"] or 0,
        },
        "candidates": {
            "total": candidates["total"] or 0,
            "needs_review": candidates["needs_review"] or 0,
            "shortlisted": candidates["shortlisted"] or 0,
            "interview_stage": candidates["interview_stage"] or 0,
            "closed": candidates["closed"] or 0,
            "on_hold": candidates["on_hold"] or 0,
            "priority": candidates["priority"] or 0,
            "interview_recommended": candidates["interview_rec"] or 0,
            "ai_failed": candidates["ai_failed"] or 0,
        },
    }


def list_profiles(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM screening_profiles"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY archived ASC, updated_at DESC, id DESC"
    profiles = [profile_to_dict(row) for row in conn.execute(sql)]
    for profile in profiles:
        profile["counts"] = profile_counts(conn, profile["id"])
    return profiles

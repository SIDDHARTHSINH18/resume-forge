"""Candidate persistence, filtering/sorting and detail aggregation."""

from __future__ import annotations

import sqlite3

from ..audit import record
from ..scoring import ScoringResult
from ..util import jdumps, jloads, now_iso

EXPERIENCE_LABELS = ((70, "Strong"), (45, "Medium"), (0.001, "Low"), (0.0, "None"))

STATUS_LABELS = {
    "REVIEW_REQUIRED": "Review required",
    "PRIORITY_REVIEW": "Priority review",
    "INTERVIEW_RECOMMENDED": "Interview recommended",
    "SHORTLISTED": "Shortlisted",
    "INTERVIEW_STAGE": "In interview stage",
    "ON_HOLD": "On hold",
    "CLOSED": "Closed",
    "HUMAN_REVIEWED": "Human reviewed",
}


def experience_label(value: float | None) -> str:
    if value is None:
        return "None"
    for threshold, label in EXPERIENCE_LABELS:
        if value >= threshold:
            return label
    return "None"


def candidate_to_row(conn_row: sqlite3.Row) -> dict:
    data = dict(conn_row)
    data["links"] = jloads(data.get("links"), [])
    data["duplicate_signals"] = jloads(data.get("duplicate_signals"), [])
    return data


# --------------------------------------------------------------------------
# creation
# --------------------------------------------------------------------------


def create_candidate(
    conn: sqlite3.Connection,
    *,
    profile_id: int,
    resume_id: int,
    facts,
    result: ScoringResult,
    signature: list[int],
    duplicate_of: int | None,
    duplicate_signals: list[dict],
    is_demo: bool,
) -> int:
    now = now_iso()
    best = facts.best_academic
    cursor = conn.execute(
        """INSERT INTO candidates
           (profile_id, resume_id, name, email, phone, location, links, dob_text, status,
            recommendation, overall_score, academic_value, academic_type, ai_status,
            duplicate_of, duplicate_signals, text_signature, is_demo, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)""",
        (
            profile_id,
            resume_id,
            facts.name or "Not found",
            facts.email,
            facts.phone,
            facts.location,
            jdumps(facts.links),
            facts.dob_text,
            status_for_recommendation(result.recommendation),
            result.recommendation,
            result.overall,
            best[0] if best else None,
            best[1] if best else None,
            duplicate_of,
            jdumps(duplicate_signals),
            jdumps(signature),
            1 if is_demo else 0,
            now,
            now,
        ),
    )
    candidate_id = int(cursor.lastrowid)

    conn.executemany(
        """INSERT INTO candidate_skills (candidate_id, skill, normalized, strength, category, sources)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                candidate_id,
                skill["skill"][:80],
                (skill.get("normalized") or skill["skill"]).lower()[:80],
                skill.get("strength", "listed"),
                skill.get("category", "general"),
                jdumps(skill.get("sources", [])),
            )
            for skill in facts.skills
        ],
    )
    conn.executemany(
        """INSERT INTO candidate_education
           (candidate_id, degree, course, institution, graduation_year, academic_value, academic_type, raw_line)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                candidate_id,
                item.get("degree"),
                item.get("course"),
                item.get("institution"),
                item.get("graduation_year"),
                item.get("academic_value"),
                item.get("academic_type"),
                (item.get("raw_line") or "")[:300],
            )
            for item in facts.education
        ],
    )

    experience_scored = result.components[2].details.get("items", [])
    conn.executemany(
        """INSERT INTO candidate_experience
           (candidate_id, title, organization, kind, start_date, end_date, duration_months, description, relevant)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                candidate_id,
                (item.get("title") or "")[:150] or None,
                (item.get("organization") or "")[:150] or None,
                item.get("kind", "internship"),
                item.get("start_date"),
                item.get("end_date"),
                item.get("duration_months"),
                (item.get("description") or "")[:1000],
                1 if item.get("relevant") else 0,
            )
            for item in experience_scored
        ],
    )
    projects_scored = result.components[3].details.get("items", [])
    conn.executemany(
        """INSERT INTO candidate_projects (candidate_id, name, technologies, description, relevant)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (
                candidate_id,
                (item.get("name") or "")[:200] or None,
                jdumps(item.get("technologies") or []),
                (item.get("description") or "")[:1000],
                1 if item.get("relevant") else 0,
            )
            for item in projects_scored
        ],
    )
    conn.executemany(
        "INSERT INTO candidate_certifications (candidate_id, name, issuer, year) VALUES (?, ?, ?, ?)",
        [
            (
                candidate_id,
                (item.get("name") or "")[:200],
                (item.get("issuer") or "")[:120] or None,
                (item.get("year") or "")[:20] or None,
            )
            for item in facts.certifications
        ],
    )
    conn.executemany(
        "INSERT INTO candidate_achievements (candidate_id, text) VALUES (?, ?)",
        [(candidate_id, text[:300]) for text in facts.achievements],
    )

    save_scores(conn, candidate_id, result)
    conn.execute("UPDATE candidates SET updated_at = ? WHERE id = ?", (now_iso(), candidate_id))
    return candidate_id


def save_scores(conn: sqlite3.Connection, candidate_id: int, result: ScoringResult) -> None:
    conn.execute("DELETE FROM candidate_scores WHERE candidate_id = ?", (candidate_id,))
    conn.executemany(
        """INSERT INTO candidate_scores
           (candidate_id, component, score, weight, points, max_points, evidence, details)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                candidate_id,
                component.component,
                component.score,
                component.weight,
                component.points,
                component.max_points,
                component.evidence,
                jdumps(component.details),
            )
            for component in result.components
        ],
    )


def status_for_recommendation(recommendation: str) -> str:
    if recommendation == "PRIORITY_REVIEW":
        return "PRIORITY_REVIEW"
    if recommendation == "INTERVIEW_RECOMMENDATION":
        return "INTERVIEW_RECOMMENDED"
    return "REVIEW_REQUIRED"


# --------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------

SORT_COLUMNS = {
    "overall": "c.overall_score",
    "academic": "c.academic_value",
    "skills": "skills_score",
    "experience": "experience_score",
    "projects": "projects_score",
    "newest": "c.created_at",
    "name": "LOWER(c.name)",
}

EXPERIENCE_FILTERS = {
    "strong": "experience_score >= 70",
    "medium": "experience_score >= 45 AND experience_score < 70",
    "low": "experience_score > 0 AND experience_score < 45",
    "none": "experience_score = 0",
}


def list_candidates(conn: sqlite3.Connection, params: dict) -> dict:
    where: list[str] = []
    args: list = []

    if params.get("profile_id"):
        where.append("c.profile_id = ?")
        args.append(int(params["profile_id"]))
    if params.get("search"):
        term = f"%{str(params['search']).strip().lower()}%"
        where.append(
            """(LOWER(c.name) LIKE ? OR LOWER(COALESCE(c.email,'')) LIKE ?
                OR EXISTS (SELECT 1 FROM candidate_skills s
                           WHERE s.candidate_id = c.id AND LOWER(s.skill) LIKE ?)
                OR EXISTS (SELECT 1 FROM candidate_education e
                           WHERE e.candidate_id = c.id
                             AND (LOWER(COALESCE(e.degree,'')) LIKE ? OR LOWER(COALESCE(e.course,'')) LIKE ?
                                  OR LOWER(COALESCE(e.institution,'')) LIKE ?)))"""
        )
        args.extend([term] * 6)
    if params.get("degree"):
        where.append(
            """EXISTS (SELECT 1 FROM candidate_education e
                       WHERE e.candidate_id = c.id AND LOWER(COALESCE(e.course,'')) = ?)"""
        )
        args.append(str(params["degree"]).strip().lower())
    if params.get("skill"):
        where.append(
            """EXISTS (SELECT 1 FROM candidate_skills s
                       WHERE s.candidate_id = c.id AND s.normalized = ?)"""
        )
        args.append(str(params["skill"]).strip().lower())
    if params.get("recommendation"):
        where.append("c.recommendation = ?")
        args.append(str(params["recommendation"]))
    if params.get("status"):
        where.append("c.status = ?")
        args.append(str(params["status"]))
    if params.get("resume_status"):
        where.append("r.status = ?")
        args.append(str(params["resume_status"]))
    academic_type = str(params.get("academic_type") or "cgpa").strip().lower()
    if academic_type not in ("cgpa", "percentage"):
        academic_type = "cgpa"
    # Candidate values are stored in their own unit; compare on one scale.
    academic_pct = (
        "CASE WHEN LOWER(COALESCE(c.academic_type, 'cgpa')) = 'percentage' "
        "THEN c.academic_value ELSE c.academic_value * 9.5 END"
    )
    academic_filter_scale = 1.0 if academic_type == "percentage" else 9.5
    if params.get("min_academic") not in (None, ""):
        where.append(f"c.academic_value IS NOT NULL AND {academic_pct} >= ?")
        args.append(float(params["min_academic"]) * academic_filter_scale)
    if params.get("max_academic") not in (None, ""):
        where.append(f"c.academic_value IS NOT NULL AND {academic_pct} <= ?")
        args.append(float(params["max_academic"]) * academic_filter_scale)
    if params.get("experience"):
        clause = EXPERIENCE_FILTERS.get(str(params["experience"]))
        if clause:
            where.append(clause)
    if params.get("duplicates_only"):
        where.append("c.duplicate_of IS NOT NULL")

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""

    base_from = f"""
        FROM candidates c
        JOIN resumes r ON r.id = c.resume_id
        JOIN screening_profiles p ON p.id = c.profile_id
        LEFT JOIN (SELECT candidate_id, score FROM candidate_scores WHERE component='skills') sk
               ON sk.candidate_id = c.id
        LEFT JOIN (SELECT candidate_id, score FROM candidate_scores WHERE component='experience') ex
               ON ex.candidate_id = c.id
        LEFT JOIN (SELECT candidate_id, score FROM candidate_scores WHERE component='projects') pr
               ON pr.candidate_id = c.id
        {where_sql}
    """
    select_sql = f"""
        SELECT c.*, r.status AS resume_status, r.filename AS resume_filename, p.title AS profile_title,
               p.type AS profile_type,
               COALESCE(sk.score, 0) AS skills_score,
               COALESCE(ex.score, 0) AS experience_score,
               COALESCE(pr.score, 0) AS projects_score,
               (SELECT COUNT(*) FROM candidate_projects cp WHERE cp.candidate_id = c.id) AS projects_count
        {base_from}
        ORDER BY
    """
    # count first
    total = conn.execute(f"SELECT COUNT(*) AS n {base_from}", args).fetchone()["n"]

    sort_key = str(params.get("sort") or "overall")
    sort_column = SORT_COLUMNS.get(sort_key, "c.overall_score")
    order = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"
    if sort_key in ("name",):
        order = "ASC" if str(params.get("order", "asc")).lower() != "desc" else "DESC"
    secondary = ", c.id DESC"

    page = max(1, int(params.get("page") or 1))
    page_size = min(200, max(1, int(params.get("page_size") or 25)))
    offset = (page - 1) * page_size

    rows = conn.execute(
        select_sql + f" {sort_column} {order}, c.overall_score DESC{secondary} LIMIT ? OFFSET ?",
        args + [page_size, offset],
    ).fetchall()

    primary_edu = primary_education(conn, [row["id"] for row in rows])
    items = []
    for row in rows:
        data = candidate_to_row(row)
        education = primary_edu.get(row["id"])
        items.append(
            {
                "id": data["id"],
                "profile_id": data["profile_id"],
                "profile_title": data["profile_title"],
                "profile_type": data["profile_type"],
                "name": data["name"],
                "email": data["email"],
                "education": education["course"] if education else None,
                "education_detail": education["degree"] if education else None,
                "institution": education["institution"] if education else None,
                "academic_value": data["academic_value"],
                "academic_type": data["academic_type"],
                "skills_match": round(float(data["skills_score"]), 1),
                "experience_label": experience_label(data["experience_score"]),
                "experience_score": round(float(data["experience_score"]), 1),
                "projects_score": round(float(data["projects_score"]), 1),
                "projects_count": data["projects_count"],
                "overall_score": data["overall_score"],
                "recommendation": data["recommendation"],
                "status": data["status"],
                "status_label": STATUS_LABELS.get(data["status"], data["status"]),
                "ai_status": data["ai_status"],
                "resume_status": data["resume_status"],
                "duplicate_of": data["duplicate_of"],
                "duplicate_signals": data["duplicate_signals"],
                "is_demo": bool(data["is_demo"]),
                "human_decision": data["human_decision"],
                "created_at": data["created_at"],
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def primary_education(conn: sqlite3.Connection, candidate_ids: list[int]) -> dict[int, dict]:
    if not candidate_ids:
        return {}
    placeholders = ",".join("?" for _ in candidate_ids)
    rows = conn.execute(
        f"SELECT * FROM candidate_education WHERE candidate_id IN ({placeholders}) ORDER BY id",
        candidate_ids,
    ).fetchall()
    out: dict[int, dict] = {}
    for row in rows:
        current = out.get(row["candidate_id"])
        data = dict(row)
        if current is None:
            out[row["candidate_id"]] = data
        elif current.get("academic_value") is None and data.get("academic_value") is not None:
            out[row["candidate_id"]] = data
    return out


def filter_options(conn: sqlite3.Connection, profile_id: int | None) -> dict:
    profile_clause = " WHERE profile_id = ?" if profile_id else ""
    profile_args = [int(profile_id)] if profile_id else []

    def distinct(sql: str) -> list[str]:
        return [row[0] for row in conn.execute(sql, profile_args) if row[0]]

    degrees = distinct(
        f"""SELECT DISTINCT e.course FROM candidate_education e
            JOIN candidates c ON c.id = e.candidate_id
            {'WHERE c.profile_id = ?' if profile_id else ''}
            AND e.course IS NOT NULL ORDER BY e.course"""
    )
    skills = distinct(
        f"""SELECT s.skill FROM candidate_skills s
            JOIN candidates c ON c.id = s.candidate_id
            {'WHERE c.profile_id = ?' if profile_id else ''}
            GROUP BY LOWER(s.skill) ORDER BY COUNT(*) DESC LIMIT 60"""
    )
    return {"degrees": degrees, "skills": skills}


# --------------------------------------------------------------------------
# detail
# --------------------------------------------------------------------------


def candidate_detail(conn: sqlite3.Connection, candidate_id: int) -> dict | None:
    row = conn.execute(
        """SELECT c.*, r.status AS resume_status, r.filename AS resume_filename,
                  r.error_reason AS resume_error, r.size_bytes AS resume_size,
                  p.title AS profile_title, p.type AS profile_type,
                  p.required_skills AS profile_required_skills,
                  p.preferred_skills AS profile_preferred_skills,
                  p.communication_note AS profile_communication_note,
                  p.experience_requirement AS profile_experience_requirement,
                  p.projects_requirement AS profile_projects_requirement,
                  p.certifications_requirement AS profile_certifications_requirement,
                  p.min_academic AS profile_min_academic, p.min_academic_type AS profile_min_academic_type,
                  p.education_requirement AS profile_education_requirement,
                  p.ai_enabled AS profile_ai_enabled,
                  p.thresholds AS profile_thresholds, p.weights AS profile_weights
           FROM candidates c
           JOIN resumes r ON r.id = c.resume_id
           JOIN screening_profiles p ON p.id = c.profile_id
           WHERE c.id = ?""",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    data = candidate_to_row(row)
    data["ai_analysis"] = jloads(data.get("ai_analysis"), None)
    profile_fields = {
        "required_skills", "preferred_skills", "communication_note", "experience_requirement",
        "projects_requirement", "certifications_requirement", "min_academic", "min_academic_type",
        "education_requirement", "ai_enabled",
    }
    profile = {"id": data["profile_id"], "title": data["profile_title"], "type": data["profile_type"]}
    for field_name in profile_fields:
        value = data.get(f"profile_{field_name}")
        if field_name in ("required_skills", "preferred_skills"):
            value = jloads(value, [])
        elif field_name == "ai_enabled":
            value = bool(value)
        profile[field_name] = value
    profile["thresholds"] = jloads(data.get("profile_thresholds"), {})
    profile["weights"] = jloads(data.get("profile_weights"), {})
    data["profile"] = profile
    for field_name in profile_fields:
        data.pop(f"profile_{field_name}", None)
    data.pop("profile_thresholds", None)
    data.pop("profile_weights", None)

    data["skills"] = [
        {**dict(skill), "sources": jloads(skill["sources"], [])}
        for skill in conn.execute(
            "SELECT * FROM candidate_skills WHERE candidate_id = ? ORDER BY category, skill", (candidate_id,)
        )
    ]
    data["education"] = [dict(item) for item in conn.execute(
        "SELECT * FROM candidate_education WHERE candidate_id = ? ORDER BY id", (candidate_id,)
    )]
    data["experience"] = [dict(item) for item in conn.execute(
        "SELECT * FROM candidate_experience WHERE candidate_id = ? ORDER BY id", (candidate_id,)
    )]
    data["projects"] = [
        {**dict(item), "technologies": jloads(item["technologies"], [])}
        for item in conn.execute(
            "SELECT * FROM candidate_projects WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        )
    ]
    data["certifications"] = [dict(item) for item in conn.execute(
        "SELECT * FROM candidate_certifications WHERE candidate_id = ? ORDER BY id", (candidate_id,)
    )]
    data["achievements"] = [dict(item) for item in conn.execute(
        "SELECT * FROM candidate_achievements WHERE candidate_id = ? ORDER BY id", (candidate_id,)
    )]
    data["scores"] = [
        {**dict(score), "details": jloads(score["details"], {})}
        for score in conn.execute(
            "SELECT * FROM candidate_scores WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        )
    ]
    data["reviews"] = [dict(item) for item in conn.execute(
        "SELECT * FROM candidate_reviews WHERE candidate_id = ? ORDER BY id DESC", (candidate_id,)
    )]
    data["audit"] = [dict(item) for item in conn.execute(
        "SELECT * FROM audit_events WHERE candidate_id = ? ORDER BY id DESC LIMIT 100", (candidate_id,)
    )]
    if data.get("duplicate_of"):
        other = conn.execute("SELECT id, name FROM candidates WHERE id = ?", (data["duplicate_of"],)).fetchone()
        data["duplicate_of_name"] = other["name"] if other else None
    related = conn.execute(
        "SELECT id, name, duplicate_signals FROM candidates WHERE duplicate_of = ?", (candidate_id,)
    ).fetchall()
    data["duplicated_by"] = [
        {"id": row["id"], "name": row["name"], "signals": jloads(row["duplicate_signals"], [])}
        for row in related
    ]
    return data


def add_note(conn: sqlite3.Connection, candidate_id: int, author: str, note: str) -> None:
    conn.execute(
        "INSERT INTO candidate_reviews (candidate_id, author, note, kind, created_at) VALUES (?, ?, ?, 'note', ?)",
        (candidate_id, author, note, now_iso()),
    )
    record(
        conn,
        "review_note_added",
        entity_type="candidate",
        entity_id=candidate_id,
        candidate_id=candidate_id,
        message=f"Reviewer note added by {author}",
    )


DECISION_TO_STATUS = {
    "move_to_interview": "INTERVIEW_STAGE",
    "shortlist": "SHORTLISTED",
    "hold": "ON_HOLD",
    "close": "CLOSED",
}

DECISION_LABELS = {
    "move_to_interview": "Moved to interview",
    "shortlist": "Shortlisted",
    "hold": "Put on hold",
    "close": "Closed",
}


def apply_decision(conn: sqlite3.Connection, candidate_id: int, decision: str, reason: str, author: str) -> dict | None:
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        return None
    previous_status = row["status"]
    previous_decision = row["human_decision"]
    new_status = DECISION_TO_STATUS[decision]
    now = now_iso()
    conn.execute(
        """UPDATE candidates SET status = ?, human_decision = ?, human_decision_note = ?,
                                 human_decided_by = ?, human_decided_at = ?, updated_at = ?
           WHERE id = ?""",
        (new_status, decision, reason, author, now, now, candidate_id),
    )
    conn.execute(
        """INSERT INTO candidate_reviews (candidate_id, author, note, kind, decision, created_at)
           VALUES (?, ?, ?, 'decision', ?, ?)""",
        (candidate_id, author, reason, decision, now),
    )
    record(
        conn,
        "human_decision_made",
        entity_type="candidate",
        entity_id=candidate_id,
        candidate_id=candidate_id,
        profile_id=row["profile_id"],
        message=f"Human decision: {DECISION_LABELS[decision]}",
        data={
            "decision": decision,
            "previous_status": previous_status,
            "previous_decision": previous_decision,
            "reason": reason[:500],
        },
    )
    if previous_status != new_status:
        record(
            conn,
            "candidate_status_changed",
            entity_type="candidate",
            entity_id=candidate_id,
            candidate_id=candidate_id,
            profile_id=row["profile_id"],
            message=f"Status changed: {previous_status} -> {new_status}",
        )
    return candidate_detail(conn, candidate_id)

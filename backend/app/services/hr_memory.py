"""HR decision memory and explainable recommendation support.

Two hard rules govern this module:

* It *describes* what reviewers already did; it never decides. Nothing here can
  change a score, a recommendation or a candidate status. ``app.scoring`` does
  not import this module, and the required-skill guardrail is applied before
  any HR pattern is even computed, so remembered behaviour can never outrank a
  stated job requirement.
* Every pattern states its evidence: the skills it came from, how many
  decisions support it, the total sample size and a confidence label. Below
  ``MIN_PATTERN_SUPPORT`` decisions the module refuses to generalise and says
  so instead of inventing a trend.
"""

from __future__ import annotations

import sqlite3

from ..util import jloads, now_iso
from ..scoring import GRADE_STRONG, RECOMMENDATION_LABELS

MIN_PATTERN_SUPPORT = 3

POSITIVE_DECISIONS = ("shortlist", "move_to_interview", "hire")
NEGATIVE_DECISIONS = ("close",)
NEUTRAL_DECISIONS = ("hold",)

DECISION_GROUPS = {
    "advanced": POSITIVE_DECISIONS,
    "rejected": NEGATIVE_DECISIONS,
    "on_hold": NEUTRAL_DECISIONS,
}


# --------------------------------------------------------------------------
# writing memory
# --------------------------------------------------------------------------


def _skill_gap(conn: sqlite3.Connection, candidate_id: int) -> dict:
    """Read the stored skills component so memory matches the scored evidence."""
    row = conn.execute(
        "SELECT details FROM candidate_scores WHERE candidate_id = ? AND component = 'skills'",
        (candidate_id,),
    ).fetchone()
    details = jloads(row["details"], {}) if row else {}
    required = details.get("required") or []
    preferred = details.get("preferred") or []
    return {
        "matched_required": [item["skill"] for item in required if item.get("found")],
        "missing_required": [item["skill"] for item in required if not item.get("found")],
        "strong_required": [
            item["skill"] for item in required if (item.get("grade") or 0) >= GRADE_STRONG
        ],
        "matched_preferred": [item["skill"] for item in preferred if item.get("found")],
    }


def _experience_level(conn: sqlite3.Connection, candidate_id: int) -> str:
    rows = conn.execute(
        "SELECT duration_months, relevant FROM candidate_experience WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchall()
    if not rows:
        return "none"
    longest = max(int(row["duration_months"] or 0) for row in rows)
    relevant = any(row["relevant"] for row in rows)
    if relevant and longest >= 12:
        return "experienced"
    if relevant:
        return "internship"
    return "unrelated_experience"


def _source_kind(conn: sqlite3.Connection, resume_id: int) -> str:
    row = conn.execute(
        """SELECT rs.kind FROM source_items si
           JOIN resume_sources rs ON rs.id = si.source_id
           WHERE si.resume_id = ? ORDER BY si.id DESC LIMIT 1""",
        (resume_id,),
    ).fetchone()
    return row["kind"] if row else "manual"


def record_decision(
    conn: sqlite3.Connection,
    candidate: sqlite3.Row,
    *,
    decision: str,
    reason: str,
    author: str,
    decided_at: str | None = None,
) -> int:
    """Store one reviewer decision together with the evidence behind it.

    Called from ``apply_decision``; the row is a snapshot of the candidate at
    decision time, which is what makes later insight computation honest (the
    reviewer's reasoning is not re-derived from a score that may have changed).
    """
    gap = _skill_gap(conn, int(candidate["id"]))
    stamp = decided_at or now_iso()
    cursor = conn.execute(
        """INSERT INTO decision_memory
           (candidate_id, profile_id, decision, previous_decision, reason,
            matched_required, missing_required, matched_preferred, experience_level,
            source_kind, overall_score, recommendation, decided_by, decided_at, is_demo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            int(candidate["id"]),
            int(candidate["profile_id"]),
            decision,
            candidate["human_decision"],
            (reason or "")[:1000],
            _dumps(gap["matched_required"]),
            _dumps(gap["missing_required"]),
            _dumps(gap["matched_preferred"]),
            _experience_level(conn, int(candidate["id"])),
            _source_kind(conn, int(candidate["resume_id"])),
            candidate["overall_score"],
            candidate["recommendation"],
            author,
            stamp,
            1 if candidate["is_demo"] else 0,
            stamp,
        ),
    )
    return int(cursor.lastrowid)


def _dumps(value: list[str]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def decision_history(conn: sqlite3.Connection, candidate_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT m.*, p.title AS profile_title FROM decision_memory m
           JOIN screening_profiles p ON p.id = m.profile_id
           WHERE m.candidate_id = ? ORDER BY m.id DESC""",
        (candidate_id,),
    ).fetchall()
    out = []
    for row in rows:
        data = dict(row)
        for key in ("matched_required", "missing_required", "matched_preferred"):
            data[key] = jloads(data.get(key), [])
        out.append(data)
    return out


# --------------------------------------------------------------------------
# insights (aggregate, advisory)
# --------------------------------------------------------------------------


def _counts(rows: list[sqlite3.Row], key: str) -> dict[str, int]:
    tally: dict[str, int] = {}
    for row in rows:
        for skill in jloads(row[key], []):
            tally[skill] = tally.get(skill, 0) + 1
    return tally


def _confidence(support: int, total: int) -> str:
    if total == 0:
        return "low"
    ratio = support / total
    if support >= 8 and ratio >= 0.6:
        return "high"
    if support >= 5:
        return "medium"
    return "low"


def _top(tally: dict[str, int], limit: int = 3) -> list[str]:
    return [skill for skill, _ in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def profile_insights(conn: sqlite3.Connection, profile_id: int) -> dict:
    """Explainable "HR preference insights" for one screening profile."""
    rows = conn.execute(
        "SELECT * FROM decision_memory WHERE profile_id = ? ORDER BY id DESC",
        (profile_id,),
    ).fetchall()
    profile = conn.execute(
        "SELECT title, required_skills, preferred_skills FROM screening_profiles WHERE id = ?",
        (profile_id,),
    ).fetchone()
    required = jloads(profile["required_skills"], []) if profile else []

    advanced = [row for row in rows if row["decision"] in POSITIVE_DECISIONS]
    rejected = [row for row in rows if row["decision"] in NEGATIVE_DECISIONS]
    on_hold = [row for row in rows if row["decision"] in NEUTRAL_DECISIONS]
    demo_rows = [row for row in rows if row["is_demo"]]

    patterns: list[dict] = []
    if len(advanced) >= MIN_PATTERN_SUPPORT:
        shared = _top(_counts(advanced, "matched_required"))
        if shared:
            support = sum(
                1 for row in advanced if set(shared).issubset(set(jloads(row["matched_required"], [])))
            )
            patterns.append(
                {
                    "kind": "advanced_pattern",
                    "text": (
                        f"HR advanced {len(advanced)} candidate(s) for this role; "
                        f"{', '.join(shared)} appeared in {support} of them."
                    ),
                    "skills": shared,
                    "support": support,
                    "sample_size": len(advanced),
                    "confidence": _confidence(support, len(advanced)),
                }
            )
    if len(rejected) >= MIN_PATTERN_SUPPORT:
        gaps = _top(_counts(rejected, "missing_required"))
        if gaps:
            support = sum(
                1 for row in rejected if set(gaps).issubset(set(jloads(row["missing_required"], [])))
            )
            patterns.append(
                {
                    "kind": "rejection_pattern",
                    "text": (
                        f"{len(rejected)} candidate(s) were closed for this role; "
                        f"{', '.join(gaps)} was missing in {support} of them."
                    ),
                    "skills": gaps,
                    "support": support,
                    "sample_size": len(rejected),
                    "confidence": _confidence(support, len(rejected)),
                }
            )

    levels = _count_levels(advanced)
    if levels and len(advanced) >= MIN_PATTERN_SUPPORT:
        best_level, best_count = max(levels.items(), key=lambda kv: (kv[1], kv[0]))
        patterns.append(
            {
                "kind": "experience_pattern",
                "text": (
                    f"{best_count} of {len(advanced)} advanced candidates were at "
                    f"'{best_level.replace('_', ' ')}' level."
                ),
                "skills": [],
                "support": best_count,
                "sample_size": len(advanced),
                "confidence": _confidence(best_count, len(advanced)),
            }
        )

    requirement_note = (
        f"For this job, meeting part of the requirement list is not enough: "
        f"{', '.join(required)} are required skills, and a candidate missing any of them is "
        "capped at manual review regardless of HR patterns."
        if required
        else "This profile has no required skills configured, so no requirement gate applies."
    )

    return {
        "profile_id": profile_id,
        "profile_title": profile["title"] if profile else None,
        "decisions": {
            "total": len(rows),
            "advanced": len(advanced),
            "rejected": len(rejected),
            "on_hold": len(on_hold),
            "demo": len(demo_rows),
        },
        "required_skills": required,
        "patterns": patterns,
        "requirement_note": requirement_note,
        "enough_data": len(rows) >= MIN_PATTERN_SUPPORT,
        "note": (
            ""
            if len(rows) >= MIN_PATTERN_SUPPORT
            else (
                f"Only {len(rows)} decision(s) recorded so far — MeritOS does not infer "
                "preferences from such a small sample."
            )
        ),
        "advisory_only": True,
    }


def _count_levels(rows: list[sqlite3.Row]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row["experience_level"]] = out.get(row["experience_level"], 0) + 1
    return out


# --------------------------------------------------------------------------
# per-candidate explanation
# --------------------------------------------------------------------------


def hr_pattern(
    conn: sqlite3.Connection,
    profile_id: int,
    matched_required: list[str],
    *,
    exclude_candidate_id: int | None = None,
) -> dict | None:
    """How closely this candidate resembles previously advanced candidates."""
    sql = (
        "SELECT matched_required FROM decision_memory "
        "WHERE profile_id = ? AND decision IN ('shortlist','move_to_interview','hire')"
    )
    params: list = [profile_id]
    if exclude_candidate_id is not None:
        sql += " AND candidate_id <> ?"
        params.append(exclude_candidate_id)
    rows = conn.execute(sql, params).fetchall()
    if len(rows) < MIN_PATTERN_SUPPORT:
        return None

    current = {skill.lower() for skill in matched_required}
    if not current:
        return None
    scores = []
    for row in rows:
        other = {str(skill).lower() for skill in jloads(row["matched_required"], [])}
        if not other:
            continue
        union = current | other
        scores.append(len(current & other) / len(union))
    if not scores:
        return None
    similarity = round(sum(scores) / len(scores), 2)
    close = sum(1 for value in scores if value >= 0.5)
    return {
        "similarity": similarity,
        "based_on": len(scores),
        "similar_candidates": close,
        "text": (
            f"Matches the required-skill profile of {close} of {len(scores)} previously "
            "advanced candidates for this role."
        ),
        "confidence": "medium" if similarity >= 0.5 and close >= 3 else "low",
        "advisory_only": True,
    }


def explain_candidate(conn: sqlite3.Connection, detail: dict) -> dict:
    """Build the "Why MeritOS recommends this candidate" payload.

    Deterministic: composed from the stored score components, the profile's own
    requirement list, and (advisory only) HR decision memory. No AI call, no
    invented evidence, and the requirement gate is stated before the pattern.
    """
    candidate_id = int(detail["id"])
    profile = detail.get("profile") or {}
    skills_component = next(
        (row for row in detail.get("scores", []) if row["component"] == "skills"), None
    )
    details = (skills_component or {}).get("details") or {}
    required_items = details.get("required") or []
    preferred_items = details.get("preferred") or []

    matched_required = [item for item in required_items if item.get("found")]
    missing = list(details.get("missing_required") or [])
    weak = list(details.get("weak_required") or [])
    matched_preferred = [item for item in preferred_items if item.get("found")]

    codes = [code for code in str(detail.get("guardrail") or "").split(",") if code]
    warnings: list[str] = []
    if missing:
        warnings.append(
            "Do not auto-shortlist: "
            + ", ".join(missing)
            + (" is" if len(missing) == 1 else " are")
            + " required by this role and not evidenced in the resume."
        )
    if weak:
        # "weak" covers both "listed but unused" and "used but not listed" — the
        # shared truth is that neither reached strong evidence, so say just that.
        warnings.append(
            f"{', '.join(weak)} {'is' if len(weak) == 1 else 'are'} required but only weakly "
            "evidenced — not strongly supported by experience or projects."
        )
    if "experience_required_missing" in codes:
        warnings.append("Experience is required by this profile but none relevant was found.")

    pattern = hr_pattern(
        conn,
        int(detail["profile_id"]),
        [item["skill"] for item in matched_required],
        exclude_candidate_id=candidate_id,
    )

    overall = detail.get("overall_score")
    interview_threshold = (profile.get("thresholds") or {}).get("interview_recommendation")
    if codes:
        confidence = "low"
    elif overall is None:
        confidence = "low"
    elif interview_threshold and float(overall) >= float(interview_threshold) + 10:
        confidence = "high"
    else:
        confidence = "medium"

    recommendation = detail.get("recommendation") or ""
    label = RECOMMENDATION_LABELS.get(recommendation, recommendation)
    if matched_required and not missing:
        headline = (
            f"{label} because this candidate evidences every required skill "
            f"({', '.join(item['skill'] for item in matched_required)})."
        )
    elif matched_required and missing:
        headline = (
            f"Strong on {', '.join(item['skill'] for item in matched_required)}, but "
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} required — "
            f"so this stays {label.lower()}."
        )
    else:
        headline = f"{label}: no required skill from this profile was found in the resume."

    return {
        "headline": headline,
        "matched_required": matched_required,
        "missing_required": missing,
        "weak_required": weak,
        "matched_preferred": matched_preferred,
        "guardrail": {
            "codes": codes,
            "detail": detail.get("guardrail_detail") or "",
            "capped": bool(codes),
        },
        "hr_pattern": pattern,
        "warnings": warnings,
        "confidence": confidence,
        "score": overall,
        "recommendation": recommendation,
        "advisory_only": (
            "MeritOS explains; a reviewer decides. Nothing here sends an email, "
            "changes a status or rejects a candidate."
        ),
    }

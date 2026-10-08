"""Demo workspace management: show exactly what is demo, then clear or reset it.

Every statement here is scoped to rows that are provably synthetic:

* candidates flagged ``is_demo = 1`` — the flag comes from the "DEMO DATA"
  banner inside the parsed resume text, never from a profile name alone;
* resumes whose candidate carries that flag, plus demo resumes that never
  produced a candidate (the deliberately broken demo PDF) — identified by living
  in a ``DEMO —`` profile *and* having a ``demo_`` filename or the banner text;
* processing jobs whose every resume is demo;
* screening profiles whose title starts with ``DEMO —``.

Rows with ``is_demo = 0`` are never deleted or archived. A real candidate inside
a demo profile keeps that profile alive and is reported back instead. Nothing in
this module runs on a schedule or as a side effect of viewing a page.

Archiving vs deleting: ``screening_profiles`` has an ``archived`` column, so
demo profiles can be archived (``mode='archive'``). ``candidates`` and
``resumes`` have no archive column, so demo rows in those tables are always hard
deleted — archiving only the profile would leave the demo candidates visible in
the candidate list, which is not a clear.
"""

from __future__ import annotations

from pathlib import Path

from ..audit import record
from ..util import now_iso, safe_join_under

DEMO_PROFILE_PREFIX = "DEMO —"
DEMO_PROFILE_TITLE_BACKEND = f"{DEMO_PROFILE_PREFIX} Backend Engineer (Python, SQL, FastAPI)"
DEMO_PROFILE_TITLE_FRONTEND = f"{DEMO_PROFILE_PREFIX} Frontend Engineer (React, TypeScript)"
DEMO_JOB_LABEL = "DEMO workspace seed — do not treat as real candidates"
DEMO_BANNER = "DEMO DATA"

_DEMO_PROFILES_SQL = "SELECT id FROM screening_profiles WHERE title LIKE ?"
_DEMO_PROFILES_LIKE = f"{DEMO_PROFILE_PREFIX}%"

# A resume is demo when its candidate carries the flag, or when it was ingested
# into a DEMO profile and is itself labelled (filename prefix / banner text)
# while having produced no real candidate.
_DEMO_RESUMES_SELECT = """
    SELECT dr.id FROM resumes dr
    WHERE EXISTS (SELECT 1 FROM candidates dc WHERE dc.resume_id = dr.id AND dc.is_demo = 1)
       OR (
            dr.profile_id IN (SELECT dp.id FROM screening_profiles dp WHERE dp.title LIKE 'DEMO —%')
            AND (SUBSTR(dr.filename, 1, 5) = 'demo_'
                 OR INSTR(UPPER(SUBSTR(COALESCE(dr.extracted_text, ''), 1, 400)), 'DEMO DATA') > 0)
            AND NOT EXISTS (SELECT 1 FROM candidates dc2 WHERE dc2.resume_id = dr.id AND dc2.is_demo = 0)
          )
"""

# A job is demo when every resume it touched is demo (job_resumes cascades with
# the resume rows, so this must be computed before any delete runs).
_DEMO_JOBS_SELECT = """
    SELECT j.id FROM processing_jobs j
    WHERE EXISTS (SELECT 1 FROM job_resumes jr WHERE jr.job_id = j.id)
      AND NOT EXISTS (
            SELECT 1 FROM job_resumes jr
            JOIN resumes r ON r.id = jr.resume_id
            WHERE jr.job_id = j.id AND r.id NOT IN ({resumes})
          )
"""


def _count(conn, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0] or 0)


def _seed_temp_tables(conn) -> None:
    """Materialise the three demo id sets for this connection/transaction."""
    conn.execute("DROP TABLE IF EXISTS _demo_candidates")
    conn.execute("DROP TABLE IF EXISTS _demo_resumes")
    conn.execute("DROP TABLE IF EXISTS _demo_jobs")
    conn.execute("DROP TABLE IF EXISTS _demo_profiles")
    conn.execute("CREATE TEMP TABLE _demo_candidates AS SELECT id FROM candidates WHERE is_demo = 1")
    conn.execute(f"CREATE TEMP TABLE _demo_resumes AS {_DEMO_RESUMES_SELECT}")
    conn.execute(
        "CREATE TEMP TABLE _demo_profiles AS SELECT id, title FROM screening_profiles WHERE title LIKE ?",
        (DEMO_PROFILE_PREFIX + "%",),
    )
    conn.execute(
        "CREATE TEMP TABLE _demo_jobs AS "
        + _DEMO_JOBS_SELECT.replace("{resumes}", "SELECT id FROM _demo_resumes")
    )


def _drop_temp_tables(conn) -> None:
    for name in ("_demo_candidates", "_demo_resumes", "_demo_jobs", "_demo_profiles"):
        conn.execute(f"DROP TABLE IF EXISTS {name}")


_DEMO_AUDIT_WHERE = """
    a.event_type LIKE 'demo%'
       OR a.candidate_id IN (SELECT id FROM _demo_candidates)
       OR (a.entity_type = 'candidate' AND a.entity_id IN (SELECT id FROM _demo_candidates))
       OR (a.entity_type = 'resume' AND a.entity_id IN (SELECT id FROM _demo_resumes))
       OR (a.entity_type = 'processing_job' AND a.entity_id IN (SELECT id FROM _demo_jobs))
"""


def workspace_summary(conn) -> dict:
    """Live, honest view of how much of this database is demo data."""
    return {
        "demo_candidates": _count(conn, "SELECT COUNT(*) FROM candidates WHERE is_demo = 1"),
        "real_candidates": _count(conn, "SELECT COUNT(*) FROM candidates WHERE is_demo = 0"),
        "demo_resumes": _count(conn, f"SELECT COUNT(*) FROM ({_DEMO_RESUMES_SELECT})"),
        "demo_jobs": _count(
            conn,
            "SELECT COUNT(*) FROM ("
            + _DEMO_JOBS_SELECT.replace("{resumes}", _DEMO_RESUMES_SELECT)
            + ")",
        ),
        "demo_profiles": [
            {
                "id": row["id"],
                "title": row["title"],
                "archived": bool(row["archived"]),
            }
            for row in conn.execute(
                "SELECT id, title, archived FROM screening_profiles WHERE title LIKE ? ORDER BY id",
                (DEMO_PROFILE_PREFIX + "%",),
            )
        ],
        "demo_decisions": _count(
            conn,
            "SELECT COUNT(*) FROM candidates WHERE is_demo = 1 AND human_decision IS NOT NULL",
        ),
    }


def has_demo_data(conn) -> bool:
    """True when a live demo workspace exists.

    Archived demo profiles left behind by "clear demo workspace (archive)" are
    empty shells, so they must not block a re-seed: seeding re-activates them
    instead of creating a second pair with the same titles.
    """
    summary = workspace_summary(conn)
    return bool(
        summary["demo_candidates"]
        or summary["demo_resumes"]
        or summary["demo_jobs"]
        or any(not profile["archived"] for profile in summary["demo_profiles"])
    )


def clear_workspace(ctx, *, mode: str = "delete") -> dict:
    """Remove demo rows only. ``mode='archive'`` keeps demo profiles as
    archived shells instead of deleting them."""
    if mode not in ("delete", "archive"):
        raise ValueError("mode must be 'delete' or 'archive'.")

    conn = ctx.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _seed_temp_tables(conn)

        real_candidates_before = _count(conn, "SELECT COUNT(*) FROM candidates WHERE is_demo = 0")

        files_to_remove: list[Path] = []
        for row in conn.execute(
            "SELECT stored_path FROM resumes WHERE id IN (SELECT id FROM _demo_resumes)"
        ):
            files_to_remove.append(Path(safe_join_under(ctx.data_dir, row["stored_path"])))

        counts = {
            "candidates": _count(conn, "SELECT COUNT(*) FROM _demo_candidates"),
            "resumes": _count(conn, "SELECT COUNT(*) FROM _demo_resumes"),
            "jobs": _count(conn, "SELECT COUNT(*) FROM _demo_jobs"),
            "reviews": _count(
                conn,
                "SELECT COUNT(*) FROM candidate_reviews WHERE candidate_id IN (SELECT id FROM _demo_candidates)",
            ),
            "decisions": _count(
                conn,
                """SELECT COUNT(*) FROM candidates
                   WHERE is_demo = 1 AND human_decision IS NOT NULL""",
            ),
        }

        # Detach references from surviving rows to the rows about to disappear —
        # these foreign keys have no ON DELETE clause, so SQLite would refuse
        # the delete (or leave a dangling pointer) otherwise.
        conn.execute(
            "UPDATE candidates SET duplicate_of = NULL WHERE duplicate_of IN (SELECT id FROM _demo_candidates)"
        )
        conn.execute(
            "UPDATE resumes SET duplicate_hash_of = NULL WHERE duplicate_hash_of IN (SELECT id FROM _demo_resumes)"
        )
        conn.execute(
            "UPDATE source_items SET resume_id = NULL WHERE resume_id IN (SELECT id FROM _demo_resumes)"
        )
        conn.execute(
            "UPDATE source_items SET matched_candidate = NULL WHERE matched_candidate IN (SELECT id FROM _demo_candidates)"
        )
        conn.execute(
            "UPDATE source_syncs SET job_id = NULL WHERE job_id IN (SELECT id FROM _demo_jobs)"
        )

        # Decide what happens to each demo profile *before* touching audit
        # history: a profile that still holds non-demo rows is kept, and so is
        # its history.
        profiles_removed: list[int] = []
        profiles_archived: list[int] = []
        profiles_kept: list[dict] = []
        for row in conn.execute("SELECT id, title FROM _demo_profiles ORDER BY id"):
            profile_id = int(row["id"])
            remaining_candidates = _count(
                conn,
                "SELECT COUNT(*) FROM candidates WHERE profile_id = ? AND is_demo = 0",
                (profile_id,),
            )
            remaining_resumes = _count(
                conn,
                "SELECT COUNT(*) FROM resumes WHERE profile_id = ? "
                "AND id NOT IN (SELECT id FROM _demo_resumes)",
                (profile_id,),
            )
            if remaining_candidates or remaining_resumes:
                profiles_kept.append(
                    {
                        "id": profile_id,
                        "title": row["title"],
                        "reason": f"still holds {remaining_candidates} candidate(s) / "
                        f"{remaining_resumes} resume(s) that are not flagged demo",
                    }
                )
                continue
            (profiles_archived if mode == "archive" else profiles_removed).append(profile_id)

        gone_profile_ids = profiles_removed if mode == "delete" else []
        audit_sql = "SELECT a.id FROM audit_events a WHERE " + _DEMO_AUDIT_WHERE
        audit_params: list = []
        if gone_profile_ids:
            placeholders = ",".join("?" for _ in gone_profile_ids)
            audit_sql += (
                f"       OR (a.entity_type = 'screening_profile' AND a.entity_id IN ({placeholders}))\n"
                f"       OR a.profile_id IN ({placeholders})"
            )
            audit_params = gone_profile_ids + gone_profile_ids
        audit_ids = [row["id"] for row in conn.execute(audit_sql, audit_params)]
        if audit_ids:
            conn.executemany("DELETE FROM audit_events WHERE id = ?", [(i,) for i in audit_ids])

        conn.execute("DELETE FROM candidates WHERE id IN (SELECT id FROM _demo_candidates)")
        conn.execute("DELETE FROM resumes WHERE id IN (SELECT id FROM _demo_resumes)")
        conn.execute("DELETE FROM processing_jobs WHERE id IN (SELECT id FROM _demo_jobs)")

        for profile_id in profiles_archived:
            conn.execute(
                "UPDATE screening_profiles SET archived = 1, updated_at = ? WHERE id = ?",
                (now_iso(), profile_id),
            )
        for profile_id in profiles_removed:
            conn.execute("DELETE FROM screening_profiles WHERE id = ?", (profile_id,))

        counts["audit"] = len(audit_ids)
        files_removed = 0
        for path in files_to_remove:
            try:
                if path.is_file():
                    path.unlink()
                    files_removed += 1
            except OSError:
                # A file we could not delete must not abort the database clear.
                continue

        summary_after = workspace_summary(conn)
        record(
            conn,
            "demo_workspace_cleared",
            entity_type="demo",
            message=(
                f"Demo workspace cleared ({mode}): {counts['candidates']} demo candidate(s), "
                f"{counts['resumes']} resume(s), {counts['jobs']} job(s), "
                f"{len(profiles_removed) + len(profiles_archived)} profile(s) "
                f"{'archived' if mode == 'archive' else 'removed'}, "
                f"{counts['audit']} audit entr(ies)."
            ),
            data={
                "mode": mode,
                "candidates": counts["candidates"],
                "resumes": counts["resumes"],
                "jobs": counts["jobs"],
                "profiles_archived": len(profiles_archived),
                "profiles_removed": len(profiles_removed),
                "audit_events": counts["audit"],
                "real_candidates_preserved": real_candidates_before,
            },
        )
        conn.execute("COMMIT")

        return {
            "mode": mode,
            "method": (
                "candidates/resumes/jobs: hard delete of is_demo=1 rows only; "
                "demo profiles: " + ("archived (archived=1)" if mode == "archive" else "deleted")
                + "; demo audit entries: deleted; stored demo files: removed from disk"
            ),
            "candidates_removed": counts["candidates"],
            "resumes_removed": counts["resumes"],
            "jobs_removed": counts["jobs"],
            "reviews_removed": counts["reviews"],
            "decisions_removed": counts["decisions"],
            "audit_events_removed": counts["audit"],
            "resume_files_removed": files_removed,
            "profiles": {
                "removed": profiles_removed,
                "archived": profiles_archived,
                "kept": profiles_kept,
            },
            "real_data_preserved": {
                "candidates": real_candidates_before,
                "note": "No row with is_demo = 0 was deleted or archived.",
            },
            "remaining": summary_after,
        }
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        try:
            _drop_temp_tables(conn)
        except Exception:  # noqa: BLE001 - cleanup only
            pass
        conn.close()

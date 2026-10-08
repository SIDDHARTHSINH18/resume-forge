"""DEMO DATA endpoints — clearly separated from real usage.

Demo resumes are generated as files only; they enter the application solely
through the normal upload + processing pipeline, so demo rows are always
flagged and never mixed silently with real candidates.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..audit import record
from ..schemas import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from ..services.candidates import apply_decision
from ..services.demo_data import demo_status, generate_demo_resumes
from ..services.demo_workspace import (
    DEMO_JOB_LABEL,
    DEMO_PROFILE_TITLE_BACKEND,
    DEMO_PROFILE_TITLE_FRONTEND,
    clear_workspace,
    has_demo_data,
    workspace_summary,
)
from ..services.pipeline import UploadError, handle_upload, process_job
from ..services.profiles import create_profile, get_profile
from ..util import now_iso

router = APIRouter(prefix="/api/demo", tags=["demo"])


# Applied in order to the first N candidates (by score desc) after the seed
# pipeline runs. Any candidate not listed stays in "needs review" — the
# default post-processing state, which is one of the four statuses the
# demo is meant to show.
DEMO_DECISIONS = [
    ("shortlist", "Demo: strong match on required skills and intern experience."),
    ("move_to_interview", "Demo: solid fundamentals, schedule screen."),
    ("hold", "Demo: profile fits but limited evidence, revisit later."),
    ("close", "Demo: not a fit for this req (missing required skills)."),
]


class _DiskUpload:
    """Adapts an on-disk demo file to the interface handle_upload expects."""

    def __init__(self, path: Path):
        self.filename = path.name
        self.file = open(path, "rb")


@router.get("/status")
def status(request: Request):
    ctx = request.app.state.ctx
    payload = demo_status(ctx)
    conn = ctx.connect()
    try:
        payload["workspace"] = workspace_summary(conn)
    finally:
        conn.close()
    return payload



@router.post("/generate")
def generate(request: Request):
    ctx = request.app.state.ctx
    result = generate_demo_resumes(ctx.demo_dir)
    conn = ctx.connect()
    try:
        record(
            conn,
            "demo_data_generated",
            entity_type="demo",
            message=f"Demo dataset generated: {result['count']} files",
            data={"count": result["count"]},
        )
    finally:
        conn.close()
    return result


@router.post("/upload/{profile_id}", status_code=202)
def upload_demo(request: Request, profile_id: int):
    """Ingest the demo files into a profile through the normal pipeline.

    It is an explicit, clearly-labelled action; every resulting candidate is
    flagged is_demo because of the DEMO DATA banner inside each file.
    """
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        profile = get_profile(conn, profile_id)
    finally:
        conn.close()
    if profile is None:
        raise HTTPException(status_code=404, detail="Screening profile not found.")
    if profile["archived"]:
        raise HTTPException(status_code=400, detail="This screening profile is archived.")

    current = demo_status(ctx)
    if not current["count"]:
        generate_demo_resumes(ctx.demo_dir)
        current = demo_status(ctx)

    uploads = [_DiskUpload(path) for path in sorted(Path(ctx.demo_dir).iterdir()) if path.is_file()]
    try:
        result = handle_upload(ctx, profile, uploads)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for upload in uploads:
            upload.file.close()

    conn = ctx.connect()
    try:
        record(
            conn,
            "demo_data_uploaded",
            entity_type="demo",
            profile_id=profile_id,
            message=f"Demo dataset ingested into profile '{profile['title']}' ({len(uploads)} files)",
            data={"count": len(uploads)},
        )
    finally:
        conn.close()
    return {**result, "demo_files": len(uploads)}


@router.post("/seed")
def seed(request: Request, force: bool = False):
    """Create a demo workspace end-to-end and return the counts.

    Refuses to pile a second copy of the demo set on top of an existing one:
    use ``/api/demo/reset`` (clear then seed) to replace it. ``force=true`` is
    the explicit confirmation for that path. Real user data is never modified —
    the seed only touches profiles whose title starts with "DEMO —", and the
    four decisions are applied only to candidates with is_demo = 1.
    """
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        existing = has_demo_data(conn)
    finally:
        conn.close()
    if existing and not force:
        raise HTTPException(status_code=409, detail=DEMO_EXISTS_MESSAGE)
    return _seed_workspace(ctx)


DEMO_EXISTS_MESSAGE = "Demo data already exists. Use Reset demo workspace to replace it."


def _seed_workspace(ctx) -> dict:
    # 1. Ensure demo files exist.
    current = demo_status(ctx)
    if not current["count"]:
        generate_demo_resumes(ctx.demo_dir)

    # 2. Ensure the two demo profiles exist (create, or re-activate an
    # archived one left behind by "clear demo workspace (archive)").
    def _ensure_profile(title: str, required: list[str], preferred: list[str], description: str) -> int:
        conn = ctx.connect()
        try:
            existing = conn.execute(
                "SELECT id, archived FROM screening_profiles WHERE title = ? ORDER BY id LIMIT 1",
                (title,),
            ).fetchone()
            if existing:
                if existing["archived"]:
                    conn.execute(
                        "UPDATE screening_profiles SET archived = 0, updated_at = ? WHERE id = ?",
                        (now_iso(), existing["id"]),
                    )
                    record(
                        conn,
                        "profile_unarchived",
                        entity_type="screening_profile",
                        entity_id=int(existing["id"]),
                        profile_id=int(existing["id"]),
                        message=f"Screening profile '{title}' re-activated for the demo workspace",
                    )
                return int(existing["id"])
            return create_profile(
                conn,
                {
                    "type": "recruitment",
                    "title": title,
                    "description": description,
                    "required_skills": required,
                    "preferred_skills": preferred,
                    "min_academic": 7.0,
                    "min_academic_type": "cgpa",
                    "weights": dict(DEFAULT_WEIGHTS),
                    "thresholds": dict(DEFAULT_THRESHOLDS),
                    "ai_enabled": False,
                },
            )
        finally:
            conn.commit()
            conn.close()

    backend_id = _ensure_profile(
        DEMO_PROFILE_TITLE_BACKEND,
        ["Python", "SQL"],
        ["FastAPI", "Django", "Git", "Docker"],
        "Demo job: entry-level backend engineer for a Python + SQL team. "
        "Synthetic workspace for demos only.",
    )
    frontend_id = _ensure_profile(
        DEMO_PROFILE_TITLE_FRONTEND,
        ["React", "JavaScript"],
        ["TypeScript", "HTML", "CSS", "Git"],
        "Demo job: frontend engineer working in React. Synthetic workspace "
        "for demos only.",
    )

    # 3. Load demo files into both profiles via the normal pipeline, then
    # process synchronously so candidates exist when this endpoint returns.
    files = [p for p in sorted(Path(ctx.demo_dir).iterdir()) if p.is_file()]
    job_ids: list[int] = []
    created_candidates: dict[int, list[int]] = {}
    for profile_id in (backend_id, frontend_id):
        conn = ctx.connect()
        try:
            profile_row = conn.execute(
                "SELECT * FROM screening_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        finally:
            conn.close()
        if profile_row is None:
            continue
        from ..services.profiles import profile_to_dict

        profile = profile_to_dict(profile_row)
        uploads = [_DiskUpload(p) for p in files]
        try:
            result = handle_upload(
                ctx,
                profile,
                uploads,
                label=DEMO_JOB_LABEL,
            )
        except UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            for upload in uploads:
                upload.file.close()
        if result.get("job_id"):
            job_id = int(result["job_id"])
            job_ids.append(job_id)
            # handle_upload queues the job for the background worker. Wait for it
            # before running the synchronous pass, otherwise worker and inline
            # processing race and create duplicate candidates for one resume.
            # process_job is idempotent (it only picks UPLOADED/PARSING resumes),
            # so this still completes the seed when no worker is running.
            if ctx.jobs is not None:
                ctx.jobs.wait_idle(timeout=180.0)
            process_job(ctx, job_id)
        conn = ctx.connect()
        try:
            rows = conn.execute(
                """SELECT c.id FROM candidates c
                   JOIN resumes r ON r.id = c.resume_id
                   WHERE c.profile_id = ? AND r.profile_id = ? AND c.is_demo = 1
                   ORDER BY c.overall_score DESC NULLS LAST, c.id ASC""",
                (profile_id, profile_id),
            ).fetchall()
            created_candidates[profile_id] = [int(r["id"]) for r in rows]
        finally:
            conn.close()

    # 4. Apply one decision from the demo set to the top candidates of the
    # backend profile only, so the UI shows shortlisted / interview / hold /
    # rejected / needs-review simultaneously.
    applied: list[dict] = []
    target_ids = created_candidates.get(backend_id, [])[: len(DEMO_DECISIONS)]
    for candidate_id, (decision, reason) in zip(target_ids, DEMO_DECISIONS):
        conn = ctx.connect()
        try:
            demo_flag = conn.execute(
                "SELECT is_demo FROM candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
            if demo_flag is None or not demo_flag["is_demo"]:
                continue
            apply_decision(conn, candidate_id, decision, reason, "MeritOS demo")
            conn.commit()
            applied.append({"candidate_id": candidate_id, "decision": decision})
        finally:
            conn.close()

    # 5. Audit the seed action.
    conn = ctx.connect()
    try:
        record(
            conn,
            "demo_workspace_seeded",
            entity_type="demo",
            message=(
                f"Demo workspace seeded: {len(job_ids)} job(s), "
                f"{sum(len(v) for v in created_candidates.values())} candidate(s), "
                f"{len(applied)} demo decision(s)."
            ),
            data={
                "profiles": [backend_id, frontend_id],
                "jobs": job_ids,
                "candidates_per_profile": {str(k): len(v) for k, v in created_candidates.items()},
                "decisions": [d["decision"] for d in applied],
            },
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "profiles": {
            "backend_id": backend_id,
            "frontend_id": frontend_id,
        },
        "processed_jobs": len(job_ids),
        "candidates": {
            str(profile_id): len(ids) for profile_id, ids in created_candidates.items()
        },
        "decisions_applied": applied,
        "note": "All seeded candidates carry is_demo=1. Real user data was not modified.",
    }


@router.post("/clear")
def clear(request: Request, mode: str = "delete"):
    """Remove demo rows only.

    ``mode='delete'`` (default) also removes the two DEMO profiles;
    ``mode='archive'`` keeps them as archived shells so their history survives.
    Candidates, resumes and jobs have no archive column, so demo rows in those
    tables are always hard deleted — and only rows flagged ``is_demo = 1`` (or
    demo resumes that never produced a candidate). ``is_demo = 0`` rows are
    never touched; a demo profile that still holds real rows is kept and
    reported under ``profiles.kept``.
    """
    if mode not in ("delete", "archive"):
        raise HTTPException(status_code=400, detail="mode must be 'delete' or 'archive'.")
    ctx = request.app.state.ctx
    try:
        return clear_workspace(ctx, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset")
def reset(request: Request, mode: str = "delete"):
    """Clear the existing demo workspace, then seed a fresh one.

    This is the supported way to replace demo data: it prevents the
    "seed twice, get double candidates" mess without touching real candidates.
    """
    ctx = request.app.state.ctx
    cleared = clear_workspace(ctx, mode=mode)
    seeded = _seed_workspace(ctx)
    return {
        "cleared": cleared,
        "seeded": seeded,
        "note": "Only demo rows were removed; real candidates were not modified.",
    }

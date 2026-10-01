"""DEMO DATA endpoints — clearly separated from real usage.

Demo resumes are generated as files only; they enter the application solely
through the normal upload + processing pipeline, so demo rows are always
flagged and never mixed silently with real candidates.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..audit import record
from ..services.demo_data import demo_status, generate_demo_resumes
from ..services.pipeline import UploadError, handle_upload
from ..services.profiles import get_profile

router = APIRouter(prefix="/api/demo", tags=["demo"])


class _DiskUpload:
    """Adapts an on-disk demo file to the interface handle_upload expects."""

    def __init__(self, path: Path):
        self.filename = path.name
        self.file = open(path, "rb")


@router.get("/status")
def status(request: Request):
    return demo_status(request.app.state.ctx)


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

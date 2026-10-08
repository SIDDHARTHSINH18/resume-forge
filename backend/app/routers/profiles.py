"""Screening profile endpoints + resume upload."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..audit import record
from ..schemas import ProfileIn
from ..services import hr_memory
from ..services.pipeline import UploadError, handle_upload
from ..services.profiles import (
    create_profile,
    get_profile,
    list_profiles,
    profile_counts,
    update_profile,
)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def ctx_of(request: Request):
    return request.app.state.ctx


@router.get("")
def list_all(request: Request, include_archived: bool = False):
    conn = ctx_of(request).connect()
    try:
        return {"items": list_profiles(conn, include_archived=include_archived)}
    finally:
        conn.close()


@router.post("", status_code=201)
def create(request: Request, payload: ProfileIn):
    conn = ctx_of(request).connect()
    try:
        profile_id = create_profile(conn, payload.model_dump())
        return get_profile(conn, profile_id)
    finally:
        conn.close()


@router.get("/{profile_id}")
def get_one(request: Request, profile_id: int):
    conn = ctx_of(request).connect()
    try:
        profile = get_profile(conn, profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Screening profile not found.")
        profile["counts"] = profile_counts(conn, profile_id)
        return profile
    finally:
        conn.close()


@router.put("/{profile_id}")
def update(request: Request, profile_id: int, payload: ProfileIn):
    conn = ctx_of(request).connect()
    try:
        if get_profile(conn, profile_id) is None:
            raise HTTPException(status_code=404, detail="Screening profile not found.")
        update_profile(conn, profile_id, payload.model_dump())
        return get_profile(conn, profile_id)
    finally:
        conn.close()


@router.post("/{profile_id}/archive")
def archive(request: Request, profile_id: int):
    conn = ctx_of(request).connect()
    try:
        profile = get_profile(conn, profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Screening profile not found.")
        new_state = 0 if profile["archived"] else 1
        conn.execute("UPDATE screening_profiles SET archived = ? WHERE id = ?", (new_state, profile_id))
        record(
            conn,
            "profile_archived" if new_state else "profile_unarchived",
            entity_type="screening_profile",
            entity_id=profile_id,
            profile_id=profile_id,
            message=f"Profile '{profile['title']}' {'archived' if new_state else 'restored'}",
        )
        return get_profile(conn, profile_id)
    finally:
        conn.close()


@router.get("/{profile_id}/insights")
def insights(request: Request, profile_id: int):
    """Advisory HR preference insights derived from recorded decisions.

    Read-only and explainable: patterns appear only once enough decisions exist,
    and each pattern states its support and sample size.
    """
    conn = ctx_of(request).connect()
    try:
        if get_profile(conn, profile_id) is None:
            raise HTTPException(status_code=404, detail="Screening profile not found.")
        return hr_memory.profile_insights(conn, profile_id)
    finally:
        conn.close()


@router.post("/{profile_id}/upload", status_code=202)
def upload(request: Request, profile_id: int, files: list[UploadFile] = File(...)):
    ctx = ctx_of(request)
    conn = ctx.connect()
    try:
        profile = get_profile(conn, profile_id)
    finally:
        conn.close()
    if profile is None:
        raise HTTPException(status_code=404, detail="Screening profile not found.")
    if profile["archived"]:
        raise HTTPException(status_code=400, detail="This screening profile is archived.")
    try:
        return handle_upload(ctx, profile, files)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

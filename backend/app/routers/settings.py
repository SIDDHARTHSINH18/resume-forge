"""Settings endpoints: AI provider configuration and reviewer identity."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..ai import resolve_provider
from ..audit import record
from ..schemas import AISettingsIn, ReviewerIn
from ..services.settings_store import get_ai_settings, get_public_ai_settings, set_ai_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        reviewer = conn.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    finally:
        conn.close()
    return {
        "ai": get_public_ai_settings(ctx),
        "reviewer": {"name": reviewer["name"] if reviewer else "Local Reviewer"},
        "data_dir": str(ctx.data_dir),
        "demo_dir": str(ctx.demo_dir),
    }


@router.put("/ai")
def update_ai(request: Request, payload: AISettingsIn):
    ctx = request.app.state.ctx
    public = set_ai_settings(
        ctx,
        {
            "provider": payload.provider,
            "base_url": payload.base_url,
            "model": payload.model,
            "api_key": payload.api_key,
            "timeout_seconds": payload.timeout_seconds,
        },
        clear_api_key=payload.clear_api_key,
    )
    conn = ctx.connect()
    try:
        record(
            conn,
            "settings_updated",
            entity_type="settings",
            message=f"AI settings updated (provider: {payload.provider})",
            data={"provider": payload.provider, "model": payload.model, "base_url": payload.base_url},
        )
    finally:
        conn.close()
    return public


@router.post("/ai/test")
def test_ai(request: Request):
    ctx = request.app.state.ctx
    provider = resolve_provider(get_ai_settings(ctx))
    if provider is None:
        return {"ok": False, "message": "No provider configured.", "provider": "none"}
    ok, message = provider.test_connection()
    return {"ok": ok, "message": message, "provider": provider.name}


@router.put("/reviewer")
def update_reviewer(request: Request, payload: ReviewerIn):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="Reviewer user missing.")
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (payload.name, row["id"]))
        record(conn, "settings_updated", entity_type="settings", message="Reviewer name updated")
        return {"name": payload.name}
    finally:
        conn.close()

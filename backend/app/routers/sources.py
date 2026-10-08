"""Resume source APIs: listing, Gmail OAuth, preview, import and sync history.

Conventions follow the existing routers: plain FastAPI functions, HTTPException
with user-facing detail strings, application context on request.app.state.ctx.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..audit import record
from ..sources import SourceError
from ..sources import gmail as gmail_module
from ..sources.base import SearchCriteria
from ..services import source_records
from ..services.pipeline import UploadError
from ..sources.service import (
    instance_for,
    import_sync,
    preview,
    source_cards,
    source_row_or_error,
    sync_detail,
    sync_history,
)
from ..services.profiles import get_profile

router = APIRouter(prefix="/api/sources", tags=["sources"])

_CONNECTION_MESSAGE = (
    "LinkedIn integration requires an approved official API connection. No browser scraping is used."
)


class PreviewPayload(BaseModel):
    profile_id: int
    date_from: str | None = None
    date_to: str | None = None
    sender: str = ""
    keywords: list[str] = Field(default_factory=list)


class ImportPayload(BaseModel):
    sync_id: int


class SyncNowPayload(BaseModel):
    profile_id: int
    sender: str = ""
    keywords: list[str] = Field(default_factory=list)
    date_from: str | None = None


class GmailConfigPayload(BaseModel):
    client_id: str = ""
    client_secret: str | None = None
    redirect_uri: str | None = None
    clear_client_secret: bool = False


class RecordPayload(BaseModel):
    source_kind: str
    title: str = ""
    url: str = ""
    notes: str = ""
    contact_name: str = ""
    contact_email: str = ""
    referrer: str = ""
    profile_id: int | None = None
    created_by: str = ""


class RecordStatusPayload(BaseModel):
    status: str
    actor: str = ""


class PastePayload(BaseModel):
    profile_id: int
    text: str
    label: str = ""
    actor: str = ""


def _profile_or_404(ctx, profile_id: int) -> dict:
    conn = ctx.connect()
    try:
        profile = get_profile(conn, profile_id)
    finally:
        conn.close()
    if profile is None:
        raise HTTPException(status_code=404, detail="Screening profile not found.")
    if profile["archived"]:
        raise HTTPException(status_code=400, detail="This screening profile is archived.")
    return profile


def _source_or_404(ctx, source_id: int):
    try:
        return source_row_or_error(ctx, source_id)
    except SourceError as exc:
        raise HTTPException(status_code=404, detail=exc.reason) from exc


@router.get("")
def list_sources(request: Request):
    ctx = request.app.state.ctx
    return {"items": source_cards(ctx)}


# --------------------------------------------------------------------------
# manual intake — records, pasted text, CSV
#
# Declared before "/{source_id}" so these literal paths are not swallowed by
# the numeric route. Everything here stores what a human supplied; nothing is
# fetched from any website.
# --------------------------------------------------------------------------


@router.get("/records")
def list_intake_records(
    request: Request,
    profile_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        return {
            "items": source_records.list_records(
                conn, profile_id=profile_id, status=status, source_kind=kind
            ),
            "counts": source_records.record_counts(conn, profile_id=profile_id),
            "kinds": source_records.RECORD_KIND_INFO,
            "methods": source_records.INTAKE_METHODS,
            "note": (
                "Intake records are provenance: they say where a lead came from. A record only "
                "becomes a candidate once its resume passes through the ingestion pipeline."
            ),
        }
    finally:
        conn.close()


@router.post("/records", status_code=201)
def create_intake_record(request: Request, payload: RecordPayload):
    ctx = request.app.state.ctx
    if payload.profile_id is not None:
        _profile_or_404(ctx, payload.profile_id)
    conn = ctx.connect()
    try:
        try:
            return source_records.create_record(
                conn,
                source_kind=payload.source_kind,
                profile_id=payload.profile_id,
                title=payload.title,
                url=payload.url,
                notes=payload.notes,
                contact_name=payload.contact_name,
                contact_email=payload.contact_email,
                referrer=payload.referrer,
                created_by=payload.created_by,
            )
        except SourceError as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc
    finally:
        conn.close()


@router.post("/records/{record_id}/status")
def set_intake_record_status(request: Request, record_id: int, payload: RecordStatusPayload):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        try:
            return source_records.set_status(conn, record_id, payload.status, actor=payload.actor)
        except SourceError as exc:
            status = 404 if "not found" in exc.reason.lower() else 400
            raise HTTPException(status_code=status, detail=exc.reason) from exc
    finally:
        conn.close()


@router.post("/paste", status_code=202)
def paste_resume(request: Request, payload: PastePayload):
    ctx = request.app.state.ctx
    profile = _profile_or_404(ctx, payload.profile_id)
    try:
        return source_records.import_pasted_text(
            ctx, profile, text=payload.text, label=payload.label, actor=payload.actor
        )
    except (SourceError, UploadError) as exc:
        raise HTTPException(status_code=400, detail=getattr(exc, "reason", str(exc))) from exc


@router.post("/csv", status_code=202)
async def import_csv_file(
    request: Request,
    profile_id: int = Form(...),
    file: UploadFile = File(...),
    actor: str = Form(""),
):
    ctx = request.app.state.ctx
    profile = _profile_or_404(ctx, profile_id)
    raw = await file.read(source_records.MAX_CSV_BYTES + 1)
    if len(raw) > source_records.MAX_CSV_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"CSV file is larger than {source_records.MAX_CSV_BYTES // (1024 * 1024)} MB.",
        )
    filename = (file.filename or "candidates.csv").strip()
    try:
        return source_records.import_csv(ctx, profile, raw, filename, actor=actor)
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc


@router.get("/{source_id}")
def get_source(request: Request, source_id: int):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    cards = {card["kind"]: card for card in source_cards(ctx)}
    card = cards.get(row["kind"])
    if card is None:
        raise HTTPException(status_code=404, detail="Resume source not found.")
    card["syncs"] = [item for item in sync_history(ctx, row)["items"]]
    return card


# --------------------------------------------------------------------------
# Gmail OAuth
# --------------------------------------------------------------------------


@router.get("/gmail/oauth/callback", response_class=HTMLResponse, include_in_schema=False)
def gmail_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    ctx = request.app.state.ctx
    if error:
        return _callback_page(
            False,
            "Gmail connection failed. No resumes were imported.",
            "The Google consent screen reported an error.",
        )
    try:
        pending = gmail_module.consume_oauth_state(ctx, state)
        tokens = gmail_module.exchange_code(
            ctx, code=code, verifier=pending["verifier"], redirect_uri=pending["redirect_uri"]
        )
        api = gmail_module.GmailApi(tokens["access_token"])
        tokens["account"] = api.profile_email()
        gmail_module.save_tokens(ctx, tokens)
    except SourceError as exc:
        return _callback_page(False, exc.reason, "Start the connection again from the Resume Sources page.")
    conn = ctx.connect()
    try:
        record(
            conn,
            "source_connected",
            entity_type="resume_source",
            message=f"Gmail connected as {gmail_module.mask_email(tokens.get('account')) or 'account'} (read + approved-send scopes)",
            data={"scope": gmail_module.GMAIL_SCOPE},
        )
    finally:
        conn.close()
    return _callback_page(
        True,
        "Gmail connected.",
        "You can close this tab and return to the application. Tokens are stored locally and never leave this machine.",
    )


def _callback_page(ok: bool, title: str, detail: str) -> HTMLResponse:
    colour = "#4ade80" if ok else "#f87171"
    return HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="background:#0b0f14;color:#e5e7eb;font-family:system-ui,Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="max-width:460px;padding:32px;border:1px solid #1f2937;border-radius:12px;background:#0f1520">
<div style="width:10px;height:10px;border-radius:50%;background:{colour};margin-bottom:16px"></div>
<h1 style="font-size:18px;margin:0 0 8px">{title}</h1>
<p style="color:#9ca3af;font-size:13.5px;line-height:1.5;margin:0">{detail}</p>
</div></body></html>"""
    )


@router.post("/{source_id}/connect")
def connect_source(request: Request, source_id: int, payload: dict | None = None):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    source = instance_for(row["kind"])
    try:
        result = source.connect(ctx, payload or {})
    except SourceError as exc:
        status = 409 if "approved official API" in exc.reason else 400
        raise HTTPException(status_code=status, detail=exc.reason) from exc
    return {"source_id": source_id, **result}


@router.post("/{source_id}/disconnect")
def disconnect_source(request: Request, source_id: int):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    source = instance_for(row["kind"])
    source.disconnect(ctx)
    conn = ctx.connect()
    try:
        record(
            conn,
            "source_disconnected",
            entity_type="resume_source",
            entity_id=source_id,
            message=f"{row['display_name']} disconnected",
        )
    finally:
        conn.close()
    return {"source_id": source_id, "disconnected": True}


@router.put("/{source_id}/config")
def configure_source(request: Request, source_id: int, payload: GmailConfigPayload):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    if row["kind"] != "gmail":
        raise HTTPException(status_code=400, detail="This source has no configuration.")
    config = gmail_module.save_client_config(
        ctx,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        redirect_uri=payload.redirect_uri,
    )
    if payload.clear_client_secret:
        gmail_module.clear_client_secret(ctx)
        config = gmail_module.get_client_config(ctx)
    conn = ctx.connect()
    try:
        record(
            conn,
            "source_configured",
            entity_type="resume_source",
            entity_id=source_id,
            message="Gmail OAuth client configuration updated",
            data={"client_id_masked": gmail_module.mask_secret(config["client_id"])},
        )
    finally:
        conn.close()
    return {
        "source_id": source_id,
        "client_id": config["client_id"],
        "client_id_masked": gmail_module.mask_secret(config["client_id"]),
        "has_client_secret": bool(config["client_secret"]),
        "secret_source": config["secret_source"],
        "redirect_uri": config["redirect_uri"],
    }


# --------------------------------------------------------------------------
# preview / import / sync
# --------------------------------------------------------------------------


@router.post("/{source_id}/preview")
def preview_source(request: Request, source_id: int, payload: PreviewPayload):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    profile = _profile_or_404(ctx, payload.profile_id)
    criteria = SearchCriteria(
        date_from=payload.date_from,
        date_to=payload.date_to,
        sender=payload.sender,
        keywords=payload.keywords,
    )
    try:
        return preview(ctx, row, profile, criteria)
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc


@router.post("/{source_id}/import")
def import_source(request: Request, source_id: int, payload: ImportPayload):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    conn = ctx.connect()
    try:
        sync = conn.execute(
            "SELECT * FROM source_syncs WHERE id = ? AND source_id = ?", (payload.sync_id, source_id)
        ).fetchone()
    finally:
        conn.close()
    if sync is None:
        raise HTTPException(status_code=404, detail="Scan not found for this source.")
    profile = _profile_or_404(ctx, sync["profile_id"])
    try:
        return import_sync(ctx, row, profile, payload.sync_id)
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc


@router.post("/{source_id}/sync-now")
def sync_now(request: Request, source_id: int, payload: SyncNowPayload):
    """Fetch everything since the last successful sync (incremental)."""
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    profile = _profile_or_404(ctx, payload.profile_id)
    if not row["last_successful_sync_at"]:
        raise HTTPException(
            status_code=400,
            detail="This source has no successful sync yet — choose a date range for the first fetch.",
        )
    criteria = SearchCriteria(
        date_from=row["last_successful_sync_at"][:10],
        date_to=None,
        sender=payload.sender,
        keywords=payload.keywords,
    )
    if payload.date_from:
        criteria.date_from = payload.date_from
    try:
        return preview(ctx, row, profile, criteria)
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc


@router.get("/{source_id}/syncs")
def list_source_syncs(request: Request, source_id: int, limit: int = 25):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    return sync_history(ctx, row, limit=min(100, max(1, limit)))


@router.get("/{source_id}/syncs/{sync_id}")
def get_source_sync(request: Request, source_id: int, sync_id: int):
    ctx = request.app.state.ctx
    row = _source_or_404(ctx, source_id)
    try:
        return sync_detail(ctx, row, sync_id)
    except SourceError as exc:
        raise HTTPException(status_code=404, detail=exc.reason) from exc

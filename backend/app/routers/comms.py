"""Candidate communication endpoints: drafts, approvals and the audited
double-confirmed send.

The service layer (services/comms.py) owns every guardrail; these routes only
translate payloads and errors. A blocked send is a normal, recorded outcome —
it answers 200 with the recorded outcome so the caller can show exactly what
was refused and why.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import (
    EmailApproveIn,
    EmailCancelIn,
    EmailDraftIn,
    EmailSendIn,
    EmailUpdateIn,
)
from ..services import comms

router = APIRouter(prefix="/api", tags=["communication"])


def _handle(exc: comms.CommsError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.reason)


@router.get("/comms/status")
def comms_status(request: Request):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        return comms.status_payload(ctx, conn)
    finally:
        conn.close()


@router.get("/candidates/{candidate_id}/emails")
def list_emails(request: Request, candidate_id: int):
    ctx = request.app.state.ctx
    conn = ctx.connect()
    try:
        return comms.list_payload(ctx, conn, candidate_id)
    except comms.CommsError as exc:
        raise _handle(exc)
    finally:
        conn.close()


@router.post("/candidates/{candidate_id}/emails", status_code=201)
def create_draft(request: Request, candidate_id: int, payload: EmailDraftIn):
    ctx = request.app.state.ctx
    try:
        return comms.create_draft(ctx, candidate_id, email_type=payload.email_type, actor=payload.actor)
    except comms.CommsError as exc:
        raise _handle(exc)


@router.get("/emails/{email_id}")
def email_detail(request: Request, email_id: int):
    ctx = request.app.state.ctx
    try:
        return comms.get_email(ctx, email_id)
    except comms.CommsError as exc:
        raise _handle(exc)


@router.post("/emails/{email_id}/update")
def update_email(request: Request, email_id: int, payload: EmailUpdateIn):
    ctx = request.app.state.ctx
    try:
        return comms.update_email(
            ctx,
            email_id,
            actor=payload.actor,
            recipient=payload.recipient,
            subject=payload.subject,
            body=payload.body,
        )
    except comms.CommsError as exc:
        raise _handle(exc)


@router.post("/emails/{email_id}/approve")
def approve_email(request: Request, email_id: int, payload: EmailApproveIn):
    ctx = request.app.state.ctx
    try:
        return comms.approve_email(ctx, email_id, actor=payload.actor, revision=payload.revision)
    except comms.CommsError as exc:
        raise _handle(exc)


@router.post("/emails/{email_id}/cancel")
def cancel_email(request: Request, email_id: int, payload: EmailCancelIn):
    ctx = request.app.state.ctx
    try:
        return comms.cancel_email(ctx, email_id, actor=payload.actor, reason=payload.reason)
    except comms.CommsError as exc:
        raise _handle(exc)


@router.post("/emails/{email_id}/send")
def send_email(request: Request, email_id: int, payload: EmailSendIn):
    ctx = request.app.state.ctx
    try:
        return comms.send_approved_email(
            ctx,
            email_id,
            actor=payload.actor,
            revision=payload.revision,
            expected_hash=payload.content_hash,
            recipient=payload.recipient,
            confirm=payload.confirm,
        )
    except comms.CommsError as exc:
        raise _handle(exc)

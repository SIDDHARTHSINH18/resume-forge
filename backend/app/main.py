"""FastAPI application factory for the AI Resume Screening platform."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .context import Ctx
from .routers import candidates, comms, dashboard, demo, jobs, profiles, settings, sources
from .services.pipeline import JobRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ailister")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(
    data_dir: Path | None = None,
    demo_dir: Path | None = None,
    start_worker: bool = True,
) -> FastAPI:
    ctx = Ctx(data_dir=data_dir, demo_dir=demo_dir)
    ctx.init()
    ctx.jobs = JobRunner(ctx)
    if start_worker:
        ctx.jobs.start()

    app = FastAPI(
        title="MeritOS — AI Hiring Operating Layer",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.ctx = ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Export-Count"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Details were written to the developer log."},
        )

    @app.get("/api/health")
    def health():
        from .identity import identity_payload, stability_lock_state
        from .services.settings_store import get_public_ai_settings

        payload = {
            "status": "ok",
            "version": __version__,
            "ai": get_public_ai_settings(ctx),
        }
        # Permanent, non-sensitive application identity. Frontends use
        # application_id to refuse cross-project backends (ENMA vs MeritOS vs
        # QResolve). Never contains tokens, paths, or host details.
        payload.update(identity_payload())
        try:
            payload["stability_lock"] = stability_lock_state()
        except Exception:
            # Identity reporting must not depend on the temporary policy file.
            pass
        return payload

    for router in (
        profiles.router,
        jobs.router,
        candidates.router,
        dashboard.router,
        settings.router,
        demo.router,
        sources.router,
        comms.router,
    ):
        app.include_router(router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            candidate_file = FRONTEND_DIST / full_path
            if full_path and candidate_file.is_file() and candidate_file.resolve().is_relative_to(FRONTEND_DIST):
                return FileResponse(candidate_file)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()

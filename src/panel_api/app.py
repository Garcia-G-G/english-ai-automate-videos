"""STEP 85 §2: the FastAPI app. Read-only GETs for now; `require_session` is the hook §3's spend gate fills."""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from . import build, media

HOST, PORT = "127.0.0.1", 8600          # bind this host only; nothing in this package listens on its own


def require_session() -> None:
    """§3 hook: paid routes depend on this (token header + Origin/Host pin). Read routes need nothing."""


def create_app() -> FastAPI:
    app = FastAPI(title="English Unlimited panel API", docs_url=None, redoc_url=None)

    @app.get("/api/meta")
    def meta():
        return build.meta()

    @app.get("/api/home")
    def home():
        return build.home()

    @app.get("/api/review")
    def review():
        return build.review()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        got = build.job(job_id)
        return got if got is not None else JSONResponse({"error": "No encuentro ese trabajo.", "detail": job_id}, status_code=404)

    app.include_router(media.router)
    return app


app = create_app()

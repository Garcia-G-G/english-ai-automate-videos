"""STEP 85 §2-§3: the FastAPI app. Reads are open; POSTs pass the gate (gate.py). §4 swaps the engine stubs for real ones."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from . import build, gate, media

HOST, PORT = "127.0.0.1", 8600          # bind this host only; nothing in this package listens on its own


def _not_wired(*_a, **_k):
    raise gate.GateError(501, "Esta acción todavía no está conectada al motor (STEP 85 §4).")


def create_app(engine: Optional[Dict[str, object]] = None) -> FastAPI:
    """`engine` maps produce / rerender to `f(...) -> (job_id, eta_s, runner)` and approve / reject to `f(id, body) -> dict`.
    Tests pass mocks; §4 passes the real ones."""
    eng = {"produce": _not_wired, "rerender": _not_wired, "approve": _not_wired, "reject": _not_wired, **(engine or {})}
    app = FastAPI(title="English Unlimited panel API", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_exception_handler(gate.GateError, gate.gate_error_handler)
    app.state.jobs = []                                   # the threads of paid jobs, for shutdown and tests

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def index():
        return gate.index_response()

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

    def _start(fn, *args):
        job_id, eta, runner = fn(*args)
        gate.run_job(runner, app.state.jobs)
        return {"jobId": job_id, "etaS": eta}

    @app.post("/api/produce")
    def produce(body: dict = Depends(gate.paid)):
        return _start(eng["produce"], body.get("scriptId"))

    @app.post("/api/review/{item_id}/rerender")
    def rerender(item_id: str, _body: dict = Depends(gate.paid)):
        return _start(eng["rerender"], item_id)

    @app.post("/api/review/{item_id}/approve", dependencies=[Depends(gate.free_post)])
    async def approve(item_id: str, request: Request):
        return eng["approve"](item_id, await request.json())

    @app.post("/api/review/{item_id}/reject", dependencies=[Depends(gate.free_post)])
    async def reject(item_id: str, request: Request):
        return eng["reject"](item_id, await request.json())

    app.include_router(media.router)
    return app


app = create_app()

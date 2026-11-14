"""STEP 85 §2-§3: the FastAPI app. Reads are open; POSTs pass the gate (gate.py). §4 swaps the engine stubs for real ones."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from panel_core import game
from . import build, engine as engine_mod, events, gate, media

HOST, PORT = "127.0.0.1", 8501          # bind this host only; nothing in this package listens on its own


def create_app(engine: Optional[Dict[str, object]] = None, heartbeat_s: float = events.HEARTBEAT_S) -> FastAPI:
    """`engine` overrides produce / rerender (`f(...) -> (job_id, eta_s, runner)`) and approve / reject (`f(id, body) -> dict`);
    the defaults are the real handlers in engine.py. Tests pass mocks."""
    eng = {**engine_mod.REAL, **(engine or {})}
    bus = events.Bus()
    feed = events.Feed(bus)

    @asynccontextmanager
    async def lifespan(_app):
        feed.start()                                      # job steps, done/failed and stats.refreshed reach the bus
        try:
            yield
        finally:
            feed.stop()
            bus.close()

    app = FastAPI(title="English Unlimited panel API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.bus, app.state.feed = bus, feed
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

    @app.get("/api/game")
    def game_():
        return game.snapshot()

    @app.get("/api/review")
    def review():
        return build.review()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        got = build.job(job_id)
        return got if got is not None else JSONResponse({"error": "No encuentro ese trabajo.", "detail": job_id}, status_code=404)

    @app.get("/api/events", dependencies=[Depends(gate.check_host)])
    async def live():
        return StreamingResponse(events.stream(bus, heartbeat_s), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def _start(fn, *args):
        job_id, eta, runner = fn(*args)
        gate.run_job(runner, app.state.jobs)
        return {"jobId": job_id, "etaS": eta}

    @app.post("/api/produce")
    def produce(body: dict = Depends(gate.paid)):
        return _start(eng["produce"], body.get("scriptId"))

    @app.post("/api/review/{item_id}/rerender")
    def rerender(item_id: str, _body: dict = Depends(gate.paid)):
        got = _start(eng["rerender"], item_id)
        feed.counts()                                     # the old render left «Por revisar»
        return got

    @app.post("/api/review/{item_id}/approve", dependencies=[Depends(gate.free_post)])
    async def approve(item_id: str, request: Request):
        got = eng["approve"](item_id, await request.json())
        feed.counts()                                     # Por revisar / Por subir changed
        feed.game()                                       # a scheduled video may light today's streak
        return got

    @app.post("/api/review/{item_id}/reject", dependencies=[Depends(gate.free_post)])
    async def reject(item_id: str, request: Request):
        got = eng["reject"](item_id, await request.json())
        feed.counts()
        return got

    app.include_router(media.router)
    return app


app = create_app()

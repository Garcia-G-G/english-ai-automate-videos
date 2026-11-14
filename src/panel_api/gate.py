"""STEP 85 §3: the spend gate. A per-process session token, served only inside index.html; paid routes need it
(header + `"confirm": true` + Origin/Host pinned to the panel); the voice lock opens only inside a paid request's job.

The token is never logged, never in a JSON body, never in an error message."""
from __future__ import annotations

import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

import voice_lock

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "panel" / "dist"
TOKEN = secrets.token_urlsafe(32)               # one per process: a restart invalidates every open page
HEADER = "X-EU-Session"
HOSTS = {"127.0.0.1:8501", "localhost:8501"}
DEV_HOSTS = {"127.0.0.1:5173", "localhost:5173"}
DEV_ENV = "EU_PANEL_DEV"                         # off unless set to 1/true: only then the Vite dev server is allowed


class GateError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def gate_error_handler(_request: Request, exc: GateError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


def allowed_hosts() -> set:
    return HOSTS | (DEV_HOSTS if os.environ.get(DEV_ENV, "").strip().lower() in {"1", "true", "yes", "on"} else set())


def check_origin(request: Request) -> None:
    """Host and Origin must both be the panel itself. A POST with no Origin is refused (a browser always sends one)."""
    allowed = allowed_hosts()
    if (request.headers.get("host") or "").lower() not in allowed:
        raise GateError(403, "Petición rechazada: el servidor solo responde en el panel local.")
    origin = request.headers.get("origin")
    if not origin or urlsplit(origin).netloc.lower() not in allowed:
        raise GateError(403, "Petición rechazada: no viene del panel.")


def check_host(request: Request) -> None:
    """GET-only, read-only routes (the event stream): the Host must be the panel's; no Origin or token is needed."""
    if (request.headers.get("host") or "").lower() not in allowed_hosts():
        raise GateError(403, "Petición rechazada: el servidor solo responde en el panel local.")


def free_post(request: Request) -> None:
    """Dependency for POSTs that spend nothing (approve, reject): the Origin/Host check only."""
    check_origin(request)


async def paid(request: Request) -> dict:
    """Dependency for every route that can spend: Origin/Host, the session token, then `"confirm": true`.
    Returns the parsed JSON body."""
    check_origin(request)
    sent = request.headers.get(HEADER) or ""
    if not secrets.compare_digest(sent.encode(), TOKEN.encode()):
        raise GateError(403, "Falta la sesión del panel. Recarga la página.")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise GateError(400, "Falta la confirmación: este paso gasta dinero.")
    return body


#: a runner is the blocking function that does the paid work; `run_job` holds the voice grant for exactly its length
Runner = Callable[[], object]


def run_job(runner: Runner, jobs: Optional[list] = None) -> threading.Thread:
    """Start `runner` in a thread under voice_lock.panel_grant(): the grant is opened for this job only and closed
    when it ends (success or error). Only a paid request's handler may call this."""
    def _go():
        try:
            with voice_lock.panel_grant():
                runner()
        except Exception:                                   # noqa: BLE001 — the grant is already closed; the job's own row records the failure
            logger.exception("paid job failed")
    t = threading.Thread(target=_go, name="paid-job", daemon=True)
    if jobs is not None:
        jobs.append(t)
    t.start()
    return t


Engine = Callable[..., Tuple[Optional[str], Optional[int], Runner]]


def inject_token(html: str) -> str:
    """index.html with `<meta name="eu-session" content="…">` just before </head> (the only place the token is served)."""
    meta = f'<meta name="eu-session" content="{TOKEN}">'
    return html.replace("</head>", meta + "</head>", 1) if "</head>" in html else meta + html


def index_response() -> HTMLResponse:
    page = DIST / "index.html"
    try:
        html = page.read_text(encoding="utf-8")
    except OSError:
        return HTMLResponse("<p>El panel nuevo aún no está compilado (panel/dist).</p>", status_code=404)
    return HTMLResponse(inject_token(html), headers={"Cache-Control": "no-store"})

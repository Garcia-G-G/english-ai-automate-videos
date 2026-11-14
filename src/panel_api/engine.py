"""STEP 85 §4: the write handlers, over panel_core. Each returns what `app.create_app` expects:
produce / rerender -> (job_id, eta_s, runner) with `runner` the blocking pipeline (run by gate.run_job under the
request's voice grant); approve / reject -> a JSON dict. Domain refusals are `gate.GateError(status, Spanish text)`."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import jobs
from panel_core import review, upload, videos
from .admin_free import script_for
from .gate import GateError

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Costa_Rica")
PLATFORMS = ("youtube", "facebook")          # what Revisar offers; TikTok is by hand


def _eta(video_type: str) -> Optional[int]:
    from panel import inicio
    rt = inicio.render_seconds(jobs.load_jobs().get("history", []), video_type or "")
    return None if rt is None else round(rt)


def _start(video_type: str, **kwargs):
    """The shared path: jobs.prepare_generation (job row first, then a blocking runner)."""
    try:
        job_id, runner = jobs.prepare_generation(video_type, **kwargs)
    except jobs.AlreadyRendering as busy:
        raise GateError(409, str(busy) or "Ya hay un vídeo renderizándose.") from busy
    return job_id, _eta(video_type), runner


def produce(script_id: Optional[str]):
    """«Producir ahora»: the engine makes the best queued script of the type (as Streamlit does, `use_queue=True`).
    With a scriptId, only the script that IS the next one of its type is accepted: a queued file produced out of
    order would stay in the queue and could be made twice."""
    from panel_core import queue_read
    if script_id is None:
        got = queue_read.next_best()
        if not got:
            raise GateError(409, "La cola está vacía: no hay guion que producir.")
        return _start(got[1].get("type") or "", use_queue=True)
    path = next((p for p in jobs._queue_guard().queued_scripts() if p.stem == script_id), None)
    if path is None:
        raise GateError(404, "Ese guion ya no está en la cola.")
    vtype = json.loads(path.read_text(encoding="utf-8")).get("type") or ""
    best = jobs.queue_pick(vtype, fresh=False)
    if not best or best[0] != path:
        raise GateError(409, "Ese guion no es el siguiente de su tipo en la cola; el motor produce siempre el mejor.")
    return _start(vtype, use_queue=True)


def _pending(item_id: str) -> Dict:
    video = next((v for v in videos.get_pending_videos() if v["name"] == item_id), None)
    if video is None:
        raise GateError(404, "No encuentro ese vídeo en «Por revisar».")
    if video["damaged"]:
        raise GateError(409, "El archivo de ese vídeo está dañado.")
    return video


def rerender(item_id: str):
    """«Volver a renderizar»: the video is rejected and its script is made again (rerender=True)."""
    video = _pending(item_id)
    script = script_for(video["path"])
    if not script:
        raise GateError(409, "No encuentro el guion de este vídeo, no se puede volver a renderizar.")
    got = _start(video["type"], script_data=script, rerender=True)
    try:
        videos.reject_video(video["path"])
    except OSError as e:
        jobs.complete_job(got[0], success=False, error=f"no se pudo apartar el vídeo anterior: {e}")
        raise GateError(500, "No pude apartar el vídeo anterior; no se renderizó.") from e
    return got


def _save_metadata(video: Dict, body: Dict) -> Dict:
    """Write the edited title, description and hashtags into the sidecar (as «Guardar en el vídeo» does), validated."""
    title, desc = (body.get("title") or "").strip(), (body.get("description") or "").strip()
    if not title:
        return video
    from metadata_generator import metadata_problems
    problems = metadata_problems(title) + metadata_problems(desc)
    if problems:
        raise GateError(400, "No se guardó el texto: " + ", ".join(problems))
    meta = dict((video["meta"] or {}).get("metadata") or {})
    hashtags = dict(meta.get("hashtags") or {})
    hashtags["youtube"] = [t for t in (body.get("hashtags") or []) if isinstance(t, str)]
    new = {**meta, "title": title, "description": desc, "hashtags": hashtags, "source": "edited"}
    path = Path(video["path"]).with_suffix(".json")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["metadata"] = new
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return {**video, "meta": {**(video["meta"] or {}), "metadata": new}}


def _parse_time(raw) -> datetime:
    try:
        at = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        raise GateError(400, "Esa fecha u hora no es válida.")
    if at.tzinfo is None:
        raise GateError(400, "La hora tiene que llevar su zona horaria (hora de Costa Rica, -06:00).")
    return at.astimezone(TZ)


def approve(item_id: str, body: Dict):
    """publishAt null: only approve («Por subir», no time, nothing uploaded). With a time: Garcia's exact minute is
    checked (lead rule refuses, spacing/count only warn) and the video goes through the same guarded upload as Streamlit."""
    import publication_log
    import slots
    video = _pending(item_id)
    platforms = [p for p in (body.get("platforms") or []) if p in PLATFORMS]
    raw = body.get("publishAt")
    video = _save_metadata(video, body)
    if raw is None:
        return review.approve(video["path"])
    if not platforms:
        raise GateError(400, "Elige al menos una plataforma.")
    at = _parse_time(raw)
    now = datetime.now(TZ)
    taken = slots.taken_titled(publication_log.read_ledger())
    script = script_for(video["path"])

    def scheduler(new_path: Path, plats: List[str], when: datetime) -> Dict[str, str]:
        moved = {**video, "path": new_path, "stage": "approved"}
        return upload.schedule_approved(moved, script, plats, when, state={})

    try:
        return review.approve(video["path"], at, platforms, scheduler=scheduler, now=now, taken=taken)
    except ValueError as refused:
        raise GateError(400, str(refused)) from refused


def reject(item_id: str, body: Dict):
    video = _pending(item_id)
    try:
        review.reject(video["path"], body.get("reason"), body.get("note") or "")
    except ValueError as bad:
        raise GateError(400, str(bad)) from bad
    return {"state": "rejected"}


REAL = {"produce": produce, "rerender": rerender, "approve": approve, "reject": reject}

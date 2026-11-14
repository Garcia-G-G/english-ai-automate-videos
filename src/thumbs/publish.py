"""STEP 85b §4: put the thumbnail on the platforms, and remember what the platforms answered.

A thumbnail failure never blocks or undoes an upload. YouTube is called only after processing has succeeded; a 403
is classified (forbidden_shorts on a vertical video, forbidden_channel on a 16:9 one) and remembered in
output/state/capabilities.json so the call is not repeated for nothing: «no» is re-checked once every 30 days.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "output" / "state" / "capabilities.json"
RECHECK_DAYS = 30
SHORTS, CHANNEL = "youtube_shorts_custom_thumbnail", "youtube_custom_thumbnail"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
FB_URL = "https://graph.facebook.com/v21.0/{id}/thumbnails"


def _read(path: Path = None) -> Dict:
    try:
        return json.loads((path or STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def capability(key: str, path: Path = None) -> Dict:
    return _read(path).get(key) or {"state": "unknown", "checked": None, "reason": "aún no se ha probado"}


def remember(key: str, state: str, reason: str, today: Optional[date] = None, path: Path = None) -> None:
    path = path or STATE
    data = _read(path)
    data[key] = {"state": state, "checked": (today or date.today()).isoformat(), "reason": reason[:200]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def should_try(key: str, today: Optional[date] = None, path: Path = None) -> bool:
    """unknown and yes: try. no: only once the 30 days are up."""
    cap = capability(key, path)
    if cap["state"] != "no":
        return True
    try:
        return (today or date.today()) >= date.fromisoformat(cap["checked"]) + timedelta(days=RECHECK_DAYS)
    except (TypeError, ValueError):
        return True


def capability_line(today: Optional[date] = None, path: Path = None) -> str:
    cap = capability(SHORTS, path)
    if cap["state"] == "no" and cap.get("checked"):
        again = date.fromisoformat(cap["checked"]) + timedelta(days=RECHECK_DAYS)
        return f"YouTube aún no deja poner miniatura a los Shorts de este canal (se vuelve a probar el {again:%d/%m})."
    if cap["state"] == "yes":
        return "YouTube acepta miniaturas propias en los Shorts de este canal."
    return "Aún no se sabe si YouTube deja poner miniatura a los Shorts de este canal: el próximo Short lo prueba."


def classify(status: int, vertical: bool) -> str:
    if 200 <= status < 300:
        return "ok"
    if status == 403:
        return "forbidden_shorts" if vertical else "forbidden_channel"
    if status == 429:
        return "rate_limited"
    return "error"


def wait_processed(video_id: str, token: str, get: Callable, sleep: Callable = time.sleep, max_seconds: float = 1800,
                   first_wait: float = 10) -> bool:
    """Poll videos.list(processingDetails) with backoff until processing succeeded (True) or the limit passes (False)."""
    waited, step = 0.0, first_wait
    while waited <= max_seconds:
        resp = get(VIDEOS_URL, params={"part": "processingDetails", "id": video_id}, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        items = (resp.json().get("items") or []) if resp.ok else []
        status = ((items[0].get("processingDetails") or {}).get("processingStatus") if items else None)
        if status == "succeeded":
            return True
        if status == "failed":
            return False
        sleep(step)
        waited += step
        step = min(step * 1.6, 120)
    return False


def youtube(video_id: str, jpg: Path, vertical: bool, token: str, get: Callable, post: Callable, sleep: Callable = time.sleep,
            today: Optional[date] = None, memo: Path = None) -> Dict:
    """{result, message}: result is ok | skipped | not_processed | forbidden_shorts | forbidden_channel | rate_limited | error."""
    key = SHORTS if vertical else CHANNEL
    if not should_try(key, today, memo):
        return {"result": "skipped", "message": capability(key, memo)["reason"]}
    if not wait_processed(video_id, token, get, sleep):
        return {"result": "not_processed", "message": "YouTube no terminó de procesar el vídeo a tiempo"}
    try:
        resp = post(THUMB_URL, params={"videoId": video_id}, headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                    data=Path(jpg).read_bytes(), timeout=120)
    except Exception as exc:                                # noqa: BLE001 — never raises into an upload
        return {"result": "error", "message": str(exc)[:200]}
    result = classify(resp.status_code, vertical)
    if result == "ok":
        remember(key, "yes", "thumbnails.set aceptado", today, memo)
    elif result.startswith("forbidden"):
        remember(key, "no", f"HTTP 403: {str(getattr(resp, 'text', ''))[:120]}", today, memo)
    return {"result": result, "message": "" if result == "ok" else f"HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:160]}"}


def facebook(video_id: str, jpg: Path, token: str, post: Callable) -> Dict:
    """POST /{video_id}/thumbnails with the image and is_preferred=true. A refusal is recorded; the reel stays."""
    try:
        resp = post(FB_URL.format(id=video_id), params={"access_token": token}, data={"is_preferred": "true"},
                    files={"source": ("thumb.jpg", Path(jpg).read_bytes(), "image/jpeg")}, timeout=120)
    except Exception as exc:                                # noqa: BLE001
        return {"result": "error", "message": str(exc)[:200].replace(token, "***")}
    if 200 <= resp.status_code < 300:
        return {"result": "ok", "message": ""}
    return {"result": "rate_limited" if resp.status_code == 429 else ("forbidden" if resp.status_code in (400, 403) else "error"),
            "message": f"HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:160]}"}


def record(sidecar: Path, platform: str, outcome: Dict) -> None:
    """Write the platform's answer into the sidecar's thumbnail.platforms."""
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    thumb = meta.setdefault("thumbnail", {})
    thumb.setdefault("platforms", {})[platform] = {**outcome, "at": datetime.now().isoformat(timespec="seconds")}
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


QUOTA_PER_UPLOAD, QUOTA_PER_THUMB, QUOTA_LIMIT, MAX_PER_DAY = 1600, 50, 10000, 4


def daily_quota(uploads: int = MAX_PER_DAY) -> Dict:
    used = uploads * (QUOTA_PER_UPLOAD + QUOTA_PER_THUMB)
    return {"used": used, "limit": QUOTA_LIMIT, "share": round(used / QUOTA_LIMIT, 3)}


LOG = ROOT / "output" / "state" / "thumb_results.jsonl"


def _log_and_record(artifact: str, platform: str, video_id: str, outcome: Dict, log: Path = None) -> Dict:
    """One JSONL line in the ledger and the answer in the sidecar of the artifact wherever it sits."""
    line = {"artifact": artifact, "platform": platform, "video_id": video_id, **outcome, "at": datetime.now().isoformat(timespec="seconds")}
    path = log or LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
    for stage in ("uploaded", "approved"):
        for side in (ROOT / "output" / stage).glob(f"*/{artifact}.json"):
            record(side, platform, outcome)
    return outcome


def after_facebook_upload(artifact: str, video_id: str, jpg: Path, token: Optional[str] = None, post: Optional[Callable] = None,
                          log: Path = None, background: bool = True):
    """After the reel is published: POST /{video_id}/thumbnails with is_preferred=true. Background, never raises, never
    touches the reel; a missing token or a refusal is recorded and the reel stays."""
    import threading
    try:
        blob = Path(jpg).read_bytes()
    except OSError:
        return None

    def work():
        import os
        import tempfile
        try:
            tok = token or os.getenv("FB_PAGE_TOKEN", "")
            if not tok:
                outcome = {"result": "forbidden", "message": "sin FB_PAGE_TOKEN"}
            else:
                import requests
                tmp = Path(tempfile.mkdtemp()) / "thumb.jpg"
                tmp.write_bytes(blob)
                outcome = facebook(video_id, tmp, tok, post or requests.post)
        except Exception as exc:                            # noqa: BLE001
            outcome = {"result": "error", "message": str(exc)[:200].replace(token or "\0", "***")}
        return _log_and_record(artifact, "facebook", video_id, outcome, log)

    if not background:
        return work()
    t = threading.Thread(target=work, name=f"thumb-fb-{artifact}", daemon=True)
    t.start()
    return t


def after_youtube_upload(artifact: str, video_id: str, jpg: Path, vertical: bool = True, token: Optional[str] = None,
                         get: Optional[Callable] = None, post: Optional[Callable] = None, log: Path = None,
                         background: bool = True, memo: Path = None):
    """Called after a successful YouTube upload. Runs in a daemon thread (the panel never waits for YouTube's
    processing), reads the image NOW (the folder moves with the video), never raises, logs the outcome as one JSONL
    line and updates the sidecar of the artifact wherever it sits."""
    import threading
    try:
        blob = Path(jpg).read_bytes()
    except OSError:
        return None

    def work():
        import tempfile
        import requests
        try:
            tok = token
            if tok is None:
                import channel_stats
                tok = channel_stats._youtube_token()
            tmp = Path(tempfile.mkdtemp()) / "thumb.jpg"
            tmp.write_bytes(blob)
            outcome = youtube(video_id, tmp, vertical, tok, get or requests.get, post or requests.post, memo=memo)
        except Exception as exc:                            # noqa: BLE001 — a thumbnail never touches the upload
            outcome = {"result": "error", "message": str(exc)[:200]}
        return _log_and_record(artifact, "youtube", video_id, outcome, log)

    if not background:
        return work()
    t = threading.Thread(target=work, name=f"thumb-{artifact}", daemon=True)
    t.start()
    return t

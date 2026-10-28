"""STEP 80 §5: an AI background clip behind the notebook, as an A/B test.

A 4 s, 9:16, 720p clip without audio from `google/veo-3.1-lite` through OpenRouter's video API
($0.03 a second, so $0.12), prompted from the topic: a calm, on-theme scene. It replaces the stock
footage behind the page (a one-clip library: it loops with a slow crossfade); frame 1 still shows
the list. Cached per topic, forever:

    assets/ai_backgrounds/<topic>/clip.mp4

Every other `how_do_you_say` render is the «ia» group (when its topic has a clip), the rest «stock»;
each render's group is appended to output/stats/background_ab.jsonl, which the stats join by
artifact. «Rendimiento» compares the groups once each has MIN_PER_GROUP videos older than 3 days.

Drawing a clip happens only from the panel's own click, under the voice lock and the OpenRouter caps.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "assets" / "ai_backgrounds"
AB_LOG = ROOT / "output" / "stats" / "background_ab.jsonl"
API = "https://openrouter.ai/api/v1/videos"
MODEL = "google/veo-3.1-lite"
SECONDS = 4
PRICE_PER_S = 0.03                       # 720p without audio, OpenRouter's listed SKU (26 Oct 2026)
MIN_PER_GROUP = 8
AB_TYPES = {"how_do_you_say"}
PROMPT = ("A calm, slow, softly lit vertical scene about «{topic}»: on theme, no people's faces in close-up, "
          "no text, no letters, no logos, gentle camera drift, warm and inviting, shallow depth of field. "
          "It sits behind a notebook page, so keep the centre simple.")


def estimate_usd() -> float:
    return round(SECONDS * PRICE_PER_S, 3)


def clip_dir(topic: str) -> Path:
    import illustrations
    return LIBRARY / (illustrations.slug(topic) or "tema")


def cached(topic: str) -> Optional[Path]:
    clip = clip_dir(topic) / "clip.mp4"
    return clip if clip.is_file() and clip.stat().st_size > 0 else None


def _log_rows() -> List[Dict]:
    if not AB_LOG.exists():
        return []
    rows = []
    for line in AB_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def assign(artifact: str, video_type: str, topic: str) -> Dict:
    """This render's group, logged: «ia» every other render of an A/B type when the topic has a
    clip, else «stock» (with why). {variant, background (a clips: dir or None), why}."""
    if video_type not in AB_TYPES:
        return {"variant": None, "background": None, "why": "fuera del A/B"}
    turn = sum(1 for r in _log_rows() if r.get("video_type") == video_type)
    clip = cached(topic)
    if turn % 2 == 1:
        out = {"variant": "stock", "background": None, "why": "turno de stock"}
    elif clip is None:
        out = {"variant": "stock", "background": None, "why": "turno de IA, pero el tema no tiene clip"}
    else:
        out = {"variant": "ia", "background": f"clips:{clip.parent}", "why": "turno de IA"}
    AB_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AB_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"artifact": artifact, "video_type": video_type, "topic": topic,
                            "variant": out["variant"], "why": out["why"],
                            "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    return out


def variants() -> Dict[str, str]:
    """{artifact: variant} from the A/B log."""
    return {r["artifact"]: r["variant"] for r in _log_rows() if r.get("artifact") and r.get("variant")}


def compare(videos: List[Dict], mature_days: int = 3) -> Dict:
    """The two groups' views (videos older than mature_days). `ready` once each has MIN_PER_GROUP."""
    groups: Dict[str, List[int]] = {"ia": [], "stock": []}
    for v in videos:
        g = v.get("background_variant")
        if g in groups and (v.get("days") or 0) > mature_days:
            groups[g].append(int(v.get("views", 0)))
    ready = all(len(vs) >= MIN_PER_GROUP for vs in groups.values())
    return {"ready": ready, "groups": {g: {"n": len(vs), "median": statistics.median(vs) if vs else None,
                                           "mean": round(statistics.mean(vs), 1) if vs else None}
                                       for g, vs in groups.items()}}


# ── drawing a clip: only from the panel ──────────────────────────────────────

def _call(request, opener, timeout=60):
    with opener(request, timeout=timeout) as response:
        return response.read()


def generate(topic: str, opener=None, sleep=time.sleep, poll_s: float = 15.0, max_wait_s: float = 600.0) -> Path:
    """Draw and cache the topic's clip; returns its path. Checked against the caps and the lock
    before anything is sent, logged once it comes back."""
    import secret_store
    import tts_openrouter
    import voice_lock
    from cost_tracker import get_tracker
    have = cached(topic)
    if have is not None:
        return have
    price = estimate_usd()
    tts_openrouter.check_caps(price)
    voice_lock.check(f"un fondo IA para «{topic}» en OpenRouter ({MODEL}, ${price:.2f})")
    key = secret_store.get(tts_openrouter.KEY_NAME)
    if not key:
        raise tts_openrouter.OpenRouterRefused("No hay clave de OpenRouter. No se pidió nada.")
    opener = opener or urllib.request.urlopen
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "English Unlimited"}
    body = json.dumps({"model": MODEL, "prompt": PROMPT.format(topic=topic), "duration": SECONDS,
                       "aspect_ratio": "9:16", "resolution": "720p", "generate_audio": False}).encode()
    job = json.loads(_call(urllib.request.Request(API, data=body, method="POST", headers=headers), opener))
    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"OpenRouter no aceptó el vídeo: {str(job)[:160]}")
    waited, state = 0.0, job
    while state.get("status") not in ("completed", "failed", "cancelled", "expired"):
        if waited >= max_wait_s:
            raise RuntimeError(f"el vídeo {job_id} no terminó en {max_wait_s:.0f} s")
        sleep(poll_s)
        waited += poll_s
        state = json.loads(_call(urllib.request.Request(f"{API}/{job_id}", headers=headers), opener))
    if state["status"] != "completed":
        raise RuntimeError(f"el vídeo {job_id} terminó «{state['status']}»: {str(state.get('error'))[:160]}")
    data = _call(urllib.request.Request(f"{API}/{job_id}/content?index=0", headers=headers), opener, timeout=180)
    target = clip_dir(topic) / "clip.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    cost = float((state.get("usage") or {}).get("cost") or price)
    get_tracker()._add_entry("openrouter_video", MODEL, round(cost, 4), "ai_background",
                             {"topic": topic, "seconds": SECONDS, "provider": "openrouter", "job": job_id})
    return target

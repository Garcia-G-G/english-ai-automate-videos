"""STEP 85 §2: the read side of the contract (panel/src/api/contract.ts), built from panel_core and the engine's
own functions. Nothing here invents a value: what the engine does not know is None. Results are cached on the
mtimes of the files they read (`cached`), so a repeated call costs a few stat() calls."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import jobs
from panel_core import costs, counts, game, jobstate, queue_read, schedule, thumbnails, videos
from . import media
from .admin_free import script_for

ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("America/Costa_Rica")
STARTED_AT = datetime.now(TZ).isoformat(timespec="seconds")
THUMBS_ROOT = ROOT / "output" / "thumbs" / "scripts"          # drawn frame 0 of queued scripts (STEP 83 §2)
STREAMLIT_URL = "http://localhost:8501"
FAMILIES = {"casa", "comida", "cuerpo", "animales", "ropa", "ciudad", "emociones", "clima", "vida", "reto", "test"}
#: one colour per format for the bars; a format not listed takes the next of FALLBACK_COLORS
FORMAT_COLORS = {"how_do_you_say": "#1F6FD1", "level_test": "#FF6F4F", "phrases_level": "#12854F", "vocabulary": "#2BB5A8",
                 "say_it_level": "#8A5CD6"}
FALLBACK_COLORS = ["#E0A21B", "#C2437A", "#5B6770", "#7A9E2E"]
STRIP_LABELS = ["0 %", "25 %", "50 %", "75 %", "final", "fin"]

_CACHE: Dict[str, tuple] = {}


def cached(key: str, fingerprint: Callable[[], tuple], build: Callable[[], dict]) -> dict:
    fp = fingerprint()
    hit = _CACHE.get(key)
    if hit and hit[0] == fp:
        return hit[1]
    value = build()
    _CACHE[key] = (fp, value)
    return value


def _mt(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _tree_mtimes(root: Path, pattern: str = "*") -> tuple:
    """The mtime of a folder and of every file in its immediate subfolders: a file added, removed or rewritten changes it."""
    out = [_mt(root)]
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir():
                out.append((d.name, _mt(d), tuple(_mt(f) for f in sorted(d.glob(pattern)))))
    return tuple(out)


def iso_cr(naive: Optional[str]) -> Optional[str]:
    """A naive local timestamp the engine wrote → ISO with the Costa Rica offset; None when unreadable."""
    try:
        t = datetime.fromisoformat(naive)
    except (TypeError, ValueError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=TZ)).isoformat(timespec="seconds")


def type_label(video_type: str) -> str:
    """admin.type_label without Streamlit: the type's own panel name, else the key made readable."""
    import series
    import video_types
    if video_type == series.PANEL_LABEL:
        return video_type
    own = (video_types.TYPES.get(video_type) or {}).get("dashboard")
    return own or {"true_false": "True/False"}.get(video_type, str(video_type).replace("_", " ").title())


def _config() -> Dict:
    import queue_priority
    return queue_priority._config()


_SHA: List[str] = []


def _version() -> str:
    if not _SHA:
        try:
            _SHA.append(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                       text=True, timeout=5).stdout.strip() or "?")
        except Exception:                                   # noqa: BLE001
            _SHA.append("?")
    return _SHA[0]


# ── /api/meta ────────────────────────────────────────────────────────

def _stats_files() -> List[Path]:
    import channel_stats
    return sorted(channel_stats.STATS_DIR.glob("youtube_*.json"))


def _meta_fp() -> tuple:
    import comments
    import publication_log
    files = _stats_files()
    return (_tree_mtimes(jobs.PENDING_DIR), _tree_mtimes(jobs.APPROVED_DIR), _mt(comments.THREADS), _mt(ROOT / "config.yaml"),
            files[-1].name if files else None, _mt(files[-1]) if files else 0, _mt(publication_log.LEDGER_PATH),
            _tree_mtimes(ROOT / "content" / "queue", "*.json"))


def meta() -> dict:
    return cached("meta", _meta_fp, _meta)


def _meta() -> dict:
    cfg = _config()
    try:
        import tts_openrouter
        spent, cap = tts_openrouter.month_spend(), tts_openrouter._settings()["monthly_usd"]
    except Exception:                                       # noqa: BLE001 — the frame must draw
        spent, cap = None, 15.0
    try:
        import cost_tracker
        stats = cost_tracker.video_cost_stats(cost_tracker.per_video_costs())
        mean = stats["mean_usd"] if stats["videos"] else None
    except Exception:                                       # noqa: BLE001
        mean = None
    try:
        per_cap = float((cfg.get("costs") or {}).get("openrouter_per_short_usd"))
    except (TypeError, ValueError):
        per_cap = None
    files = _stats_files()
    read_at = None
    if files:
        try:
            read_at = iso_cr(json.loads(files[-1].read_text(encoding="utf-8")).get("read_at"))
        except (OSError, ValueError):
            pass
    return {"version": _version(), "startedAt": STARTED_AT,
            "ownerName": (cfg.get("panel") or {}).get("owner_name", "Garcia"),
            "openrouter": {"spentUsd": spent, "capUsd": cap, "perVideoAvgUsd": mean, "perVideoCapUsd": per_cap},
            "elevenlabsChars": None,                         # no remaining-characters source in the engine: «sin dato»
            "statsReadAt": read_at, "counts": counts.sidebar_counts(), "streamlitUrl": STREAMLIT_URL}


# ── /api/home ────────────────────────────────────────────────────────

def _emoji_of(text: str) -> Optional[str]:
    m = re.search(r"([\U0001F300-\U0001FAFF☀-➿])", text or "")
    return m.group(1) if m else None


def _webp(png: Path, width: int) -> Optional[Path]:
    """A cached WebP of a PNG, rebuilt only when the PNG is newer (the drawn frame 0 of a queued script)."""
    out = png.with_name(f"{png.stem}_{width}.webp")
    try:
        if not out.exists() or out.stat().st_mtime < png.stat().st_mtime:
            from PIL import Image
            Image.open(png).convert("RGB").resize((width, width * 16 // 9)).save(out, "WEBP", quality=82)
    except Exception:                                       # noqa: BLE001 — a missing thumb is null, never an error
        return None
    return out


def _script_thumb(stem: str, script: Dict, path: Path) -> Optional[Dict]:
    from panel import inicio
    try:
        png = inicio.frame0_png(stem, script, path.stat().st_mtime, THUMBS_ROOT)
    except Exception:                                       # noqa: BLE001
        return None
    w = _webp(png, 270) if png else None
    src = media.url_for(w) if w else None
    if not src:
        return None
    w2 = _webp(png, 540)
    return {"src": src, **({"src2x": media.url_for(w2)} if w2 and media.url_for(w2) else {})}


def _topic(title: str) -> str:
    m = re.search(r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,}[A-ZÁÉÍÓÚÑ])", title or "")
    return m.group(1) if m else (title or "")


def _next(next_slot: Optional[datetime]) -> Optional[Dict]:
    got = queue_read.next_best()
    if not got:
        return None
    path, data, _why = got
    import channel_stats
    import queue_priority as qp
    from panel import inicio
    snap = channel_stats.latest() or {}
    cfg = qp.settings()
    vtype = data.get("type") or ""
    f, t = qp.format_score(vtype, snap, cfg), qp.topic_score(data, snap, cfg)
    title = data.get("video_title") or data.get("theme") or path.stem
    tone = "good" if t[0] > 1 else ("warn" if t[0] < 0.5 else "neutral")
    try:
        import repetition
        repeated = len(repetition.repeated(data, path))
    except Exception:                                       # noqa: BLE001
        repeated = None
    try:
        import duration_spec
        dur = duration_spec.band(vtype)["target_seconds"]
    except Exception:                                       # noqa: BLE001
        dur = None
    rt = inicio.render_seconds(jobs.load_jobs().get("history", []), vtype)
    family = None
    if vtype == "how_do_you_say" and data.get("items"):
        try:
            from video.tablero import frame as F, kit
            fam = (data.get("tablero_family") or kit.family_for(F.topic(data))).split()[0]
            family = fam if fam in FAMILIES else None
        except Exception:                                   # noqa: BLE001
            family = None
    return {"scriptId": path.stem, "type": vtype, "typeLabel": type_label(vtype), "title": title, "topic": _topic(title),
            "emoji": _emoji_of(title) or (str(data["items"][0].get("emoji")) if data.get("items") else None),
            "family": family, "slot": f"{next_slot:%H:%M}" if next_slot else None,
            "tags": [{"label": t[1], "tone": tone}, {"label": f"{type_label(vtype)}: {f[1]}", "tone": "neutral"}],
            "words": [i.get("english", "") for i in (data.get("items") or [])][:10],
            "facts": {"durationS": dur, "costUsd": jobs.batch_estimate_usd(1), "renderMin": None if rt is None else round(rt / 60),
                      "repeated": repeated},
            "thumb": _script_thumb(path.stem, data, path), "xp": game.BASE_XP}   # 40 published + 10 approved; the +100 is not promised


def _views_block(today: date) -> Optional[Dict]:
    """Last 28 days against the 28 before, from senal.json (per-video daily curves summed by calendar day)."""
    import senal
    try:
        s = json.loads((senal.SENAL_DIR / "senal.json").read_text(encoding="utf-8"))
        until = date.fromisoformat(s["data_until"])
    except (OSError, ValueError, KeyError):
        return None
    by_day: Dict[date, int] = {}
    uploads: Dict[date, int] = {}
    first = None
    for v in s["videos"]:
        pub = date.fromisoformat(v["published"])
        first = pub if first is None or pub < first else first
        uploads[pub] = uploads.get(pub, 0) + 1
        for i, n in enumerate(v["daily"]):
            by_day[pub + timedelta(days=i)] = by_day.get(pub + timedelta(days=i), 0) + int(n or 0)
    days = [until - timedelta(days=27 - k) for k in range(28)]
    prev = [d - timedelta(days=28) for d in days]
    have_prev = first is not None and first <= prev[-1]
    snap = [v for v in ((__import__("channel_stats").latest() or {}).get("videos") or [])]
    return {"periodDays": 28, "views": sum(by_day.get(d, 0) for d in days),
            "prevViews": sum(by_day.get(d, 0) for d in prev) if have_prev else None,
            "daily": [{"date": d.isoformat(), "views": by_day.get(d, 0), "uploads": uploads.get(d, 0)} for d in days],
            "totals": {"views": sum(int(v.get("views") or 0) for v in snap), "subs": sum(int(v.get("subs_gained") or 0) for v in snap),
                       "likes": sum(int(v.get("likes") or 0) for v in snap)},
            "dataUntil": until.isoformat()}


def _formats(vids: List[Dict]) -> tuple:
    import channel_stats
    rows = [f for f in (channel_stats.summary(vids)["formats"] if vids else []) if f["type"] not in ("", "—")]   # untyped uploads are not a format
    ranked = sorted(((f["mature_median"] if f["mature_median"] is not None else f["median"], f) for f in rows), key=lambda x: -x[0])[:5]
    spare = iter(FALLBACK_COLORS)
    out = [{"key": f["type"], "label": type_label(f["type"]), "median": round(m), "videos": f["count"],
            "color": FORMAT_COLORS.get(f["type"]) or next(spare, "#5B6770")} for m, f in ranked]
    note = None
    if len(out) >= 2 and out[1]["median"] and out[0]["median"] >= 2 * out[1]["median"]:
        note = f"«{out[0]['label']}» duplica a casi todo lo demás."          # rule: the top median is at least 2x the second
    return out, note


def _home_fp() -> tuple:
    import publication_log
    import senal
    return _meta_fp() + (_mt(senal.SENAL_DIR / "senal.json"), _mt(jobs.JOBS_FILE), int(time.time() // 60))


def home() -> dict:
    return cached("home", _home_fp, _home)


def _home(now: Optional[datetime] = None) -> dict:
    import channel_stats
    import daily_mix
    import publication_log
    import slots
    from datetime import time as dtime
    from panel import inicio
    now = now or datetime.now(TZ)
    cfg = slots.settings()
    snap = channel_stats.latest() or {}
    vids = snap.get("videos", [])
    ledger = publication_log.read_ledger()
    today_slots = [datetime.combine(now.date(), dtime.fromisoformat(t), TZ) for t in cfg["slots"]]
    try:
        bad = queue_read.bad_scripts()
        ranked = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in queue_read.queue_order(jobs._queue_guard().queued_scripts())
                  if p.relative_to(ROOT) not in bad]
    except Exception:                                       # noqa: BLE001
        ranked = []
    states0 = inicio.slot_states(now, today_slots, ledger, vids, {})
    free = [x["at"] for x in states0 if x["state"] == "free" and x["at"] > now]
    plan = slots.fill_plan(free, ranked, daily_mix.uploads_on(ledger, now.date())) if free else []
    fill = {at: (p.stem if p else "") for at, _w, p in plan}
    states = inicio.slot_states(now, today_slots, ledger, vids, fill)
    today = [{"time": f"{s['at']:%H:%M}", "state": s["state"], "title": s.get("title") or None, "emoji": _emoji_of(s.get("title") or ""),
              "views": s.get("views"), "platforms": s.get("platforms") or [], "fillsWith": s.get("fills") or None} for s in states]
    formats, note = _formats(vids)
    try:
        themes = [str(d.get("theme") or "") for _p, d in ranked]
        sequels = [{"topic": f"MÁS {x['category']}", "emoji": None, "parentViews": x["views"]}
                   for x in channel_stats.sequel_suggestions(vids, themes)[:3]]
    except Exception:                                       # noqa: BLE001
        sequels = []
    return {"daySentence": inicio.slots_sentence(states, now), "next": _next(free[0] if free else None),
            "agenda": {"tz": cfg["tz"], "today": today,
                       "tomorrow": {"slots": len(cfg["slots"]), "scripted": max(0, min(len(cfg["slots"]), len(ranked) - len(free)))}},
            "views": _views_block(now.date()), "formats": formats, "formatsNote": note, "sequels": sequels}


# ── /api/review ──────────────────────────────────────────────────────

def _strip(mp4: Path) -> List[Dict]:
    """The six tiles of the strip as six WebPs next to the MP4 (cut from the cached sprite, rebuilt with it)."""
    from panel import revisar
    f0, sprite = revisar.frames(mp4)
    if not sprite:
        return []
    from PIL import Image
    out = []
    for k, label in enumerate(STRIP_LABELS):
        p = mp4.with_name(f"{mp4.stem}_s{k}.webp")
        if not p.exists() or p.stat().st_mtime < sprite.stat().st_mtime:
            im = Image.open(sprite)
            if (k + 1) * 186 > im.width + 6:
                break
            im.crop((k * 186, 0, k * 186 + 180, im.height)).save(p, "WEBP", quality=80)
        src = media.url_for(p)
        if src:
            out.append({"label": label, "src": src})
    return out


def _placeholder_uri(b64: Optional[str]) -> Optional[str]:
    """thumb.json keeps the blurred placeholder as 2x3 RGB pixels in base64; the contract wants a data: URI."""
    import base64
    import io
    try:
        raw = base64.b64decode(b64 or "")
        if len(raw) != 18:
            return None
        from PIL import Image
        buf = io.BytesIO()
        Image.frombytes("RGB", (2, 3), raw).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:                                       # noqa: BLE001
        return None


def _frame0(mp4: Path) -> Dict:
    t = thumbnails.thumb_paths(mp4)
    if t and t["webp270"]:
        d = {"src": media.url_for(t["webp270"])}
        if t["webp540"]:
            d["src2x"] = media.url_for(t["webp540"])
        if _placeholder_uri(t.get("placeholder")):
            d["placeholder"] = _placeholder_uri(t["placeholder"])
        return d
    from panel import revisar
    f0, _ = revisar.frames(mp4)
    return {"src": media.url_for(f0) if f0 else None}


_CHECK_KEYS = {"volume": "loudness", "words": "repeats"}


def _youtube_tags(raw) -> List[str]:
    """The sidecar keeps hashtags per platform ({youtube: [...]}); older ones are a plain list."""
    tags = raw.get("youtube") if isinstance(raw, dict) else raw
    return [t for t in (tags or []) if isinstance(t, str)]


def _review_item(v: Dict) -> Dict:
    from panel import revisar
    mp4: Path = v["path"]
    meta_ = v["meta"] or {}
    md = meta_.get("metadata") or {}
    script = script_for(mp4)
    try:
        import repetition
        known = [c for c in repetition.corpus(script.get("type") or v["type"]) if c[2] and repetition.words(script) != c[1]]
        repeated = len(repetition.repeated(script, None, known)) if script else None
    except Exception:                                       # noqa: BLE001
        repeated = None
    title, desc = md.get("title", ""), md.get("description", "")
    try:
        from upload_guard import content_refusal
        cr = content_refusal(title=title or None, description=desc or None)
        problem, checked = (cr.reason if cr else None), bool(title)
    except Exception:                                       # noqa: BLE001
        problem, checked = None, False
    rows = revisar.checks(meta_, repeated, problem, checked)
    ok = {"ok": True, "bad": False, "none": None}
    good = sum(1 for r in rows if r["state"] == "ok")
    gate = meta_.get("gate")
    verdict = revisar.verdict(meta_, rows)
    return {"id": v["name"], "type": v["type"], "typeLabel": type_label(v["type"]),
            "design": (script.get("design_variant") or "tablero").capitalize() if script else None,
            "items": len(script.get("items") or []) if script else None,
            "title": title or v["name"], "description": desc, "hashtags": [h if h.startswith("#") else f"#{h}" for h in _youtube_tags(md.get("hashtags"))],
            "durationS": revisar.duration_seconds(mp4), "costUsd": revisar.cost_of(meta_),
            "frame0": _frame0(mp4), "strip": _strip(mp4), "videoUrl": media.url_for(mp4) or "",
            "checks": [{"key": _CHECK_KEYS.get(r["key"], r["key"]), "label": r["label"], "ok": ok[r["state"]],
                        "detail": None if r["state"] == "none" else r["value"]} for r in rows],
            "gate": {"passed": good, "total": len(rows), "reason": verdict if gate and gate != "PASS" else None}}


def platforms() -> List[Dict]:
    """The three platforms Revisar offers (as the Streamlit toggles do); TikTok is by hand."""
    return [{"key": "youtube", "label": "YouTube", "mode": "auto", "enabled": True, "note": "privado → público a la hora"},
            {"key": "facebook", "label": "Facebook", "mode": "auto", "enabled": True, "note": "Reel programado"},
            {"key": "tiktok", "label": "TikTok", "mode": "manual", "enabled": False, "note": "a mano"}]


def _review_fp() -> tuple:
    return _home_fp()


def review() -> dict:
    return cached("review", _review_fp, _review)


def _review() -> dict:
    items = [_review_item(v) for v in videos.get_pending_videos() if not v["damaged"]]
    return {"items": items, "schedule": schedule.schedule_info(), "platforms": platforms()}


# ── /api/jobs/{id} ───────────────────────────────────────────────────

def job(job_id: str) -> Optional[dict]:
    j = jobstate.get_job(job_id)
    if j is None:
        return None
    from panel import inicio
    state = "failed" if j.get("status") == "failed" else ("done" if j.get("status") == "completed" else "running")
    log: List[str] = []
    if j.get("log_path"):
        try:
            log = [ln for ln in Path(j["log_path"]).read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()][-8:]
        except OSError:
            pass
    eta = inicio.render_seconds(jobs.load_jobs().get("history", []), j.get("video_type") or "")
    started = iso_cr(j.get("created_at"))
    if eta is not None and state == "running" and started:
        eta = max(0, round(eta - (datetime.now(TZ) - datetime.fromisoformat(started)).total_seconds()))
    return {"id": j["id"], "scriptId": (j.get("script_key") or "").split(":")[0] or None, "title": j.get("topic") or j.get("current_step"),
            "topic": j.get("topic"), "startedAt": started, "etaS": None if eta is None or state != "running" else round(eta),
            "state": state, "steps": j["steps"], "log": log, "error": j.get("error")}

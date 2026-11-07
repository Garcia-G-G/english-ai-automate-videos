"""Señal: score each video against the typical curve of its format. Pure functions here."""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SENAL_DIR = ROOT / "output" / "senal"

BREAKOUT_SCORE = 2.0
BREAKOUT_MIN_VIEWS = 300
COLD_SCORE = 0.5
WHY_RATIO = 1.5
DAYS = 14
COHORT_DAYS = 90
MIN_COHORT = 8
SECOND_WIND_MIN = 20  # a day-3+ rise under 20 views is noise


def typical(videos: list[dict], fmt: str, today: date, exclude: str | None = None):
    """(daily, cum) median curves for ages 0..DAYS; age = len(daily) - 1."""
    recent = [v for v in videos if v["id"] != exclude
              and (today - date.fromisoformat(v["published"])).days <= COHORT_DAYS]
    cohort = [v for v in recent if v["format"] == fmt]
    if len(cohort) < MIN_COHORT:
        cohort = recent
    daily, cum, total = [], [], 0.0
    for a in range(DAYS + 1):
        vals = [v["daily"][a] for v in cohort if len(v["daily"]) > a]
        m = median(vals) if vals else 0
        total += m
        daily.append(m)
        cum.append(total)
    return daily, cum


def score(daily: list[int], cum_typical: list[float]) -> float | None:
    if not daily:
        return None
    typ = cum_typical[min(len(daily) - 1, len(cum_typical) - 1)]
    return sum(daily) / typ if typ else None


def state(daily: list[int], score: float | None, views: int) -> str:
    if score is not None and score >= BREAKOUT_SCORE and views >= BREAKOUT_MIN_VIEWS:
        return "breakout"
    old = len(daily) - 1 >= 3
    if old and daily[-1] >= SECOND_WIND_MIN and daily[-1] > daily[-2]:
        return "second_wind"
    if old and score is not None and score < COLD_SCORE:
        return "cold"
    return "normal"


def _ratio(value, base):
    if not value:
        return 0.0
    return value / base if base else float("inf")


def why(video: dict, medians: dict, channel_sources: dict) -> list[str]:
    views = video["views"]
    if not views:
        return []
    src = video["sources"]
    ratios = {
        "search": _ratio(src.get("YT_SEARCH", 0), channel_sources.get("YT_SEARCH", 0)),
        "external": _ratio(src.get("EXT", 0), channel_sources.get("EXT", 0)),
        "retention": _ratio(video["retention"], medians["retention"]),
        "shares": _ratio(video["shares"] * 1000 / views, medians["shares_per_1k"]),
        "subs": _ratio(video["subs"] * 1000 / views, medians["subs_per_1k"]),
    }
    return sorted((k for k, r in ratios.items() if r > WHY_RATIO), key=lambda k: -ratios[k])


# --- engine: read Analytics, write senal.json -------------------------------------------------

def _report(token: str, get, **params) -> list[list]:
    from channel_stats import YOUTUBE_ANALYTICS
    resp = get(YOUTUBE_ANALYTICS, params={"ids": "channel==MINE", **params},
               headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("rows") or []


def fetch_daily(video_id: str, start: date, end: date, token: str, get) -> dict[str, int]:
    rows = _report(token, get, startDate=start.isoformat(), endDate=end.isoformat(), metrics="views",
                   dimensions="day", filters=f"video=={video_id}")
    return {r[0]: int(r[1]) for r in rows}


def fetch_sources(video_id: str | None, start: date, end: date, token: str, get) -> dict[str, float]:
    extra = {"filters": f"video=={video_id}"} if video_id else {}
    rows = _report(token, get, startDate=start.isoformat(), endDate=end.isoformat(), metrics="views",
                   dimensions="insightTrafficSourceType", **extra)
    out: dict[str, float] = {}
    for kind, views in rows:
        key = kind if kind in ("SHORTS", "YT_SEARCH") else "EXT"
        out[key] = out.get(key, 0) + views
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total else {}


def estimate_tail(daily: list[int], data_until: date, published: date, snapshots: list[tuple[date, int]]):
    """Fill the days Analytics has not reached from consecutive live view counts."""
    daily, est_from = list(daily), None
    snaps = sorted(snapshots)
    for (d0, v0), (d1, v1) in zip(snaps, snaps[1:]):
        if d0 < data_until or len(daily) > DAYS or (d1 - published).days != len(daily):
            continue
        est_from = len(daily) if est_from is None else est_from
        daily.append(max(0, v1 - v0))
    return daily, est_from


def _med(values, default=0):
    values = [v for v in values if v is not None]
    return round(median(values), 2) if values else default


def build_payload(videos: list[dict], channel_sources: dict, read_at: str, data_until: date, today: date) -> dict:
    window = [v for v in videos if (today - date.fromisoformat(v["published"])).days <= COHORT_DAYS]
    medians = {
        "retention": _med(v["retention"] for v in window),
        "shares_per_1k": _med(v["shares"] * 1000 / v["views"] for v in window if v["views"]),
        "subs_per_1k": _med(v["subs"] * 1000 / v["views"] for v in window if v["views"]),
    }
    curves = {f: typical(videos, f, today) for f in sorted({v["format"] for v in videos}) + ["all"]}
    out = []
    for v in videos:
        _, cum = typical(videos, v["format"], today, exclude=v["id"])
        sc = score(v["daily"], cum)
        out.append({**v, "platform": "youtube", "daily": v["daily"][:DAYS + 1],
                    "age_days": (today - date.fromisoformat(v["published"])).days,
                    "score": None if sc is None else round(sc, 2), "state": state(v["daily"], sc, v["views"]),
                    "why": why(v, medians, channel_sources)})
    fresh = [v for v in out if v["age_days"] <= DAYS and v["state"] in ("breakout", "second_wind")]
    star = max(fresh, key=lambda v: v["score"] or 0)["id"] if fresh else None
    return {"version": 1, "read_at": read_at, "data_until": data_until.isoformat(), "platforms": ["youtube"],
            "channel": {"typical_daily": {k: [round(x, 1) for x in c[0]] for k, c in curves.items()},
                        "typical_cum": {k: [round(x, 1) for x in c[1]] for k, c in curves.items()},
                        "sources": channel_sources, "median": medians},
            "videos": out, "star": {"youtube": star}}


def refresh(today: date | None = None, get=None, token: str | None = None) -> Path:
    import channel_stats as cs
    import requests
    today, get = today or date.today(), get or requests.get
    token = token or cs._youtube_token()          # raises before anything is touched
    snap_path = cs.STATS_DIR / f"youtube_{today.isoformat()}.json"
    if not snap_path.exists():
        cs.refresh(today, get, token)             # tomorrow's estimate diffs against this
    rows = [r for r in json.loads(snap_path.read_text(encoding="utf-8"))["videos"]
            if r.get("days") is not None and r["days"] <= COHORT_DAYS + DAYS]
    history: dict[str, list[tuple[date, int]]] = {}
    for f in sorted(cs.STATS_DIR.glob("youtube_*.json")):
        day = date.fromisoformat(f.stem.removeprefix("youtube_"))
        for r in json.loads(f.read_text(encoding="utf-8"))["videos"]:
            history.setdefault(r["id"], []).append((day, r["views"]))
    raw = []
    for r in rows:
        pub = today - timedelta(days=r["days"])
        by_day = fetch_daily(r["id"], pub, min(today, pub + timedelta(days=DAYS)), token, get)
        raw.append((r, pub, by_day, fetch_sources(r["id"], pub, min(today, pub + timedelta(days=DAYS)), token, get)))
    data_until = max((date.fromisoformat(d) for _, _, by_day, _ in raw for d in by_day), default=today - timedelta(days=2))
    videos = []
    for r, pub, by_day, sources in raw:
        n = min(DAYS, (data_until - pub).days)
        daily = [by_day.get((pub + timedelta(days=i)).isoformat(), 0) for i in range(n + 1)]
        daily, est_from = estimate_tail(daily, data_until, pub, history.get(r["id"], []))
        videos.append({"id": r["id"], "format": r.get("type") or "", "published": pub.isoformat(),
                       "daily": daily, "est_from": est_from, "views": r["views"],
                       "retention": r.get("avg_view_pct"), "sources": sources,
                       "shares": r.get("shares") or 0, "subs": r.get("subs_gained") or 0})
    channel = fetch_sources(None, today - timedelta(days=COHORT_DAYS), data_until, token, get)
    payload = build_payload(videos, channel, datetime.now().isoformat(timespec="seconds"), data_until, today)
    SENAL_DIR.mkdir(parents=True, exist_ok=True)
    path, tmp = SENAL_DIR / "senal.json", SENAL_DIR / "senal.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def refresh_if_stale(max_age_hours: int = 24, **kw) -> Path | None:
    path = SENAL_DIR / "senal.json"
    try:
        age = datetime.now() - datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["read_at"])
        if age < timedelta(hours=max_age_hours):
            return None
    except (OSError, ValueError, KeyError):
        pass
    return refresh(**kw)

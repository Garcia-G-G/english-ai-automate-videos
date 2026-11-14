"""STEP 80 §2: what the channel's videos actually did, read from YouTube (free, read-only).

`refresh()` — the panel's «Actualizar estadísticas» — reads YouTube Data API `videos.list`
(statistics, snippet) for every YouTube video in output/published/ledger.jsonl, with the uploader's
own token (refreshed and saved the way the uploader does, after a snapshot of .tokens), and writes
output/stats/youtube_YYYY-MM-DD.json. Facebook reels: their views when the Page token allows
(`video_insights`), else a note.

`latest()` reads the newest snapshot; `summary(rows)` gives what «Rendimiento» shows.
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "output" / "published" / "ledger.jsonl"
STATS_DIR = ROOT / "output" / "stats"
TOKENS = ROOT / ".tokens"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
#: A video younger than this is not judged yet (STEP 80 §2).
MATURE_DAYS = 3

_HDYS = re.compile(r"se dicen?\s+(?:los |las |el |la )?(.+?)\s+en ingl", re.I)


def youtube_rows(ledger: Optional[Path] = None) -> List[Dict]:
    """One row per YouTube video in the ledger: id, type, title, when."""
    ledger = ledger or LEDGER
    out, seen = [], set()
    if not ledger.exists():
        return out
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("platform") != "youtube" or not row.get("upload_id") or row["upload_id"] in seen:
            continue
        seen.add(row["upload_id"])
        out.append({"id": row["upload_id"], "artifact": row.get("artifact"), "type": row.get("video_type") or "",
                    "title": row.get("published_title") or "", "published_at": row.get("published_at") or "",
                    "url": row.get("url"), "hashtags": row.get("hashtags") or []})
    return out


def category_word(title: str, video_type: str) -> str:
    """The category a title names (CASA, FRUTA…), else the format."""
    match = _HDYS.search(title or "")
    if match:
        return re.sub(r"[^\wáéíóúñü ]", "", match.group(1)).strip().upper()
    return video_type or "—"


def _snapshot_tokens() -> Optional[Path]:
    if not TOKENS.exists():
        return None
    target = ROOT / "output" / "stats" / f".tokens-{datetime.now():%Y%m%d-%H%M%S}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TOKENS, target)
    return target


def _youtube_token() -> str:
    from uploader import YouTubeUploader
    up = YouTubeUploader()
    if not up._token_data:
        raise RuntimeError("YouTube no está conectado (no hay token en .tokens/)")
    if up._token_expired():
        _snapshot_tokens()                                   # before the refresh rewrites it
        if not up._refresh_token():
            raise RuntimeError("No se pudo renovar el token de YouTube")
    return up._token_data["access_token"]


def fetch_youtube(ids: List[str], token: str, get=None) -> Dict[str, Dict]:
    """{id: {views, likes, comments, title}} from videos.list, 50 ids a request."""
    import requests
    get = get or requests.get
    out = {}
    for k in range(0, len(ids), 50):
        resp = get(YOUTUBE_VIDEOS, params={"part": "statistics,snippet", "id": ",".join(ids[k:k + 50])},
                   headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            s = item.get("statistics") or {}
            out[item["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                               "comments": int(s.get("commentCount", 0)),
                               "title": (item.get("snippet") or {}).get("title", ""),
                               "published": (item.get("snippet") or {}).get("publishedAt", "")}
    return out


def fetch_retention(ids: List[str], token: str, today: date, get=None) -> Dict[str, Dict]:
    """{id: {avg_view_pct, avg_view_seconds, subs_gained, shares}} from YouTube Analytics, 200 ids a
    report (the cap for the video dimension). The % passes 100 when viewers loop a Short, and it
    flatters short videos, so the seconds travel with it. {} when the report cannot be read: views
    are still worth a snapshot."""
    import requests
    get = get or requests.get
    out: Dict[str, Dict] = {}
    try:
        for k in range(0, len(ids), 200):
            chunk = ids[k:k + 200]
            resp = get(YOUTUBE_ANALYTICS, params={
                "ids": "channel==MINE", "startDate": "2020-01-01", "endDate": today.isoformat(),
                "metrics": "views,averageViewPercentage,averageViewDuration,subscribersGained,shares", "dimensions": "video",
                "filters": "video==" + ",".join(chunk), "maxResults": 200, "sort": "-views"},
                headers={"Authorization": f"Bearer {token}"}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            names = [h["name"] for h in data.get("columnHeaders", [])]
            for row in data.get("rows") or []:
                rec = dict(zip(names, row))
                out[rec["video"]] = {"avg_view_pct": round(float(rec["averageViewPercentage"]), 1),
                                     "avg_view_seconds": rec.get("averageViewDuration"),
                                     "subs_gained": rec.get("subscribersGained"), "shares": rec.get("shares")}
    except Exception as error:                              # noqa: BLE001 — a missing % is not a failed refresh
        import logging
        logging.getLogger(__name__).warning("YouTube Analytics retention unavailable: %s", error)
    return out


def fetch_facebook(ledger: Optional[Path] = None, call=None) -> Dict:
    """Facebook reels' views through video_insights, when the Page token allows it.
    {"views": {video_id: n}, "note": why some or all could not be read}."""
    import os
    from env_setup import ensure_env_loaded
    ensure_env_loaded()
    ledger = ledger or LEDGER
    rows = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("platform") == "facebook" and row.get("upload_id"):
                rows.append(row)
    token = os.getenv("FB_PAGE_TOKEN", "")
    if not rows:
        return {"views": {}, "note": "no hay reels de Facebook en el registro"}
    if not token:
        return {"views": {}, "note": "sin FB_PAGE_TOKEN: Facebook no se leyó"}
    if call is None:
        from publishers.common import GRAPH_VERSION, call as graph_call
        graph = f"https://graph.facebook.com/{GRAPH_VERSION}"
        call = lambda vid: graph_call("get", f"{graph}/{vid}/video_insights", token,
                                      params={"metric": "total_video_views", "access_token": token})
    views, errors = {}, []
    for row in rows:
        try:
            data = call(row["upload_id"])
            values = ((data.get("data") or [{}])[0].get("values") or [{}])
            views[row["upload_id"]] = int(values[0].get("value", 0))
        except Exception as error:                          # noqa: BLE001 — a note, not a failure
            errors.append(str(error)[:160])
    note = (f"{len(views)} de {len(rows)} reels leídos" + (f"; error: {errors[0]}" if errors else ""))
    return {"views": views, "note": note}


def refresh(today: Optional[date] = None, get=None, token: Optional[str] = None, facebook=None) -> Path:
    """Read every published YouTube video's numbers and write the day's snapshot."""
    today = today or date.today()
    rows = youtube_rows()
    token = token or _youtube_token()
    stats = fetch_youtube([r["id"] for r in rows], token, get)
    retention = fetch_retention([r["id"] for r in rows], token, today, get)
    import ai_background
    import design_ab
    import length_ab
    groups = ai_background.variants()                       # STEP 80 §5: each video's A/B group
    lengths = length_ab.variants()                          # the short «¿Cómo se dice…?» A/B
    designs = design_ab.variants()                          # STEP 82 §4: Tablero against the notebook
    snapshot = []
    for r in rows:
        s = stats.get(r["id"])
        if s is None:
            continue                                        # deleted or private now
        when = (s.pop("published", "") or r["published_at"] or "")[:10]   # YouTube's date: a recovered ledger row is days late
        days = (today - date.fromisoformat(when)).days if when else None
        snapshot.append({**r, **s, "days": days, "category": category_word(s["title"] or r["title"], r["type"]),
                         "background_variant": groups.get(r.get("artifact")),
                         "length_variant": lengths.get(r.get("artifact")),
                         "design_variant": designs.get(r.get("artifact")),
                         "avg_view_pct": None, "avg_view_seconds": None, "subs_gained": None, "shares": None,
                         **retention.get(r["id"], {})})
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    path = STATS_DIR / f"youtube_{today.isoformat()}.json"
    fb = (facebook or fetch_facebook)()
    path.write_text(json.dumps({"read_at": datetime.now().isoformat(timespec="seconds"), "videos": snapshot,
                                "facebook": fb}, ensure_ascii=False, indent=1), encoding="utf-8")
    for fn in list(REFRESH_LISTENERS):
        try:
            fn()
        except Exception:                                   # noqa: BLE001 — a listener never breaks the refresh
            pass
    return path


#: callables told after a snapshot is written (the live feed's `stats.refreshed`)
REFRESH_LISTENERS: list = []
REFRESH_HOURS = 20
AUTO = {"started": False, "last": None, "error": None}
_AUTO_LOCK = __import__("threading").Lock()


def snapshot_age_hours(now: Optional[datetime] = None) -> Optional[float]:
    """Hours since the newest snapshot was read, or None when there is none."""
    snap = latest()
    if not snap or not snap.get("read_at"):
        return None
    return ((now or datetime.now()) - datetime.fromisoformat(snap["read_at"])).total_seconds() / 3600


def refresh_if_stale(hours: float = REFRESH_HOURS, now: Optional[datetime] = None, do=None) -> Dict:
    """STEP 81 §1.1: read the stats again when the newest snapshot is `hours` old or missing. Read-only
    and free quota. Never raises: a failure comes back as {"error": ...} for the panel to warn about."""
    age = snapshot_age_hours(now)
    if age is not None and age < hours:
        return {"ran": False, "error": None}
    try:
        (do or refresh)()
    except Exception as exc:                                # noqa: BLE001 — never block the panel
        return {"ran": True, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"ran": True, "error": None}


def start_auto_refresh(hours: float = REFRESH_HOURS, do=None) -> Dict:
    """Once per process: refresh now if stale, then every `hours` while the panel runs (a daemon thread).
    Off under pytest or with CHANNEL_STATS_AUTO=0. Returns the shared state the panel reads."""
    import os
    import threading
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("CHANNEL_STATS_AUTO") == "0":
        return AUTO
    with _AUTO_LOCK:
        if AUTO["started"]:
            return AUTO
        AUTO["started"] = True

    def loop():
        while True:
            result = refresh_if_stale(hours, do=do)
            AUTO["last"], AUTO["error"] = datetime.now().isoformat(timespec="seconds"), result["error"]
            threading.Event().wait(hours * 3600)

    threading.Thread(target=loop, name="channel-stats-auto", daemon=True).start()
    return AUTO


def sequel_suggestions(videos: List[Dict], queued_themes: Iterable[str] = (), min_views: int = 800,
                       by_day: int = 3) -> List[Dict]:
    """STEP 81 §1.4: published «Cómo se dice» videos that reached `min_views` by day `by_day` and have no
    «MÁS <TEMA>» queued or published yet: [{category, views, title}], best first."""
    import queue_priority
    have = {queue_priority._fold(t) for t in queued_themes}
    out = []
    for v in videos:
        cat = (v.get("category") or "").strip()
        if v.get("type") != "how_do_you_say" or not cat or cat.upper().startswith("MÁS ") or cat == "—":
            continue
        if (v.get("days") or 0) < by_day or int(v.get("views", 0)) < min_views:
            continue
        key = queue_priority._fold(f"más {cat}")
        if key in have or any(h.endswith(key) or key in h for h in have):
            continue
        out.append({"category": cat, "views": int(v["views"]), "title": v.get("title") or ""})
    return sorted(out, key=lambda r: -r["views"])


def latest() -> Optional[Dict]:
    files = sorted(STATS_DIR.glob("youtube_*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def summary(videos: List[Dict]) -> Dict:
    """By format (median, mean, count, all and mature), top and bottom 10, by category word."""
    by_type: Dict[str, List[Dict]] = {}
    for v in videos:
        by_type.setdefault(v.get("type") or "—", []).append(v)
    formats = []
    for vtype, vs in by_type.items():
        views = [v["views"] for v in vs]
        mature = [v["views"] for v in vs if (v.get("days") or 0) > MATURE_DAYS]
        formats.append({"type": vtype, "count": len(vs), "median": statistics.median(views),
                        "mean": round(statistics.mean(views), 1),
                        "mature_count": len(mature), "mature_median": statistics.median(mature) if mature else None})
    formats.sort(key=lambda f: -(f["mature_median"] if f["mature_median"] is not None else f["median"]))
    # A video under MATURE_DAYS is not judged yet: not a winner, not a loser, not a category's number.
    judged = [v for v in videos if (v.get("days") or 0) > MATURE_DAYS] or videos
    ranked = sorted(judged, key=lambda v: -v["views"])
    cats: Dict[str, List[int]] = {}
    for v in judged:
        cats.setdefault(v.get("category") or "—", []).append(v["views"])
    categories = sorted(({"category": c, "count": len(vs), "median": statistics.median(vs)} for c, vs in cats.items()),
                        key=lambda c: -c["median"])
    return {"formats": formats, "top": ranked[:10], "bottom": ranked[-10:][::-1], "categories": categories,
            "hashtags": hashtags(judged)}


def hashtags(videos: List[Dict], min_videos: int = 3) -> List[Dict]:
    """Median views per hashtag. It shows what the channel used, not what caused the views: a tag
    on every winner may just be a tag on every «¿Cómo se dice…?»."""
    tags: Dict[str, List[int]] = {}
    for v in videos:
        for tag in {str(t).lstrip("#").casefold() for t in v.get("hashtags") or []} - {"shorts"}:
            tags.setdefault(tag, []).append(v["views"])
    return sorted(({"hashtag": f"#{t}", "count": len(n), "median": statistics.median(n)}
                   for t, n in tags.items() if len(n) >= min_videos), key=lambda t: -t["median"])

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
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "output" / "published" / "ledger.jsonl"
STATS_DIR = ROOT / "output" / "stats"
TOKENS = ROOT / ".tokens"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
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
                    "url": row.get("url")})
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
                               "title": (item.get("snippet") or {}).get("title", "")}
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
    stats = fetch_youtube([r["id"] for r in rows], token or _youtube_token(), get)
    snapshot = []
    for r in rows:
        s = stats.get(r["id"])
        if s is None:
            continue                                        # deleted or private now
        when = (r["published_at"] or "")[:10]
        days = (today - date.fromisoformat(when)).days if when else None
        snapshot.append({**r, **s, "days": days, "category": category_word(s["title"] or r["title"], r["type"])})
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    path = STATS_DIR / f"youtube_{today.isoformat()}.json"
    fb = (facebook or fetch_facebook)()
    path.write_text(json.dumps({"read_at": datetime.now().isoformat(timespec="seconds"), "videos": snapshot,
                                "facebook": fb}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


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
    ranked = sorted(videos, key=lambda v: -v["views"])
    cats: Dict[str, List[int]] = {}
    for v in videos:
        cats.setdefault(v.get("category") or "—", []).append(v["views"])
    categories = sorted(({"category": c, "count": len(vs), "median": statistics.median(vs)} for c, vs in cats.items()),
                        key=lambda c: -c["median"])
    return {"formats": formats, "top": ranked[:10], "bottom": ranked[-10:][::-1], "categories": categories}

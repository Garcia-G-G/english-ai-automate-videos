"""What the most-watched Shorts on a topic look like, across ALL of YouTube, not only this channel.

Before a script is written, the YouTube Data API is searched for the topic (and for the format),
most-viewed first, and the short videos (<= 3 min) that come back are kept with their real view
counts, channel, duration and tags. channel_insights.brief() hands them to the script writer.

Quota: search.list costs 100 of the default 10,000 daily units, videos.list 1. Every query is
cached on disk for CACHE_DAYS (output/stats/market/), so a topic is researched once a week.
Never raises into a caller: no token, no network or no quota means an empty list.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "output" / "stats" / "market"
CACHE_DAYS = 7
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_SHORT_SECONDS = 180
#: Shorts since this date: older hits were ranked by an algorithm that no longer exists.
PUBLISHED_AFTER = "2024-01-01T00:00:00Z"
#: The audience is teens and adults who speak Spanish: kids' songs and other languages are noise
#: (2026-10-27: a viewCount search for «números en inglés» came back as nursery rhymes and French).
AUDIO_LANGUAGES = ("es", "en")

#: The format each video type belongs to, as a viewer would search for it.
FORMAT_QUERY = {
    "how_do_you_say": "vocabulario en inglés para hispanohablantes",
    "phrases_level": "frases en inglés para hablar",
    "level_test": "test de nivel de inglés",
    "say_it_level": "cómo se dice en inglés frases",
    "true_false_level": "verdadero o falso inglés",
    "fill_level": "completa la frase en inglés",
    "choose_level": "elige la correcta inglés",
    "quiz": "quiz de inglés",
    "pronunciation": "pronunciación en inglés",
    "hecho_con_claude": "errores en inglés hispanohablantes",
}


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:80]


def _seconds(iso: str) -> int:
    """ISO-8601 duration (PT1M5S) → seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def search(query: str, token: Optional[str] = None, get=None, now: Optional[float] = None) -> List[Dict]:
    """Most-viewed short videos for `query`: [{id, title, channel, views, seconds, tags, published}]."""
    cache = CACHE_DIR / f"{_slug(query)}.json"
    now = now or time.time()
    if cache.is_file() and now - cache.stat().st_mtime < CACHE_DAYS * 86400:
        return json.loads(cache.read_text(encoding="utf-8"))["videos"]
    try:
        import requests
        get = get or requests.get
        if token is None:
            from env_setup import ensure_env_loaded
            ensure_env_loaded()                             # the refresh needs YOUTUBE_CLIENT_ID/SECRET
            import channel_stats
            token = channel_stats._youtube_token()
        auth = {"Authorization": f"Bearer {token}"}
        found = get(SEARCH_URL, params={"part": "snippet", "q": query, "type": "video", "order": "relevance",
                                        "videoDuration": "short", "relevanceLanguage": "es", "regionCode": "MX",
                                        "publishedAfter": PUBLISHED_AFTER, "maxResults": 50},
                    headers=auth, timeout=30)
        found.raise_for_status()
        ids = [i["id"]["videoId"] for i in found.json().get("items", []) if i.get("id", {}).get("videoId")]
        if not ids:
            return []
        detail = get(VIDEOS_URL, params={"part": "snippet,statistics,contentDetails,status", "id": ",".join(ids)},
                     headers=auth, timeout=30)
        detail.raise_for_status()
    except Exception as error:                              # noqa: BLE001 — research is a bonus, never a blocker
        logger.warning("market research failed for %r: %s", query, error)
        return []
    videos = []
    for item in detail.json().get("items", []):
        sn, st = item.get("snippet") or {}, item.get("statistics") or {}
        seconds = _seconds((item.get("contentDetails") or {}).get("duration", ""))
        audio = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "es")[:2].lower()
        if (0 < seconds <= MAX_SHORT_SECONDS and audio in AUDIO_LANGUAGES
                and not (item.get("status") or {}).get("madeForKids")):
            videos.append({"id": item["id"], "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                           "views": int(st.get("viewCount", 0)), "seconds": seconds,
                           "tags": (sn.get("tags") or [])[:8], "published": sn.get("publishedAt", "")[:10]})
    videos.sort(key=lambda v: -v["views"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"query": query, "videos": videos}, ensure_ascii=False, indent=1), encoding="utf-8")
    return videos


def queries(video_type: str, theme: str = "") -> List[str]:
    """The topic's own query first, then the format's."""
    theme = (theme or "").strip()
    plural = re.match(r"(los|las)\s", theme, re.I)
    out = [f"cómo se {'dicen' if plural else 'dice'} {theme} en inglés"] if theme else []
    if FORMAT_QUERY.get(video_type):
        out.append(FORMAT_QUERY[video_type])
    return out


def top_videos(video_type: str, theme: str = "", limit: int = 10) -> List[Dict]:
    """The most-viewed short videos for the topic and the format, merged, best first.
    Empty under pytest: tests never reach the network or spend quota."""
    if "pytest" in sys.modules:
        return []
    seen, merged = set(), []
    for q in queries(video_type, theme):
        for v in search(q):
            if v["id"] not in seen:
                seen.add(v["id"])
                merged.append({**v, "query": q})
    return sorted(merged, key=lambda v: -v["views"])[:limit]


def views_label(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e3 else str(n)

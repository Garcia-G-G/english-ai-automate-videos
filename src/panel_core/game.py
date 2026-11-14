"""STEP 85 §6: XP, level, streak and achievements, from real history only (the ledger, Señal's curves, the stats
snapshots, the rejection records). UI-free. A value the history cannot give is left out or null, never invented.

XP     +40 per published video (counted once, on its first platform), +10 per published video that was approved without
       a re-render, +100 when a video reached at least 2x the typical views of its format by day 3.
Level  1 + floor(xp / 1000); levelXp = xp % 1000; levelSize = 1000.
Streak consecutive Costa Rica calendar days with at least one publication; today counts once something is published or
       scheduled today.

Approximations (each is said where it applies):
- «published» is a ledger row whose time (scheduled_for, else published_at) is not in the future; a naive timestamp is Costa Rica.
- «approved without a re-render»: there is no approval log, so every published video counts, except one whose script
  was rejected on record (output/rejected sidecars) before it was made again.
- «2x its format's normal by day 3»: Señal's own typical cumulative curve of the format (senal.typical, the same one the
  panel scores with) at day 3, against the video's own views over days 0-3. Videos with fewer than 4 real days of data,
  or whose day 3 is an estimate, are left out.
- A milestone known only by day (1,000 views, 10,000 in a week) is dated 12:00 Costa Rica that day; if Señal's 15-day curve
  does not hold it, the earliest stats snapshot that shows it, and null when neither does.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Costa_Rica")
LEVEL_SIZE = 1000
XP_PUBLISHED, XP_APPROVED, XP_BREAKOUT = 40, 10, 100
BASE_XP = XP_PUBLISHED + XP_APPROVED          # what a normal video earns once published (NextVideo.xp)
FORMAT_MAIN = "how_do_you_say"

#: id, name, description, emoji (the front end's demo has the same ids for first, v100, views1k, week10k, streak7, csd50, streak30, sequelwin, noreject)
CATALOG = [
    ("first", "Primer vídeo", "Publicaste tu primer Short.", "🎬"),
    ("v10", "10 vídeos", "Diez vídeos publicados.", "🔟"),
    ("v50", "50 vídeos", "Cincuenta vídeos publicados.", "🎯"),
    ("v100", "100 vídeos", "Cien vídeos publicados.", "💯"),
    ("csd50", "50 «Cómo se dice»", "Cincuenta vídeos del formato que más rinde.", "🏆"),
    ("views1k", "Primer millar", "Un vídeo pasó de 1,000 vistas.", "⭐"),
    ("week10k", "Semana de 10,000", "10,000 vistas en 7 días.", "🔥"),
    ("streak7", "Racha de 7", "Siete días seguidos publicando.", "📅"),
    ("streak30", "Racha de 30", "Treinta días seguidos publicando.", "🗓️"),
    ("sequelwin", "La secuela gana", "Una secuela superó a su original.", "🚀"),
    ("noreject", "Semana limpia", "Siete días sin rechazar ningún vídeo.", "✨"),
]


def _aware(raw) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=TZ)).astimezone(TZ)


def _noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=TZ)


def row_time(row: Dict) -> Optional[datetime]:
    return _aware((row.get("extra") or {}).get("scheduled_for") or row.get("published_at"))


def videos_from(rows: Iterable[Dict], now: datetime) -> List[Dict]:
    """One entry per artifact: {artifact, type, at (first platform's time), upload_id (YouTube's), live}, oldest first.
    `live` is False while every row of it is still in the future (scheduled)."""
    by: Dict[str, Dict] = {}
    for r in rows:
        t = row_time(r)
        if t is None or not r.get("artifact"):
            continue
        v = by.setdefault(r["artifact"], {"artifact": r["artifact"], "type": r.get("video_type") or "", "at": t, "upload_id": None})
        v["at"] = min(v["at"], t)
        if r.get("platform") == "youtube" and r.get("upload_id"):
            v["upload_id"] = r["upload_id"]
    out = sorted(by.values(), key=lambda v: v["at"])
    for v in out:
        v["live"] = v["at"] <= now
    return out


def streak(rows: Iterable[Dict], now: datetime) -> Tuple[int, bool, Dict[int, datetime]]:
    """(days, includes_today, {length: first publication time of the day that reached it}). Future days are ignored."""
    today = now.astimezone(TZ).date()
    first: Dict[date, datetime] = {}
    for r in rows:
        t = row_time(r)
        if t is None or t.date() > today:
            continue
        if t.date() not in first or t < first[t.date()]:
            first[t.date()] = t
    # when each run length was first reached, over all of history
    reached: Dict[int, datetime] = {}
    run = 0
    prev = None
    for d in sorted(first):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        reached.setdefault(run, first[d])
        prev = d
    inc = today in first
    cursor = today if inc else today - timedelta(days=1)
    days = 0
    while cursor in first:
        days += 1
        cursor -= timedelta(days=1)
    return days, inc, reached


def _cum(daily: List[int]) -> List[int]:
    out, tot = [], 0
    for n in daily:
        tot += int(n or 0)
        out.append(tot)
    return out


def breakouts(vids: List[Dict], senal: Optional[Dict], today: date) -> Dict[str, date]:
    """{artifact: date} of videos that reached >= 2x their format's typical cumulative views by day 3 (see module doc)."""
    if not senal or not senal.get("videos"):
        return {}
    import senal as S
    sv = senal["videos"]
    by_id = {v["id"]: v for v in sv}
    out = {}
    for v in vids:
        s = by_id.get(v.get("upload_id"))
        if not s or len(s.get("daily") or []) < 4:
            continue
        est = s.get("est_from")
        if est is not None and est <= 3:
            continue
        _, cum = S.typical(sv, s["format"], today, exclude=s["id"])
        if cum[3] and sum(s["daily"][:4]) >= 2 * cum[3]:
            out[v["artifact"]] = date.fromisoformat(s["published"]) + timedelta(days=3)
    return out


def _views_by_day(senal: Optional[Dict]) -> Dict[date, int]:
    out: Dict[date, int] = {}
    for s in (senal or {}).get("videos", []):
        pub = date.fromisoformat(s["published"])
        for i, n in enumerate(s.get("daily") or []):
            out[pub + timedelta(days=i)] = out.get(pub + timedelta(days=i), 0) + int(n or 0)
    return out


def _first_1k(senal: Optional[Dict], snaps: List[Tuple[date, List[Dict]]]) -> Optional[datetime]:
    best: Optional[date] = None
    for s in (senal or {}).get("videos", []):
        pub = date.fromisoformat(s["published"])
        for i, c in enumerate(_cum(s.get("daily") or [])):
            if c >= 1000:
                d = pub + timedelta(days=i)
                best = d if best is None or d < best else best
                break
    if best is not None:
        return _noon(best)
    for d, vids in sorted(snaps):
        if any(int(v.get("views") or 0) >= 1000 for v in vids):
            return _noon(d)
    return None


def _week_10k(senal: Optional[Dict]) -> Optional[datetime]:
    by_day = _views_by_day(senal)
    if not by_day:
        return None
    for end in sorted(by_day):
        if sum(by_day.get(end - timedelta(days=k), 0) for k in range(7)) >= 10000:
            return _noon(end)
    return None


def _sequel_win(snaps: List[Tuple[date, List[Dict]]]) -> Optional[datetime]:
    """First stats snapshot in which a «MÁS X» «Cómo se dice» has more views than the «X» it follows (a snapshot holds the
    views at that day, so this is the earliest day the history can show it)."""
    import queue_priority
    for d, vids in sorted(snaps):
        parents = {}
        for v in vids:
            cat = (v.get("category") or "").strip()
            if v.get("type") == FORMAT_MAIN and cat and not cat.upper().startswith("MÁS ") and cat != "—":
                parents[queue_priority._fold(cat)] = max(parents.get(queue_priority._fold(cat), 0), int(v.get("views") or 0))
        for v in vids:
            cat = (v.get("category") or "").strip()
            if v.get("type") == FORMAT_MAIN and cat.upper().startswith("MÁS "):
                p = parents.get(queue_priority._fold(cat[4:]))
                if p is not None and int(v.get("views") or 0) > p:
                    return _noon(d)
    return None


def _clean_week(rejections: List[datetime], now: datetime) -> Optional[datetime]:
    """Rejections are on record only since Revisar kept reasons, so «a week without one» can be shown only after the first
    record: the earliest r such that no other rejection falls within 7 days after it, and those 7 days are over."""
    rej = sorted(rejections)
    for i, r in enumerate(rej):
        end = r + timedelta(days=7)
        nxt = rej[i + 1] if i + 1 < len(rej) else None
        if end <= now and (nxt is None or nxt >= end):
            return end
    return None


def compute(rows: List[Dict], senal: Optional[Dict] = None, snaps: Optional[List[Tuple[date, List[Dict]]]] = None,
            rejections: Optional[List[datetime]] = None, rerendered: Optional[Callable[[Dict], bool]] = None,
            now: Optional[datetime] = None) -> Dict:
    """The contract's `Game`. Pure: every input is passed in."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    snaps, rejections = snaps or [], rejections or []
    rows = list(rows)
    vids = videos_from(rows, now)
    live = [v for v in vids if v["live"]]
    won = breakouts(live, senal, now.date())
    xp = sum(XP_PUBLISHED + (0 if rerendered and rerendered(v) else XP_APPROVED) for v in live) + XP_BREAKOUT * len(won)
    days, inc, reached = streak(rows, now)
    unlocked: Dict[str, Optional[datetime]] = {
        "first": live[0]["at"] if live else None,
        "v10": live[9]["at"] if len(live) >= 10 else None,
        "v50": live[49]["at"] if len(live) >= 50 else None,
        "v100": live[99]["at"] if len(live) >= 100 else None,
        "csd50": (lambda m: m[49]["at"] if len(m) >= 50 else None)([v for v in live if v["type"] == FORMAT_MAIN]),
        "views1k": _first_1k(senal, snaps),
        "week10k": _week_10k(senal),
        "streak7": reached.get(7),
        "streak30": reached.get(30),
        "sequelwin": _sequel_win(snaps),
        "noreject": _clean_week(rejections, now),
    }
    return {"xp": xp, "level": 1 + xp // LEVEL_SIZE, "levelXp": xp % LEVEL_SIZE, "levelSize": LEVEL_SIZE,
            "streakDays": days, "streakIncludesToday": inc,
            "achievements": [{"id": i, "name": n, "description": d, "emoji": e,
                              "unlockedAt": unlocked[i].isoformat(timespec="seconds") if unlocked.get(i) else None}
                             for i, n, d, e in CATALOG]}


# ── real history: loaders, cached on file mtimes ─────────────────────

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "output" / "state"
_CACHE: Dict[str, tuple] = {}


def _mt(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def _sources():
    import channel_stats
    import jobs
    import publication_log
    import senal
    return publication_log.LEDGER_PATH, senal.SENAL_DIR / "senal.json", channel_stats.STATS_DIR, jobs.REJECTED_DIR


def _rejections(rejected_dir: Path) -> List[datetime]:
    out = []
    for f in rejected_dir.glob("*/*.json") if rejected_dir.is_dir() else []:
        try:
            at = _aware((json.loads(f.read_text(encoding="utf-8")).get("rejected") or {}).get("at"))
        except (OSError, ValueError):
            continue
        if at:
            out.append(at)
    return out


def _rerendered(rejected_dir: Path) -> Optional[Callable[[Dict], bool]]:
    """A published video is a re-render when its script's topic was rejected on record before. None when nothing was rejected."""
    topics = set()
    for f in rejected_dir.glob("*/*.json") if rejected_dir.is_dir() else []:
        try:
            m = (json.loads(f.read_text(encoding="utf-8")).get("script_data") or {}).get("_meta") or {}
        except (OSError, ValueError):
            continue
        if m.get("topic_id"):
            topics.add((f.parent.name, m["topic_id"]))
    if not topics:
        return None

    def check(video: Dict) -> bool:
        import publication_log
        for r in publication_log.find_by_artifact(video["artifact"]):
            side = Path(r.get("video_path") or "").with_suffix(".json")
            try:
                m = (json.loads(side.read_text(encoding="utf-8")).get("script_data") or {}).get("_meta") or {}
            except (OSError, ValueError):
                continue
            return (video["type"], m.get("topic_id")) in topics
        return False
    return check


def snapshot(now: Optional[datetime] = None) -> Dict:
    """The Game for the real history (read-only), cached until a source file changes (and per minute: a streak and a
    scheduled time depend on the clock)."""
    ledger, senal_path, stats_dir, rejected_dir = _sources()
    now = (now or datetime.now(TZ)).astimezone(TZ)
    files = sorted(stats_dir.glob("youtube_*.json")) if stats_dir.is_dir() else []
    rej = sorted(rejected_dir.glob("*/*.json")) if rejected_dir.is_dir() else []
    fp = (_mt(ledger), _mt(senal_path), tuple((f.name, _mt(f)) for f in files), tuple((f.name, _mt(f)) for f in rej),
          int(now.timestamp() // 60))
    hit = _CACHE.get("game")
    if hit and hit[0] == fp:
        return hit[1]
    import publication_log
    rows = publication_log.read_ledger()
    try:
        sen = json.loads(senal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sen = None
    snaps = []
    for f in files:
        try:
            snaps.append((date.fromisoformat(f.stem.removeprefix("youtube_")), json.loads(f.read_text(encoding="utf-8")).get("videos", [])))
        except (OSError, ValueError):
            continue
    value = compute(rows, sen, snaps, _rejections(rejected_dir), _rerendered(rejected_dir), now)
    _CACHE["game"] = (fp, value)
    return value


# ── unlocking: what is new since last time ──────────────────────────

def _state_path() -> Path:
    return STATE_DIR / "game_seen.json"


def recompute(publish: Callable[[Dict], None], now: Optional[datetime] = None, path: Optional[Path] = None) -> Dict:
    """Recompute the game; publish `achievement.unlocked` for each achievement unlocked since the last look and `game` when
    anything changed. The last-seen state lives in output/state/game_seen.json, so a restart does not announce again. The
    first ever run only records what is already unlocked (no flood of old news)."""
    path = path or _state_path()
    game = snapshot(now)
    unlocked = sorted(a["id"] for a in game["achievements"] if a["unlockedAt"])
    key = {"xp": game["xp"], "streak": game["streakDays"], "inc": game["streakIncludesToday"], "unlocked": unlocked}
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = None
    if seen is not None:
        for a in game["achievements"]:
            if a["unlockedAt"] and a["id"] not in seen.get("unlocked", []):
                publish({"type": "achievement.unlocked", "achievement": a})
        if seen != key:
            publish({"type": "game", "game": game})
    if seen != key:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(key), encoding="utf-8")
        tmp.replace(path)
    return game

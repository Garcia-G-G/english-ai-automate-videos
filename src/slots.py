"""STEP 81 §2: publishing slots, so uploads never go out in a burst.

Garcia's time zone (America/Costa_Rica): 08:30, 12:00, 16:00 and 19:30; never two videos less than
2.5 h apart, never more than 4 a day. YouTube takes the video as `private` with `status.publishAt`;
the queue fills the next free slot. Pure functions: the ledger rows and `now` are passed in.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

DEFAULTS = {"enabled": True, "tz": "America/Costa_Rica", "slots": ["08:30", "12:00", "16:00", "19:30"],
            "min_gap_hours": 2.5, "max_per_day": 4}
LEAD = timedelta(minutes=15)          # YouTube wants publishAt in the future; leave room for the upload


def settings(config: Optional[Dict] = None) -> Dict:
    if config is None:
        import queue_priority
        config = queue_priority._config()
    return {**DEFAULTS, **(config.get("youtube_schedule") or {})}


def _tz(cfg: Dict) -> ZoneInfo:
    return ZoneInfo(cfg["tz"])


def taken_times(rows: Iterable[Dict], cfg: Optional[Dict] = None, platform: str = "youtube") -> List[datetime]:
    """When each YouTube video went (or is set to go) live: the scheduled slot if the row has one,
    else the upload time, as aware datetimes."""
    cfg = cfg or settings()
    tz, out = _tz(cfg), []
    for r in rows:
        if r.get("platform") != platform:
            continue
        raw = (r.get("extra") or {}).get("scheduled_for") or r.get("published_at")
        try:
            t = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        out.append(t if t.tzinfo else t.replace(tzinfo=tz))
    return sorted(out)


def next_slots(now: datetime, taken: Iterable[datetime], n: int = 1, cfg: Optional[Dict] = None) -> List[datetime]:
    """The next `n` free slots after `now` (aware), each ≥ min_gap from every taken or chosen time and
    with at most max_per_day videos on its day."""
    cfg = cfg or settings()
    tz, gap = _tz(cfg), timedelta(hours=float(cfg["min_gap_hours"]))
    now = now.astimezone(tz)
    busy = [t.astimezone(tz) for t in taken]
    chosen: List[datetime] = []
    times = sorted(time.fromisoformat(s) for s in cfg["slots"])
    day = now.date()
    for _ in range(60):                                   # two months is far more than a queue holds
        for tm in times:
            at = datetime.combine(day, tm, tz)
            if at <= now + LEAD:
                continue
            if sum(1 for t in busy + chosen if t.date() == day) >= int(cfg["max_per_day"]):
                continue
            if any(abs(at - t) < gap for t in busy + chosen):
                continue
            chosen.append(at)
            if len(chosen) == n:
                return chosen
        day += timedelta(days=1)
    return chosen


def publish_at(at: datetime) -> str:
    """The RFC 3339 UTC string YouTube's `status.publishAt` wants."""
    return at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fill_plan(slots: List[datetime], ranked: List[Tuple[object, dict]], types_today: Optional[List[str]] = None,
              other_done: int = 0) -> List[Tuple[datetime, str, Optional[object]]]:
    """[(slot, type wanted, script path or None)]: each slot takes the best ranked script of the type the
    day's mix asks for (daily_mix), else the best left. `ranked` is [(path, script)] best first."""
    import daily_mix
    left = list(ranked)
    by_day: Dict[date, List[str]] = {}
    out = []
    for at in slots:
        todays = by_day.setdefault(at.date(), list(types_today or []) if at.date() == slots[0].date() else [])
        plan = daily_mix.next_slot(todays, other_done)
        pick = next((x for t in plan["types"] for x in left if x[1].get("type") == t), None) or (left[0] if left else None)
        if pick:
            left.remove(pick)
            todays.append(pick[1].get("type") or "")
        out.append((at, (plan["types"] or ["—"])[0], pick[0] if pick else None))
    return out


def next_free(rows: Optional[Iterable[Dict]] = None, now: Optional[datetime] = None, cfg: Optional[Dict] = None) -> Optional[datetime]:
    """The next free YouTube slot from the ledger, or None when scheduling is off (config youtube_schedule.enabled)."""
    cfg = cfg or settings()
    if not cfg["enabled"]:
        return None
    if rows is None:
        import publication_log
        rows = publication_log.read_ledger()
    found = next_slots(now or datetime.now(_tz(cfg)), taken_times(rows, cfg), 1, cfg)
    return found[0] if found else None


# ── STEP 85 §0: free «Sale». Port of panel/src/lib/schedule.ts: Garcia picks any minute; the one hard rule is
# the lead time; spacing and per-day count only warn. The limits bind only when the engine picks (next_slots). ──
GARCIA, AUTO = "garcia", "auto"
_DOW = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_DOW_LONG = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def next_days(now: datetime, count: int = 7, cfg: Optional[Dict] = None) -> List[Tuple[date, str]]:
    """[(date, label)] from today (in the schedule's zone): «Hoy», «Mañana», «mar 1 dic»."""
    today = now.astimezone(_tz(cfg or settings())).date()
    out = []
    for k in range(count):
        d = today + timedelta(days=k)
        out.append((d, "Hoy" if k == 0 else "Mañana" if k == 1 else f"{_DOW[d.weekday()]} {d.day} {_MES[d.month - 1]}"))
    return out


def long_label(at: datetime, cfg: Optional[Dict] = None) -> str:
    """«sábado 14 nov a las 21:15»."""
    at = at.astimezone(_tz(cfg or settings()))
    return f"{_DOW_LONG[at.weekday()]} {at.day} {_MES[at.month - 1]} a las {at:%H:%M}"


def taken_titled(rows: Iterable[Dict], cfg: Optional[Dict] = None) -> List[Tuple[datetime, str]]:
    """[(when, title)] of the YouTube ledger rows, the title the «Sale» warnings quote."""
    cfg = cfg or settings()
    rows = [r for r in rows if r.get("platform") == "youtube"]
    out = []
    for r in rows:
        t = taken_times([r], cfg)
        if t:
            out.append((t[0], str(r.get("published_title") or r.get("artifact") or "otro vídeo")))
    return sorted(out)


def taken_at(at: datetime, taken: Iterable[Tuple[datetime, str]], cfg: Optional[Dict] = None) -> Optional[str]:
    """The title of the video already at this exact minute, to mark a usual slot «ocupado»."""
    tz = _tz(cfg or settings())
    return next((title for t, title in taken if t.astimezone(tz).replace(second=0, microsecond=0) == at.astimezone(tz)), None)


def _gap(minutes: float) -> str:
    h, m = int(minutes // 60), int(round(minutes % 60))
    return f"{h} h{f' {m} min' if m else ''}" if h else f"{m} min"


def check_time(at: datetime, taken: Iterable[Tuple[datetime, str]], now: datetime, cfg: Optional[Dict] = None) -> Dict:
    """{error, warnings} for a time Garcia chose. Error (blocks): shorter than the lead time. Warnings (inform):
    closer than min_gap to another video, or past max_per_day that day."""
    cfg = cfg or settings()
    taken, lead = list(taken), (at - now).total_seconds() / 60
    mins = LEAD.total_seconds() / 60
    if lead < mins:
        return {"error": "Esa hora ya pasó. Elige una hora futura." if lead < 0
                else f"Tiene que ser al menos {int(mins)} min en el futuro, para que YouTube lo acepte.", "warnings": []}
    warnings = []
    if taken:
        gap, title = min((abs((t - at).total_seconds()) / 60, title) for t, title in taken)
        spacing = float(cfg["min_gap_hours"])
        if gap < spacing * 60:
            warnings.append(f"A la misma hora que «{title}»." if gap < 1
                            else f"A {_gap(gap)} de «{title}» (lo normal: {f'{spacing:g}'.replace('.', ',')} h).")
    tz, mx = _tz(cfg), int(cfg["max_per_day"])
    n = sum(1 for t, _ in taken if t.astimezone(tz).date() == at.astimezone(tz).date()) + 1
    if n > mx:
        warnings.append(f"Sería el {n}.º vídeo de ese día (lo normal: {mx}).")
    return {"error": None, "warnings": warnings}


def explicit(at: datetime, taken: Iterable[Tuple[datetime, str]], now: datetime, cfg: Optional[Dict] = None) -> Dict:
    """Accept Garcia's own time: ValueError when it fails the lead rule, else {at, scheduled_by, warnings}."""
    r = check_time(at, taken, now, cfg)
    if r["error"]:
        raise ValueError(r["error"])
    return {"at": at, "scheduled_by": GARCIA, "warnings": r["warnings"]}

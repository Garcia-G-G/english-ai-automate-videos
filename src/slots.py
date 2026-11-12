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

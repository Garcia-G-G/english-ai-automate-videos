"""STEP 85 §1: slots and the schedule check, UI-free. The rules live in slots.py (§0); this builds the
`ScheduleInfo` the front end needs (panel/src/api/contract.ts)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import slots
from slots import check_time, explicit, long_label, next_days   # noqa: F401  re-exported

HORIZON_DAYS = 14


def schedule_info(rows=None, now: Optional[datetime] = None, cfg: Optional[Dict] = None) -> Dict:
    """ScheduleInfo: tz, utcOffset, slots, taken (next 14 days), minLeadMin, spacingH, maxPerDay and `next`
    (the next free usual slot, ISO, or None when none fits or scheduling is off)."""
    cfg = cfg or slots.settings()
    if rows is None:
        import publication_log
        rows = publication_log.read_ledger()
    tz = slots._tz(cfg)
    now = (now or datetime.now(tz)).astimezone(tz)
    taken = [(t, title) for t, title in slots.taken_titled(rows, cfg) if now - timedelta(hours=1) <= t <= now + timedelta(days=HORIZON_DAYS)]
    nxt = slots.next_slots(now, [t for t, _ in slots.taken_titled(rows, cfg)], 1, cfg) if cfg["enabled"] else []
    off = now.utcoffset() or timedelta(0)
    sign, mins = ("-" if off < timedelta(0) else "+"), abs(int(off.total_seconds() // 60))
    return {"tz": cfg["tz"], "utcOffset": f"{sign}{mins // 60:02d}:{mins % 60:02d}", "slots": list(cfg["slots"]),
            "taken": [{"at": t.astimezone(tz).isoformat(), "title": title} for t, title in taken],
            "minLeadMin": int(slots.LEAD.total_seconds() // 60), "spacingH": float(cfg["min_gap_hours"]),
            "maxPerDay": int(cfg["max_per_day"]), "next": nxt[0].isoformat() if nxt else None}

"""STEP 85 §1: the costs snapshot and the gate records, UI-free. Reads only; no paid call, no lock opened."""
from __future__ import annotations

from typing import Dict, Optional


def costs_snapshot(days: int = 7) -> Dict:
    """{month_usd, daily, videos: {mean, median, ...}, voice_locked, voice_forced}. Values the ledger does not hold
    are absent or zero as cost_tracker reports them; the caller shows «sin dato» for None."""
    import cost_tracker
    import voice_lock
    return {"month_usd": cost_tracker.get_monthly_total(), "daily": cost_tracker.get_daily_costs(days),
            "videos": cost_tracker.video_cost_stats(cost_tracker.per_video_costs()),
            "voice_locked": voice_lock.locked(), "voice_forced": voice_lock.forced()}


def gate_record(meta: Optional[Dict]) -> Dict:
    """{gate, flags, passed}: what the sidecar says about the quality gate; gate None means no verdict."""
    meta = meta or {}
    gate = meta.get("gate")
    return {"gate": gate, "flags": list(meta.get("blocking_flags") or []), "passed": None if gate is None else gate == "PASS"}

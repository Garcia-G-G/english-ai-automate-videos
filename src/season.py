"""STEP 81 §0.2: seasonal scripts are only picked inside their window (config.yaml content_calendar).

An out-of-season script is blocked by the queue guard («OUT OF SEASON») rather than deleted, so it
is picked again when its window opens.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional


def calendar() -> Dict[str, dict]:
    import queue_priority
    return queue_priority._config().get("content_calendar") or {}


def _md(text: str):
    month, day = text.split("-")
    return int(month), int(day)


def out_of_season(data: dict, today: Optional[date] = None, cal: Optional[Dict[str, dict]] = None) -> Optional[str]:
    """A Spanish message when the script names a seasonal topic outside its window, else None."""
    today = today or date.today()
    haystack = " ".join(str((data or {}).get(k) or "") for k in ("theme", "title", "video_title")).lower()
    for name, rule in (cal if cal is not None else calendar()).items():
        if name.lower() not in haystack and not any(w.lower() in haystack for w in rule.get("words") or []):
            continue
        start, end = _md(rule["from"]), _md(rule["to"])
        if not start <= (today.month, today.day) <= end:
            return f"OUT OF SEASON: {name} only from {rule['from']} to {rule['to']}"
    return None

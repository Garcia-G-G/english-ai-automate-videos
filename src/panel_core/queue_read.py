"""STEP 85 §1: queue reading and «next best», UI-free. A facade over jobs.py / queue_priority.py so the Streamlit
page and the API call the same functions; the rules stay where they are."""
from __future__ import annotations

from typing import Optional

import jobs
from jobs import next_best, queue_order, queue_pick, queue_status   # noqa: F401  re-exported


def bad_scripts(fresh: bool = False) -> set:
    """Paths the queue guard refuses (repeated, unfit): the wrapper of jobs._queue_bad with the live guard."""
    return jobs._queue_bad(jobs._queue_guard(), fresh)


def next_best_summary() -> Optional[dict]:
    """{path, type, why} for the script «Producir el siguiente mejor» would make now, or None."""
    got = next_best()
    if not got:
        return None
    path, data, why = got
    return {"path": str(path), "type": data.get("type"), "why": why}

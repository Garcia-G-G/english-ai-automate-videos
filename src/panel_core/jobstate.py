"""STEP 85 §1: job state with per-step progress, UI-free. Each step is 0..1 (guion, voz, sonido, montaje, control)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import jobs
from jobs import AlreadyRendering, start_generation   # noqa: F401  re-exported


def active_jobs() -> List[Dict]:
    return [with_steps(j) for j in jobs.get_active_jobs()]


def with_steps(job: Dict) -> Dict:
    """The job row plus `steps`; rows written before step progress existed get it derived from `progress`."""
    return {**job, "steps": job.get("steps") or jobs.steps_from_progress(job.get("progress"))}


def get_job(job_id: str) -> Optional[Dict]:
    data = jobs.load_jobs()
    return next((with_steps(j) for j in data["active"] + data["history"] if j["id"] == job_id), None)


def on_progress(fn: Callable[[str, Dict], None]) -> Callable[[], None]:
    """Call fn(job_id, steps) after every progress change (the SSE feed uses this). Returns the unsubscribe."""
    jobs.PROGRESS_LISTENERS.append(fn)
    return lambda: jobs.PROGRESS_LISTENERS.remove(fn) if fn in jobs.PROGRESS_LISTENERS else None

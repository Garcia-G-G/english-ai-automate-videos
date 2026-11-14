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


def on_progress(fn: Callable[[str, Dict], None], with_text: bool = False) -> Callable[[], None]:
    """Call fn(job_id, steps) (or fn(job_id, steps, text) with `with_text`) after every progress change. Returns the unsubscribe."""
    hook = fn if with_text else (lambda job_id, steps, text=None: fn(job_id, steps))
    jobs.PROGRESS_LISTENERS.append(hook)
    return lambda: jobs.PROGRESS_LISTENERS.remove(hook) if hook in jobs.PROGRESS_LISTENERS else None


def on_complete(fn: Callable[[str, bool, Optional[str], Optional[str]], None]) -> Callable[[], None]:
    """Call fn(job_id, success, video_path, error) when a job ends. Returns the unsubscribe."""
    jobs.COMPLETE_LISTENERS.append(fn)
    return lambda: jobs.COMPLETE_LISTENERS.remove(fn) if fn in jobs.COMPLETE_LISTENERS else None

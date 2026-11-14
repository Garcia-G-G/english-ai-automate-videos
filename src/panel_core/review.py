"""STEP 85 §1: Revisar's actions, UI-free: approve (with or without a time), reject with a reason, re-render."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import videos

#: schedule(video_path_after_approval, platforms, at) -> {platform: reason} for the ones that failed.
#: The guarded upload (guard decision, attempt log, ledger, Meta lock) lives in admin.py for now; §4 gives the API its own.
Scheduler = Callable[[Path, List[str], datetime], Dict[str, str]]


def approve(video_path: Path, publish_at: Optional[datetime] = None, platforms: Optional[List[str]] = None,
            scheduler: Optional[Scheduler] = None, now: Optional[datetime] = None, taken=None) -> Dict:
    """publish_at None: approve only, the video waits in «Por subir», nothing is uploaded. With a time: Garcia's
    time is checked (lead rule refuses before anything moves; spacing and count only warn), the video is approved
    and `scheduler` sends it through the guarded upload. -> {state, publishAt, results, warnings}."""
    import jobs
    import slots
    video_path = Path(video_path)
    if publish_at is None:
        videos.approve_video(video_path)
        return {"state": "approved", "publishAt": None, "results": [], "warnings": []}
    if scheduler is None:
        raise ValueError("a scheduler is needed to approve with a time")
    plan = slots.explicit(publish_at, taken or [], now or datetime.now(publish_at.tzinfo))     # ValueError: refused
    videos.approve_video(video_path)
    new_path = jobs.APPROVED_DIR / video_path.parent.name / video_path.name
    failed = scheduler(new_path, list(platforms or ["youtube"]), publish_at)
    results = [{"platform": p, "ok": p not in failed, "note": failed.get(p)} for p in (platforms or ["youtube"])]
    return {"state": "scheduled" if not failed else "approved", "publishAt": publish_at.isoformat(),
            "results": results, "warnings": plan["warnings"]}


def reject(video_path: Path, reason: str, note: str = "", now: Optional[datetime] = None) -> None:
    """Write the reason into the sidecar, then move the video to rejected/."""
    from panel.revisar import REASONS, save_reject_reason
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    video_path = Path(video_path)
    save_reject_reason(video_path.with_suffix(".json"), reason, note, (now or datetime.now()).isoformat())
    videos.reject_video(video_path)


def rerender(video_path: Path, script: Dict) -> str:
    """Reject the render and start it again from its script; returns the job id. The paid locks (voice_lock,
    voice_credits) still apply inside start_generation: this opens nothing."""
    import jobs
    video_path = Path(video_path)
    videos.reject_video(video_path)
    return jobs.start_generation(video_path.parent.name, script_data=script, rerender=True)

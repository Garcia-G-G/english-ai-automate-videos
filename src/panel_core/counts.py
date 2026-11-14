"""STEP 85 §2: the four numbers the sidebar badges show. admin._badge_counts reads the same sources; a test pins
that both agree. A source that fails counts 0, as the sidebar does."""
from __future__ import annotations

from . import videos


def sidebar_counts() -> dict:
    import jobs
    out = {}
    try:
        out["queue"] = len(jobs._queue_guard().queued_scripts())
    except Exception:                                       # noqa: BLE001 — same as the sidebar: never break
        out["queue"] = 0
    out["review"] = len(videos.get_pending_videos())
    out["upload"] = len(videos.get_approved_videos())
    try:
        import comments
        out["comments"] = comments.unanswered_count()
    except Exception:                                       # noqa: BLE001
        out["comments"] = 0
    return out

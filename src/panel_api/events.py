"""STEP 85 §5: GET /api/events, Server-Sent Events. The engine pushes (jobs.PROGRESS_LISTENERS and friends) into an
in-process broadcast `Bus`; every connected client has its own bounded asyncio.Queue (drop-oldest for a slow one) and is
unsubscribed when it disconnects. Worker threads hand events to the loop with call_soon_threadsafe. Nothing polls files."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import AsyncIterator, Callable, Dict, Optional

from panel_core import counts, game, jobstate, videos

logger = logging.getLogger(__name__)
STEP_ORDER = ["guion", "voz", "sonido", "montaje", "control"]       # the pipeline's order
HEARTBEAT_S = 15.0
QUEUE_MAX = 200
_CLOSE = object()


class Subscription:
    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int):
        self.loop, self.queue = loop, asyncio.Queue(maxsize)

    def _put(self, item) -> None:                                   # runs on the loop
        while True:
            try:
                self.queue.put_nowait(item)
                return
            except asyncio.QueueFull:
                self.queue.get_nowait()                              # slow client: drop the oldest event


class Bus:
    def __init__(self, maxsize: int = QUEUE_MAX):
        self._subs: set = set()
        self._lock = threading.Lock()
        self.maxsize = maxsize

    def subscribe(self) -> Subscription:
        sub = Subscription(asyncio.get_running_loop(), self.maxsize)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    def count(self) -> int:
        with self._lock:
            return len(self._subs)

    def _fan_out(self, item) -> None:
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub._put, item)
            except RuntimeError:                                     # its loop is gone: forget it
                self.unsubscribe(sub)

    def publish(self, event: Dict) -> None:
        """Any thread. `event` is a ServerEvent dict (it carries its own `type`)."""
        self._fan_out(event)

    def close(self) -> None:
        """End every stream (shutdown, tests)."""
        self._fan_out(_CLOSE)


def frame(event: Dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream(bus: Bus, heartbeat_s: float = HEARTBEAT_S) -> AsyncIterator[str]:
    """The SSE body: a comment first (flushes the headers), then one frame per event and a `: hb` comment per quiet interval."""
    sub = bus.subscribe()
    try:
        yield "retry: 3000\n: connected\n\n"
        while True:
            try:
                item = await asyncio.wait_for(sub.queue.get(), heartbeat_s)
            except asyncio.TimeoutError:
                yield ": hb\n\n"
                continue
            if item is _CLOSE:
                return
            yield frame(item)
    finally:
        bus.unsubscribe(sub)                                         # disconnect, cancel or close: never a leak


def reason_in_spanish(error: Optional[str]) -> str:
    return "No se pudo producir el vídeo." + (f" {str(error).strip()[:200]}" if error else "")


class Feed:
    """Turns the engine's callbacks into ServerEvents on the bus. `start()` hooks the engine; `stop()` unhooks it."""

    def __init__(self, bus: Bus):
        self.bus = bus
        self._last: Dict[str, Dict[str, float]] = {}
        self._off: list = []

    def on_progress(self, job_id: str, steps: Dict[str, float], text: Optional[str] = None) -> None:
        seen = self._last.setdefault(job_id, {})
        first = True
        for step in STEP_ORDER:
            value = steps.get(step)
            if value is None or seen.get(step, 0.0) == value:
                continue
            seen[step] = value
            ev = {"type": "job.step", "jobId": job_id, "step": step, "progress": value}
            if first and text:
                ev["log"] = str(text)
            first = False
            self.bus.publish(ev)

    def on_complete(self, job_id: str, success: bool, video_path: Optional[str], error: Optional[str]) -> None:
        self._last.pop(job_id, None)
        if success:
            self.bus.publish({"type": "job.done", "jobId": job_id, "artifact": Path(video_path).stem if video_path else None,
                              "reviewCount": len(videos.get_pending_videos()), "xpGained": game.BASE_XP})
            self.counts()
            self.game()
        else:
            self.bus.publish({"type": "job.failed", "jobId": job_id, "reason": reason_in_spanish(error)})

    def counts(self) -> None:
        self.bus.publish({"type": "counts", "counts": counts.sidebar_counts()})

    def stats_refreshed(self) -> None:
        self.bus.publish({"type": "stats.refreshed"})
        self.game()

    def game(self) -> None:
        """Recompute; `achievement.unlocked` and `game` go out only for what changed since the last look."""
        try:
            game.recompute(self.bus.publish)
        except Exception:                                   # noqa: BLE001 — a score never breaks a job or a click
            logger.exception("game recompute failed")

    def start(self) -> None:
        import channel_stats
        self._off = [jobstate.on_progress(self.on_progress, with_text=True), jobstate.on_complete(self.on_complete)]
        channel_stats.REFRESH_LISTENERS.append(self.stats_refreshed)
        self._off.append(lambda: channel_stats.REFRESH_LISTENERS.remove(self.stats_refreshed)
                         if self.stats_refreshed in channel_stats.REFRESH_LISTENERS else None)

    def stop(self) -> None:
        for off in self._off:
            off()
        self._off = []

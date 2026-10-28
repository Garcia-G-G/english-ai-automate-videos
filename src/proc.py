"""External commands with a time limit (STEP 75 §2).

A bare subprocess.run() on ffmpeg/ffprobe/Manim waits forever. A render holds the
render lock while it runs, so one hung ffprobe blocked every later job until someone
restarted the panel. Every external call goes through run(), which requires a limit.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

#: Seconds. A probe reads headers; an ffmpeg pass here is audio work or a short clip.
FFPROBE = 30
FFMPEG = 300


class CommandTimeout(subprocess.TimeoutExpired):
    """A TimeoutExpired, so every `except subprocess.SubprocessError` still catches it."""

    def __str__(self) -> str:
        return f"{self.cmd[0] if self.cmd else '?'} exceeded {self.timeout:g}s: {tail(self.stderr)}"


def tail(text, chars: int = 600) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text.strip()[-chars:]


def run(cmd: Sequence, *, timeout: Optional[float], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with a required time limit. On expiry the child is killed, the
    command and its stderr tail are logged, and CommandTimeout is raised."""
    if timeout is None:
        raise ValueError("proc.run needs a timeout")
    try:
        return subprocess.run(list(map(str, cmd)), timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:
        err = CommandTimeout(exc.cmd, exc.timeout, output=exc.output, stderr=exc.stderr)
        logger.error("timeout after %gs: %s\n%s", timeout, " ".join(map(str, cmd))[:400], tail(exc.stderr))
        raise err from None

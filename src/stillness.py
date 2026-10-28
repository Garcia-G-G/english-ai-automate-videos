"""How long a video stays still (STEP 78b §1 for the series, STEP 79 §3 for the lessons).

A frame is still when its mean absolute difference from the previous one, in grey levels, stays
under STILL_DIFF: x264 repeats a static frame at exactly 0, while grain, a blinking cursor, a
breathing Bubi or a slow push are far above it. numpy and ffmpeg only, so the lesson studio's
own venv can use it too.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

STILL_DIFF = 0.003


def longest_still(mp4: Path, fps: float, size: Tuple[int, int]) -> Dict:
    """{seconds, from}: the longest run of consecutive frames that do not move, and where it starts."""
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                            stdout=subprocess.PIPE)
    n = size[0] * size[1]
    prev, run, best, best_end, k = None, 0, 0, 0, 0
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            frame = np.frombuffer(buf, np.uint8).astype(np.int16)
            if prev is not None:
                run = run + 1 if float(np.abs(frame - prev).mean()) < STILL_DIFF else 0
                if run > best:
                    best, best_end = run, k
            prev, k = frame, k + 1
    finally:
        proc.stdout.close()
        proc.wait()
    seconds = (best + 1) / fps if best else 0.0
    return {"seconds": round(seconds, 2), "from": round((best_end - best) / fps, 2) if best else None}

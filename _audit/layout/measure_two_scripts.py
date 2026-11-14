#!/usr/bin/env python3
"""Card emptiness for two different educational scripts.

    python3 _audit/layout/measure_two_scripts.py

The card-fill fix was prototyped and measured on one video. One video is a
demo, not a result: the phrase lengths in a single script are one sample of
how the grouping happens to fall. This runs the same measurement over a
second, longer script so the number has somewhere to fail.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)

from measure_card_fill import card_fill  # noqa: E402

import video as videomod          # noqa: E402
import video.character as ch      # noqa: E402

SCRIPTS = [
    ("giving_compliments",
     "output/audio/educational/giving_compliments_20260817_154739.json",
     "output/audio/educational/giving_compliments_20260817_154739.mp3"),
    ("edu3_FRESH",
     "output/step3_verify/edu3_FRESH.json",
     "output/step3_verify/edu3_FRESH.mp3"),
]

SAMPLE_FPS = 4


def measure(data_path: str, audio_path: str):
    ch._renderer = None
    ch._renderer_resolved = True
    captured = []
    original = videomod.create_frame_educational

    def spy(t, data, duration, *a, **kw):
        frame = original(t, data, duration, *a, **kw)
        captured.append(np.asarray(frame))
        return frame

    videomod.create_frame_educational = spy
    try:
        videomod.generate_video(
            audio_path=str(ROOT / audio_path), data_path=str(ROOT / data_path),
            output_path="/tmp/two_scripts.mp4", video_type="educational",
            fps=SAMPLE_FPS, background="static_ocean")
    finally:
        videomod.create_frame_educational = original

    rows = [card_fill(f) for f in captured]
    rows = [r for r in rows if r]
    empties = np.array([e for _, _, e in rows])
    return len(rows), float(np.median(empties)), int((empties > 0.5).sum())


def main():
    print(f"{'script':22s} {'frames':>7s} {'median empty':>13s} {'>50% empty':>12s}")
    print("-" * 58)
    for name, dp, ap in SCRIPTS:
        if not (ROOT / dp).exists() or not (ROOT / ap).exists():
            print(f"{name:22s} MISSING")
            continue
        n, med, over = measure(dp, ap)
        print(f"{name:22s} {n:7d} {med:12.0%} {f'{over}/{n}':>12s}")


if __name__ == "__main__":
    main()

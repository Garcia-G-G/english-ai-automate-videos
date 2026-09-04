#!/usr/bin/env python3
"""Grab one frame per changed type, for before/after comparison.

    python3 _audit/layout/grab_frames.py <outdir>

Run once per code state (the caller stashes between runs), then compose.
Timestamps are the ones the layout pin flagged as changed.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)

import video as videomod          # noqa: E402
import video.character as ch      # noqa: E402

TARGETS = [
    ("educational", 6.0, "output/step3_verify/edu2_FRESH.json", "output/step3_verify/edu2_FRESH.mp3"),
    ("quiz", 31.0, "output/step3_verify/q_FRESH.json", "output/step3_verify/q_FRESH.mp3"),
    ("fill_blank", 1.0, "output/r1_verify/trim_run1.json", "output/r1_verify/trim_run1.mp3"),
    ("vocabulary", 1.0, "output/smoke/vocabulary.json", "output/smoke/vocabulary.mp3"),
]

FN = {
    "educational": "create_frame_educational",
    "quiz": "create_frame_quiz",
    "fill_blank": "create_frame_fill_blank",
    "vocabulary": "create_frame_vocabulary",
}


def main(outdir: Path):
    ch._renderer = None
    ch._renderer_resolved = True     # mascot off; this is about text layout
    outdir.mkdir(parents=True, exist_ok=True)

    for vt, want_t, dp, ap in TARGETS:
        grabbed = {}
        name = FN[vt]
        original = getattr(videomod, name)

        def spy(t, data, duration, *a, **kw):
            frame = original(t, data, duration, *a, **kw)
            if abs(float(t) - want_t) < 1e-6:
                grabbed["f"] = np.asarray(frame).copy()
            return frame

        setattr(videomod, name, spy)
        try:
            videomod.generate_video(
                audio_path=str(ROOT / ap), data_path=str(ROOT / dp),
                output_path=str(outdir / f"_{vt}.mp4"),
                video_type=vt, fps=1, background="static_ocean",
            )
        finally:
            setattr(videomod, name, original)

        if "f" not in grabbed:
            print(f"  {vt}: t={want_t} not sampled")
            continue
        Image.fromarray(grabbed["f"][:, :, :3]).save(outdir / f"{vt}.png")
        print(f"  {vt} @ t={want_t} -> {outdir / (vt + '.png')}")

    for f in outdir.glob("_*.mp4"):
        f.unlink()


if __name__ == "__main__":
    main(Path(sys.argv[1]))

#!/usr/bin/env python3
"""STEP 75 §6 A/B: the same Short rendered in-process twice, band (old) then softened (new).

    python3 _audit/stills/STEP75/s6_ab.py OUT_DIR

Same narration (levelled once), same clips, same encoder; only video_types.OPAQUE_PAGE_TYPES
differs. Writes OUT_DIR/{old,new}.mp4, stills new_t{4,30,70}.png / old_t*.png and ab.json.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

NAME = "cómo_se_dice_20261019_163101"


def main(out_dir):
    import subprocess
    import loudness
    import video as videomod
    import video_types
    out = Path(out_dir)
    data = ROOT / "output" / "audio" / "how_do_you_say" / f"{NAME}.json"
    narration = out / "narration.wav"
    if not narration.exists():
        loudness.prepare_narration(data.with_suffix(".mp3"), data, narration)
    clips = ROOT / "output" / "rendering" / "step75_s5" / "clips"
    opaque = video_types.OPAQUE_PAGE_TYPES
    result = {}
    for label, types in (("old", frozenset()), ("new", opaque)):
        video_types.OPAQUE_PAGE_TYPES = types
        t0 = time.time()
        videomod.generate_video(audio_path=str(narration), data_path=str(data), output_path=str(out / f"{label}.mp4"),
                                video_type="how_do_you_say", background=f"clips:{clips}")
        result[label] = round(time.time() - t0, 1)
        for t in (4, 30, 70):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(out / f"{label}.mp4"),
                            "-frames:v", "1", str(out / f"{label}_t{t}.png")], check=True, timeout=60)
        (out / "ab.json").write_text(json.dumps(result))
    return result


if __name__ == "__main__":
    print(main(sys.argv[1]))

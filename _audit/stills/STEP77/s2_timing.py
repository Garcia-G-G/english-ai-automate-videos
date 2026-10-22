#!/usr/bin/env python3
"""STEP 77 §2: time generate_video (frames + encode) on cached audio and footage, per mode.
python3 _audit/stills/STEP77/s2_timing.py OUT_DIR NAME:TYPE [NAME:TYPE ...]"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def main(out_dir, specs):
    import video as V
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in specs:
        name, vtype = spec.split(":")
        audio = ROOT / "output" / "audio" / vtype / name
        dur = json.loads(audio.with_suffix(".json").read_text())["duration"]
        load = os.getloadavg()[0]
        t = time.time()
        V.generate_video(audio_path=str(audio.with_suffix(".mp3")), data_path=str(audio.with_suffix(".json")),
                         output_path=str(out / f"{name}.mp4"), video_type=vtype,
                         background=f"clips:{ROOT / 'output' / 'clips' / name}")
        rows.append({"type": vtype, "artifact": name, "video_s": round(dur, 1), "render_s": round(time.time() - t, 1),
                     "load_before": round(load, 1), "load_after": round(os.getloadavg()[0], 1)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    (out / "timing.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

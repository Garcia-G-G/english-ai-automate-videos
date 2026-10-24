#!/usr/bin/env python3
"""Give a rendered level video today's thinking time without asking for its voice again. FREE.

    python3 tools/level_retime.py output/artifacts/lv001_cocina_step60 lv001_cocina_think4

Every think_<i> in a level narration is generated silence (generate_level_audio_segmented
asks no API for it), so lengthening it is inserting silence at its end and shifting what
follows. The words, already heard and approved, stay the very same samples. The new
artifact gets the retimed audio and its own video, rendered over the source's clips and
gated like any other render.

When every think is already today's, nothing is inserted and the source's audio is copied
byte for byte (a decode and re-encode would move the MP3 padding): that is a re-render
from cached audio, for a change in the picture alone. The render's wall time goes in
video/render.json.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

RATE = 44100


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def _encode(samples: np.ndarray, path: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(path)], input=samples.tobytes(), check=True)


def retime(meta: dict, samples: np.ndarray) -> tuple:
    """(new meta, new samples): each think_<i> lasts what LEVEL_PLANS says today."""
    from tts_elevenlabs import level_thinks
    inserts = []                                       # (at second, extra seconds), in time order
    for i, think in enumerate(level_thinks(meta), start=1):
        st = meta["segment_times"][f"think_{i}"]
        extra = round(think - (st["end"] - st["start"]), 3)
        if extra < 0:
            raise ValueError(f"think_{i} would shrink by {-extra}s; this tool only lengthens")
        inserts.append((st["end"], extra))

    def shift(t: float) -> float:
        # an insert sits at a think's end: that end and everything from it on move
        return round(t + sum(extra for at, extra in inserts if at <= t), 3)

    out = dict(meta)
    out["segment_times"] = {k: {**v, "start": shift(v["start"]), "end": shift(v["end"])}
                            for k, v in meta["segment_times"].items()}
    for k, v in out["segment_times"].items():
        if "duration" in v:
            v["duration"] = round(v["end"] - v["start"], 3)
    out["segments"] = [{**s, **{f: out["segment_times"][s["id"]][f] for f in ("start", "end", "duration")
                                if f in out["segment_times"][s["id"]]}}
                       for s in meta["segments"]]
    pieces, cut = [], 0
    for at, extra in inserts:
        n = int(round(at * RATE))
        pieces += [samples[cut:n], np.zeros(int(round(extra * RATE)), dtype=samples.dtype)]
        cut = n
    pieces.append(samples[cut:])
    new = np.concatenate(pieces)
    out["duration"] = round(len(new) / RATE, 3)
    return out, new


def main():
    import pipeline
    src, name = Path(sys.argv[1]).resolve(), sys.argv[2]
    dst = ROOT / "output" / "artifacts" / name
    if dst.exists():
        sys.exit(f"{dst} exists; pick another name")
    meta = json.loads((src / "audio" / "narration.json").read_text(encoding="utf-8"))
    new_meta, new = retime(meta, _decode(src / "audio" / "narration.mp3"))
    (dst / "audio").mkdir(parents=True)
    shutil.copytree(src / "script", dst / "script")
    audio, data = dst / "audio" / "narration.mp3", dst / "audio" / "narration.json"
    if new_meta["segment_times"] == meta["segment_times"]:
        shutil.copy2(src / "audio" / "narration.mp3", audio)    # nothing grew: the cached audio as is
        new_meta = dict(meta, rerendered_from=src.name)
    else:
        _encode(new, audio)
        new_meta["retimed_from"] = src.name
    data.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    timeout = pipeline.render_timeout(meta["type"])
    started = time.monotonic()
    video = pipeline.render_video(audio, data, dst / "video" / "final.mp4", video_type=meta["type"],
                                  background=f"clips:{src / 'clips'}", timeout=timeout)
    wall = round(time.monotonic() - started, 1)
    (dst / "video" / "render.json").write_text(json.dumps(
        {"video_type": meta["type"], "render_seconds": wall, "timeout_s": timeout}, indent=1), encoding="utf-8")
    print(json.dumps({"render_seconds": wall, **pipeline.finalize_video(video, data)},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

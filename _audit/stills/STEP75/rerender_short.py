#!/usr/bin/env python3
"""Re-render one approved Short from its cached audio and its recorded Pexels queries. $0, no TTS.

    python3 _audit/stills/STEP75/rerender_short.py output/approved/how_do_you_say/<name>.json OUT_DIR

The clips come back through topic_clips.fetch_query (the local cache, else Pexels: free), in the
order the sidecar recorded them. The render goes through pipeline.render_video and
pipeline.finalize_video, as the panel's would. Prints the wall seconds of each stage as JSON.
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from env_setup import ensure_env_loaded  # noqa: E402


def main(sidecar: str, out_dir: str) -> dict:
    ensure_env_loaded()
    import pipeline
    from topic_clips import fetch_query
    meta = json.loads(Path(sidecar).read_text(encoding="utf-8"))
    name, vtype = meta["artifact"], meta["video_type"]
    audio = ROOT / "output" / "audio" / vtype / f"{name}.mp3"
    data = audio.with_suffix(".json")
    out = Path(out_dir)
    clips = out / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, clip in enumerate(meta["background"]["clips"]):
        got = fetch_query(clip["query"])
        if got is None:
            raise SystemExit(f"no clip for {clip['query']!r}")
        shutil.copy2(got, clips / f"{i:02d}_{got.name}")
    t1 = time.time()
    video = out / f"{name}.mp4"
    pipeline.render_video(audio, data, video, vtype, background=f"clips:{clips}",
                          timeout=pipeline.render_timeout(vtype))
    t2 = time.time()
    fin = pipeline.finalize_video(video, data)
    t3 = time.time()
    return {"clips": round(t1 - t0, 1), "frames+encode": round(t2 - t1, 1), "gate+outro": round(t3 - t2, 1),
            "final": fin}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    result = main(sys.argv[1], sys.argv[2])
    text = json.dumps(result, ensure_ascii=False, default=str, indent=1)
    (Path(sys.argv[2]) / "result.json").write_text(text, encoding="utf-8")
    print(text)

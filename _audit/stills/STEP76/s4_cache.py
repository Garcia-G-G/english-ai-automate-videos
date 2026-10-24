#!/usr/bin/env python3
"""STEP 76 §4 proof: the same script through tts_bilingual twice; the second run asks nothing.
python3 _audit/stills/STEP76/s4_cache.py <script.json> <out_dir>   (the first run is PAID on a cold cache)"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def main(script_path, out_dir):
    from env_setup import ensure_env_loaded
    ensure_env_loaded()
    import tts_bilingual as TB
    import tts_cache
    import tts_elevenlabs as TE
    real = TE.get_client
    asked = {"calls": 0, "chars": 0}

    def counting_client():
        client = real()
        tts = client.text_to_speech
        for name in ("convert", "convert_with_timestamps"):
            fn = getattr(tts, name)
            def wrapped(*a, _fn=fn, **kw):
                asked["calls"] += 1
                asked["chars"] += len(kw.get("text", ""))
                return _fn(*a, **kw)
            setattr(tts, name, wrapped)
        return client
    TE.get_client = counting_client
    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    script = script.get("script_data") or script
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs = []
    for n in (1, 2):
        before = dict(asked)
        tts_cache.STATS.update(hits=0, misses=0)
        t = time.time()
        r = TB.generate_bilingual_narration(script, str(out / f"run{n}.mp3"))
        runs.append({"run": n, "http_calls": asked["calls"] - before["calls"],
                     "chars_sent": asked["chars"] - before["chars"],
                     "usd": round((asked["chars"] - before["chars"]) / 1000 * 0.11, 4),
                     "cache": dict(tts_cache.STATS), "seconds": round(time.time() - t, 1),
                     "duration": r["duration"]})
    (out / "cache_runs.json").write_text(json.dumps(runs, indent=1))
    return runs


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1))

#!/usr/bin/env python3
"""STEP 76 §2 proof: re-synthesise one educational script through tts_bilingual (PAID) and
measure its seams.

    python3 _audit/stills/STEP76/s2_resynth.py <script.json> <out_dir>

Seams: for each pair of clips, the silence between the last speech of one and the first of
the next (against the configured pause), the level of the last 1 ms of one clip and the first
1 ms of the next (dBFS; a loud edge is a click), and the largest sample step across the join.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

TURBO_PER_1K = 0.11


def seams(mp3: Path, calls: list) -> list:
    import loudness
    x = loudness.decode(mp3)
    rate, frame = loudness.RATE, int(0.005 * loudness.RATE)

    def speech(a, b):
        seg = x[int(a * rate):int(b * rate)]
        n = seg.size // frame
        db = 10 * np.log10(np.maximum((seg[:n * frame].reshape(n, frame) ** 2).mean(1), 1e-12))
        loud = np.where(db > -45)[0]
        return (a + loud[0] * frame / rate, a + (loud[-1] + 1) * frame / rate) if loud.size else (a, a)

    out = []
    for c, d in zip(calls, calls[1:]):
        _, end = speech(c["clip_start"], c["clip_end"])
        start, _ = speech(d["clip_start"], d["clip_end"])
        b = int(c["clip_end"] * rate)
        db = lambda v: round(20 * float(np.log10(v + 1e-9)), 1)
        out.append({"after": c["index"], "lang": f"{c['lang']}→{d['lang']}", "configured_pause": c["pause_after"],
                    "silence_between_speech": round(start - end, 3),
                    "edge_out_dbfs": db(np.max(np.abs(x[b - 44:b]))),
                    "edge_in_dbfs": db(np.max(np.abs(x[int(d["clip_start"] * rate):int(d["clip_start"] * rate) + 44]))),
                    "step_dbfs": db(np.max(np.abs(np.diff(x[b - 44:b + 44]))))})
    return out


def main(script_path, out_dir):
    from env_setup import ensure_env_loaded
    ensure_env_loaded()
    import tts_bilingual as TB
    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    script = script.get("script_data") or script
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (Path(script_path).stem + ".mp3")
    result = TB.generate_bilingual_narration(script, str(out))
    sent = sum(len(c["text"]) * c.get("takes", 1) for c in result["tts_calls"])
    report = {"sent_chars": sent, "usd_turbo": round(sent / 1000 * TURBO_PER_1K, 4),
              "duration": result["duration"], "calls": result["tts_calls"], "seams": seams(out, result["tts_calls"])}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2])
    print(json.dumps({k: v for k, v in r.items() if k != "calls"}, ensure_ascii=False, indent=1, default=str))

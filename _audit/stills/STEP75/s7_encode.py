"""STEP 75 §7 proof: python3 _audit/stills/STEP75/s7_encode.py <registered lesson.mp4> (re-encodes it in place)."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "manim_voiceover_poc")); sys.path.insert(0, str(ROOT / "src"))
import renders as R
t = time.time()
report = R.final_encode(Path(sys.argv[1]))
report["seconds"] = round(time.time() - t, 1)
(ROOT / "output" / "rendering" / "step75_s7" / "encode.json").write_text(json.dumps(report))
print(report)

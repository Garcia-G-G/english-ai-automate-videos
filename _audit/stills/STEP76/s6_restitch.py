#!/usr/bin/env python3
"""STEP 76 §6 proof: re-stitch a script from its cached TTS clips ($0) with one code tree.
python3 _audit/stills/STEP76/s6_restitch.py <src_dir> <script.json> <out.json>
The API client is replaced by one that refuses, so a single uncached clip fails the run."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
src_dir, script_path, out_path = sys.argv[1:4]
sys.path.insert(0, str(Path(src_dir).resolve()))
import logging
logging.disable(logging.WARNING)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")                 # a worktree has no .env of its own
from env_setup import ensure_env_loaded  # noqa: E402
ensure_env_loaded()
import tts_cache  # noqa: E402
import tts_elevenlabs as TE  # noqa: E402
import tts_bilingual as TB  # noqa: E402
tts_cache.CACHE_DIR = REPO / "output" / "cache" / "tts"
TE.get_client = lambda: (_ for _ in ()).throw(RuntimeError("uncached clip: would call the API"))
script = json.loads(Path(script_path).read_text(encoding="utf-8"))
script = script.get("script_data") or script
mp3 = str(Path(out_path).with_suffix(".mp3"))
r = TB.generate_bilingual_narration(script, mp3)
keep = {"duration": r["duration"], "words": r["words"], "segments": r.get("segments"),
        "clips": [{k: c.get(k) for k in ("index", "clip_start", "clip_end", "takes", "gain_db")} for c in r["tts_calls"]],
        "cache": dict(tts_cache.STATS)}
Path(out_path).write_text(json.dumps(keep, ensure_ascii=False, indent=1))
print(json.dumps({"duration": keep["duration"], "words": len(keep["words"]), "cache": keep["cache"]}))

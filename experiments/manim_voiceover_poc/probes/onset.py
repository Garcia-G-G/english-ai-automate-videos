"""Onset of a speech file: where it starts, and whether it starts with a short fragment
(burst → dip → speech) — the «i-ira» the owner hears. 5 ms RMS frames.

The code lives in src/stitch.py since STEP 76 §2 (shared with the Shorts); this module
re-exports it for the probes and their tests."""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[3] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from stitch import (FINE, FRAME, RATE, _fine, _hf_share, doubled_onset, env_db,  # noqa: E402,F401
                    fragment, load, onset)

if __name__ == "__main__":
    for path in sys.argv[1:]:
        x = load(path)
        s, e = onset(x)
        print(path, s * 5 if s is not None else None, fragment(e, s, e.max()) if s is not None else None)

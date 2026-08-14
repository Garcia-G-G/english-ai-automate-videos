#!/usr/bin/env python3
"""Re-measure the mascot's per-frame cost, with and without the memo fix.

    python3 _audit/layout/measure_mascot_cost.py

The first attempt at this number compared two whole renders run back to back
and got +0.0955 s/frame, which did not reproduce — the machine was cold for
the first one. Conditions are alternated here so thermal drift cancels
instead of landing entirely on whichever ran first.

config.yaml is really rewritten between conditions rather than _load_config
being stubbed, because the per-frame yaml.safe_load is the thing under test
and stubbing it out would measure its absence.
"""

import importlib
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

CONFIG = ROOT / "config.yaml"
BACKUP = ROOT / "_audit" / "layout" / "_config_backup.yaml"
CHAR = ROOT / "src" / "video" / "character.py"
CHAR_BACKUP = ROOT / "_audit" / "layout" / "_character_backup.py"
PRE_FIX_REV = "ac90bab^"      # everything except the memo fix

N_FRAMES = 120
WARMUP = 15


def set_enabled(flag: bool) -> None:
    text = CONFIG.read_text()
    other = "true" if not flag else "false"
    want = "true" if flag else "false"
    CONFIG.write_text(text.replace(f"character:\n  enabled: {other}",
                                   f"character:\n  enabled: {want}"))


def bench(enabled: bool, words, duration: float) -> float:
    """Median seconds per finalize_frame call under this condition."""
    import video.character as ch
    from video.utils import create_base_frame, finalize_frame

    set_enabled(enabled)
    ch._renderer = None
    if hasattr(ch, "_renderer_resolved"):
        ch._renderer_resolved = False

    for i in range(WARMUP):
        f, d = create_base_frame(5.0 + i * 0.033)
        finalize_frame(f, d, 5.0 + i * 0.033, duration, words)

    times = []
    for i in range(N_FRAMES):
        t = 5.0 + i * 0.0333
        f, d = create_base_frame(t)
        t0 = time.perf_counter()
        finalize_frame(f, d, t, duration, words)
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def run_pair(label: str, words, duration: float) -> tuple:
    """Alternate OFF/ON twice each so drift cancels."""
    a1 = bench(False, words, duration)
    b1 = bench(True, words, duration)
    a2 = bench(False, words, duration)
    b2 = bench(True, words, duration)
    off, on = (a1 + a2) / 2, (b1 + b2) / 2
    print(f"  {label:22s} OFF={off:.4f}  ON={on:.4f}  "
          f"delta=+{on - off:.4f} s/frame  (+{100 * (on - off) / off:.0f}%)")
    return off, on


def main():
    import json
    shutil.copy(CONFIG, BACKUP)
    shutil.copy(CHAR, CHAR_BACKUP)

    data = json.loads((ROOT / "_audit/mascota/render/edu.json").read_text())
    words, duration = data["words"], data["duration"]

    try:
        from video.backgrounds import set_background
        set_background("photo_earth")

        print(f"finalize_frame, {N_FRAMES} frames per condition, "
              f"conditions alternated twice\n")

        fixed = run_pair("memo fix IN  (HEAD)", words, duration)

        # Swap in the pre-fix character.py and reload the module tree.
        old = subprocess.run(["git", "show", f"{PRE_FIX_REV}:src/video/character.py"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        CHAR.write_text(old)
        import video.character as ch
        importlib.reload(ch)
        import video.utils as vu
        importlib.reload(vu)

        prefix = run_pair("memo fix OUT (before)", words, duration)

        print()
        print(f"  effect of the memo fix on the OFF side: "
              f"{prefix[0]:.4f} -> {fixed[0]:.4f} s/frame "
              f"({100 * (prefix[0] - fixed[0]) / prefix[0]:+.0f}%)")
        print(f"  effect of the memo fix on the ON  side: "
              f"{prefix[1]:.4f} -> {fixed[1]:.4f} s/frame "
              f"({100 * (prefix[1] - fixed[1]) / prefix[1]:+.0f}%)")
    finally:
        shutil.copy(CHAR_BACKUP, CHAR)
        shutil.copy(BACKUP, CONFIG)
        CHAR_BACKUP.unlink(missing_ok=True)
        BACKUP.unlink(missing_ok=True)
        print("\nrestored config.yaml and character.py")


if __name__ == "__main__":
    main()

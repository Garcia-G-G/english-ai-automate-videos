#!/usr/bin/env python3
"""Timing-engine validation over a REAL audio data.json.

    python3 tests/test_timing_engine.py [path/to/data.json]

Builds word groups exactly like the render pipeline does, applies the
timing engine and prints the display-window table, asserting every rule:
golden rule (no exit before last word + 350ms), minimum hold, no
overlaps, no dead gaps > HOLD threshold, monotonicity, clamped alphas.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from video.educational import add_sentence_boundaries        # noqa: E402
from video.v2 import timing_engine as TE                     # noqa: E402


def build_groups(data):
    words = data.get("words") or []
    proc = SubtitleProcessor()
    if not words:
        words = proc.estimate_words_from_segments(
            data.get("segments", []), data.get("english_phrases", []))
    words = add_sentence_boundaries(words, data.get("full_script", ""))
    return proc.group_words(words)


def main():
    path = (sys.argv[1] if len(sys.argv) > 1 else
            str(ROOT / "output/audio/educational/give_up_20260113_185732.json"))
    data = json.load(open(path, encoding="utf-8"))
    duration = float(data["duration"])
    cta_start = max(0.0, duration - 2.5)

    groups = build_groups(data)
    print(f"data: {path}")
    print(f"duration={duration:.2f}s  cta_start={cta_start:.2f}s  "
          f"groups={len(groups)}\n")

    groups = TE.compute_display_windows(groups, duration,
                                        content_end=cta_start)
    print(TE.debug_table(groups))

    # ── Rule checks (beyond the engine's internal asserts) ────────────
    problems = []
    for i, g in enumerate(groups):
        t_in, t_out = g["display_start"], g["display_end"]
        dur = t_out - t_in
        lwe = TE._last_word_end(g)
        next_in = (groups[i + 1]["display_start"] if i + 1 < len(groups)
                   else None)

        # Golden rule (unless clamped by overlapping next audio)
        if (next_in is None or lwe + TE.TAIL_PAD <= next_in) and \
                t_out < lwe + TE.TAIL_PAD - 1e-3:
            problems.append(f"group {i}: exits {t_out:.2f} < last word "
                            f"{lwe:.2f}+{TE.TAIL_PAD}")
        # Minimum hold (unless clamped by neighbor)
        min_d = TE._min_duration(g)
        if dur < min_d - 1e-3 and next_in is not None and t_out < next_in - 1e-3:
            problems.append(f"group {i}: window {dur:.2f}s < min {min_d:.2f}s")
        # No overlap
        if next_in is not None and t_out > next_in + 1e-3:
            problems.append(f"group {i}: overlaps next")
        # No dead gap beyond HOLD_RELEASE
        if next_in is not None and next_in - t_out > TE.HOLD_RELEASE + 1e-3:
            problems.append(f"group {i}: dead gap {next_in - t_out:.2f}s")

    # Alpha clamping sweep
    t = 0.0
    while t < duration:
        for g in groups:
            a = TE.group_alpha(g, t)
            if a < 0.0 or a > 1.0:
                problems.append(f"alpha out of range at t={t:.2f}: {a}")
        t += 0.05
    # Never two groups visible at once
    t = 0.0
    while t < duration:
        vis = sum(1 for g in groups if TE.group_alpha(g, t) > 0.0)
        if vis > 1:
            problems.append(f"{vis} groups visible at t={t:.2f}")
        t += 0.05

    print()
    if problems:
        print(f"{len(problems)} RULE VIOLATIONS:")
        for p in problems[:20]:
            print("  -", p)
        sys.exit(1)
    print("ALL TIMING RULES SATISFIED "
          "(golden rule, min hold, no overlap, no dead gaps, alpha in [0,1])")


if __name__ == "__main__":
    main()

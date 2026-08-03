# QA gate baselines

One file per capture. **Old baselines are kept, never deleted** — a stale
baseline is still the only record of what the gate reported at that commit.

| baseline | commit | blocking | artifacts | use |
|---|---|---|---|---|
| `qa_baseline_2026-07-30.json` | `812aae8` | off | 195 | historical only |
| `qa_baseline_2026-08-03.json` | `a87a513` | **on** | 206 | **current** |

## Always diff against the CURRENT baseline

The 2026-07-30 capture predates `BLOCKING` (added in `3ca6cbd`), so it contains
no `missing_required_timing` flags — that check did not exist yet. Diffing new
work against it reports **52 phantom regressions** that are really just the
flag appearing for the first time. Two other deltas have the same cause: the
resolved `clipping` (37) is the ppm rule replacing the `-1.0 dB` peak test, and
`speech_in_declared_silence` (26) is the countdown-evidence fix.

Every step so far worked around this by diffing immediately-before-the-change
against after, which is correct but should not have to be re-derived each time.

Each baseline carries a `_capture` block recording the commit, whether blocking
was on, the thresholds in force, and which flags it is capable of reporting —
so a future diff can tell "this flag is new" from "this artifact regressed".

## Re-capture when

- a check is added, removed, or its threshold changes
- `BLOCKING` or `BLOCKING_FLAGS` changes
- the artifact corpus grows materially

## How

    python3 src/qa_gate.py                       # writes output/qa/
    # then copy output/qa/_baseline_summary.json here with a _capture block

The gate never changes an exit code, so this is always safe to run.

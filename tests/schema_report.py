#!/usr/bin/env python3
"""Run script_schema over the fixture corpus and print a result table.

    python tests/schema_report.py

The video type is taken from the fixture's parent directory, not from its
`type` key — otherwise a script with a missing/wrong `type` would be reported
against the wrong model and the failure would read as noise.

This is a reporting tool, not a test. The pinned expectations live in
tests/test_script_schema.py.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from script_schema import check_script  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "scripts"


def main() -> int:
    rows = []
    for path in sorted(FIXTURES.glob("*/*.json")):
        video_type = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        _, errors, warnings = check_script(
            data, video_type=video_type, source=str(path.relative_to(ROOT)))
        rows.append((video_type, path.name, errors, warnings))

    width_t = max(len(r[0]) for r in rows)
    width_f = max(len(r[1]) for r in rows)

    print(f"{'TYPE':<{width_t}}  {'FIXTURE':<{width_f}}  RESULT")
    print("-" * (width_t + width_f + 12))
    for video_type, name, errors, warnings in rows:
        verdict = "FAIL" if errors else "pass"
        print(f"{video_type:<{width_t}}  {name:<{width_f}}  {verdict}")
        for e in errors:
            print(f"{'':<{width_t + width_f + 4}}  ! {e}")

    n_fail = sum(1 for r in rows if r[2])
    print()
    print(f"{len(rows) - n_fail}/{len(rows)} pass, {n_fail} fail")

    print()
    print("LINT WARNINGS (advisory; do not block a render)")
    print("-" * (width_t + width_f + 12))
    total = 0
    for video_type, name, errors, warnings in rows:
        if errors:
            print(f"{video_type}/{name}: (not validated)")
            continue
        if not warnings:
            print(f"{video_type}/{name}: -")
            continue
        print(f"{video_type}/{name}:")
        for w in warnings:
            total += 1
            print(f"    ~ {w}")
    print()
    print(f"{total} lint warnings across the corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

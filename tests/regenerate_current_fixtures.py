#!/usr/bin/env python3
"""Regenerate the `current` fixture tier — one fresh script per video type.

    OPENAI_API_KEY=... python3 tests/regenerate_current_fixtures.py

Why this tier exists
--------------------
Every fixture under tests/fixtures/scripts/<type>/ predates the current
prompts (newest is 2026-04-16; the prompts changed on 2026-03-17 and
2026-03-24). The schema was derived from historical output and validated
against historical output, which proves backward compatibility and nothing
else. This tier answers the other question: does TODAY's generator emit
something TODAY's schema accepts?

The two tiers test different things and must not be mixed:

    scripts/<type>/    historical — backward compatibility
    scripts/current/   present-tense correctness

Script generation only. No TTS, no render. ~$0.003 per full run on
gpt-4o-mini.

Topic selection is deterministic — always index 0 of the named category — so
a re-run is comparable to the last one. The category per type mirrors the
historical corpus where one exists, so the comparison is apples-to-apples.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Bare load_dotenv() on purpose: it walks up from cwd, and this checkout's
# .env lives in the PARENT of the repo root. `load_dotenv(ROOT / ".env")`
# — what src/admin.py:39 does — silently finds nothing here.
from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from script_generator import generate_script, load_topics  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "scripts" / "current"

# (video_type, category) — category chosen to match the historical fixture of
# the same type where one exists.
PLAN = [
    ("educational",   "false_friends"),   # matches educational/actually.json
    ("quiz",          "slang"),           # matches quiz/cool_20260416_084217
    ("true_false",    "false_friends"),   # matches true_false/actually.json
    ("fill_blank",    "grammar"),
    ("pronunciation", "pronunciation"),   # matches pronunciation/asking_for_help
    ("vocabulary",    "food_restaurant"),
]


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)

    for video_type, category in PLAN:
        topic = load_topics(category)[0]
        print(f"generating {video_type:<14} category={category}")
        script = generate_script(category, topic, video_type)

        path = OUT / f"{video_type}.json"
        path.write_text(
            json.dumps(script, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

        warns = script.get("_validation_warnings", [])
        errs = script.get("_validation_errors", [])
        print(f"  -> {path.relative_to(ROOT)}  "
              f"({len(errs)} errors, {len(warns)} warnings)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""SMOKE: generate one real artifact per type, run the QA gate, report.

    make smoke                    # all six types
    make smoke TYPES=quiz,educational
    python3 tests/smoke_generate.py --types quiz

COSTS MONEY AND CALLS THE LIVE API. Run manually before a release, never per
commit. Roughly $0.50 and ~10 minutes for the full set.

WHY THIS EXISTS. A NameError broke live educational generation for two
commits while 136 tests passed, because every test avoids the paid paths. A
second bug broke fill_blank, true_false and vocabulary the same way. Both were
found by hand-generating an artifact — so that is now a target instead of a
thing someone remembers to do.

It matters more with BLOCKING on: a broken generator means every artifact is
rejected for the wrong reason, and the reject report will say "no timing
declaration" rather than "the generator raised".

tests/test_generator_add_audio_arity.py is the free complement — it catches
contract drift from source, at commit time. Keep both: one proves the shape,
this one proves it runs.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: One representative script per type. Chosen to be real corpus scripts that
#: validate, so a failure here is the GENERATOR, not the input.
CASES = {
    "quiz":          "output/scripts/quiz/fabric_20260116_201133.json",
    "true_false":    "output/scripts/true_false/actually.json",
    "fill_blank":    "output/scripts/fill_blank/desert_vs_dessert_20260210_175642.json",
    "vocabulary":    "output/scripts/vocabulary/pull_vs_pool_20260210_183300.json",
    "educational":   "output/scripts/educational/freak_out_20260202_142757.json",
    "pronunciation": "output/scripts/pronunciation/asking_for_help_20260207_151200.json",
}

OUT = ROOT / "output" / "smoke"


def _generate(vtype: str, script: dict, out_mp3: str) -> dict:
    """Route exactly as pipeline.py:157 does, so smoke tests the real path."""
    if vtype in ("educational", "pronunciation"):
        from tts_bilingual import generate_bilingual_narration
        res = generate_bilingual_narration(script, out_mp3)
        merged = dict(script)
        merged.update(res)
        return merged
    import tts_elevenlabs as TE
    fn = getattr(TE, f"generate_{vtype}_audio_segmented")
    return fn(script, out_mp3)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--types", default=",".join(CASES),
                    help="comma-separated subset of: " + ",".join(CASES))
    args = ap.parse_args(argv)
    wanted = [t.strip() for t in args.types.split(",") if t.strip()]

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)

    from qa_gate import analyze, verdict

    rows, failures = [], 0
    for vtype in wanted:
        rel = CASES.get(vtype)
        if rel is None:
            print(f"  {vtype:14} SKIP — no smoke case defined")
            continue
        src = ROOT / rel
        if not src.exists():
            print(f"  {vtype:14} SKIP — script missing: {rel}")
            continue

        mp3 = OUT / f"{vtype}.mp3"
        t0 = time.time()
        try:
            script = json.loads(src.read_text(encoding="utf-8"))
            result = _generate(vtype, script, str(mp3))
            (OUT / f"{vtype}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:                      # noqa: BLE001 — report every type
            failures += 1
            print(f"  {vtype:14} GENERATOR FAILED  {type(e).__name__}: {e}")
            rows.append({"type": vtype, "generated": False, "error": repr(e)})
            continue

        report = analyze(OUT / f"{vtype}.json")
        v = verdict(report) if report else {"verdict": "NO_REPORT", "blocking_flags": []}
        if v["verdict"] != "PASS":
            failures += 1
        rows.append({"type": vtype, "generated": True, **v})
        print(f"  {vtype:14} {v['verdict']:>7}  {time.time()-t0:5.1f}s  "
              f"{v.get('blocking_flags') or ''}")

    (OUT / "_smoke_report.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(rows)} types, {failures} not passing -> {OUT}/_smoke_report.json")
    # Non-zero ONLY here, in the smoke target. The gate itself never changes an
    # exit code; this is a release check and is meant to fail a release.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

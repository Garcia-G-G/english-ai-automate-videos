#!/usr/bin/env python3
"""The gate's own acceptance criterion: it must FLAG the known-bad cases.

    python3 -m pytest tests/test_qa_gate_known_bad.py -v

If the gate passes tests/fixtures/known_bad/, the gate is broken — and we
already know exactly what that failure mode looks like, because
quality_reviewer.py and video_analyzer.py passed everything for months by
auditing the generator's own self-report.

Each case is asserted at the layer it actually lives in. An audio gate cannot
detect a render timeout, and pretending otherwise would be its own silent lie,
so those cases assert scope explicitly rather than a verdict.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qa_gate import LETTER_WORD_MIN_SILENCE, analyze  # noqa: E402

MANIFEST = ROOT / "tests" / "fixtures" / "known_bad" / "manifest.json"


def _audio_json(script_rel: str) -> Path:
    """scripts/quiz/x.json -> output/audio/quiz/x.json"""
    return ROOT / "output" / "audio" / script_rel.replace("scripts/", "")


def _cases(group: str):
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {c["id"]: c for c in m.get(group, [])}


def _report(script_rel: str):
    j = _audio_json(script_rel)
    if not j.exists():
        pytest.skip(f"artifact not in the corpus: {j}")
    r = analyze(j)
    if r is None:
        pytest.skip(f"no paired mp3 for {j}")
    return r


# ── acoustic: the one the gate exists to catch ───────────────────────

def test_afabric_option_letter_elision_is_flagged():
    """The letter is elided into the following word: 'Opción A, fábrica' heard
    as 'Opción afábrica'. Invisible to every JSON check — the script is
    well-formed and the defect exists only in the waveform. This is the case
    that proves the gate measures audio."""
    case = _cases("acoustic_cases")["afabric_option_letter_elision"]
    r = _report(case["source_script"])
    l2w = r["checks"]["letter_to_word"]

    assert l2w["available"], "check 3 could not run — the gate cannot see this case"
    assert l2w["verdict"] == "LETTER_ELIDED_INTO_WORD", (
        f"gate PASSED the afabric case: gaps={l2w['letter_to_word_gaps_s']} "
        f"vs required {LETTER_WORD_MIN_SILENCE}s. The gate is broken."
    )
    assert l2w["worst_s"] < LETTER_WORD_MIN_SILENCE
    assert any(f.startswith("letter_to_word:") for f in r["flags"])


def test_afabric_assertion_matches_the_manifest():
    """The manifest states the rule as >= 250 ms. Pin that the gate uses the
    same number rather than a second, drifting copy."""
    case = _cases("acoustic_cases")["afabric_option_letter_elision"]
    assert "250" in case["assertion"]
    assert LETTER_WORD_MIN_SILENCE == 0.250


# ── script_json: the audio-visible half of that case ─────────────────

def test_fabric_educational_zero_word_timestamps_is_flagged():
    """Of this case's three defects, one is audio-visible: the companion TTS
    JSON has words: [] so nothing can drive word-level karaoke.

    This artifact DOES carry segment_times, so check 1 runs on it and is
    perfectly happy. That is exactly the trap — a gate that only reported
    drift would score this file as clean while the karaoke it renders has no
    timeline at all. educational renders word-level karaoke, so an empty word
    array must be flagged on its own.
    """
    case = _cases("schema_cases")["fabric_educational_20260116_192025"]
    r = _report(case["script"])

    assert r["n_words"] == 0, "fixture changed: this case is defined by words: []"
    assert r["video_type"] == "educational"
    assert not r["checks"]["sentence_timeline"]["available"], (
        "check 2 cannot run without a word timeline"
    )
    assert "no_word_timeline" in r["flags"], (
        f"gate PASSED an educational artifact with words: [] — flags={r['flags']}. "
        "Word-level karaoke has nothing to render from and the gate said nothing."
    )


def test_fabric_educational_other_defects_are_not_this_gates_layer():
    """The other two defects (no full_script, Spanish in english_phrases) are
    script-JSON, already enforced by script_schema and the Step 1 tests. Recorded
    so nobody later expects the audio gate to catch them."""
    case = _cases("schema_cases")["fabric_educational_20260116_192025"]
    kinds = {d["kind"] for d in case["defects"]}

    assert kinds == {"missing_required_field", "spanish_token_in_english_phrases",
                     "zero_word_timestamps"}


# ── render: explicitly out of scope, asserted as scope ───────────────

@pytest.mark.parametrize("case_id", ["cool_20260416_084217",
                                     "scared_stiff_20260416_083126",
                                     "lay_vs_lie_20260416_082045"])
def test_render_timeout_cases_are_out_of_scope_but_still_analysed(case_id):
    """These are ffmpeg-deadlock render timeouts, fixed in d96c65b. An audio
    gate has no instrument for render wall-clock, so it must NOT claim them.
    It does still analyse their audio, and in fact flags all three for the
    letter-elision defect they share with every quiz."""
    case = _cases("render_cases")[case_id]
    assert case["defects"][0]["kind"] == "render_timeout"

    r = _report(case["script"])
    assert "render_timeout" not in " ".join(r["flags"]), (
        "the audio gate must not claim to detect render wall-clock"
    )
    # but it is not silent about them either
    assert r["flags"], f"{case_id} produced no flags at all"


def test_every_manifest_case_is_accounted_for():
    """No case may be silently dropped from this file."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = {c["id"] for g in ("acoustic_cases", "schema_cases", "render_cases")
           for c in m.get(g, [])}

    covered = {"afabric_option_letter_elision",
               "fabric_educational_20260116_192025",
               "cool_20260416_084217", "scared_stiff_20260416_083126",
               "lay_vs_lie_20260416_082045"}

    assert ids == covered, f"manifest changed; unaccounted cases: {ids ^ covered}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

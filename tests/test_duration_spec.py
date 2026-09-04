#!/usr/bin/env python3
"""Duration is a specification, judged after synthesis, recorded either way.

    python3 -m pytest tests/test_duration_spec.py

THE DEFECT THIS PINS. Nothing in the pipeline aimed at a duration. Video
length was whatever the script model happened to write plus whatever fixed
structure its type adds, and 27 of 138 measured videos — 20% — landed in the
50-80 s band. Duration was an outcome nobody checked.

THREE MEASUREMENT TRAPS, each of which produced a wrong number before it was
found, and each pinned below:

  1. UNPAIRED ARITHMETIC. Overheads had been computed from one group's audio
     duration against a different group's video duration. Recomputed per
     artifact — same mp3, same mp4 — educational's overhead came out at
     9.5 s against an earlier ~20.8 s estimate.

  2. full_script IS NOT WHAT IS SPOKEN. On quiz it carries 140 words where
     the segments carry 53. A word target aimed at full_script aims at
     nothing.

  3. DECLARED SILENCE IS INSIDE THE NARRATION. Countdowns and repeat-pauses
     are part of the narration duration, so they never appear in
     video-minus-narration. project() must add the outro and nothing else,
     or the silence is counted twice.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import duration_spec as ds  # noqa: E402

TYPES = ["educational", "pronunciation", "vocabulary",
         "true_false", "fill_blank", "quiz"]


# ────────────── the spec lives in config, not in a prompt string ──────────────

def test_every_type_has_a_measured_spec():
    for t in TYPES:
        spec = ds.type_spec(t)
        assert spec is not None, t
        assert spec["rate"] > 0 and spec["silence"] >= 0
        assert spec["n"] > 0, f"{t} records no sample size — is it measured?"


def test_an_unmeasured_type_returns_none_rather_than_a_default():
    """A default rate would put an invented number in the same field as six
    measured ones, indistinguishable from them."""
    assert ds.type_spec("banana") is None
    assert ds.word_target("banana") is None
    assert ds.overhead("banana") is None


def test_the_prompt_instruction_comes_from_config_not_a_literal():
    """(a) says the target is config, not hardcoded in a prompt. If the band
    moves, the prompt text must move with it without a code edit."""
    import script_generator as sg
    before = sg.build_prompt_pronunciation("travel", {"topic": "quiet"})
    assert str(ds.word_range("pronunciation")["target"]) in before
    assert "50 y 80 segundos" in before


def test_no_prompt_still_hardcodes_a_duration():
    """Every builder used to open with its own '20-30 segundos'. Those are
    the numbers that disagreed with each other and with reality."""
    import inspect

    import script_generator as sg
    for name in ("educational", "quiz", "true_false", "fill_blank",
                 "pronunciation", "vocabulary"):
        src = inspect.getsource(getattr(sg, f"build_prompt_{name}"))
        assert "duration_rule" in src, name
        assert "segundos para" not in src.split("duration_rule")[0], name


# ──────────────────────────── the arithmetic ────────────────────────────

def test_overhead_is_declared_silence_plus_the_outro():
    for t in TYPES:
        assert ds.overhead(t) == pytest.approx(
            ds.type_spec(t)["silence"] + ds.outro_seconds())


def test_projection_adds_only_the_outro():
    """Trap 3. The narration already contains its declared silence; adding
    it again here would double-count and every video would read long."""
    assert ds.project("quiz", 41.0) == pytest.approx(41.0 + ds.outro_seconds())


def test_word_target_inverts_the_projection():
    """A video built to the word target must land on the target duration.
    Round-trip, so the two formulas cannot drift apart."""
    for t in TYPES:
        words = ds.word_target(t)
        speech = words / ds.type_spec(t)["rate"]
        narration = speech + ds.type_spec(t)["silence"]
        assert ds.project(t, narration) == pytest.approx(
            ds.band()["target_seconds"], abs=0.5), t


def test_the_word_range_brackets_the_band():
    for t in TYPES:
        r = ds.word_range(t)
        assert r["min"] < r["target"] < r["max"], t


def test_the_target_is_centred_so_a_miss_still_lands_in_band():
    """A model that misses by 20% from the centre stays inside; aimed at an
    edge it would fall out on every miss in one direction."""
    b = ds.band()
    assert b["min_seconds"] < b["target_seconds"] < b["max_seconds"]
    assert abs((b["min_seconds"] + b["max_seconds"]) / 2
               - b["target_seconds"]) < 1.0


# ─────────────────────────── the recorded verdict ───────────────────────────

def test_a_video_inside_the_band_passes():
    v = ds.check("quiz", narration_seconds=60.0)
    assert v["status"] == ds.PASS and v["projected_seconds"] == 64.0


@pytest.mark.parametrize("narration,edge", [(20.0, "floor"), (90.0, "ceiling")])
def test_out_of_band_is_recorded_with_the_edge_it_missed(narration, edge):
    v = ds.check("quiz", narration_seconds=narration)
    assert v["status"] == ds.OUT_OF_BAND
    assert edge in v["reason"]


def test_the_verdict_is_shaped_like_a_gate_record():
    """It sits in artifact.gates beside compatibility and final_qa, so an
    operator should not have to learn a second vocabulary to read it."""
    v = ds.check("quiz", 60.0)
    assert v["kind"] == "duration" and v["version"] == 1
    assert set(v) >= {"kind", "version", "status", "reason", "band"}


def test_a_measured_video_beats_the_projection():
    """Before the render only a projection exists; after it, the real thing
    does, and the record must not keep asserting the estimate."""
    v = ds.check("quiz", narration_seconds=60.0, measured_video_seconds=95.0)
    assert v["status"] == ds.OUT_OF_BAND
    assert v["measured_seconds"] == 95.0
    assert v["projected_seconds"] == 64.0, "the projection is kept, not overwritten"


def test_an_unmeasured_type_is_not_a_pass():
    """Same rule as the timing contract: unknown is a refusal to judge."""
    v = ds.check("banana", 60.0)
    assert v["status"] == ds.UNKNOWN != ds.PASS


# ───────────────────────────── repetition ─────────────────────────────

def test_repetition_is_configured_per_type_and_educational_is_untouched():
    """The owner judges current pacing good. educational declares 1 take, so
    no pause anywhere in its narration changes."""
    assert ds.takes("educational") == 1
    assert ds.takes("pronunciation") == 3
    assert ds.takes("vocabulary") == 2


def test_takes_is_never_zero():
    """A type configured to say its phrase zero times would silently drop
    the content it exists to teach."""
    for t in TYPES + ["banana", None, ""]:
        assert ds.takes(t) >= 1


def test_the_pause_is_long_enough_to_repeat_into():
    """0.18s is the segmenter's longest punctuation gap and it is not a
    pause a learner can say a word in. That is why the override exists."""
    assert ds.repetition_pause() >= 0.5


def test_repetition_pauses_reach_the_bilingual_call_plan():
    """The mechanism, end to end: a short English segment in a repeating
    type gets REAL spliced silence, not a comma."""
    from tts_bilingual import plan_calls
    script = {"type": "pronunciation", "word": "quiet",
              "english_phrases": ["quiet"],
              "full_script": "La palabra es 'quiet'. Otra vez. 'quiet'."}
    calls = plan_calls(script)
    english = [c for c in calls if c["is_english"]]
    assert english, "the English term was not isolated"
    assert all(c["pause_after"] == pytest.approx(ds.repetition_pause())
               for c in english)


def test_a_non_repeating_type_keeps_the_segmenter_pauses():
    from tts_bilingual import plan_calls
    script = {"type": "educational", "english_phrases": ["quiet"],
              "full_script": "La palabra es 'quiet'. Significa silencioso."}
    for c in plan_calls(script):
        assert c["pause_after"] < 0.5, "educational pacing must not change"


def test_repeat_segments_are_not_treated_as_declared_silence():
    """(e). The gate flags speech inside a declared-silent span. A repeat is
    SPEECH and is declared as such — only 'countdown_' ids are silent — so
    the declaration and the waveform agree by construction."""
    import qa_gate
    for take in (2, 3):
        assert not f"repeat_answer_take{take}".startswith(
            qa_gate.SILENT_SEGMENT_PREFIXES)
        assert not f"repeat_0_take{take}".startswith(
            qa_gate.SILENT_SEGMENT_PREFIXES)


# ──────────────────────── vocabulary's row cap (c) ────────────────────────

def test_the_vocabulary_row_cap_is_enforced_not_merely_declared():
    """Logged debt for two passes: 'declared but never enforced'. Raising
    the prompt to 10-12 pairs walked the deck to the limit, so it had to
    become real."""
    import inspect

    from config.layout import VOCAB_MAX_ROWS
    import video.vocabulary as vocab
    src = inspect.getsource(vocab.create_frame_vocabulary)
    assert "VOCAB_MAX_ROWS" in src
    assert "pairs[:VOCAB_MAX_ROWS]" in src
    assert VOCAB_MAX_ROWS == 12


def test_the_vocabulary_prompt_asks_for_a_full_card():
    import script_generator as sg
    prompt = sg.build_prompt_vocabulary("travel", {"topic": "restaurant"})
    assert "10-12 pares" in prompt or "10 y 12 pares" in prompt

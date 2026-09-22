#!/usr/bin/env python3
"""A type can have its own duration band; the global one is the fallback.

    python3 -m pytest tests/test_per_type_band.py

THE PROBLEM THIS SOLVES. `duration.band` was ONE 50-80s window applied to
all six types, while `duration.types` carried rate, silence, n,
fixed_words and items_spoken per type and no band at all. A 2-item quiz
runs past 80s, and the only lever was the global ceiling -- raising it
would also stop the guard catching a runaway educational or vocabulary
video. Six formats that differ by design cannot share one window.

THE MECHANISM LANDS BEFORE THE NUMBERS. No type overrides anything yet:
quiz's ceiling has to come from re-fitting over a batch of 2-item renders.
A round number chosen to fit today's video is a guessed value inside a
guard, which is the shape of defect this repo keeps paying for.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import duration_spec as ds  # noqa: E402


@pytest.fixture
def cfg(monkeypatch):
    """A config whose band and types we control."""
    def install(types):
        monkeypatch.setattr(ds, "_config", lambda: {
            "band": {"min_seconds": 50.0, "max_seconds": 80.0,
                     "target_seconds": 65.0},
            "outro_seconds": 4.0,
            "types": types,
        })
    return install


BASE = {"rate": 2.0, "silence": 10.0, "n": 10}


def test_a_type_with_no_override_gets_the_global_band(cfg):
    cfg({"quiz": dict(BASE)})
    assert ds.band("quiz") == {"min_seconds": 50.0, "max_seconds": 80.0,
                               "target_seconds": 65.0}


def test_a_type_overrides_only_what_it_declares(cfg):
    """Restating the floor and target is how two numbers drift apart."""
    cfg({"quiz": dict(BASE, max_seconds=100.0)})
    b = ds.band("quiz")
    assert b["max_seconds"] == 100.0
    assert b["min_seconds"] == 50.0
    assert b["target_seconds"] == 65.0


def test_one_types_override_does_not_touch_another(cfg):
    """THE WHOLE POINT. Raising quiz's ceiling must not stop the guard
    catching a runaway educational video."""
    cfg({"quiz": dict(BASE, max_seconds=100.0),
         "educational": dict(BASE)})

    assert ds.band("quiz")["max_seconds"] == 100.0
    assert ds.band("educational")["max_seconds"] == 80.0
    assert ds.band()["max_seconds"] == 80.0


def test_an_unknown_type_gets_the_global_band(cfg):
    cfg({"quiz": dict(BASE, max_seconds=100.0)})
    assert ds.band("nonexistent")["max_seconds"] == 80.0


def test_the_type_name_is_case_insensitive(cfg):
    cfg({"quiz": dict(BASE, max_seconds=100.0)})
    assert ds.band("QUIZ")["max_seconds"] == 100.0


# ── the band must reach the things that use it ───────────────────────

def test_the_verdict_judges_against_the_types_own_ceiling(cfg):
    """A judge that reads the global band while the type declares its own
    is the same bug wearing a different hat."""
    cfg({"quiz": dict(BASE, max_seconds=100.0)})

    record = ds.check("quiz", narration_seconds=80.0,
                      measured_video_seconds=92.0)
    assert record["status"] == ds.PASS, (
        f"92s judged against quiz's own 100s ceiling: {record.get('reason')}")
    assert record["band"] == [50.0, 100.0]

    record = ds.check("quiz", narration_seconds=100.0,
                      measured_video_seconds=104.0)
    assert record["status"] == ds.OUT_OF_BAND, "104s is past quiz's ceiling"


def test_another_type_is_still_caught_at_eighty(cfg):
    cfg({"quiz": dict(BASE, max_seconds=100.0),
         "educational": dict(BASE)})

    record = ds.check("educational", narration_seconds=88.0,
                      measured_video_seconds=92.0)
    assert record["status"] == ds.OUT_OF_BAND, (
        "a runaway educational video passed on quiz's ceiling")
    assert record["band"] == [50.0, 80.0]


def test_the_word_range_follows_the_types_band(cfg):
    """The prompt tells the writer how long to make it; if that ignores the
    override, scripts are written to the wrong length."""
    cfg({"quiz": dict(BASE)})
    narrow = ds.word_range("quiz")

    cfg({"quiz": dict(BASE, max_seconds=120.0)})
    wide = ds.word_range("quiz")

    assert wide["max"] > narrow["max"]
    assert wide["min"] == narrow["min"]


def test_the_prompt_instruction_quotes_the_types_own_numbers(cfg):
    cfg({"quiz": dict(BASE, max_seconds=100.0)})
    text = ds.prompt_instruction("quiz")
    assert "100" in text, f"the instruction still quotes the global band: {text}"


# ── the live config ──────────────────────────────────────────────────

def test_quiz_is_the_only_type_with_its_own_band():
    """Quiz's band was MEASURED, over four 2-item renders (72.9 / 75.0 /
    87.7 / 89.4 s). The tripwire this replaces said it was to be updated by
    the commit carrying a measured number and not by one carrying a chosen
    one; this is that update, and it keeps the same job for the next type."""
    ds.reload()
    overriding = sorted(t for t in ("quiz", "educational", "fill_blank",
                                    "true_false", "pronunciation", "vocabulary")
                        if ds.band(t) != ds.band())
    assert overriding == ["quiz"], (
        f"{overriding} declare a band — if that number was measured, update "
        "this test in the same commit; if it was chosen to fit, do not")


def test_quizs_band_holds_every_two_item_render_it_was_fitted_on():
    """The four the number came from. If a later change moves quiz's
    duration, this names which render fell out."""
    ds.reload()
    for name, seconds in (("pv033_take_over", 72.9),
                          ("gr004_first_conditional", 75.0),
                          ("sl001_lowkey", 87.7),
                          ("id016_early_bird", 89.4)):
        record = ds.check("quiz", narration_seconds=seconds - 4.0,
                          measured_video_seconds=seconds)
        assert record["status"] == ds.PASS, f"{name}: {record['reason']}"


def test_quizs_band_still_catches_one_and_three_item_cuts():
    """A band wide enough for two items must not be so wide that the
    formats the owner rejected sail through it."""
    ds.reload()
    for label, seconds in (("a 1-item cut", 43.5), ("a 3-item cut", 123.9)):
        record = ds.check("quiz", narration_seconds=seconds - 4.0,
                          measured_video_seconds=seconds)
        assert record["status"] == ds.OUT_OF_BAND, f"{label} passed"


def test_the_predictor_agrees_with_the_renders_it_was_fitted_on():
    """Within a few seconds of the real length — the acceptance for the
    re-fit. Loose enough for four samples, tight enough that a rate or
    silence typo fails it."""
    ds.reload()
    for name, words, seconds in (("pv033_take_over", 50, 72.9),
                                 ("gr004_first_conditional", 57, 75.0),
                                 ("sl001_lowkey", 66, 87.7),
                                 ("id016_early_bird", 75, 89.4)):
        spec = ds.type_spec("quiz")
        predicted = words / spec["rate"] + spec["silence"] + ds.outro_seconds()
        assert abs(predicted - seconds) <= 5.0, (
            f"{name}: predicted {predicted:.1f}s against a real {seconds}s")


def test_the_other_types_still_answer_with_the_global_band():
    ds.reload()
    for vtype in ("educational", "vocabulary", "true_false", "fill_blank",
                  "pronunciation"):
        assert ds.band(vtype)["max_seconds"] == 80.0, (
            f"{vtype} drifted off the global ceiling")

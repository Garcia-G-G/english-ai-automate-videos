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

def test_no_type_overrides_the_band_yet():
    """Deliberate. quiz's ceiling comes from the re-fit over 2-item
    renders; this test is what turns that from an intention into a
    tripwire, and it is EXPECTED to be updated in the same commit that
    adds the measured number."""
    ds.reload()
    overriding = [t for t in ("quiz", "educational", "fill_blank",
                              "true_false", "pronunciation", "vocabulary")
                  if ds.band(t) != ds.band()]
    assert not overriding, (
        f"{overriding} declare a band — if that number was measured, update "
        "this test in the same commit; if it was chosen to fit, do not")

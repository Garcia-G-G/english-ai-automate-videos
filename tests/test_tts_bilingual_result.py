#!/usr/bin/env python3
"""Pin the shape of the bilingual TTS result — the LIVE educational path.

    python3 -m pytest tests/test_tts_bilingual_result.py

Nothing exercised `tts_bilingual` until now, and it cost a real outage: a
`tts_model_id` line added in 812aae8 referenced a `settings` local that does
not exist in `_build_result`'s scope, so EVERY educational generation raised
NameError. Two commits and a full test suite went past without noticing,
because 110 passing tests all avoided this module.

These tests build the result dict directly instead of calling the API, so they
cost nothing and still cover the assembly path where that bug lived.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts_bilingual as TB  # noqa: E402

SCRIPT = {
    "type": "educational",
    "full_script": "Hola. Hoy aprendemos 'give up'. Significa rendirse.",
    "english_phrases": ["give up"],
}
WORDS = [
    {"word": "Hola.", "start": 0.0, "end": 0.5, "is_english": False},
    {"word": "Hoy", "start": 0.6, "end": 0.9, "is_english": False},
    {"word": "aprendemos", "start": 0.9, "end": 1.6, "is_english": False},
    {"word": "give", "start": 1.7, "end": 2.0, "is_english": True},
    {"word": "up.", "start": 2.0, "end": 2.3, "is_english": True},
    {"word": "Significa", "start": 2.5, "end": 3.1, "is_english": False},
    {"word": "rendirse.", "start": 3.1, "end": 3.8, "is_english": False},
]
CALLS = [
    {"index": 0, "lang": "es", "text": "Hola. Hoy aprendemos", "speed": 0.95,
     "pause_after": 0.0, "model_id": "eleven_turbo_v2_5"},
    {"index": 1, "lang": "en", "text": "give up.", "speed": 0.87,
     "pause_after": 0.0, "model_id": "eleven_turbo_v2_5"},
]


def build(words=None, calls=None):
    return TB._build_result(SCRIPT, list(words if words is not None else WORDS),
                            4.0, list(calls if calls is not None else CALLS))


def test_build_result_does_not_raise():
    """The regression. This raised NameError for two commits."""
    assert build() is not None


def test_model_id_comes_from_the_calls_actually_made():
    r = build()

    assert r["tts_model_id"] == "eleven_turbo_v2_5"


def test_model_id_is_none_rather_than_wrong_when_there_are_no_calls():
    """A dry run makes no calls. Reporting None is honest; reporting a
    resolved-but-unused model would be the self-report problem again."""
    r = build(calls=[])

    assert r["tts_model_id"] is None


def test_result_carries_the_keys_the_renderer_and_gate_read():
    r = build()

    for key in ("duration", "words", "segments", "tts_model_id"):
        assert key in r, key


def test_educational_emits_a_word_timeline_and_no_segment_times():
    """This is the live contract, and the QA gate depends on it: educational
    is covered by check 2 (sentence timeline), never by check 1. If
    segment_times ever appears here, the gate's coverage split needs revisiting
    — and docs/recorded-debt.md item 5 stops being true."""
    r = build()

    assert r["words"], "educational must carry a word timeline"
    assert "segment_times" not in r


def test_word_timeline_spans_the_audio():
    """The check-2 span assertion, at the source rather than after the fact."""
    r = build()
    last_end = max(w["end"] for w in r["words"])

    assert 0.90 <= last_end / r["duration"] <= 1.02


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

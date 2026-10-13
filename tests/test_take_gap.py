#!/usr/bin/env python3
"""Two takes of one word in ONE clip: finding the pause, and shortening it.

    python3 -m pytest tests/test_take_gap.py

how_do_you_say speaks "Family. Family." in a single call. eleven_v3 reads
". " as a sentence break and left 0.83-1.63 s between the takes on bv001:
ten of them added ~9 s, and the longest tripped qa_gate's 1.5 s dead-air
check. clamp_take_gap cuts SILENCE out of the middle of that pause;
measure_first_take_end finds where the first take stops, which is what the
renderer writes the word over.

Offline: the clips are ffmpeg tones, not speech.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _tone(path, spans, total):
    """An mp3 with a 440 Hz tone over each (start, end) and silence between."""
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*({expr})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_the_first_take_end_is_found(tmp_path):
    from tts_common import measure_first_take_end
    path = str(tmp_path / "en.mp3")
    _tone(path, [(0.05, 0.55), (0.95, 1.45)], 1.6)
    assert measure_first_take_end(path) == pytest.approx(0.55, abs=0.05)


def test_one_take_has_no_first_take_end(tmp_path):
    """None, not a guessed midpoint: the caller decides what to do."""
    from tts_common import measure_first_take_end
    path = str(tmp_path / "es.mp3")
    _tone(path, [(0.05, 0.75)], 0.9)
    assert measure_first_take_end(path) is None


def test_a_long_pause_between_takes_is_cut_to_take_gap(tmp_path):
    """bv001's first render: eleven_v3 left 1.06-1.63 s between the takes,
    adding ~9 s and tripping the 1.5 s dead-air check. Only silence is cut."""
    from tts_common import TAKE_GAP_S, clamp_take_gap, get_audio_duration, measure_first_take_end
    path = str(tmp_path / "en.mp3")
    _tone(path, [(0.05, 0.55), (2.05, 2.55)], 2.7)          # 1.5 s gap
    before = get_audio_duration(path)
    r = clamp_take_gap(path)
    assert r["clamped"] and r["gap_before"] == pytest.approx(1.5, abs=0.1)
    assert get_audio_duration(path) == pytest.approx(before - (r["gap_before"] - TAKE_GAP_S), abs=0.06)
    assert measure_first_take_end(path) == pytest.approx(0.55, abs=0.05)
    again = clamp_take_gap(path)
    assert not again["clamped"] and again["gap_before"] == pytest.approx(TAKE_GAP_S, abs=0.06)


def test_a_short_pause_is_left_alone(tmp_path):
    from tts_common import clamp_take_gap, get_audio_duration
    path = str(tmp_path / "en.mp3")
    _tone(path, [(0.05, 0.55), (0.85, 1.35)], 1.5)
    before = get_audio_duration(path)
    assert not clamp_take_gap(path)["clamped"]
    assert get_audio_duration(path) == before

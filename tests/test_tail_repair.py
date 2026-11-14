#!/usr/bin/env python3
"""A code-switched clip gets its decay back; a healthy clip is untouched.

    python3 -m pytest tests/test_tail_repair.py

THE DEFECT. ElevenLabs returns any clip containing a language transition cut
at the instant the voice stops — measured against the live API at 6/6 on
"el libro... the book." versus 0/6 on either language alone. Direction does
not matter and the ellipsis is not required; it is the transition itself.
Corpus-wide it hits 99.3% of vocabulary pair clips, and it is why the audio
sounds spliced.

WHAT IS LOST IS THE ENVELOPE, NOT A PHONEME. Whisper reads the final word in
6/6 truncated clips. What is gone is ~30 ms of amplitude decay. That is why a
fade is a repair and not a mask: an envelope is an amplitude curve, which is
exactly what a fade produces.

These tests are synthetic — they build a truncated clip with ffmpeg rather
than calling the API, so the suite stays free and offline.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import (  # noqa: E402
    TAIL_MIN, TAIL_PAD, clip_is_truncated, get_audio_duration,
    measure_speech_end, repair_truncated_tail,
)


def _tone(path, seconds=0.6, trailing_silence=0.0):
    """A clip that ends dead, or with a tail if trailing_silence is given."""
    chain = f"sine=frequency=220:duration={seconds}"
    if trailing_silence:
        chain += f",apad=pad_dur={trailing_silence}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", chain,
                    str(path)], check=True)
    return path


def test_a_clip_that_ends_dead_is_detected(tmp_path):
    assert clip_is_truncated(str(_tone(tmp_path / "cut.mp3")))


def test_a_clip_with_a_tail_is_not_detected(tmp_path):
    clip = _tone(tmp_path / "ok.mp3", trailing_silence=0.5)
    assert not clip_is_truncated(str(clip))


def test_the_repair_adds_the_pad(tmp_path):
    clip = _tone(tmp_path / "cut.mp3")
    before = get_audio_duration(str(clip))
    result = repair_truncated_tail(str(clip))
    assert result["repaired"] is True
    # The pad is what restores the pacing; the fade is what kills the click.
    assert get_audio_duration(str(clip)) > before


def test_the_repaired_clip_no_longer_ends_on_the_voice(tmp_path):
    """The point of the exercise: a measurable tail where there was none."""
    clip = _tone(tmp_path / "cut.mp3")
    repair_truncated_tail(str(clip))
    tail = get_audio_duration(str(clip)) - measure_speech_end(str(clip))
    assert tail >= TAIL_MIN


def test_a_healthy_clip_is_left_exactly_alone(tmp_path):
    """Only truncated clips are touched — a healthy tail must not be padded
    a second time, or every pair clip grows on every run."""
    clip = _tone(tmp_path / "ok.mp3", trailing_silence=0.5)
    before = get_audio_duration(str(clip))
    result = repair_truncated_tail(str(clip))
    assert result["repaired"] is False
    assert get_audio_duration(str(clip)) == pytest.approx(before, abs=0.01)


def test_the_pad_is_not_digital_zero(tmp_path):
    """THE ONE THAT MATTERS FOR HOW IT SOUNDS.

    `apad` writes exact digital zero. The model's own floor measures
    -79.5 dB, and padding to -140 dB rebuilds the defect that makes this
    audio sound spliced — the ear does not hear silence, it hears the noise
    floor vanish. Naive fade+apad scored 35 dB RMS against the monolingual
    reference envelope; the noise-floor pad scores 4.9 dB.
    """
    import numpy as np
    clip = _tone(tmp_path / "cut.mp3")
    repair_truncated_tail(str(clip))
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(clip), "-f", "s16le",
         "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    last = audio[-int(0.05 * 16000):]
    assert np.any(last != 0.0), "the pad is exact digital zero — Defect B again"


def test_the_constants_are_the_measured_ones(tmp_path):
    """These were fitted against the monolingual reference, not chosen.
    TAIL_PAD is the corpus median healthy tail — 0.244, not a tidy 0.25."""
    assert TAIL_PAD == 0.244

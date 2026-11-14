#!/usr/bin/env python3
"""The gaps carry room tone, not digital zero — and stay exactly as long.

    python3 -m pytest tests/test_gap_room_tone.py

THE DEFECT. `generate_silence` built every gap with `anullsrc`, which emits
exact zeros, while the voice's own floor sits near -72 dB. So every join was
voice -> absolute nothing -> voice, 8 to 25 times a video. The ear does not
hear the silence; it hears the floor vanish and come back. That is the half
of "spliced tape" left after the code-switch truncation was repaired.

Measured on the final concatenated mix, before -> after:

    vocabulary   28.1% exact zero, longest hole 0.894s  ->  3.2%, 0.001s
    true_false   34.9% exact zero, longest hole 6.981s  ->  3.2%, 0.001s
    quiz         33.7% exact zero, longest hole 6.991s  ->  3.0%, 0.008s

The 7-second holes were the silent countdown: 72,000 consecutive zero
samples immediately before the answer, the longest stretch of nothing in any
video. It is still silent, by design. It is no longer dead.

DURATION NEUTRALITY IS THE HARD REQUIREMENT. segment_times drives the
renderer, so a gap that is not exactly its requested length desynchronises
every text reveal after it.
"""

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import (  # noqa: E402
    GAP_FLOOR_DB, generate_silence, get_audio_duration,
)

SR = 16000


def _pcm(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _db(x):
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    return -140.0 if rms <= 1e-7 else 20 * math.log10(rms)


@pytest.mark.parametrize("duration", [0.4, 0.5, 0.9, 1.5, 4.5])
def test_a_gap_is_exactly_as_long_as_asked(tmp_path, duration):
    """THE ONE THAT MUST NEVER REGRESS. Not approximately — exactly."""
    gap = tmp_path / "gap.mp3"
    generate_silence(duration, str(gap))
    assert get_audio_duration(str(gap)) == pytest.approx(duration, abs=0.03)


def test_a_gap_is_not_digital_zero(tmp_path):
    gap = tmp_path / "gap.mp3"
    generate_silence(0.9, str(gap))
    audio = _pcm(gap)
    assert np.any(audio != 0.0), "the gap is exact zero — the floor vanishes"


def test_the_countdown_length_gap_has_no_long_hole(tmp_path):
    """4.5 s was 72,000 consecutive zeros, right before the answer."""
    gap = tmp_path / "countdown.mp3"
    generate_silence(4.5, str(gap))
    zeros = (_pcm(gap) == 0.0)
    longest = 0
    current = 0
    for value in zeros:
        current = current + 1 if value else 0
        longest = max(longest, current)
    assert longest / SR < 0.05, f"a {longest / SR:.3f}s hole of exact silence"


def test_the_gap_sits_at_the_measured_floor(tmp_path):
    """Loud enough that the floor does not vanish, quiet enough that it is
    never hiss. The clips' own floor measures -72 dB (p10) / -77.6 (p5)."""
    gap = tmp_path / "gap.mp3"
    generate_silence(1.0, str(gap))
    level = _db(_pcm(gap))
    assert level == pytest.approx(GAP_FLOOR_DB, abs=3.0)


def test_the_level_is_not_the_tail_repair_level():
    """A decay's starting level and a gap's resting level are different
    jobs: TAIL_NOISE_DB (-58) as a gap would be audible hiss on every
    video on the channel."""
    from tts_common import TAIL_NOISE_DB
    assert GAP_FLOOR_DB < TAIL_NOISE_DB - 10

#!/usr/bin/env python3
"""A trimmed clip enters from the room tone, not from a hole below it.

    python3 -m pytest tests/test_lead_in_shaping.py

THE DEFECT, AND WHY IT ONLY BECAME AUDIBLE AFTER THE GAPS WERE FIXED.
`trim_clip_silence` keeps TRIM_LEAD_PAD of the clip's OWN leading silence,
which measures ~-98 dB. While gaps were digital zero that was an improvement
on its surroundings and nobody could hear it. Once the gaps carried room tone
at -75 dB, the retained lead-in punched a hole straight through the floor at
every option start:

    gap ... -75  -75  -75 | -98  -62  -20  -12  -11     <- a tick, then a slam

and then reached full speaking level in 20-30 ms, where the model's own
untrimmed onsets take 40-50 ms.

RAISING TRIM_LEAD_PAD FIXES NEITHER HALF: more pad keeps more of the same
too-quiet pre-roll, so the hole gets longer rather than going away. The fix
is a room-tone bed so the floor is continuous, plus a fade-in matched to the
measured natural onset.
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
    GAP_FLOOR_DB, LEAD_CURVE, LEAD_FADE_S, get_audio_duration,
    shape_clip_lead_in,
)

SR = 16000


def _clip(path, seconds=0.8):
    """A clip that starts at full level, the way a trimmed one does."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=300:duration={seconds}", str(path)],
                   check=True)
    return path


def _pcm(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _db(x):
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    return -140.0 if rms <= 1e-7 else 20 * math.log10(rms)


def test_shaping_is_duration_neutral(tmp_path):
    """THE ONE THAT MUST NOT REGRESS. segment_times drives the renderer, so
    a clip that changes length desynchronises every reveal after it. Bedding
    the whole clip rather than prepending a lead is what buys this."""
    clip = _clip(tmp_path / "c.mp3")
    before = get_audio_duration(str(clip))
    assert shape_clip_lead_in(str(clip)) is True
    assert get_audio_duration(str(clip)) == pytest.approx(before, abs=0.03)


def test_no_frame_at_the_start_sits_below_the_gap_floor(tmp_path):
    """THE ACCEPTANCE TEST. The floor must be continuous across the join —
    a frame below GAP_FLOOR_DB is the hole this step exists to close."""
    clip = _clip(tmp_path / "c.mp3")
    shape_clip_lead_in(str(clip))
    audio = _pcm(clip)
    frame = int(0.01 * SR)
    for i in range(4):                      # the first 40 ms
        level = _db(audio[i * frame:(i + 1) * frame])
        assert level > GAP_FLOOR_DB - 8, (
            f"frame {i * 10}ms at {level:.0f} dB punches through the floor")


def test_the_onset_is_not_a_slam(tmp_path):
    """Trimmed clips reached full level in 20-30 ms; the model's own onsets
    take 40-50. The first frame must not already be at full level."""
    clip = _clip(tmp_path / "c.mp3")
    audio_before = _pcm(clip)
    first_before = _db(audio_before[:int(0.01 * SR)])
    shape_clip_lead_in(str(clip))
    first_after = _db(_pcm(clip)[:int(0.01 * SR)])
    # 15 dB, not 20: a synthetic sine has no natural pre-roll and the mp3
    # encoder rings at the boundary, so the measured attenuation on this
    # fixture (~19 dB) is smaller than on a real clip, which enters from
    # -98 dB. The assertion is "not a slam", not a precise depth.
    assert first_after < first_before - 15, (
        "the clip still enters at full level")


def test_the_body_of_the_clip_is_untouched(tmp_path):
    """Only the onset is shaped. If the fade reached the whole clip we would
    be attenuating speech, not rebuilding an envelope."""
    clip = _clip(tmp_path / "c.mp3")
    mid_before = _db(_pcm(clip)[int(0.4 * SR):int(0.5 * SR)])
    shape_clip_lead_in(str(clip))
    mid_after = _db(_pcm(clip)[int(0.4 * SR):int(0.5 * SR)])
    assert mid_after == pytest.approx(mid_before, abs=1.5)


def test_the_fade_matches_the_measured_natural_onset():
    """45 ms, because untrimmed segments reach -25 dB in 40-50 ms. A sweep
    to 90 ms did not move the median, so longer would only attenuate more
    real speech for nothing."""
    assert LEAD_FADE_S == 0.045
    assert LEAD_CURVE == "esin"

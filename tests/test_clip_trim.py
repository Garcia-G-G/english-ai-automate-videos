#!/usr/bin/env python3
"""Trimming clip-intrinsic silence — and never cutting speech to do it.

    python3 -m pytest tests/test_clip_trim.py

WHY THIS EXISTS. The same script produced 1.957s of clip-intrinsic silence on
one run and 2.916s on another, so block duration could not be compared between
renders. Trimming to a measured boundary makes it reproducible; the shorter
block is the secondary benefit.

measure_speech_end is on this repo's list of heuristics that could silently
never fire, so these tests assert it fires on real signal rather than trusting
it. Clips are synthesised with ffmpeg — no API calls.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import (  # noqa: E402
    TRIM_LEAD_PAD, TRIM_TAIL_PAD, get_audio_duration, measure_speech_end,
    measure_speech_start, trim_clip_silence,
)


def _make(path, spec):
    """Build an mp3 from an ffmpeg filter spec (tone/silence concat)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-filter_complex",
                    spec, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2",
                    "-ar", "44100", "-ac", "1", str(path)],
                   check=True, capture_output=True)
    return path


def _tone_then_silence(path, tone_s, sil_s):
    return _make(path, (
        f"sine=frequency=300:duration={tone_s}[a];"
        f"anullsrc=r=44100:cl=mono,atrim=duration={sil_s}[b];"
        f"[a][b]concat=n=2:v=0:a=1[out]" if sil_s > 0 else
        f"sine=frequency=300:duration={tone_s}[out]"))


# ── it fires ─────────────────────────────────────────────────────────

def test_measure_speech_end_fires_on_a_clip_with_trailing_silence(tmp_path):
    """The check the repo's history demands: prove it does something."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=1.0)

    end = measure_speech_end(str(p))
    dur = get_audio_duration(str(p))

    assert dur > 1.8, "fixture is wrong"
    assert end < dur - 0.5, f"did not fire: end={end:.3f} dur={dur:.3f}"
    assert 0.8 < end < 1.3, f"fired but at the wrong place: {end:.3f}"


def test_measure_speech_end_returns_full_duration_when_there_is_no_tail(tmp_path):
    """Not firing is the CORRECT answer here, and must be distinguishable
    from a broken detector — it returns the duration, not 0."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=0)

    end = measure_speech_end(str(p))

    assert end >= get_audio_duration(str(p)) - 0.06


def test_measure_speech_start_finds_leading_silence(tmp_path):
    p = _make(tmp_path / "t.mp3",
              "anullsrc=r=44100:cl=mono,atrim=duration=0.5[a];"
              "sine=frequency=300:duration=1.0[b];[a][b]concat=n=2:v=0:a=1[out]")

    assert measure_speech_start(str(p)) > 0.3


# ── the over-trim guard ──────────────────────────────────────────────

def test_a_clip_whose_speech_runs_to_the_last_frame_is_not_cut(tmp_path):
    """The case the guard exists for. Speech to the final sample means there
    is nothing to remove, and an eager trim would cut the word itself."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.2, sil_s=0)
    before = get_audio_duration(str(p))

    r = trim_clip_silence(str(p))
    after = get_audio_duration(str(p))

    assert after >= before - 0.06, f"cut a clip with no trailing silence: {before:.3f} -> {after:.3f}"
    assert not r["trimmed"] or r["after"] >= r["before"] - 0.06


def test_trimming_never_shortens_the_speech_itself(tmp_path):
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=1.5)
    speech_before = measure_speech_end(str(p)) - measure_speech_start(str(p))

    trim_clip_silence(str(p))
    speech_after = measure_speech_end(str(p)) - measure_speech_start(str(p))

    assert speech_after + 0.05 >= speech_before, (
        f"lost speech: {speech_before:.3f} -> {speech_after:.3f}")


def test_a_silent_clip_is_refused_rather_than_reduced_to_nothing(tmp_path):
    p = _make(tmp_path / "t.mp3", "anullsrc=r=44100:cl=mono,atrim=duration=1.0[out]")

    r = trim_clip_silence(str(p))

    assert not r["trimmed"]
    assert r["reason"]


def test_the_result_reports_what_it_did(tmp_path):
    """A caller must be able to assert on the outcome instead of trusting it."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=1.5)

    r = trim_clip_silence(str(p))

    assert r["trimmed"] is True
    assert r["after"] < r["before"]
    for key in ("before", "after", "lead", "speech_end", "reason"):
        assert key in r


# ── the deliberate tail ──────────────────────────────────────────────

def test_a_tail_is_left_deliberately(tmp_path):
    """Trimming to the exact speech end clips the decay of a final consonant.
    The tail is also below silencedetect's 0.10s window, so it does not
    register as silence and the measured gaps stay equal to the constants."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=1.5)
    r = trim_clip_silence(str(p))

    assert TRIM_TAIL_PAD > 0
    assert TRIM_TAIL_PAD < 0.10, "tail must stay under the detection window"
    assert r["after"] > r["speech_end"] - r["lead"], "no tail was left"


def test_trim_is_idempotent(tmp_path):
    """A second pass must not keep eating into the clip."""
    p = _tone_then_silence(tmp_path / "t.mp3", tone_s=1.0, sil_s=1.5)
    trim_clip_silence(str(p))
    once = get_audio_duration(str(p))
    trim_clip_silence(str(p))
    twice = get_audio_duration(str(p))

    assert abs(once - twice) < 0.05, f"{once:.3f} -> {twice:.3f}"


# ── wiring ───────────────────────────────────────────────────────────

def test_every_option_clip_is_trimmed_in_the_generator():
    import ast
    src = (ROOT / "src" / "tts_elevenlabs.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "emit_split_options")
    trims = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_trim"]

    assert len(trims) == 3, (
        f"expected transition + label + word to be trimmed, found {len(trims)}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

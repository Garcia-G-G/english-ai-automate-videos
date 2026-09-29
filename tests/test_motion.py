#!/usr/bin/env python3
"""The v1 motion helpers: bounded, deterministic, and settled when done.

    python3 -m pytest tests/test_motion.py

What these pin is not taste -- the amplitudes are tunable -- but the three
rules in video/motion.py's docstring, because each one protects a fix this
repo already paid for: pure functions of t, never later than the voice,
never below a floor.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video import motion as m  # noqa: E402

FRAMES = [i / 30.0 for i in range(0, 30 * 20)]   # 20s at 30fps


# ── entrance ─────────────────────────────────────────────────────────

def test_an_entrance_settles_exactly_where_the_element_always_was():
    """After it ends, (1.0, 0.0) exactly -- a settled element draws on the
    same pixel as before this module existed."""
    assert m.entrance(5.0 + m.ENTRANCE_SECONDS, 5.0) == (1.0, 0.0)
    assert m.entrance(60.0, 5.0) == (1.0, 0.0)


def test_an_entrance_starts_from_its_first_frame_not_from_nothing():
    scale, dy = m.entrance(5.0, 5.0)
    assert scale == pytest.approx(m.ENTRANCE_FROM_SCALE)
    assert dy == pytest.approx(m.ENTRANCE_RISE_PX)
    # Before its start it holds that first frame rather than jumping.
    assert m.entrance(4.0, 5.0) == m.entrance(5.0, 5.0)


def test_an_entrance_is_bounded_and_has_no_visible_jump_at_its_end():
    start = 1.0
    prev = None
    for t in FRAMES:
        scale, dy = m.entrance(t, start)
        assert m.ENTRANCE_FROM_SCALE - 1e-9 <= scale <= 1.02, t
        assert 0.0 <= dy <= m.ENTRANCE_RISE_PX + 1e-9, t
        if prev is not None:
            assert abs(scale - prev[0]) < 0.06, f"scale jumps at {t}"
            assert abs(dy - prev[1]) < 18, f"position jumps at {t}"
        prev = (scale, dy)


def test_an_entrance_never_moves_its_start():
    """Rule 2: the motion only changes HOW it arrives. Nothing here takes or
    returns a time, so an entrance cannot delay the element -- but the
    element must already be nearly settled within ~0.15s of its start,
    which is how long the reader waits on it."""
    scale, dy = m.entrance(0.15, 0.0)
    assert scale > 0.96 and dy < 12


# ── idle ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phase", [0.0, 0.23, 0.5, 0.77])
def test_idle_never_goes_below_rest_and_stays_small(phase):
    """Rule 3. Floors are clamped at the resting position; a positive dy
    would reopen every overflow those clamps closed."""
    values = [m.idle_dy(t, 2.0, phase=phase) for t in FRAMES]
    assert max(values) <= 0.0
    assert min(values) >= -m.IDLE_AMPLITUDE_PX - 1e-9


@pytest.mark.parametrize("phase", [0.0, 0.5])
def test_idle_starts_at_rest_whatever_the_phase(phase):
    """The ramp is what makes the first frame 0; without it a phased card
    would jump by up to the full amplitude the moment it starts."""
    assert m.idle_dy(2.0, 2.0, phase=phase) == 0.0
    assert abs(m.idle_dy(2.0 + 1 / 30, 2.0, phase=phase)) < 0.1


def test_idle_actually_moves():
    """The whole point: a card on screen for seconds is not a still image."""
    values = [m.idle_dy(t, 0.0) for t in FRAMES]
    assert max(values) - min(values) > m.IDLE_AMPLITUDE_PX * 0.9


def test_idle_is_a_pure_function_of_time():
    a = [m.idle_dy(t, 1.0, phase=0.3) for t in FRAMES[::7]]
    b = [m.idle_dy(t, 1.0, phase=0.3) for t in reversed(FRAMES[::7])]
    assert a == list(reversed(b))


def test_idle_scale_is_bounded():
    values = [m.idle_scale(t, 0.0) for t in FRAMES]
    assert min(values) >= 1.0 and max(values) <= 1.0125


# ── scene cuts ───────────────────────────────────────────────────────

def test_cuts_are_the_section_starts_and_not_the_countdown():
    st = {
        "question": {"start": 0.2}, "option_a": {"start": 5.0},
        "option_b": {"start": 5.5}, "think": {"start": 12.0},
        "countdown_3": {"start": 13.0}, "countdown_2": {"start": 14.0},
        "answer": {"start": 20.0}, "explanation": {"start": 21.5},
    }
    # question at 0.2 is the opening, option_b is 0.5s after option_a, and
    # the countdown numbers are never cuts.
    assert m.scene_cuts(st) == [5.0, 12.0, 20.0, 21.5]


def test_a_second_quiz_item_opens_with_a_cut():
    st = {"question": {"start": 0.0}, "answer": {"start": 20.0},
          "i2_question": {"start": 40.0}, "i2_answer": {"start": 60.0}}
    assert m.scene_cuts(st) == [20.0, 40.0, 60.0]


def test_vocabulary_pairs_are_sections():
    st = {"title": {"start": 0.0}, "pair_0": {"start": 3.0},
          "pair_1": {"start": 8.0}}
    assert m.scene_cuts(st) == [3.0, 8.0]


@pytest.mark.parametrize("bad", [None, {}, [], "x",
                                 {"answer": "nope"},
                                 {"answer": {"start": None}}])
def test_unreadable_timing_means_no_transitions_not_a_crash(bad):
    assert m.scene_cuts(bad) == []


# ── transitions ──────────────────────────────────────────────────────

def test_a_transition_never_starts_before_its_cut():
    """Rule 2 for transitions: a punch before the cut would land on the
    previous section, ahead of the voice."""
    assert m.transition_at(9.999, [10.0]) == (1.0, 0.0)
    assert m.transition_at(10.0 + m.TRANSITION_SECONDS, [10.0]) == (1.0, 0.0)


def test_a_transition_is_bounded():
    for i in range(40):
        zoom, flash = m.transition_at(10.0 + i * 0.01, [10.0])
        assert 1.0 <= zoom <= 1.0 + m.TRANSITION_ZOOM + 1e-9
        assert 0.0 <= flash <= m.TRANSITION_FLASH + 1e-9


def test_apply_transition_is_free_outside_a_cut():
    frame = Image.new("RGBA", (108, 192), (10, 20, 30, 255))
    before = frame.tobytes()
    out = m.apply_transition(frame, 3.0, [10.0])
    assert out is frame and frame.tobytes() == before


def test_apply_transition_changes_the_frame_at_a_cut_and_keeps_its_size():
    frame = Image.new("RGBA", (108, 192), (10, 20, 30, 255))
    frame.paste((250, 0, 0, 255), (0, 0, 108, 20))    # a band at the top
    before = frame.tobytes()
    m.apply_transition(frame, 10.05, [10.0])
    assert frame.size == (108, 192) and frame.mode == "RGBA"
    assert frame.tobytes() != before


def test_finalize_frame_accepts_no_cuts_exactly_as_before():
    """The renderers that pass nothing must render byte-for-byte as they
    did: scene_cuts defaults to None and does nothing."""
    import inspect
    from video.utils import finalize_frame
    param = inspect.signature(finalize_frame).parameters["scene_cuts"]
    assert param.default is None

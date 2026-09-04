#!/usr/bin/env python3
"""A clip is measured across time, and the band is solved, not guessed.

    python3 -m pytest tests/test_clip_contrast.py

THE DEFECTS THESE PIN, all three found by measuring rather than by reading:

  1. A SINGLE-FRAME READING IS AN ANECDOTE. Across the 23 clips fetched for
     P1, the widest within-clip swing was 13.45 contrast points — one clip
     ran 1.52:1 at t=0.5s and 14.97:1 at its best. A gate that samples once
     passes or fails that clip essentially at random.

  2. A FLAT DIM CANNOT SERVE BOTH ENDS. dim=0.35 on every pixel rendered the
     technology videos black (night footage, already dark) while still
     leaving bright footage unreadable. The two failures pull opposite ways.

  3. CONTRAST IS SYMMETRIC, SO DARKENING IS NOT MONOTONIC. This is the
     subtle one and it survived two wrong implementations. Darkening a
     background BRIGHTER than the text pushes it down THROUGH the text's own
     luminance, where contrast is 1.00, before it comes out darker on the
     other side. So the worst frame before treatment is not the worst frame
     after it, and a bisection on strength is invalid.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import clip_contrast as cc  # noqa: E402
from text_contrast import HEADLINE_COLOR, relative_luminance  # noqa: E402


def _patch(rgb, size=(40, 40)):
    return np.full((*size, 3), rgb, dtype=np.uint8)


# ───────────────────── one band, not two implementations ─────────────────────

def test_the_still_scrim_and_the_clip_scrim_are_the_same_function():
    """topic_background wrote this curve first, for images. A second copy
    for clips would drift one edit at a time until a still and a clip were
    darkened differently for no stated reason."""
    import inspect

    import topic_background as tb
    source = inspect.getsource(tb.apply_readability_scrim)
    assert "scrim_profile" in source
    assert "np.cos" not in source, "the curve must not be reimplemented here"


def test_the_profile_is_flat_inside_the_band_and_untouched_outside():
    prof = cc.scrim_profile(1920, (700, 1000), strength=0.5).ravel()
    assert prof[850] == pytest.approx(0.5)        # inside: full strength
    assert prof[0] == pytest.approx(1.0)          # far above: untouched
    assert prof[1900] == pytest.approx(1.0)       # far below: untouched


def test_the_profile_has_no_seam():
    """A hard edge would look worse than the problem it fixes. Raised
    cosine, so the derivative is zero at both ends of the falloff."""
    prof = cc.scrim_profile(1920, (700, 1000), strength=0.6).ravel()
    steps = np.abs(np.diff(prof))
    assert steps.max() < 0.01, "a visible seam"


def test_zero_strength_is_the_identity():
    assert np.allclose(cc.scrim_profile(1920, (700, 1000), strength=0.0), 1.0)


# ─────────────────────── the zones are per video type ───────────────────────

def test_each_type_gets_its_own_text_zone():
    """One band for everything would either miss true_false's question at
    0.10 of the frame or darken most of the picture for educational."""
    assert cc.text_zone("quiz") != cc.text_zone("educational")
    assert cc.text_zone("quiz") == cc.TEXT_ZONES["quiz"]


def test_an_unknown_type_gets_the_union_and_never_a_narrow_guess():
    """Guessing narrow leaves text unprotected; guessing wide costs a
    slightly larger dark band. Only one of those is a defect."""
    zone = cc.text_zone("something_new")
    assert zone == cc.DEFAULT_ZONE
    for known in cc.TEXT_ZONES.values():
        assert zone[0] <= known[0] and zone[1] >= known[1]


def test_every_declared_type_has_a_zone_inside_the_frame():
    for name, (top, bottom) in cc.TEXT_ZONES.items():
        assert 0 <= top < bottom <= 1920, name


# ───────────── sampling across time, and reporting the worst ─────────────

def test_sampling_never_returns_a_single_point():
    """The entire premise: one sample of a moving picture is an anecdote."""
    for duration in (0.0, 0.4, 1.0, 12.0, 35.0):
        assert len(cc.sample_times(duration)) >= 2


def test_sampling_covers_the_whole_clip_including_its_last_frame():
    times = cc.sample_times(12.3)
    assert times[0] == 0.0
    assert times[-1] == pytest.approx(12.3)
    assert max(b - a for a, b in zip(times, times[1:])) <= cc.SAMPLE_INTERVAL + 1e-6


def test_the_interval_is_shorter_than_the_shortest_text_state():
    """The quiz countdown holds a number for 1.5s. An interval above that
    could step straight over a state."""
    assert cc.SAMPLE_INTERVAL <= 1.5


# ──────────────── the solve: symmetric contrast, non-monotonic ────────────────

def test_darkening_is_not_monotonic_in_contrast():
    """The finding that invalidated two implementations, pinned so nobody
    reintroduces a bisection. A background brighter than the text passes
    THROUGH the text's luminance on its way down."""
    bright = _patch((255, 255, 255))
    ratios = [cc._contrast_at([[255.0, 255.0, 255.0]], s) for s in (0.0, 0.25, 0.5, 0.75)]
    assert ratios[0] > min(ratios), "white should get worse before it gets better"
    assert min(ratios) < 1.35, "it must actually cross the text luminance"


def test_the_solved_band_clears_the_floor_for_every_sample_not_just_the_worst():
    """Solving on the pre-treatment worst frame gave a band that took that
    frame to exactly 3.00 while dragging a different one down to 2.29."""
    # A bright sample and a mid sample: darkening enough for the bright one
    # drags the mid one through the text luminance.
    samples = [[255.0, 255.0, 255.0], [205.0, 180.0, 90.0], [30.0, 30.0, 40.0]]
    strength = cc.solve_strength(samples)
    assert cc._contrast_at(samples, strength) >= cc.FLOOR


def test_a_clip_that_already_passes_is_left_completely_alone():
    """The dark-footage case. A flat 0.35 crushed these to black for no
    readability gain at all."""
    dark = [[12.0, 12.0, 16.0]]
    assert cc.solve_strength(dark) == 0.0


def test_the_band_is_capped_rather_than_darkening_to_black():
    """MAX_STRENGTH exists because a dark rectangle with a video behind it
    is not footage. The caller reports the shortfall instead."""
    assert cc.solve_strength([[255.0, 255.0, 255.0]], floor=21.0) == cc.MAX_STRENGTH


def test_the_p95_pixel_is_returned_so_the_solve_can_be_exact():
    """Three numbers per sample instead of a megabyte of frame."""
    patch = np.zeros((10, 10, 3), dtype=np.uint8)
    patch[0, 0] = (250, 250, 250)          # one bright pixel, above p95
    metrics = cc.measure_zone_patch(patch)
    assert "p95_rgb" in metrics and len(metrics["p95_rgb"]) == 3


def test_worst_is_reported_never_the_mean():
    """An average is exactly the statistic that lets three bad seconds hide
    behind twenty good ones."""
    import inspect
    source = inspect.getsource(cc.worst_over_clip)
    assert "min(samples" in source
    assert "mean(" not in source.split("return")[0].split("samples.append")[-1]


# ─────────────────────────── the measured frame ───────────────────────────

def test_the_measured_frame_is_the_one_that_ships():
    """Measuring the raw file measures pixels the viewer never sees. A
    1080x2048 clip loses 64 rows top and bottom to the crop, and the first
    version of this module measured them — its band undershot the floor on
    every playlist."""
    tall = np.zeros((2048, 1080, 3), dtype=np.uint8)
    assert cc.fit_frame(tall).shape == (1920, 1080, 3)
    wide = np.zeros((1920, 2400, 3), dtype=np.uint8)
    assert cc.fit_frame(wide).shape == (1920, 1080, 3)
    exact = np.zeros((1920, 1080, 3), dtype=np.uint8)
    assert cc.fit_frame(exact) is exact


def test_the_grey_inverse_round_trips():
    """_grey_for is the inverse of relative_luminance for a neutral value.
    A wrong inverse would silently mis-size every band."""
    for luminance in (0.002, 0.02, 0.1, 0.35, 0.68, 0.95):
        grey = cc._grey_for(luminance)
        back = float(relative_luminance(np.array([grey, grey, grey])))
        assert back == pytest.approx(luminance, abs=1e-6)


def test_an_empty_directory_asks_for_no_treatment_rather_than_raising(tmp_path):
    plan = cc.treatment_for_dir(tmp_path, "quiz")
    assert plan["strength"] == 0.0 and plan["clips"] == []


# ──────────────────── the renderer actually uses the band ────────────────────

def test_the_flat_dim_no_longer_defaults_to_anything(tmp_path):
    """dim=0.35 on every pixel is what rendered the technology videos black.
    The default is 0.0 and the band replaces it."""
    import inspect

    from video.clip_background import ClipLibraryBackground
    signature = inspect.signature(ClipLibraryBackground.__init__)
    assert signature.parameters["dim"].default == 0.0
    assert "video_type" in signature.parameters
    assert signature.parameters["scrim"].default is None


def test_the_background_factory_passes_the_type_through():
    """Without the type the band would cover the union zone and darken more
    of the picture than the layout needs."""
    import inspect

    import video.backgrounds as backgrounds
    source = inspect.getsource(backgrounds._get_clip_background)
    assert 'options.get("video_type")' in source
    assert 'options.get("dim", 0.0)' in source, "the 0.35 default must be gone"

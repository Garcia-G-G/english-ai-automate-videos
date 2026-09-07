#!/usr/bin/env python3
"""The watermark is measured, and its background is solved — not tuned.

    python3 -m pytest tests/test_watermark_contrast.py

THE DEFECT THIS PINS. The mark is white text in the bottom third. The
background standard made that third BRIGHT on purpose, and the mark's only
treatment was a blurred black shadow whose two constants were chosen by eye
against a dark backdrop. brand.py said the shadow "is tuned for the bright
case even though today's backdrop rarely needs it". It never was: measured
against the median clip (background p95 0.797) the mark reads 1.24:1 white
against background, and the shadow lifts glyph-against-halo only to 1.64:1.

Tuning the two shadow constants cannot fix it, and this is the part worth
pinning so nobody spends another pass on it. Sweeping alpha 160..255 against
blur 4..12 reaches 1.82:1 at its best, against a floor of 3.0 — and blurring
MORE makes it worse, because the halo spreads and lightens.

So the mark gets what the text band already gets: a scrim whose strength is
SOLVED from a measurement of the pixels underneath it. Three things this
must not become:

  1. A CONSTANT. `SHADOW_ALPHA = 160` is already a constant chosen by eye,
     and it is the thing that failed. strength_for() solves.
  2. A STRIP. Extending the readability band down to row 1920 would darken
     the bottom of every video. The treatment is local in BOTH axes.
  3. A TAX ON DARK CLIPS. strength_for returns 0.0 when the floor is already
     cleared, so night footage must come back completely untouched.

And the mark must be MEASURED. It shipped illegible for months because
nothing looked at it — text_contrast measured the headline band and stopped
there. An unmeasured element is one nobody can be wrong about.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import clip_contrast as cc  # noqa: E402
import text_contrast as tc  # noqa: E402
from video import brand as B  # noqa: E402


#: The measured median of the clip library, and the row of the table in the
#: step report where the mark reads 1.24:1 today.
MEDIAN_CLIP_P95 = 0.797


def _grey(luminance: float) -> int:
    """The 0-255 neutral whose relative luminance is `luminance`."""
    return int(round(cc._grey_for(luminance)))


def _flat(luminance: float) -> np.ndarray:
    v = _grey(luminance)
    return np.full((tc.VIDEO_HEIGHT, tc.VIDEO_WIDTH, 3), v, dtype=np.uint8)


def _write_clip(path: Path, luminance: float, frames: int = 15) -> Path:
    """A one-colour mp4 at a known luminance."""
    import cv2

    v = _grey(luminance)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             30.0, (tc.VIDEO_WIDTH, tc.VIDEO_HEIGHT))
    frame = np.full((tc.VIDEO_HEIGHT, tc.VIDEO_WIDTH, 3), v, dtype=np.uint8)
    for _ in range(frames):
        writer.write(frame)
    writer.release()
    return path


# ────────────────── the mark is measured, by text_contrast ──────────────────

def test_text_contrast_knows_where_the_mark_is_drawn():
    """One definition of the box. A second copy would drift from the overlay
    one edit at a time, and the measurement would quietly move off the mark."""
    assert tc.WATERMARK_BOX == B.watermark_bounds()


def test_measure_frame_reports_the_watermark_and_not_only_the_headline():
    """The roadmap's own wording: `text_contrast` must measure the mark.
    Today nothing does, which is why this shipped for months."""
    metrics = tc.measure_frame(_flat(MEDIAN_CLIP_P95))

    assert "watermark_contrast_worst" in metrics
    assert "watermark_luminance_p95" in metrics
    # Distinct measurements of distinct zones against distinct colours: the
    # headline is yellow at rows 780..990, the mark is white at 1555..1609.
    assert metrics["watermark_contrast_worst"] != metrics["contrast_worst"]


def test_the_mark_is_measured_against_white_not_the_headline_yellow():
    """The mark's admissible background is more permissive than the band's
    precisely because it is white — (1.0 + 0.05)/3.0 - 0.05 = 0.300."""
    assert tc.WATERMARK_COLOR == (255, 255, 255)


def test_the_untreated_mark_fails_the_floor_on_the_median_clip():
    """The regression. 1.24:1 against a floor of 3.0, on the MEDIAN of the
    library — not its worst clip."""
    metrics = tc.measure_frame(_flat(MEDIAN_CLIP_P95))

    assert metrics["watermark_contrast_worst"] == pytest.approx(1.24, abs=0.02)
    assert not tc.passes_watermark(metrics)


def test_the_mark_passes_on_footage_dark_enough_to_carry_it():
    """It is not broken everywhere — it holds to roughly p95 0.25, which is
    why a dark-backdrop-era eyeball never caught it."""
    assert tc.passes_watermark(tc.measure_frame(_flat(0.05)))


def test_worst_case_over_time_carries_the_mark_too():
    """A preset that is dark at t=0 and bright at t=6 must be reported at its
    brightest for the mark as well, not only for the headline."""
    frames = {0.0: _flat(0.05), 1.0: _flat(0.95)}
    worst = tc.measure_over_time(lambda t: frames[t], (0.0, 1.0))

    assert worst["watermark_contrast_worst"] == pytest.approx(1.05, abs=0.02)


# ─────────────────── solved for white, never tuned by eye ───────────────────

def test_the_local_scrim_is_solved_from_the_measurement():
    """The derived table from the step report, reproduced. Not four
    constants — four outputs of strength_for() with white passed in."""
    solved = {p: round(cc.strength_for(p, cc.FLOOR, cc.MARK_COLOR), 3)
              for p in (0.400, 0.600, 0.797, 0.950)}

    assert solved == {0.400: 0.122, 0.600: 0.268, 0.797: 0.355, 0.950: 0.403}


def test_the_mark_is_always_solvable_within_the_cap():
    """White text is the most permissive case there is, so even a blown-out
    frame stays well under MAX_STRENGTH. If this ever hits the cap, the
    frame is not footage."""
    assert cc.strength_for(1.0, cc.FLOOR, cc.MARK_COLOR) < cc.MAX_STRENGTH


def test_a_dark_clip_asks_for_no_treatment_at_all():
    """The cost question, pinned. A dark clip that already clears the floor
    must come back at exactly zero — not 'a little', which would be a
    visible dark patch it never needed."""
    assert cc.strength_for(0.05, cc.FLOOR, cc.MARK_COLOR) == 0.0
    assert cc.solve_strength([[12.0, 12.0, 16.0]], cc.FLOOR, cc.MARK_COLOR) == 0.0


def test_tuning_the_shadow_cannot_reach_the_floor():
    """Swept, not assumed: alpha 160..255 x blur 4..12 tops out at 1.82:1.
    This exists so the next reader does not spend a pass on those two
    constants. It measures the SHADOW's own contribution — glyph ink against
    its halo — with no scrim underneath."""
    best = max(_glyph_over_halo(alpha, blur, MEDIAN_CLIP_P95)
               for alpha in (160, 200, 255) for blur in (4, 8, 12))

    assert best < 2.0, f"the shadow alone reached {best:.2f}:1 — re-derive"


def test_the_shadow_stays_because_it_does_real_work_where_it_can():
    """This adds a floor under the shadow; it does not replace it. Below
    p95 0.25 the shadow is carrying the mark on its own and costs nothing."""
    assert B.SHADOW_ALPHA == 160 and B.SHADOW_BLUR == 4
    assert _glyph_over_halo(B.SHADOW_ALPHA, B.SHADOW_BLUR, 0.05) > 3.0


# ───────────────────────── local in BOTH axes ─────────────────────────

def test_the_mark_scrim_is_local_in_both_axes():
    """Extending the readability band to row 1920 would darken the bottom of
    every video. The treatment covers the mark's box plus a feather and
    nothing else — including horizontally, which a row profile cannot do."""
    prof = cc.mark_profile(strength=0.4)
    x0, y0, x1, y1 = cc.MARK_BOX

    inside = prof[(y0 + y1) // 2 - y0 + cc.MARK_FEATHER,
                  (x0 + x1) // 2 - x0 + cc.MARK_FEATHER, 0]
    assert inside == pytest.approx(0.6)          # full strength on the mark
    assert prof[0, 0, 0] == pytest.approx(1.0)   # the corner is untouched


def test_the_mark_scrim_reaches_neither_the_text_band_nor_the_frame_bottom():
    """A patch that reaches the bottom of the frame is a strip by another
    name, and one that reaches the text band double-darkens it."""
    left, top, right, bottom = cc.mark_rect()

    assert top > max(b for _t, b in cc.TEXT_ZONES.values()), "reaches the text band"
    assert bottom < tc.VIDEO_HEIGHT, "reaches the bottom of the frame"
    assert right < tc.VIDEO_WIDTH * 0.5, "spans half the frame"
    assert left == 0, "stops short of the left edge and floats in the frame"


def test_the_scrim_fades_out_before_the_left_edge_rather_than_being_cut():
    """It runs to the left frame edge on purpose — anchored shading reads
    better than a floating slab — but a ramp CLAMPED mid-slope would put a
    hard vertical line down the edge of the video."""
    prof = cc.mark_profile(strength=cc.MAX_STRENGTH)
    at_edge = 1.0 - prof[prof.shape[0] // 2, 0, 0]

    assert at_edge < 0.02, f"{at_edge:.1%} darkening at the frame edge is a seam"


def test_the_mark_scrim_has_no_seam():
    """A visible rectangle is worse than the faint mark it replaces."""
    prof = cc.mark_profile(strength=0.5)
    assert np.abs(np.diff(prof[:, prof.shape[1] // 2, 0])).max() < 0.03
    assert np.abs(np.diff(prof[prof.shape[0] // 2, :, 0])).max() < 0.03


def test_zero_strength_is_the_identity():
    assert np.allclose(cc.mark_profile(strength=0.0), 1.0)


# ──────────────── the clip measurement and the solved plan ────────────────

def test_the_plan_measures_the_mark_zone_per_clip(tmp_path):
    """Sampled the way treatment_for_dir samples the text zone — across the
    clip, worst moment, per clip and not per project."""
    _write_clip(tmp_path / "bright.mp4", MEDIAN_CLIP_P95)
    plan = cc.treatment_for_dir(tmp_path, "quiz")

    assert plan["mark_worst_contrast"] == pytest.approx(1.24, abs=0.05)
    assert plan["mark_strength"] > 0
    assert plan["mark_meets_floor"]
    assert plan["clips"][0]["mark_worst_contrast"] == pytest.approx(1.24, abs=0.05)


def test_the_treated_mark_clears_the_floor_on_the_brightest_footage(tmp_path):
    """The proof, end to end: every row of the table at or above 3.0."""
    _write_clip(tmp_path / "blown.mp4", 0.95)
    plan = cc.treatment_for_dir(tmp_path, "educational")

    assert plan["mark_treated_contrast"] >= cc.FLOOR


def test_a_dark_playlist_is_left_completely_alone(tmp_path):
    """What the treatment costs a dark clip: nothing. If this ever returns a
    non-zero strength, the solve is wrong."""
    _write_clip(tmp_path / "night.mp4", 0.03)
    plan = cc.treatment_for_dir(tmp_path, "quiz")

    assert plan["mark_strength"] == 0.0


def test_the_band_already_over_the_mark_is_not_darkened_twice(tmp_path):
    """quiz's band ends 109px above the mark and its feather reaches past
    it, so those rows are ALREADY darkened. Solving the mark against raw
    pixels would stack the two and produce the visible patch this is
    supposed to avoid. educational's band stops 199px outside the feather,
    so its mark gets no help and must ask for more."""
    _write_clip(tmp_path / "bright.mp4", MEDIAN_CLIP_P95)

    quiz = cc.treatment_for_dir(tmp_path, "quiz")
    educational = cc.treatment_for_dir(tmp_path, "educational")

    assert quiz["mark_strength"] < educational["mark_strength"]
    assert quiz["mark_meets_floor"] and educational["mark_meets_floor"]


# ─────────────────── the renderer actually applies it ───────────────────

def test_the_clip_background_darkens_the_mark_and_nothing_else(tmp_path):
    """The band is a row profile and cannot reach the mark's columns. This
    is the second, local scrim — and everything outside its rectangle must
    come back byte-identical to the untreated frame."""
    from video.clip_background import ClipLibraryBackground

    _write_clip(tmp_path / "bright.mp4", MEDIAN_CLIP_P95)
    bg = ClipLibraryBackground(str(tmp_path), tc.VIDEO_WIDTH, tc.VIDEO_HEIGHT,
                               duration=0.4, video_type="educational")
    treated = bg.get_frame(0.0)
    # The same frame down the same decode path with the mark scrim switched
    # off. Compared against each other rather than against the colour that
    # was written, because mp4 is lossy — flat grey 231 comes back as
    # (228, 231, 228), which says nothing about the treatment.
    bg._mark = None
    untreated = bg.get_frame(0.0)
    bg.close()

    x0, y0, x1, y1 = cc.MARK_BOX
    under_mark = tc.relative_luminance(treated[y0:y1, x0:x1]).mean()
    assert tc.contrast_ratio(1.0, float(under_mark)) >= cc.FLOOR

    changed = np.any(treated != untreated, axis=2)
    rx0, ry0, rx1, ry1 = cc.mark_rect()
    outside = changed.copy()
    outside[ry0:ry1, rx0:rx1] = False
    assert not outside.any(), (
        f"{outside.sum()} pixels changed outside the mark's rectangle")
    assert changed[ry0:ry1, rx0:rx1].any(), "the mark was not treated at all"


def test_a_pinned_scrim_still_gets_a_measured_mark(tmp_path):
    """`scrim=` pins the BAND. It must not silently switch the mark off —
    the two are solved from different zones against different colours."""
    from video.clip_background import ClipLibraryBackground

    _write_clip(tmp_path / "bright.mp4", MEDIAN_CLIP_P95)
    bg = ClipLibraryBackground(str(tmp_path), tc.VIDEO_WIDTH, tc.VIDEO_HEIGHT,
                               duration=0.4, video_type="educational", scrim=0.0)
    frame = bg.get_frame(0.0)
    bg.close()

    x0, y0, x1, y1 = cc.MARK_BOX
    under_mark = tc.relative_luminance(frame[y0:y1, x0:x1]).mean()
    assert tc.contrast_ratio(1.0, float(under_mark)) >= cc.FLOOR


# ── the shadow sweep, measured the way the step report measured it ──

def _glyph_over_halo(alpha: int, blur: int, background: float) -> float:
    """Median glyph ink against median halo, compositing the REAL overlay.

    The honest question about a drop shadow: can the eye separate the letter
    from what the shadow put immediately around it. Not max-against-min
    inside the box, which compares the whitest pixel to the darkest core of
    the halo and flatters the treatment by roughly a factor of two.
    """
    from PIL import Image, ImageDraw, ImageFilter

    from config.layout import MARGIN_X, SAFE_AREA_BOTTOM
    from video.utils import manrope

    size = (tc.VIDEO_WIDTH, tc.VIDEO_HEIGHT)
    font = manrope(B.WATERMARK_SIZE, B.WATERMARK_WEIGHT)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, _right, bottom = probe.textbbox((0, 0), B.WATERMARK_TEXT, font=font)
    x = MARGIN_X - left
    y = SAFE_AREA_BOTTOM - B.WATERMARK_BOTTOM_GAP - (bottom - top) - top

    glyph = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((x, y), B.WATERMARK_TEXT, font=font,
                               fill=(255, 255, 255, 255))
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + B.SHADOW_OFFSET[0], y + B.SHADOW_OFFSET[1]),
                                B.WATERMARK_TEXT, font=font, fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))

    v = _grey(background)
    frame = Image.new("RGBA", size, (v, v, v, 255))
    frame.alpha_composite(shadow)
    frame.alpha_composite(Image.alpha_composite(
        Image.new("RGBA", size, (0, 0, 0, 0)), glyph))

    x0, y0, x1, y1 = B.watermark_bounds()
    sl = (slice(y0, y1), slice(x0, x1))
    ga = np.asarray(glyph)[:, :, 3][sl]
    sa = np.asarray(shadow)[:, :, 3][sl]
    lum = tc.relative_luminance(np.asarray(frame.convert("RGB"))[sl])

    ink, halo = ga > 200, (ga < 8) & (sa > 8)
    return tc.contrast_ratio(float(np.median(lum[ink])),
                             float(np.median(lum[halo])))


def test_a_non_canonical_canvas_is_skipped_rather_than_crashing(tmp_path):
    """mark_rect() is in absolute 1920-row coordinates, because the mark
    itself is — brand.py positions it off SAFE_AREA_BOTTOM, not off a
    fraction of the frame. Slicing those rows out of a smaller canvas gives
    a smaller array, and `*=` against the full-size profile is a shape
    mismatch: a crash in the middle of a render, for a canvas on which the
    watermark's own position is already undefined.
    """
    from video.clip_background import ClipLibraryBackground

    import cv2
    writer = cv2.VideoWriter(str(tmp_path / "small.mp4"),
                             cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (540, 960))
    for _ in range(10):
        writer.write(np.full((960, 540, 3), 231, dtype=np.uint8))
    writer.release()

    bg = ClipLibraryBackground(str(tmp_path), 540, 960, duration=0.3,
                               video_type="educational")
    frame = bg.get_frame(0.0)
    bg.close()

    assert frame.shape == (960, 540, 3)

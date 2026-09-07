#!/usr/bin/env python3
"""Readability for MOVING backgrounds: measured across time, fixed by band.

    from clip_contrast import worst_over_clip, treatment_for_dir
    report = worst_over_clip(Path("…/clips/pexels_123.mp4"), "quiz")
    plan   = treatment_for_dir(Path("…/clips"), "quiz")

WHY A CLIP IS NOT A STILL, WHICH IS THE WHOLE POINT.

A generated image is one picture. Measure it once and the measurement holds
for the entire video. F3's gate does exactly that and it is correct there.

A clip is a different picture every frame. The travel footage in the P1
sheet opens on dark rock and brightens into white surf; the food footage
opens on dough and ends on tomatoes under a bright spray. A single-frame
reading cannot see this BY CONSTRUCTION — it samples one moment of a
picture that has many, and reports it as though it were the whole. A
background that is beautiful for 20 seconds and unreadable for 3 passes
that gate every time.

So everything here samples ACROSS the clip and reports the WORST sample.
Never the average: an average is exactly the statistic that lets three bad
seconds hide behind twenty good ones.

WHY THE FIX IS THE F3 BAND AND NOT A BIGGER DIM.

ClipLibraryBackground darkened every pixel by a flat 35%. The P1 contact
sheet showed both ways that fails:

  · The technology videos rendered BLACK. Night city, a server room and
    fibre optic cables are already dark; 35% off the whole frame left
    nothing to see. This is the F3 black-frame failure arriving through a
    different door — the footage is present and invisible.
  · The faded option cards died over BRIGHT footage — tomatoes under water,
    a kitten on a pale floor, a balloon against sky. 35% was not enough
    there, while being far too much for the server room.

One number cannot serve both, because the two failures pull opposite ways.

What actually helps is what F3 already learned: darken WHERE THE TEXT IS and
leave the picture alone everywhere else. Brightness outside the text zone is
not a readability problem, it is the reason we fetched footage at all. So
the flat dim goes to zero and the raised-cosine band from
topic_background.apply_readability_scrim is reused here — the same profile
function, imported, not a second implementation of the same curve.

The band's STRENGTH is then solved per clip from the measurement rather than
picked: see strength_for(). A dark clip needs almost none and keeps its
picture; a bright one gets as much as it needs and only across the rows that
carry text.

THE WATERMARK IS A SECOND ZONE, AND THE BAND CANNOT REACH IT.

The brand mark is white text at rows 1555..1609 — below every text zone here,
and on three of the six types below the band's feather as well. It had only a
blurred black shadow whose constants were chosen by eye against a dark
backdrop, and once the background standard made the bottom third bright it
read 1.24:1 on the median clip. Sweeping the shadow's two constants tops out
at 1.82:1 against a floor of 3.0, so there is nothing to tune there.

So the mark gets the same treatment the band gets, over its own small box:
measured per clip (mark_patch), solved against WHITE rather than the headline
yellow (MARK_COLOR), and applied as a patch local in both axes
(mark_profile). Where the band already darkens those rows its contribution is
credited first (band_over_mark), so the two cannot stack into a dark slab.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

import sys as _sys
_SRC = str(Path(__file__).resolve().parent)
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

from text_contrast import (  # noqa: E402
    HEADLINE_COLOR, VIDEO_HEIGHT, VIDEO_WIDTH, WATERMARK_BOX, WATERMARK_COLOR,
    WCAG_LARGE_TEXT, contrast_ratio, relative_luminance,
)

logger = logging.getLogger(__name__)

#: How often to sample a clip, in seconds. Stated rather than buried: every
#: report this module produces names the interval it used, because "worst of
#: N samples" means nothing without N.
#:
#: 0.5 s is below the shortest text state in any layout — the quiz countdown
#: holds a number for 1.5 s — so no state can slip between two samples. It
#: is also cheap: a 30 s clip is 60 decoded frames, under a second.
SAMPLE_INTERVAL = 0.5

#: The rows each video type draws text on, from config/layout.py. NOT one
#: band for everything: true_false starts at 0.10 of the frame and quiz's
#: countdown runs to 0.75, so a single band would either miss text or darken
#: most of the picture.
#:
#: Each is (top, bottom) in 1920-row coordinates, taken as the union of that
#: type's declared zones plus a little slack for card shadow.
TEXT_ZONES = {
    "quiz":          (270, 1450),   # question zone top .. countdown zone
    "true_false":    (180, 1400),   # question .. explanation
    "fill_blank":    (230, 1120),   # sentence card .. translation pill
    "pronunciation": (230, 1160),   # title .. correct text
    "vocabulary":    (240, 1400),   # card top .. timer bar
    "educational":   (700, 1060),   # the headline band, widened for shadow
}

#: When the type is unknown, cover the union of every zone above. Wider than
#: any single type and deliberately so — guessing narrow would leave text
#: unprotected, and the cost of guessing wide is a slightly larger dark band.
DEFAULT_ZONE = (min(t for t, _ in TEXT_ZONES.values()),
                max(b for _, b in TEXT_ZONES.values()))

#: Falloff distance either side of the band, in 1920-row coordinates.
#: Inherited from topic_background.SCRIM_FEATHER for the same reason it was
#: chosen there: a visible seam is worse than the problem it fixes, and a
#: raised cosine over a distance comparable to the band has zero derivative
#: at both ends so there is no edge to catch the eye.
FEATHER = 300

#: The floor. WCAG_LARGE_TEXT (3.0), not the stricter 4.5, because every
#: layout here draws its text on a card or at headline size. Applied to the
#: WORST sample of the worst clip, which makes it a real floor rather than a
#: target the average clears.
FLOOR = WCAG_LARGE_TEXT

#: Ceiling on how much the band may darken. Above this the picture stops
#: being footage and becomes a dark rectangle with a video behind it — which
#: is the outcome F3 spent a batch of six videos discovering.
MAX_STRENGTH = 0.75

#: sRGB transfer exponent. Multiplying 8-bit values by f scales relative
#: luminance by about f**GAMMA, which is what lets strength_for solve for
#: the darkening instead of searching for it.
GAMMA = 2.4

# ── the watermark's own zone ────────────────────────────────────────────
#
# WHY THE MARK NEEDS ITS OWN TREATMENT AND NOT A TALLER BAND.
#
# The mark is white text at rows 1555..1609. The band above ends at 1450 on
# quiz and at 1060 on educational, so measured against the mark's top row:
#
#     quiz            109 px below the band     (feather reaches it)
#     true_false      159 px                    (feather reaches it)
#     vocabulary      159 px                    (feather reaches it)
#     pronunciation   399 px — 99 px OUTSIDE the feather
#     fill_blank      439 px — 139 px OUTSIDE
#     educational     499 px — 199 px OUTSIDE
#
# In three of six types the band cannot reach the mark at all. Stretching it
# to row 1920 would fix that by darkening the bottom of every video, which
# is the flat-dim mistake wearing a different hat: brightness where there is
# no text is the footage we went and fetched.
#
# So the mark gets a scrim over ITS OWN box and nothing else — local in both
# axes, which a row profile cannot express.
MARK_BOX = WATERMARK_BOX

#: White. The mark's admissible background is therefore 0.300 rather than the
#: yellow headline's 0.129, and every solve below is more permissive as a
#: result. Passed explicitly rather than defaulted, because taking
#: HEADLINE_COLOR here would over-darken the mark by roughly a factor of two.
MARK_COLOR = WATERMARK_COLOR

#: Falloff around the mark's box, in 1920-row coordinates.
#:
#: A SEAM PARAMETER, NOT A CONTRAST ONE — the strength is solved (see
#: strength_for); this only decides how the patch fades out, and it was
#: chosen by looking at the brightest clip in the library rather than by
#: arithmetic, which is the honest description of it.
#:
#: 60 px was tried first and rendered a floating grey slab: the box is 354 px
#: wide, so a 60 px ramp around it still reads as a rectangle with rounded
#: corners — the pasted-on-UI quality brand.py rejected the opaque pill for.
#:
#: 80 px is the value where the horizontal ramp runs out exactly at the left
#: frame edge (the mark starts at column 73), so the patch reads as shading
#: anchored in the corner rather than an object floating in the frame, and it
#: gets there with 0.8% darkening at the edge itself — no clamp seam. It
#: still stops 25 px above the lowest text zone's 1450, 231 px above the
#: frame bottom, and spans 47% of the width. Past ~90 px it starts eating
#: into quiz's band and the edge stops being clean.
MARK_FEATHER = 80


def text_zone(video_type: Optional[str]) -> Tuple[int, int]:
    """The rows this type draws text on. Unknown types get the union."""
    return TEXT_ZONES.get((video_type or "").lower(), DEFAULT_ZONE)


def scrim_profile(height: int, zone: Tuple[int, int] = None,
                  feather: int = FEATHER, strength: float = 1.0) -> np.ndarray:
    """The raised-cosine darkening profile, as a column of multipliers.

    THE one implementation of this curve. topic_background.apply_readability_scrim
    calls it for stills and ClipLibraryBackground calls it per frame, so the
    band a clip gets and the band an image gets are the same shape by
    construction rather than by two functions agreeing.

    Returns shape (height, 1, 1) so it broadcasts straight onto an
    (h, w, 3) frame.
    """
    top, bottom = zone or DEFAULT_ZONE
    # Coordinates are declared in 1920 rows; scale to whatever this image is.
    scale = height / VIDEO_HEIGHT
    top, bottom, feather = top * scale, bottom * scale, max(1.0, feather * scale)

    band = _ramp(np.arange(height, dtype=np.float32), top, bottom, feather)
    return (1.0 - float(strength) * band)[:, None, None]


def _ramp(coords: np.ndarray, lo: float, hi: float,
          feather: float) -> np.ndarray:
    """1.0 between `lo` and `hi`, raised cosine to 0.0 over `feather`.

    THE curve, in one place. scrim_profile applies it down the rows and
    mark_profile applies it along both axes; a second copy for the mark
    would have been a second thing to keep in step with topic_background,
    which already imports this one for stills.

    Raised cosine because its derivative is zero at both ends of the
    falloff, so there is no edge for the eye to catch.
    """
    out = np.zeros_like(coords, dtype=np.float32)
    out[(coords >= lo) & (coords <= hi)] = 1.0

    upper = (coords < lo) & (coords > lo - feather)
    out[upper] = 0.5 * (1 + np.cos(np.pi * (lo - coords[upper]) / feather))
    lower = (coords > hi) & (coords < hi + feather)
    out[lower] = 0.5 * (1 + np.cos(np.pi * (coords[lower] - hi) / feather))
    return out


def mark_rect(box: Tuple[int, int, int, int] = MARK_BOX,
              feather: int = MARK_FEATHER) -> Tuple[int, int, int, int]:
    """The rectangle the mark's treatment actually touches, feather included.

    Returned so the renderer can multiply a 474x174 sub-array instead of the
    whole 1080x1920 frame. That is not only cheaper — it is the claim that
    the treatment is local, in a form the caller cannot accidentally widen.
    """
    x0, y0, x1, y1 = box
    return (max(0, x0 - feather), max(0, y0 - feather),
            min(VIDEO_WIDTH, x1 + feather), min(VIDEO_HEIGHT, y1 + feather))


def mark_profile(box: Tuple[int, int, int, int] = MARK_BOX,
                 feather: int = MARK_FEATHER,
                 strength: float = 1.0) -> np.ndarray:
    """The mark's darkening, as multipliers over mark_rect() only.

    Shape (h, w, 1) covering the rectangle — NOT the frame. The band is a
    column of multipliers because it spans the full width by design; the
    mark must fall off horizontally too, or it is a strip.

    Separable: the same raised cosine down the rows and along the columns,
    multiplied. The product is 1.0 across the box, falls smoothly to 0 at
    every edge, and rounds the corners for free.
    """
    rx0, ry0, rx1, ry1 = mark_rect(box, feather)
    rows = _ramp(np.arange(ry0, ry1, dtype=np.float32), box[1], box[3], feather)
    cols = _ramp(np.arange(rx0, rx1, dtype=np.float32), box[0], box[2], feather)
    return (1.0 - float(strength) * (rows[:, None] * cols[None, :]))[:, :, None]


def mark_patch(frame: np.ndarray,
               box: Tuple[int, int, int, int] = MARK_BOX) -> np.ndarray:
    """The pixels under the mark, from a fitted frame.

    The box, not the feathered rectangle: the feather exists so the
    treatment has no visible edge, not because anything is read there.
    """
    x0, y0, x1, y1 = box
    patch = frame[y0:y1, x0:x1]
    return patch if patch.size else frame


def band_over_mark(strength: float, zone: Tuple[int, int],
                   box: Tuple[int, int, int, int] = MARK_BOX,
                   feather: int = FEATHER) -> float:
    """How much the TEXT band has already darkened the mark's rows.

    WITHOUT THIS THE TWO TREATMENTS STACK. quiz's band ends 109 px above the
    mark and its 300 px feather reaches well past it, so rows 1555..1609 are
    already darkened to between 0.73 and 0.45 of the band's strength before
    the mark's own scrim is applied. Solving the mark against raw clip pixels
    and then multiplying both together is exactly the visible dark patch this
    step exists to avoid.

    Returns the WEAKEST darkening anywhere over the box — the largest
    multiplier, at the box's bottom row. Conservative on purpose: crediting
    the band with its strongest reach would leave the mark's bottom rows
    short of the floor, and undershooting the floor is the failure that
    matters. Types whose band cannot reach the mark get exactly 1.0.
    """
    if strength <= 0:
        return 1.0
    profile = scrim_profile(VIDEO_HEIGHT, zone, feather, strength).ravel()
    return float(profile[box[1]:box[3]].max())


def fit_frame(frame: np.ndarray) -> np.ndarray:
    """Scale and centre-crop to 1080x1920, exactly as the renderer does.

    MEASURING THE RAW FILE IS MEASURING THE WRONG PIXELS. A 1080x2048 clip
    loses 64 rows top and bottom on the way to the frame, and a wider one
    loses columns; a zone mapped onto the raw file's own height lands on
    content the viewer never sees. The first version of this module did
    that, and its predicted band undershot the floor by 0.4-0.7 ratio
    points on every playlist — the treatment was computed against different
    pixels from the ones it was later applied to.

    Duplicated in shape from ClipLibraryBackground._fit rather than
    imported, because importing it would drag cv2's renderer module into a
    measurement tool; the crop is four lines of arithmetic and both are
    pinned by test.
    """
    import cv2

    fh, fw = frame.shape[:2]
    if (fw, fh) == (VIDEO_WIDTH, VIDEO_HEIGHT):
        return frame
    scale = max(VIDEO_WIDTH / fw, VIDEO_HEIGHT / fh)
    resized = cv2.resize(frame, (int(round(fw * scale)), int(round(fh * scale))),
                         interpolation=cv2.INTER_AREA)
    y0 = (resized.shape[0] - VIDEO_HEIGHT) // 2
    x0 = (resized.shape[1] - VIDEO_WIDTH) // 2
    return resized[y0:y0 + VIDEO_HEIGHT, x0:x0 + VIDEO_WIDTH]


def measure_zone(frame: np.ndarray, zone: Tuple[int, int],
                 text_color=HEADLINE_COLOR) -> Dict[str, float]:
    """Contrast of one frame's TEXT ZONE against the text colour.

    `frame` must already be 1080x1920 — pass it through fit_frame first.

    p95 rather than the mean, mirroring text_contrast.measure_frame: a
    bright patch behind two words is what makes a caption unreadable, and a
    mean over 1180 rows will not notice it.
    """
    patch = zone_patch(frame, zone)
    if patch.size == 0:
        patch = frame
    return measure_zone_patch(patch, text_color)


def strength_for(luminance_p95: float, floor: float = FLOOR,
                 text_color=HEADLINE_COLOR) -> float:
    """The band strength that brings THIS luminance up to `floor`. Derived.

    Not a tuned constant — solved. For a target contrast C against text
    luminance Lt, the background may reach at most

        (Lt + 0.05) / (L' + 0.05) >= C   =>   L' <= (Lt + 0.05)/C - 0.05

    and the darkening factor comes from inverting the sRGB transfer.

    THE POWER LAW IS NOT GOOD ENOUGH HERE, which cost a measurement pass to
    learn. The obvious model says luminance scales as f**GAMMA, but sRGB
    linearisation is ((c + 0.055)/1.055)**GAMMA, and that additive 0.055
    means a darkened pixel stays brighter than the pure power predicts.
    Using f = (L'/L)**(1/GAMMA) undershot the floor on all eight playlists
    — 2.27 to 2.83 against a floor of 3.0, wrong in the unsafe direction.

    So the transfer is inverted properly: treat the measured luminance as
    coming from a grey of value v, where lum(v) = L, and solve for the grey
    that lands on L'. Exact for grey and far closer for real footage than
    the power law was.

    Returns 0.0 when the clip already clears the floor, which is the case
    that matters most: a dark clip is left completely alone and keeps its
    picture, instead of being crushed by a flat 35% it never needed.
    """
    l_text = float(relative_luminance(np.array(text_color)))
    if luminance_p95 <= 0:
        return 0.0
    allowed = (l_text + 0.05) / float(floor) - 0.05
    if allowed >= luminance_p95:
        return 0.0
    if allowed <= 0:
        return MAX_STRENGTH
    have, want = _grey_for(luminance_p95), _grey_for(allowed)
    if have <= 0:
        return 0.0
    return float(min(MAX_STRENGTH, max(0.0, 1.0 - want / have)))


def _grey_for(luminance: float) -> float:
    """The 0-255 grey whose relative luminance is `luminance`.

    The inverse of text_contrast.relative_luminance for a neutral value,
    including the linear toe below 0.03928 — the toe never fires for the
    bright patches this is used on, but omitting it would make the function
    quietly wrong for dark ones.
    """
    luminance = max(0.0, float(luminance))
    linear_toe = 0.03928 / 12.92
    if luminance <= linear_toe:
        return 255.0 * luminance * 12.92
    return 255.0 * (1.055 * (luminance ** (1.0 / GAMMA)) - 0.055)


def solve_strength(p95_pixels, floor: float = FLOOR,
                   text_color=HEADLINE_COLOR, step: float = 0.005) -> float:
    """The smallest band strength for which EVERY sampled moment clears the floor.

    WHY A SCAN AND NOT A BISECTION — this cost two measurement passes to
    learn, and it is the subtle part of this module.

    WCAG contrast is SYMMETRIC: it divides the lighter luminance by the
    darker one. A background brighter than the text therefore scores well,
    scores 1.00 as it passes through the text's own luminance, and scores
    well again once it is darker. Darkening is consequently NOT monotonic in
    contrast — it pushes a too-bright background DOWN THROUGH the text
    luminance and out the other side.

    Two consequences, both of which bit:

      · The frame that is worst before treatment is not the frame that is
        worst after it. Solving on the pre-treatment worst frame gave social
        a band of 0.434 that took its own frame to exactly 3.00 while
        dragging a different frame, half a second earlier, down to 2.29.
      · A bisection is invalid on a non-monotonic function.

    So this evaluates candidate strengths against every sampled moment and
    returns the smallest that clears the floor everywhere. `p95_pixels` is
    one RGB triple per sample, so the scan is arithmetic on a few hundred
    triples — no decoding, no frames held in memory.

    Returns 0.0 when nothing needs treating, and MAX_STRENGTH when no
    strength suffices; the caller reports the shortfall rather than
    darkening to black on its own initiative.
    """
    pixels = np.asarray(list(p95_pixels), dtype=np.float32)
    if pixels.size == 0:
        return 0.0
    l_text = float(relative_luminance(np.array(text_color)))

    def worst_at(strength: float) -> float:
        darkened = np.clip(pixels * (1.0 - strength), 0, 255)
        lums = relative_luminance(darkened)
        return float(min(contrast_ratio(l_text, float(l)) for l in lums))

    if worst_at(0.0) >= floor:
        return 0.0
    steps = int(MAX_STRENGTH / step) + 1
    for i in range(1, steps + 1):
        strength = min(MAX_STRENGTH, i * step)
        if worst_at(strength) >= floor:
            return float(strength)
    return MAX_STRENGTH


def _contrast_at(p95_pixels, strength: float, text_color=HEADLINE_COLOR) -> float:
    """Worst contrast across these sampled pixels at one band strength."""
    pixels = np.asarray(list(p95_pixels), dtype=np.float32)
    if pixels.size == 0:
        return float("inf")
    l_text = float(relative_luminance(np.array(text_color)))
    lums = relative_luminance(np.clip(pixels * (1.0 - strength), 0, 255))
    return float(min(contrast_ratio(l_text, float(l)) for l in lums))


def measure_zone_patch(patch: np.ndarray, text_color=HEADLINE_COLOR) -> Dict[str, float]:
    """measure_zone's arithmetic, on a patch that is already cropped.

    Also returns `p95_rgb`: the actual pixel sitting at the 95th percentile
    of luminance. That one triple is what makes the treatment solvable
    exactly — darkening scales every channel, and per-pixel luminance is
    monotonic in each channel, so the p95 pixel of a darkened patch is the
    darkened p95 pixel. Three numbers per sample instead of a megabyte.
    """
    flat = patch.reshape(-1, patch.shape[-1])
    lum = relative_luminance(flat)
    l_text = float(relative_luminance(np.array(text_color)))
    index = int(np.argsort(lum)[min(len(lum) - 1, int(0.95 * len(lum)))])
    l_p95 = float(lum[index])
    return {
        "bg_luminance_p95": l_p95,
        "bg_luminance_mean": float(lum.mean()),
        "p95_rgb": [float(c) for c in flat[index]],
        "contrast_worst": contrast_ratio(l_text, l_p95),
        "contrast_mean": contrast_ratio(l_text, float(lum.mean())),
    }


def zone_patch(frame: np.ndarray, zone: Tuple[int, int]) -> np.ndarray:
    """The rows and columns measure_zone looks at, from a fitted frame."""
    top, bottom = zone
    x0 = (VIDEO_WIDTH - 920) // 2
    return frame[top:bottom, x0:x0 + 920]


def sample_times(duration: float, interval: float = SAMPLE_INTERVAL) -> List[float]:
    """Every `interval` seconds, plus the last frame. Never a single point."""
    duration = max(0.0, float(duration or 0))
    n = max(2, int(duration / max(1e-3, interval)) + 1)
    times = [min(duration, i * interval) for i in range(n)]
    if times[-1] < duration:
        times.append(duration)
    return times


def worst_over_clip(path: Path, video_type: str = None,
                    interval: float = SAMPLE_INTERVAL) -> Optional[Dict]:
    """Sample one clip across its whole duration. Reports the WORST moment.

    The returned dict names the interval and the sample count, because
    "worst case" without them is not a measurement anyone can check.
    """
    import cv2

    zone = text_zone(video_type)
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frames <= 0 or fps <= 0:
        capture.release()
        logger.warning("clip_contrast: unreadable clip %s", path)
        return None
    duration = frames / fps

    samples = []
    for t in sample_times(duration, interval):
        capture.set(cv2.CAP_PROP_POS_FRAMES, min(frames - 1, int(t * fps)))
        ok, frame = capture.read()
        if not ok:
            continue
        rgb = fit_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        # Both zones off the same decoded frame: the mark's box is 19k
        # pixels against the text zone's 1.09M, so measuring it costs
        # nothing next to the decode that already happened.
        samples.append((t, measure_zone(rgb, zone),
                        measure_zone_patch(mark_patch(rgb), MARK_COLOR)))
    capture.release()

    if not samples:
        return None

    # WORST, not average. The whole reason this module exists.
    worst_t, worst, _ = min(samples, key=lambda s: s[1]["contrast_worst"])
    best_t, best, _ = max(samples, key=lambda s: s[1]["contrast_worst"])
    mark_worst = min(m["contrast_worst"] for _, _, m in samples)
    return {
        # Every sample's p95 pixel, for the treatment scan. Kept because
        # the post-treatment worst moment is not the pre-treatment one —
        # see solve_strength.
        "p95_pixels": [m["p95_rgb"] for _, m, _ in samples],
        "mark_p95_pixels": [m["p95_rgb"] for _, _, m in samples],
        "mark_worst_contrast": round(mark_worst, 2),
        "mark_passes_untreated": mark_worst >= FLOOR,
        "path": str(path),
        "duration": round(duration, 2),
        "samples": len(samples),
        "interval": interval,
        "zone": zone,
        "worst_contrast": round(worst["contrast_worst"], 2),
        "worst_at": round(worst_t, 2),
        "best_contrast": round(best["contrast_worst"], 2),
        "best_at": round(best_t, 2),
        "worst_luminance_p95": worst["bg_luminance_p95"],
        "needed_strength": round(strength_for(worst["bg_luminance_p95"]), 3),
        "passes_untreated": worst["contrast_worst"] >= FLOOR,
    }


def treatment_for_dir(clips_dir: Path, video_type: str = None,
                      interval: float = SAMPLE_INTERVAL,
                      band_strength: float = None) -> Dict:
    """Measure every clip in a directory and size the band for the worst.

    ONE strength for the whole playlist rather than one per clip, and that
    is deliberate: the band changing strength as the playlist cuts between
    clips would pump visibly, which is a worse artefact than a slightly
    over-darkened band on the darker clips. The band is sized for the
    brightest moment ANY clip reaches, so no cut can surprise it.
    """
    reports = []
    for path in sorted(Path(clips_dir).rglob("*.mp4")):
        report = worst_over_clip(path, video_type, interval)
        if report:
            reports.append(report)

    if not reports:
        return {"clips": [], "strength": 0.0, "worst_contrast": None,
                "mark_strength": 0.0, "mark_worst_contrast": None,
                "mark_treated_contrast": None, "mark_meets_floor": True,
                "interval": interval, "video_type": video_type}

    zone = text_zone(video_type)
    worst = min(reports, key=lambda r: r["worst_contrast"])

    # SOLVED ACROSS EVERY SAMPLED MOMENT OF EVERY CLIP IN THE PLAYLIST, not
    # against one frame. The band must survive the brightest instant any
    # clip reaches AND every instant that darkening would drag through the
    # text's own luminance, which is a different frame.
    every = [px for r in reports for px in r["p95_pixels"]]
    strength = float(band_strength) if band_strength is not None \
        else solve_strength(every)
    achieved = _contrast_at(every, strength)

    # ── the mark, solved over its own zone against white ──
    #
    # Against the pixels the band has ALREADY darkened, not the raw ones.
    # For quiz the band's feather reaches the mark's rows, so part of the
    # work is done; for educational it stops 199 px short and none of it is.
    # Solving against raw pixels would stack the two treatments on the types
    # where they overlap and put a visible dark patch under the mark.
    leak = band_over_mark(strength, zone)
    mark_pixels = [[c * leak for c in px]
                   for r in reports for px in r["mark_p95_pixels"]]
    mark_strength = solve_strength(mark_pixels, FLOOR, MARK_COLOR)
    mark_achieved = _contrast_at(mark_pixels, mark_strength, MARK_COLOR)
    mark_worst = min(r["mark_worst_contrast"] for r in reports)

    for report in reports:
        report.pop("p95_pixels", None)
        report.pop("mark_p95_pixels", None)

    return {
        "clips": reports,
        "video_type": video_type,
        "zone": zone,
        "interval": interval,
        "strength": round(float(strength), 3),
        "worst_contrast": worst["worst_contrast"],
        "worst_clip": worst["path"],
        "worst_at": worst["worst_at"],
        "treated_contrast": round(achieved, 2) if achieved else None,
        "meets_floor": bool(achieved is not None and achieved >= FLOOR),
        "failing_untreated": [r["path"] for r in reports
                              if not r["passes_untreated"]],
        "mark_box": MARK_BOX,
        "mark_rect": mark_rect(),
        "mark_band_credit": round(leak, 3),
        "mark_strength": round(float(mark_strength), 3),
        "mark_worst_contrast": round(mark_worst, 2),
        "mark_treated_contrast": round(mark_achieved, 2),
        "mark_meets_floor": bool(mark_achieved >= FLOOR),
        "mark_failing_untreated": [r["path"] for r in reports
                                   if not r["mark_passes_untreated"]],
    }


def _patch_at(path: Path, t: float, zone: Tuple[int, int]) -> Optional[np.ndarray]:
    """The measured patch of one clip at one moment, fitted as it will ship."""
    import cv2

    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frames <= 0:
        capture.release()
        return None
    capture.set(cv2.CAP_PROP_POS_FRAMES, min(frames - 1, int(t * fps)))
    ok, frame = capture.read()
    capture.release()
    if not ok:
        return None
    return zone_patch(fit_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), zone)

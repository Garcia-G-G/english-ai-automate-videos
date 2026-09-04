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
    HEADLINE_COLOR, VIDEO_HEIGHT, VIDEO_WIDTH, WCAG_LARGE_TEXT,
    contrast_ratio, relative_luminance,
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

    y = np.arange(height, dtype=np.float32)
    band = np.zeros(height, dtype=np.float32)
    band[(y >= top) & (y <= bottom)] = 1.0

    upper = (y < top) & (y > top - feather)
    band[upper] = 0.5 * (1 + np.cos(np.pi * (top - y[upper]) / feather))
    lower = (y > bottom) & (y < bottom + feather)
    band[lower] = 0.5 * (1 + np.cos(np.pi * (y[lower] - bottom) / feather))

    return (1.0 - float(strength) * band)[:, None, None]


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
        samples.append((t, measure_zone(rgb, zone)))
    capture.release()

    if not samples:
        return None

    # WORST, not average. The whole reason this module exists.
    worst_t, worst = min(samples, key=lambda s: s[1]["contrast_worst"])
    best_t, best = max(samples, key=lambda s: s[1]["contrast_worst"])
    return {
        # Every sample's p95 pixel, for the treatment scan. Kept because
        # the post-treatment worst moment is not the pre-treatment one —
        # see solve_strength.
        "p95_pixels": [m["p95_rgb"] for _, m in samples],
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
                      interval: float = SAMPLE_INTERVAL) -> Dict:
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
                "interval": interval, "video_type": video_type}

    zone = text_zone(video_type)
    worst = min(reports, key=lambda r: r["worst_contrast"])

    # SOLVED ACROSS EVERY SAMPLED MOMENT OF EVERY CLIP IN THE PLAYLIST, not
    # against one frame. The band must survive the brightest instant any
    # clip reaches AND every instant that darkening would drag through the
    # text's own luminance, which is a different frame.
    every = [px for r in reports for px in r["p95_pixels"]]
    strength = solve_strength(every)
    achieved = _contrast_at(every, strength)

    for report in reports:
        report.pop("p95_pixels", None)

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

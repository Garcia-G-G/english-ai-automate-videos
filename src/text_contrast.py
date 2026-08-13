"""How legible is the headline going to be on this background?

One definition of the measurement, imported by everything that needs it —
the contact sheet, the palette generator's accept/reject gate, and any
report quoting a contrast floor. Two copies of this would drift, and then
two reports would disagree about the same preset.

What is measured, precisely:

* The **headline band** — the rectangle the big English word occupies. Not
  the whole frame: a background can be brilliant at the top and still be
  perfectly readable, and averaging over the full frame hides exactly the
  failure this is looking for.
* The **bare background**, before any text is drawn, and therefore before
  the 6px black outline every string carries. The outline lifts real-world
  legibility well above these numbers. That makes this measurement
  pessimistic on purpose: it asks whether the background alone can carry
  the text, rather than whether the outline can rescue it.
* Against **WCAG relative luminance**, so the numbers mean the same thing
  as the 3.0 (large text, AA) and 4.5 (normal text, AA) thresholds
  everybody already knows.

Two numbers come back per frame and they answer different questions.
``mean`` is what the band looks like on average. ``worst`` is the brightest
5% of it — the patch where a glyph will disappear if any patch will. A
preset that averages well and has a bright hotspot behind one word reads as
fine by ``mean`` and fails in the video, so ``worst`` is the one worth
gating on.
"""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

import numpy as np

# The band the headline occupies, matching where the contact sheet draws it.
# Kept here rather than imported from video.constants so this module stays
# usable without pulling in the renderer.
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
TEXT_AREA_WIDTH = 920
HEADLINE_TOP = 780
HEADLINE_BOTTOM = 990

# The yellow the English headline is drawn in (config.colors.ENGLISH_WORD_COLOR).
HEADLINE_COLOR = (255, 215, 0)

# WCAG AA: 3.0 for large text, 4.5 for normal. The gate used by the palette
# generator is the stricter one, applied to the worst-case patch.
WCAG_LARGE_TEXT = 3.0
WCAG_NORMAL_TEXT = 4.5


def relative_luminance(rgb) -> np.ndarray:
    """WCAG relative luminance for sRGB values in 0..255, any array shape."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def contrast_ratio(l1: float, l2: float) -> float:
    """WCAG contrast ratio between two relative luminances."""
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def headline_band(frame: np.ndarray) -> np.ndarray:
    """The slice of a full frame that the headline sits on."""
    x0 = (VIDEO_WIDTH - TEXT_AREA_WIDTH) // 2
    return frame[HEADLINE_TOP:HEADLINE_BOTTOM, x0:x0 + TEXT_AREA_WIDTH]


def measure_frame(frame: np.ndarray, text_color=HEADLINE_COLOR) -> Dict[str, float]:
    """Contrast of one bare background frame against the headline colour."""
    lum = relative_luminance(headline_band(frame))
    l_text = float(relative_luminance(np.array(text_color)))

    l_mean = float(lum.mean())
    l_bright = float(np.percentile(lum, 95))

    return {
        "bg_luminance_mean": l_mean,
        "bg_luminance_p95": l_bright,
        "contrast_mean": contrast_ratio(l_text, l_mean),
        "contrast_worst": contrast_ratio(l_text, l_bright),
        "contrast_white_mean": contrast_ratio(1.0, l_mean),
    }


def measure_over_time(render, times: Sequence[float],
                      text_color=HEADLINE_COLOR) -> Dict[str, float]:
    """Worst contrast a preset reaches anywhere in its cycle.

    An animated gradient is a different picture at t=0 and t=6, so a single
    sample is not a floor, it is an anecdote. ``render(t)`` is called for
    each time and the returned figures are the least favourable seen.

    Static presets can pass ``times=(0.0,)`` — the extra samples would be
    identical frames.
    """
    samples = [measure_frame(render(t), text_color) for t in times]
    worst = min(samples, key=lambda s: s["contrast_worst"])
    return {
        **worst,
        "contrast_mean": min(s["contrast_mean"] for s in samples),
        "contrast_worst": min(s["contrast_worst"] for s in samples),
        "samples": len(samples),
    }


def cycle_samples(preset: Dict, n: int = 12) -> Sequence[float]:
    """Times to sample so an animated preset is caught at its brightest.

    Covers one full colour cycle where the preset declares one, and a
    30s span otherwise, which is the duration the renderer assumes.
    """
    if preset.get("type") not in ("animated_gradient", "aurora", "bokeh_particles",
                                  "dynamic_glow_orbs", "particle_flow", "light_rays",
                                  "photo_kenburns", "solid_vignette"):
        return (0.0,)
    span = float(preset.get("cycle_duration", 30.0))
    return tuple(span * i / n for i in range(n))


def passes(metrics: Dict[str, float], floor: float = WCAG_NORMAL_TEXT) -> bool:
    """Gate on the worst-case patch, not the average."""
    return metrics["contrast_worst"] >= floor


def format_row(name: str, metrics: Dict[str, float]) -> str:
    return (f"{name:22s} mean {metrics['contrast_mean']:6.2f}:1   "
            f"worst {metrics['contrast_worst']:6.2f}:1")


def floor_of(all_metrics: Iterable[Dict[str, float]]) -> float:
    """The lowest worst-case contrast across a set — the set's floor."""
    return min(m["contrast_worst"] for m in all_metrics)

"""Motion engine for the v2 renderer.

Hand-rolled easing curves and animation primitives. Every function is a
pure, deterministic function of time ``t`` so the compositor can call
``f(t)`` in any order and always get the same frame.

Conventions:
    * ``p`` is a normalized progress value; inputs are clamped to [0, 1].
    * Time-based primitives take ``(t, start, dur)`` and clamp internally.
"""

import math
from typing import Tuple

__all__ = [
    "clamp01", "ease_out_back", "ease_out_expo", "ease_in_out_cubic",
    "spring", "pop_in", "slide_up", "fade", "fade_out", "stagger", "pulse",
]


def clamp01(p: float) -> float:
    """Clamp a progress value to [0, 1]."""
    return 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)


# ── Easing curves ────────────────────────────────────────────────────


def ease_out_back(p: float, overshoot: float = 1.70158) -> float:
    """Decelerating curve that overshoots past 1.0 and settles back."""
    p = clamp01(p)
    c = overshoot
    q = p - 1.0
    return 1.0 + (c + 1.0) * q * q * q + c * q * q


def ease_out_expo(p: float) -> float:
    """Very fast start, long exponential settle. Great for slides."""
    p = clamp01(p)
    return 1.0 if p >= 1.0 else 1.0 - math.pow(2.0, -10.0 * p)


def ease_in_out_cubic(p: float) -> float:
    """Smooth symmetric acceleration/deceleration."""
    p = clamp01(p)
    if p < 0.5:
        return 4.0 * p * p * p
    return 1.0 - math.pow(-2.0 * p + 2.0, 3) / 2.0


def spring(p: float, damping: float = 6.0, frequency: float = 2.2) -> float:
    """Damped spring settling on 1.0 (may overshoot on the way).

    Args:
        p: Normalized progress 0..1.
        damping: Exponential decay rate — higher settles faster.
        frequency: Number of half-oscillations across the animation.
    """
    p = clamp01(p)
    if p >= 1.0:
        return 1.0
    envelope = math.exp(-damping * p)
    return 1.0 - envelope * math.cos(frequency * math.pi * p)


# ── Animation primitives ─────────────────────────────────────────────


def pop_in(t: float, start: float, dur: float = 0.38) -> Tuple[float, float]:
    """Pop entrance: scale 0 -> 1.08 -> 1.0 with a fast fade-in.

    Returns:
        (scale, alpha) with alpha in 0..1.
    """
    if t < start:
        return 0.0, 0.0
    p = clamp01((t - start) / dur)
    alpha = clamp01(p / 0.4)
    if p < 0.62:
        scale = 1.08 * ease_out_expo(p / 0.62)
    else:
        scale = 1.08 - 0.08 * ease_in_out_cubic((p - 0.62) / 0.38)
    return scale, alpha


def slide_up(t: float, start: float, dur: float = 0.45, dist: float = 60.0) -> float:
    """Vertical entrance offset: returns ``dist`` before start, easing to 0."""
    if t < start:
        return dist
    p = clamp01((t - start) / dur)
    return dist * (1.0 - ease_out_expo(p))


def fade(t: float, start: float, dur: float = 0.3) -> float:
    """Linear-eased fade-in 0..1."""
    if t < start:
        return 0.0
    return ease_in_out_cubic(clamp01((t - start) / dur))


def fade_out(t: float, end: float, dur: float = 0.3) -> float:
    """Fade-out multiplier: 1.0 until ``end - dur``, easing to 0.0 at ``end``."""
    if t >= end:
        return 0.0
    if t <= end - dur:
        return 1.0
    return 1.0 - ease_in_out_cubic((t - (end - dur)) / dur)


def stagger(index: int, delay: float = 0.07) -> float:
    """Start-time offset for the ``index``-th element of a staggered reveal."""
    return max(0, index) * delay


def pulse(t: float, start: float, dur: float = 0.16,
          lo: float = 1.0, hi: float = 1.10) -> float:
    """Karaoke pulse: scale ramps ``lo -> hi`` with overshoot, then holds ``hi``."""
    if t < start:
        return lo
    p = clamp01((t - start) / dur)
    return lo + (hi - lo) * ease_out_back(p)

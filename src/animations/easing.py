"""
Easing functions for smooth animations.

Provides mathematical easing curves for TikTok-style pop animations,
spring physics, bounce effects, and karaoke word highlighting.
"""

import math
from typing import Tuple


# ============== CORE EASING FUNCTIONS ==============

def ease_out_back(t: float) -> float:
    """Ease out with slight overshoot - great for pop-in effects."""
    c = 1.70158
    return 1 + (c + 1) * pow(t - 1, 3) + c * pow(t - 1, 2)


def ease_out_cubic(t: float) -> float:
    """Smooth deceleration curve."""
    return 1 - pow(1 - t, 3)


def ease_out_quad(t: float) -> float:
    """Gentle deceleration curve."""
    return 1 - (1 - t) * (1 - t)


def ease_in_out_cubic(t: float) -> float:
    """Smooth acceleration then deceleration."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def ease_in_out_quad(x: float) -> float:
    """Smooth ease in-out for seamless transitions."""
    if x < 0.5:
        return 2 * x * x
    return 1 - pow(-2 * x + 2, 2) / 2


def ease_in_out_sine(x: float) -> float:
    """Very smooth sine-based ease in-out."""
    return -(math.cos(math.pi * x) - 1) / 2


def ease_out_elastic(t: float) -> float:
    """Elastic ease out for bouncy effects."""
    if t == 0 or t == 1:
        return t
    p = 0.3
    s = p / 4
    return pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / p) + 1


def ease_out_bounce(t: float) -> float:
    """Bounce ease out."""
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


# ============== SPRING PHYSICS ==============

def spring_animation(t: float, start: float, duration: float = 0.5,
                     stiffness: float = 180, damping: float = 12,
                     mass: float = 1.0) -> float:
    """
    Spring physics animation - critically damped for snappy motion.

    Args:
        t: Current time
        start: When animation begins
        duration: Animation duration
        stiffness: Spring stiffness (higher = snappier)
        damping: Damping ratio (higher = less bounce)
        mass: Mass (higher = more sluggish)

    Returns:
        Value from 0.0 to ~1.0 (may overshoot slightly)
    """
    if t < start:
        return 0.0

    elapsed = t - start
    if elapsed >= duration:
        return 1.0

    progress = elapsed / duration

    # Damped spring equation
    omega = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))

    if zeta < 1.0:
        # Under-damped (oscillates)
        omega_d = omega * math.sqrt(1 - zeta * zeta)
        envelope = math.exp(-zeta * omega * progress)
        value = 1.0 - envelope * (
            math.cos(omega_d * progress) +
            (zeta * omega / omega_d) * math.sin(omega_d * progress)
        )
    else:
        # Critically or over-damped (no oscillation)
        value = 1.0 - math.exp(-omega * progress) * (1 + omega * progress)

    return max(0.0, min(1.2, value))  # Allow slight overshoot


# ============== TIKTOK-STYLE ANIMATIONS ==============

# TikTok pop animation constants
TIKTOK_POP_DURATION = 0.18
TIKTOK_POP_START_SCALE = 0.85
TIKTOK_POP_OVERSHOOT = 1.08
TIKTOK_POP_FINAL = 1.0


def tiktok_pop_scale(t: float, start: float,
                     duration: float = TIKTOK_POP_DURATION) -> float:
    """
    TikTok-style pop animation: 85% -> 108% -> 100%
    Creates a snappy, dynamic pop-in effect.
    """
    if t < start:
        return 0.0

    elapsed = t - start
    if elapsed >= duration:
        return TIKTOK_POP_FINAL

    progress = elapsed / duration

    # Phase 1: 0-50% - grow from 85% to 108%
    if progress < 0.5:
        phase_progress = progress / 0.5
        eased = ease_out_cubic(phase_progress)
        return TIKTOK_POP_START_SCALE + (TIKTOK_POP_OVERSHOOT - TIKTOK_POP_START_SCALE) * eased

    # Phase 2: 50-100% - settle from 108% to 100%
    else:
        phase_progress = (progress - 0.5) / 0.5
        eased = ease_out_cubic(phase_progress)
        return TIKTOK_POP_OVERSHOOT - (TIKTOK_POP_OVERSHOOT - TIKTOK_POP_FINAL) * eased


# ============== KARAOKE / HIGHLIGHT ANIMATIONS ==============

# Word highlight constants
WORD_HIGHLIGHT_ACTIVE = 1.0
WORD_HIGHLIGHT_PREVIOUS = 0.50
WORD_HIGHLIGHT_UPCOMING = 0.0

# Word transition timing
WORD_FADE_IN = 0.06
WORD_FADE_OUT = 0.20


def word_highlight_alpha(t: float, word_start: float, word_end: float,
                         is_current: bool = False, is_previous: bool = False) -> float:
    """
    Get alpha multiplier for karaoke-style word highlighting.
    Current word: full brightness
    Previous words: dimmed
    Upcoming words: hidden until their time
    """
    if t < word_start:
        return WORD_HIGHLIGHT_UPCOMING

    if is_current or (word_start <= t <= word_end):
        return WORD_HIGHLIGHT_ACTIVE

    if is_previous or t > word_end:
        return WORD_HIGHLIGHT_PREVIOUS

    return WORD_HIGHLIGHT_ACTIVE


# ============== BOUNCE / EMPHASIS ANIMATIONS ==============

BOUNCE_AMPLITUDE = 6
BOUNCE_FREQUENCY = 10
BOUNCE_DURATION = 0.30


def bounce_offset(t: float, start: float,
                  duration: float = BOUNCE_DURATION) -> Tuple[int, int]:
    """
    Calculate bounce/shake offset for emphasis animation.
    Returns (x_offset, y_offset) in pixels.
    """
    if t < start:
        return (0, 0)

    elapsed = t - start
    if elapsed >= duration:
        return (0, 0)

    # Decaying oscillation
    progress = elapsed / duration
    decay = 1.0 - progress

    oscillation = math.sin(elapsed * BOUNCE_FREQUENCY * 2 * math.pi)

    x_offset = int(BOUNCE_AMPLITUDE * oscillation * decay * 0.3)
    y_offset = int(BOUNCE_AMPLITUDE * abs(oscillation) * decay)

    return (x_offset, -y_offset)  # Negative Y = upward bounce


# ============== UTILITY ANIMATION FUNCTIONS ==============

def pulse_scale(t: float, start: float, duration: float = 0.6) -> float:
    """Pulsing scale effect (1.0 -> 1.08 -> 1.0) for correct answer."""
    if t < start:
        return 1.0
    elapsed = t - start
    cycle = elapsed % duration
    progress = cycle / duration
    return 1.0 + 0.08 * math.sin(progress * math.pi * 2)


def glow_intensity(t: float, start: float) -> float:
    """Glowing intensity that pulses."""
    if t < start:
        return 0.0
    elapsed = t - start
    if elapsed < 0.3:
        return elapsed / 0.3
    return 0.7 + 0.3 * math.sin((elapsed - 0.3) * 4)


def get_alpha(t: float, start: float, fade_duration: float = 0.2) -> int:
    """Get alpha for fade-in effect."""
    if t < start:
        return 0
    elapsed = t - start
    if elapsed >= fade_duration:
        return 255
    return int(255 * ease_out_cubic(elapsed / fade_duration))


def get_scale(t: float, start: float, duration: float = 0.2) -> float:
    """Get scale for pop-in effect."""
    if t < start:
        return 0
    elapsed = t - start
    if elapsed >= duration:
        return 1.0
    progress = elapsed / duration
    return ease_out_back(progress)

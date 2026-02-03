"""
Easing functions for smooth animations.

Implements Disney's 12 Principles of Animation for professional motion:
- Anticipation: Prepare viewers for action
- Follow-through: Objects continue past their destination
- Squash/Stretch: Organic deformation during motion
- Slow in/Slow out: Natural acceleration/deceleration

Provides mathematical easing curves for TikTok-style pop animations,
spring physics, bounce effects, and karaoke word highlighting.
"""

import math
from typing import Tuple, Dict


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


# ============== DISNEY'S 12 PRINCIPLES ==============

def anticipation_scale(t: float, start: float, anticipation_duration: float = 0.08,
                       action_duration: float = 0.15) -> float:
    """
    Disney Principle: Anticipation

    Small scale-down before the main pop-up action.
    Creates a "wind-up" effect that makes motion feel intentional.

    Timeline: [anticipation: shrink to 0.92] -> [action: pop to 1.08 -> settle to 1.0]
    """
    if t < start:
        return 1.0

    elapsed = t - start
    total_duration = anticipation_duration + action_duration

    if elapsed >= total_duration:
        return 1.0

    # Phase 1: Anticipation - slight shrink (wind-up)
    if elapsed < anticipation_duration:
        progress = elapsed / anticipation_duration
        # Ease into the shrink
        eased = ease_in_out_quad(progress)
        return 1.0 - 0.08 * eased  # Shrink to 0.92

    # Phase 2: Action - pop out with overshoot
    action_elapsed = elapsed - anticipation_duration
    progress = action_elapsed / action_duration

    # From 0.92 -> 1.10 -> 1.0
    if progress < 0.5:
        phase = progress / 0.5
        eased = ease_out_cubic(phase)
        return 0.92 + (1.10 - 0.92) * eased
    else:
        phase = (progress - 0.5) / 0.5
        eased = ease_out_cubic(phase)
        return 1.10 - (1.10 - 1.0) * eased


def follow_through_offset(t: float, start: float, duration: float = 0.4,
                          amplitude: float = 8.0) -> Tuple[float, float]:
    """
    Disney Principle: Follow-Through and Overlapping Action

    After main motion, elements overshoot and settle back.
    Creates a natural, organic feel to movement.

    Returns (x_offset, y_offset) for secondary motion.
    """
    if t < start:
        return (0.0, 0.0)

    elapsed = t - start
    if elapsed >= duration:
        return (0.0, 0.0)

    progress = elapsed / duration

    # Damped oscillation for natural settle
    decay = math.exp(-4.0 * progress)
    oscillation = math.sin(progress * math.pi * 3)  # ~1.5 oscillations

    # Y has more follow-through (gravity effect)
    y_offset = amplitude * decay * oscillation
    # X has subtle secondary motion
    x_offset = amplitude * 0.3 * decay * math.cos(progress * math.pi * 2)

    return (x_offset, y_offset)


def squash_stretch(t: float, start: float, duration: float = 0.2,
                   squash_ratio: float = 0.85) -> Tuple[float, float]:
    """
    Disney Principle: Squash and Stretch

    Objects deform during motion to convey weight and flexibility.
    Preserves volume: if width increases, height decreases.

    Returns (scale_x, scale_y) where scale_x * scale_y ≈ 1.0
    """
    if t < start:
        return (1.0, 1.0)

    elapsed = t - start
    if elapsed >= duration:
        return (1.0, 1.0)

    progress = elapsed / duration

    # Impact phase (first 30%) - squash
    if progress < 0.3:
        phase = progress / 0.3
        eased = ease_out_quad(phase)
        # Squash: wider and shorter
        scale_y = 1.0 - (1.0 - squash_ratio) * eased
        scale_x = 1.0 / scale_y  # Preserve volume
        return (scale_x, scale_y)

    # Recovery phase (70%) - stretch and settle
    phase = (progress - 0.3) / 0.7
    eased = ease_out_elastic(phase) if phase > 0.1 else ease_out_quad(phase * 10)

    # Gradually return to 1.0
    scale_y = squash_ratio + (1.0 - squash_ratio) * min(1.0, eased)
    scale_x = 1.0 / scale_y if scale_y > 0.5 else 1.0

    return (min(1.2, scale_x), max(0.8, scale_y))


# ============== ADVANCED SPRING PHYSICS ==============

def spring_with_anticipation(t: float, start: float,
                             anticipation: float = 0.06,
                             spring_duration: float = 0.35,
                             tension: float = 200,
                             friction: float = 15) -> float:
    """
    Advanced spring animation with anticipation phase.

    Combines Disney's anticipation principle with physics-based spring.
    Used by React Spring, Framer Motion for natural UI motion.

    Args:
        t: Current time
        start: Animation start time
        anticipation: Duration of wind-up phase
        spring_duration: Duration of spring motion
        tension: Spring tension (higher = snappier)
        friction: Friction coefficient (higher = less bounce)
    """
    if t < start:
        return 0.0

    elapsed = t - start
    total = anticipation + spring_duration

    if elapsed >= total:
        return 1.0

    # Phase 1: Anticipation - slight pullback
    if elapsed < anticipation:
        progress = elapsed / anticipation
        return -0.05 * ease_in_out_sine(progress)  # Pull back to -0.05

    # Phase 2: Spring release
    spring_elapsed = elapsed - anticipation
    progress = spring_elapsed / spring_duration

    # Critically damped spring equation
    omega = math.sqrt(tension)
    zeta = friction / (2 * omega)

    if zeta < 1.0:
        # Under-damped: oscillates
        omega_d = omega * math.sqrt(1 - zeta * zeta)
        t_scaled = progress * 5  # Scale time for animation feel
        envelope = math.exp(-zeta * omega * t_scaled / 10)
        value = 1.0 - envelope * (
            math.cos(omega_d * t_scaled / 10) +
            (zeta / math.sqrt(1 - zeta * zeta)) * math.sin(omega_d * t_scaled / 10)
        )
    else:
        # Over-damped: no oscillation
        value = 1.0 - math.exp(-progress * 5) * (1 + progress * 5)

    # Blend from anticipation state (-0.05) to spring value
    return -0.05 + (value + 0.05) * min(1.0, progress * 2)


# ============== PROFESSIONAL TIKTOK ANIMATIONS ==============

def tiktok_viral_pop(t: float, start: float) -> Dict[str, float]:
    """
    Full TikTok viral-style animation state.

    Returns complete animation state including:
    - scale: Size multiplier
    - alpha: Opacity (0-255)
    - rotation: Slight rotation for organic feel
    - glow: Glow intensity

    Based on analysis of top-performing TikTok videos.
    """
    if t < start:
        return {'scale': 0.0, 'alpha': 0, 'rotation': 0.0, 'glow': 0.0}

    elapsed = t - start

    # Phase timing (total ~400ms for full effect)
    ANTICIPATION = 0.05
    POP = 0.12
    SETTLE = 0.15
    GLOW_IN = 0.08

    state = {'scale': 1.0, 'alpha': 255, 'rotation': 0.0, 'glow': 1.0}

    # Scale animation
    if elapsed < ANTICIPATION:
        # Anticipation: slight shrink
        progress = elapsed / ANTICIPATION
        state['scale'] = 1.0 - 0.1 * ease_in_out_sine(progress)
        state['alpha'] = int(255 * progress)
    elif elapsed < ANTICIPATION + POP:
        # Pop: explosive growth
        progress = (elapsed - ANTICIPATION) / POP
        eased = ease_out_back(progress)
        state['scale'] = 0.9 + 0.2 * eased  # 0.9 -> 1.1
    elif elapsed < ANTICIPATION + POP + SETTLE:
        # Settle: ease back to 1.0
        progress = (elapsed - ANTICIPATION - POP) / SETTLE
        eased = ease_out_cubic(progress)
        state['scale'] = 1.1 - 0.1 * eased  # 1.1 -> 1.0

    # Subtle rotation for organic feel
    if elapsed < 0.3:
        state['rotation'] = math.sin(elapsed * 20) * 2 * (1 - elapsed / 0.3)

    # Glow pulses in
    if elapsed < GLOW_IN:
        state['glow'] = ease_out_cubic(elapsed / GLOW_IN)
    elif elapsed < 0.5:
        # Subtle pulse
        state['glow'] = 0.85 + 0.15 * math.sin((elapsed - GLOW_IN) * 8)

    return state


def word_emphasis_animation(t: float, word_start: float, word_end: float,
                            is_teaching_word: bool = False) -> Dict[str, float]:
    """
    Professional word emphasis animation for karaoke subtitles.

    Returns animation state for a single word:
    - scale: Size multiplier
    - alpha: Opacity 0-255
    - y_offset: Vertical bounce
    - brightness: Color brightness multiplier
    - glow_intensity: Glow effect strength
    """
    # Anticipation: Start highlighting 80ms BEFORE word audio
    ANTICIPATION = 0.08
    anticipated_start = word_start - ANTICIPATION

    state = {
        'scale': 1.0,
        'alpha': 0,
        'y_offset': 0.0,
        'brightness': 0.6,
        'glow_intensity': 0.0
    }

    if t < anticipated_start:
        return state

    # Calculate phases
    is_anticipating = anticipated_start <= t < word_start
    is_active = word_start <= t <= word_end
    is_past = t > word_end

    if is_anticipating:
        # Building up - fade in with slight scale
        progress = (t - anticipated_start) / ANTICIPATION
        eased = ease_out_cubic(progress)

        state['alpha'] = int(200 * eased)
        state['scale'] = 0.95 + 0.05 * eased
        state['brightness'] = 0.7 + 0.2 * eased
        state['y_offset'] = -3 * (1 - eased)  # Slight rise

    elif is_active:
        # Full emphasis
        duration = word_end - word_start
        progress = (t - word_start) / max(0.01, duration)

        state['alpha'] = 255
        state['brightness'] = 1.0

        # Pop at start, then subtle pulse
        if progress < 0.3:
            pop = ease_out_back(progress / 0.3)
            state['scale'] = 1.0 + 0.08 * pop
            state['y_offset'] = -5 * pop * (1 - progress / 0.3)
        else:
            # Subtle breathing effect
            breath = math.sin((progress - 0.3) * math.pi * 2)
            state['scale'] = 1.0 + 0.02 * breath

        # Teaching words get glow
        if is_teaching_word:
            state['glow_intensity'] = 0.8 + 0.2 * math.sin(progress * math.pi * 4)

    elif is_past:
        # Fade to dimmed state
        fade_duration = 0.15
        fade_progress = min(1.0, (t - word_end) / fade_duration)
        eased = ease_out_cubic(fade_progress)

        state['alpha'] = int(255 - 100 * eased)  # Fade to 155
        state['brightness'] = 1.0 - 0.4 * eased  # Dim to 0.6
        state['scale'] = 1.0
        state['glow_intensity'] = (1 - eased) * 0.3 if is_teaching_word else 0

    return state


# ============== BEAT-SYNC ANIMATIONS ==============

def beat_pulse(t: float, bpm: float = 120, intensity: float = 0.05) -> float:
    """
    Pulse animation synced to music beat.

    Args:
        t: Current time in seconds
        bpm: Beats per minute
        intensity: Pulse strength (0.05 = 5% scale change)

    Returns scale multiplier (e.g., 1.0 to 1.05)
    """
    beats_per_second = bpm / 60.0
    beat_progress = (t * beats_per_second) % 1.0

    # Sharp attack, smooth decay (like a kick drum)
    if beat_progress < 0.1:
        # Attack
        return 1.0 + intensity * ease_out_cubic(beat_progress / 0.1)
    else:
        # Decay
        decay_progress = (beat_progress - 0.1) / 0.9
        return 1.0 + intensity * (1 - ease_out_cubic(decay_progress))


def wave_offset(t: float, index: int, wave_speed: float = 2.0,
                amplitude: float = 5.0) -> float:
    """
    Wave animation for sequential elements (like words in a line).

    Creates a "wave" effect where each element moves slightly
    offset from its neighbors.

    Args:
        t: Current time
        index: Element index (0, 1, 2, ...)
        wave_speed: How fast the wave moves
        amplitude: Maximum offset in pixels
    """
    phase = t * wave_speed - index * 0.3
    return amplitude * math.sin(phase * math.pi)

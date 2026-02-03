"""
Animation styles for CapCut-inspired text effects.

Provides three distinct animation style classes:
- CleanPopStyle: Professional, subtle scale-up with dimming
- EnergeticStyle: High-energy TikTok slam-in with shake and glow
- KaraokeStyle: Sing-along with color sweep and progress underline

Each style produces per-word and per-group transform dictionaries
that can be consumed by the rendering pipeline.
"""

import math
import random
from typing import Dict, List, Optional

from .easing import (
    ease_out_back,
    ease_out_cubic,
    ease_out_quad,
    ease_out_bounce,
    ease_out_elastic,
    ease_in_out_sine,
    ease_in_out_cubic,
    spring_animation,
)


# ============== BASE CLASS ==============

class AnimationStyle:
    """Base class for animation styles."""

    name: str = "base"

    def get_word_transform(
        self,
        word_index: int,
        current_time: float,
        word_start: float,
        word_end: float,
        group_words: List[Dict],
    ) -> Dict:
        """
        Calculate transform for a single word.

        Returns:
            dict with keys: x_offset, y_offset, scale, alpha, rotation,
                            color, glow_radius, extra_effects
        """
        return {
            "x_offset": 0,
            "y_offset": 0,
            "scale": 1.0,
            "alpha": 255,
            "rotation": 0.0,
            "color": (255, 255, 255),
            "glow_radius": 0,
            "extra_effects": {},
        }

    def get_group_transform(
        self,
        current_time: float,
        group_start: float,
        group_end: float,
    ) -> Dict:
        """
        Calculate group-level transform (applied to the whole phrase).

        Returns:
            dict with keys: shake_x, shake_y, fade_alpha, bg_dim, extra_effects
        """
        return {
            "shake_x": 0,
            "shake_y": 0,
            "fade_alpha": 255,
            "bg_dim": 0.0,
            "extra_effects": {},
        }


# ============== STYLE 1: CLEAN POP ==============

class CleanPopStyle(AnimationStyle):
    """
    Professional, clean animation style.

    Words appear with a smooth scale-up: 0% -> 105% -> 100% (ease-out-back).
    Current word is bold white/yellow with a subtle drop shadow.
    Previous words dim to 80% opacity.
    Groups crossfade smoothly.
    """

    name = "clean_pop"

    POP_DURATION = 0.15          # 150ms per word
    OVERSHOOT = 1.05
    ACTIVE_COLOR = (255, 255, 255)
    ACTIVE_HIGHLIGHT = (255, 235, 120)  # Warm yellow-white
    DIMMED_ALPHA_RATIO = 0.80
    SHADOW_OFFSET = 3
    CROSSFADE_DURATION = 0.20    # Group crossfade

    def get_word_transform(
        self,
        word_index: int,
        current_time: float,
        word_start: float,
        word_end: float,
        group_words: List[Dict],
    ) -> Dict:
        t = current_time
        is_current = word_start <= t <= word_end
        is_future = t < word_start
        is_past = t > word_end

        # --- Scale ---
        if is_future:
            scale = 0.0
            alpha = 0
        elif t < word_start + self.POP_DURATION:
            # Pop-in phase
            progress = (t - word_start) / self.POP_DURATION
            eased = ease_out_back(progress)
            # 0 -> overshoot -> 1.0 (ease_out_back naturally overshoots)
            scale = eased * self.OVERSHOOT
            # Clamp the settle: after the overshoot, converge to 1.0
            if scale > self.OVERSHOOT:
                scale = self.OVERSHOOT
            alpha = int(255 * min(1.0, progress * 2.0))
        elif is_current:
            scale = 1.0
            alpha = 255
        else:
            # Past word - settled
            scale = 1.0
            alpha = int(255 * self.DIMMED_ALPHA_RATIO)

        # --- Color ---
        if is_current:
            color = self.ACTIVE_HIGHLIGHT
        elif is_past:
            color = self.ACTIVE_COLOR
        else:
            color = self.ACTIVE_COLOR

        # --- Drop shadow as extra effect ---
        extra = {}
        if is_current:
            extra["drop_shadow"] = {
                "offset_x": self.SHADOW_OFFSET,
                "offset_y": self.SHADOW_OFFSET,
                "color": (0, 0, 0, 100),
            }

        return {
            "x_offset": 0,
            "y_offset": 0,
            "scale": scale,
            "alpha": alpha,
            "rotation": 0.0,
            "color": color,
            "glow_radius": 0,
            "extra_effects": extra,
        }

    def get_group_transform(
        self,
        current_time: float,
        group_start: float,
        group_end: float,
    ) -> Dict:
        t = current_time

        # Fade in
        if t < group_start:
            fade = 0
        elif t < group_start + self.CROSSFADE_DURATION:
            progress = (t - group_start) / self.CROSSFADE_DURATION
            fade = int(255 * ease_out_cubic(progress))
        # Fade out
        elif t > group_end:
            elapsed = t - group_end
            progress = min(1.0, elapsed / self.CROSSFADE_DURATION)
            fade = int(255 * (1.0 - ease_out_cubic(progress)))
        else:
            fade = 255

        return {
            "shake_x": 0,
            "shake_y": 0,
            "fade_alpha": fade,
            "bg_dim": 0.0,
            "extra_effects": {},
        }


# ============== STYLE 2: ENERGETIC ==============

class EnergeticStyle(AnimationStyle):
    """
    High-energy TikTok style.

    Words SLAM in from random directions with rotation and overshoot bounce.
    Current word has bright color + glow + slight shake.
    Screen shake on word impact (2-3px).
    Words exit with quick shrink + fade.
    """

    name = "energetic"

    SLAM_DURATION = 0.20         # 200ms slam-in
    EXIT_DURATION = 0.12         # Quick exit
    SHAKE_PIXELS = 3
    SHAKE_DECAY = 0.15           # Shake decays over 150ms
    GLOW_RADIUS_ACTIVE = 18
    ENTRY_DISTANCE = 250         # Pixels to travel from off-screen
    MAX_ROTATION = 8.0           # Degrees

    # Vibrant colors that cycle per word
    COLORS = [
        (255, 80, 80),    # Red
        (80, 255, 120),   # Green
        (80, 200, 255),   # Cyan
        (255, 220, 60),   # Yellow
        (255, 130, 255),  # Pink
        (255, 160, 40),   # Orange
    ]

    DIMMED_COLOR = (200, 200, 200)

    def __init__(self):
        # Pre-generate random directions per word index (seeded for consistency)
        self._rng = random.Random(42)
        # Cache: word_index -> (direction_x, direction_y, rotation_sign)
        self._directions = {}

    def _get_direction(self, word_index: int):
        if word_index not in self._directions:
            rng = random.Random(42 + word_index)
            choice = rng.choice(["left", "right", "top"])
            if choice == "left":
                dx, dy = -1, 0
            elif choice == "right":
                dx, dy = 1, 0
            else:
                dx, dy = 0, -1
            rot_sign = rng.choice([-1, 1])
            self._directions[word_index] = (dx, dy, rot_sign)
        return self._directions[word_index]

    def get_word_transform(
        self,
        word_index: int,
        current_time: float,
        word_start: float,
        word_end: float,
        group_words: List[Dict],
    ) -> Dict:
        t = current_time
        is_current = word_start <= t <= word_end
        is_future = t < word_start
        is_past = t > word_end

        dir_x, dir_y, rot_sign = self._get_direction(word_index)
        color_idx = word_index % len(self.COLORS)

        # --- Entry animation ---
        if is_future:
            return {
                "x_offset": dir_x * self.ENTRY_DISTANCE,
                "y_offset": dir_y * self.ENTRY_DISTANCE,
                "scale": 0.0,
                "alpha": 0,
                "rotation": rot_sign * self.MAX_ROTATION,
                "color": self.COLORS[color_idx],
                "glow_radius": 0,
                "extra_effects": {},
            }

        slam_elapsed = t - word_start

        if slam_elapsed < self.SLAM_DURATION:
            # Slam-in with overshoot bounce
            progress = slam_elapsed / self.SLAM_DURATION
            eased = ease_out_bounce(progress)

            x_off = int(dir_x * self.ENTRY_DISTANCE * (1.0 - eased))
            y_off = int(dir_y * self.ENTRY_DISTANCE * (1.0 - eased))

            # Scale overshoots then settles
            scale_eased = ease_out_elastic(progress)
            scale = max(0.0, scale_eased)

            rotation = rot_sign * self.MAX_ROTATION * (1.0 - eased)
            alpha = int(255 * min(1.0, progress * 3.0))

            return {
                "x_offset": x_off,
                "y_offset": y_off,
                "scale": scale,
                "alpha": alpha,
                "rotation": rotation,
                "color": self.COLORS[color_idx],
                "glow_radius": int(self.GLOW_RADIUS_ACTIVE * progress),
                "extra_effects": {},
            }

        # --- Active word: subtle shake ---
        if is_current:
            # Continuous micro-shake
            shake_t = (t - word_start) * 25.0
            shake_x = int(1.5 * math.sin(shake_t))
            shake_y = int(1.5 * math.cos(shake_t * 1.3))

            return {
                "x_offset": shake_x,
                "y_offset": shake_y,
                "scale": 1.0,
                "alpha": 255,
                "rotation": 0.0,
                "color": self.COLORS[color_idx],
                "glow_radius": self.GLOW_RADIUS_ACTIVE,
                "extra_effects": {"glow_pulse": True},
            }

        # --- Exit: quick shrink + fade ---
        exit_elapsed = t - word_end
        if exit_elapsed < self.EXIT_DURATION:
            progress = exit_elapsed / self.EXIT_DURATION
            eased = ease_out_cubic(progress)
            scale = 1.0 - 0.3 * eased
            alpha = int(255 * (1.0 - eased * 0.6))

            return {
                "x_offset": 0,
                "y_offset": 0,
                "scale": scale,
                "alpha": alpha,
                "rotation": 0.0,
                "color": self.DIMMED_COLOR,
                "glow_radius": 0,
                "extra_effects": {},
            }

        # Settled past word
        return {
            "x_offset": 0,
            "y_offset": 0,
            "scale": 0.7,
            "alpha": int(255 * 0.5),
            "rotation": 0.0,
            "color": self.DIMMED_COLOR,
            "glow_radius": 0,
            "extra_effects": {},
        }

    def get_group_transform(
        self,
        current_time: float,
        group_start: float,
        group_end: float,
    ) -> Dict:
        t = current_time

        # Screen shake on group entry
        shake_x = 0
        shake_y = 0
        if group_start <= t < group_start + self.SHAKE_DECAY:
            progress = (t - group_start) / self.SHAKE_DECAY
            decay = 1.0 - ease_out_cubic(progress)
            shake_x = int(self.SHAKE_PIXELS * math.sin(progress * 30) * decay)
            shake_y = int(self.SHAKE_PIXELS * math.cos(progress * 25) * decay)

        # Fade
        if t < group_start:
            fade = 0
        elif t > group_end + 0.15:
            fade = 0
        elif t > group_end:
            progress = (t - group_end) / 0.15
            fade = int(255 * (1.0 - ease_out_cubic(progress)))
        else:
            fade = 255

        return {
            "shake_x": shake_x,
            "shake_y": shake_y,
            "fade_alpha": fade,
            "bg_dim": 0.0,
            "extra_effects": {"impact_flash": t < group_start + 0.05},
        }


# ============== STYLE 3: KARAOKE ==============

class KaraokeStyle(AnimationStyle):
    """
    Sing-along / karaoke style.

    All words in the group are visible from the start (dimmed).
    Current word highlights with a left-to-right color sweep.
    Highlight color: bright yellow/gold.
    Scale pulse on highlight: 100% -> 110% -> 100%.
    Progress underline grows under each word as it is spoken.
    """

    name = "karaoke"

    DIMMED_ALPHA = 140
    DIMMED_COLOR = (180, 180, 200)
    HIGHLIGHT_COLOR = (255, 220, 50)      # Gold
    HIGHLIGHT_COLOR_END = (255, 180, 30)  # Darker gold for gradient feel
    SPOKEN_COLOR = (240, 240, 240)
    PULSE_SCALE = 1.10
    PULSE_DURATION = 0.25
    UNDERLINE_HEIGHT = 6
    UNDERLINE_COLOR = (255, 220, 50, 200)

    def get_word_transform(
        self,
        word_index: int,
        current_time: float,
        word_start: float,
        word_end: float,
        group_words: List[Dict],
    ) -> Dict:
        t = current_time
        is_current = word_start <= t <= word_end
        is_future = t < word_start
        is_past = t > word_end

        # All words are visible once the group starts
        group_start = group_words[0]["start"] if group_words else word_start

        if t < group_start:
            return {
                "x_offset": 0,
                "y_offset": 0,
                "scale": 1.0,
                "alpha": 0,
                "rotation": 0.0,
                "color": self.DIMMED_COLOR,
                "glow_radius": 0,
                "extra_effects": {},
            }

        # --- Dimmed / future word ---
        if is_future:
            return {
                "x_offset": 0,
                "y_offset": 0,
                "scale": 1.0,
                "alpha": self.DIMMED_ALPHA,
                "rotation": 0.0,
                "color": self.DIMMED_COLOR,
                "glow_radius": 0,
                "extra_effects": {"underline_progress": 0.0},
            }

        # --- Current word: color sweep + pulse ---
        if is_current:
            word_duration = max(0.001, word_end - word_start)
            word_progress = (t - word_start) / word_duration  # 0..1

            # Color sweep: interpolate from dimmed to highlight left-to-right
            # word_progress represents how far the sweep has gone
            r = int(self.DIMMED_COLOR[0] + (self.HIGHLIGHT_COLOR[0] - self.DIMMED_COLOR[0]) * word_progress)
            g = int(self.DIMMED_COLOR[1] + (self.HIGHLIGHT_COLOR[1] - self.DIMMED_COLOR[1]) * word_progress)
            b = int(self.DIMMED_COLOR[2] + (self.HIGHLIGHT_COLOR[2] - self.DIMMED_COLOR[2]) * word_progress)
            color = (r, g, b)

            # Scale pulse: sin curve over the word duration
            pulse_progress = math.sin(word_progress * math.pi)
            scale = 1.0 + (self.PULSE_SCALE - 1.0) * pulse_progress

            # Alpha ramps to full
            alpha_progress = min(1.0, word_progress * 4.0)
            alpha = int(self.DIMMED_ALPHA + (255 - self.DIMMED_ALPHA) * alpha_progress)

            return {
                "x_offset": 0,
                "y_offset": 0,
                "scale": scale,
                "alpha": alpha,
                "rotation": 0.0,
                "color": color,
                "glow_radius": int(8 * word_progress),
                "extra_effects": {
                    "underline_progress": word_progress,
                    "color_sweep_progress": word_progress,
                },
            }

        # --- Past word: fully highlighted, settled ---
        return {
            "x_offset": 0,
            "y_offset": 0,
            "scale": 1.0,
            "alpha": 255,
            "rotation": 0.0,
            "color": self.SPOKEN_COLOR,
            "glow_radius": 0,
            "extra_effects": {"underline_progress": 1.0},
        }

    def get_group_transform(
        self,
        current_time: float,
        group_start: float,
        group_end: float,
    ) -> Dict:
        t = current_time
        FADE_IN = 0.20
        FADE_OUT = 0.25

        if t < group_start:
            fade = 0
        elif t < group_start + FADE_IN:
            progress = (t - group_start) / FADE_IN
            fade = int(255 * ease_in_out_sine(progress))
        elif t > group_end:
            elapsed = t - group_end
            progress = min(1.0, elapsed / FADE_OUT)
            fade = int(255 * (1.0 - ease_out_cubic(progress)))
        else:
            fade = 255

        return {
            "shake_x": 0,
            "shake_y": 0,
            "fade_alpha": fade,
            "bg_dim": 0.0,
            "extra_effects": {},
        }


# ============== REGISTRY ==============

STYLES = {
    "clean_pop": CleanPopStyle,
    "energetic": EnergeticStyle,
    "karaoke": KaraokeStyle,
}


def get_style(name: str) -> AnimationStyle:
    """
    Get an animation style instance by name.

    Args:
        name: One of 'clean_pop', 'energetic', 'karaoke'

    Returns:
        AnimationStyle instance

    Raises:
        ValueError: If the style name is unknown
    """
    cls = STYLES.get(name)
    if cls is None:
        available = ", ".join(sorted(STYLES.keys()))
        raise ValueError(
            f"Unknown animation style '{name}'. Available: {available}"
        )
    return cls()

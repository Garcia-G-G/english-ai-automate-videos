"""Background configuration and legacy gradient renderer."""

import math
import random

import numpy as np

from .constants import VIDEO_WIDTH, VIDEO_HEIGHT, GRADIENT_COLORS

# Import background system
try:
    from backgrounds import BackgroundGenerator, BACKGROUND_PRESETS, get_recommended_preset
    BACKGROUNDS_AVAILABLE = True
except ImportError:
    BACKGROUNDS_AVAILABLE = False

import logging
import os
import yaml

logger = logging.getLogger(__name__)

# Global background settings
CURRENT_BACKGROUND = {
    "preset": None,
    "type": None,
    "options": {},
    "duration": 30.0
}

# Background generator instance (lazy initialized)
_bg_generator = None

# Config file path — resolve to absolute path so it works regardless of cwd
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.yaml")


def load_config() -> dict:
    """Load configuration from config.yaml."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_default_background() -> str:
    """Get a background based on config."""
    config = load_config()
    video_config = config.get("video", {})

    mode = video_config.get("background_mode", "random")

    if mode == "random" and BACKGROUNDS_AVAILABLE:
        enabled = video_config.get("enabled_backgrounds", [])
        if enabled:
            valid = [bg for bg in enabled if bg in BACKGROUND_PRESETS]
            if valid:
                import random as _rand
                # Use SystemRandom to avoid being affected by global seed
                _sysrand = _rand.SystemRandom()
                choice = _sysrand.choice(valid)
                return choice
        mode = "fixed"

    if BACKGROUNDS_AVAILABLE:
        default_bg = video_config.get("default_background")
        if default_bg and default_bg in BACKGROUND_PRESETS:
            return default_bg
        return get_recommended_preset()
    return None


def get_background_generator():
    """Get or create the background generator instance."""
    global _bg_generator
    if _bg_generator is None and BACKGROUNDS_AVAILABLE:
        _bg_generator = BackgroundGenerator(VIDEO_WIDTH, VIDEO_HEIGHT)
    return _bg_generator


def set_background(preset: str = None, bg_type: str = None, options: dict = None, duration: float = 30.0):
    """Configure the background for video generation."""
    CURRENT_BACKGROUND["preset"] = preset
    CURRENT_BACKGROUND["type"] = bg_type
    CURRENT_BACKGROUND["options"] = options or {}
    CURRENT_BACKGROUND["duration"] = duration


def reset_background():
    """Reset to legacy gradient background."""
    CURRENT_BACKGROUND["preset"] = None
    CURRENT_BACKGROUND["type"] = None
    CURRENT_BACKGROUND["options"] = {}
    CURRENT_BACKGROUND["duration"] = 30.0


# Bokeh particle system
random.seed(42)
BOKEH_PARTICLES = []
for i in range(20):
    BOKEH_PARTICLES.append({
        'x': random.random(),
        'y': random.random(),
        'size': random.randint(40, 120),
        'speed_x': (random.random() - 0.5) * 0.012,
        'speed_y': (random.random() - 0.5) * 0.006 - 0.002,
        'alpha': random.random() * 0.2 + 0.1,
        'color_shift': random.random() * 2 * math.pi,
        'pulse_speed': random.random() * 0.4 + 0.2,
    })


def gradient(w: int, h: int, t: float) -> np.ndarray:
    """Create animated background.

    Uses cached frames for speed if available, otherwise generates on-the-fly.
    """
    # Check if custom background is configured
    if BACKGROUNDS_AVAILABLE and (CURRENT_BACKGROUND["preset"] or CURRENT_BACKGROUND["type"]):
        bg = get_background_generator()
        if bg:
            static = bg.get_static_frame()
            if static is not None:
                return static

            if bg.has_cache():
                return bg.get_cached_frame(t)

            # Auto-cache static_gradient type (same every frame)
            bg_type = CURRENT_BACKGROUND.get("type")
            if CURRENT_BACKGROUND["preset"]:
                preset_info = BACKGROUND_PRESETS.get(CURRENT_BACKGROUND["preset"], {})
                bg_type = preset_info.get("type", bg_type)

            if bg_type == "static_gradient" and CURRENT_BACKGROUND["preset"]:
                return bg.render_static_once(CURRENT_BACKGROUND["preset"])

            if CURRENT_BACKGROUND["preset"]:
                return bg.render_from_preset(
                    t,
                    CURRENT_BACKGROUND["preset"],
                    duration=CURRENT_BACKGROUND["duration"]
                )
            elif CURRENT_BACKGROUND["type"]:
                return bg.render_frame(
                    t,
                    bg_type=CURRENT_BACKGROUND["type"],
                    options=CURRENT_BACKGROUND["options"],
                    duration=CURRENT_BACKGROUND["duration"]
                )

    # ===== LEGACY VIBRANT GRADIENT =====
    idx = int(t / 5) % len(GRADIENT_COLORS)
    nxt = (idx + 1) % len(GRADIENT_COLORS)
    blend = (t % 5) / 5

    pal = GRADIENT_COLORS[idx]
    npal = GRADIENT_COLORS[nxt]

    breath = 1.0 + 0.06 * math.sin(t * 0.8)

    colors = np.array([
        [min(255, int((pal[i][j] + (npal[i][j] - pal[i][j]) * blend) * breath))
         for j in range(3)] for i in range(3)
    ], dtype=np.float32)

    y_coords = np.arange(h).reshape(-1, 1)
    x_coords = np.arange(w).reshape(1, -1)

    wave = math.sin(t * 0.3) * 0.08
    wave2 = math.sin(t * 0.5 + 1.5) * 0.04

    aurora = (
        30 * np.sin(y_coords * 0.008 + t * 0.4) +
        20 * np.sin(y_coords * 0.012 + t * 0.6 + 1.5) +
        40 * np.sin(y_coords * 0.005 + t * 0.3 + 3.0)
    ) / h * 0.08

    ratio = ((y_coords / h) + wave + wave2 * (x_coords / w) + aurora) % 1.0

    img = np.zeros((h, w, 3), dtype=np.float32)

    mask1 = ratio < 0.5
    r1 = ratio * 2
    r2 = (ratio - 0.5) * 2

    for c in range(3):
        img[:, :, c] = np.where(
            mask1,
            colors[0, c] + (colors[1, c] - colors[0, c]) * r1,
            colors[1, c] + (colors[2, c] - colors[1, c]) * r2
        )

    # Floating bokeh particles
    for particle in BOKEH_PARTICLES:
        px = (particle['x'] + particle['speed_x'] * t * 50) % 1.0
        py = (particle['y'] + particle['speed_y'] * t * 50) % 1.0

        cx = int(px * w)
        cy = int(py * h)

        pulse = 1.0 + 0.25 * math.sin(t * particle['pulse_speed'] * 2 + particle['color_shift'])
        size = int(particle['size'] * pulse)
        alpha = particle['alpha'] * (0.7 + 0.3 * math.sin(t * particle['pulse_speed'] + particle['color_shift']))

        hue = t * 0.3 + particle['color_shift']
        p_color = np.array([
            220 + 35 * math.sin(hue),
            190 + 40 * math.sin(hue + 2),
            230 + 25 * math.cos(hue)
        ], dtype=np.float32)

        y_min, y_max = max(0, cy - size), min(h, cy + size + 1)
        x_min, x_max = max(0, cx - size), min(w, cx + size + 1)

        if y_max > y_min and x_max > x_min:
            yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            mask = dist <= size

            falloff = np.exp(-2.5 * (dist / max(size, 1)) ** 2)
            blend_alpha = alpha * falloff * mask

            for c in range(3):
                img[y_min:y_max, x_min:x_max, c] = (
                    img[y_min:y_max, x_min:x_max, c] * (1 - blend_alpha) +
                    p_color[c] * blend_alpha
                )

    # Light leaks
    yy_full, xx_full = np.ogrid[0:h, 0:w]

    lx1 = w * (0.75 + 0.15 * math.sin(t * 0.2))
    ly1 = h * (0.18 + 0.08 * math.sin(t * 0.25 + 1))
    lr1 = max(w, h) * 0.55

    dist1 = np.sqrt((xx_full - lx1) ** 2 + (yy_full - ly1) ** 2)
    mask1 = dist1 < lr1
    intensity1 = 0.1 * ((1 - dist1 / lr1) ** 2) * mask1

    img[:, :, 0] += 255 * intensity1
    img[:, :, 1] += 190 * intensity1
    img[:, :, 2] += 160 * intensity1

    lx2 = w * (0.25 + 0.12 * math.sin(t * 0.18 + 2))
    ly2 = h * (0.82 + 0.06 * math.sin(t * 0.22))
    lr2 = max(w, h) * 0.45

    dist2 = np.sqrt((xx_full - lx2) ** 2 + (yy_full - ly2) ** 2)
    mask2 = dist2 < lr2
    intensity2 = 0.07 * ((1 - dist2 / lr2) ** 2) * mask2

    img[:, :, 0] += 140 * intensity2
    img[:, :, 1] += 170 * intensity2
    img[:, :, 2] += 255 * intensity2

    # Shimmer overlay
    shimmer = 8 * np.sin(y_coords * 0.02 + x_coords * 0.01 + t * 2)
    shimmer += 5 * np.sin(y_coords * 0.015 - x_coords * 0.008 + t * 1.5 + 1)

    img[:, :, 0] += shimmer
    img[:, :, 1] += shimmer * 0.9
    img[:, :, 2] += shimmer * 1.1

    return np.clip(img, 0, 255).astype(np.uint8)

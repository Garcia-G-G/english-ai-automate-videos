"""Background configuration and legacy gradient renderer."""

import math
import random

import numpy as np

from .constants import GRADIENT_COLORS

# Global background settings
CURRENT_BACKGROUND = {
    "preset": None,
    "type": None,
    "options": {},
    "duration": 30.0
}

# Clip-library background instance (lazy initialized, keyed by dir/duration/size)
_clip_bg = None
_clip_bg_key = None


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


# Bokeh particle system. Its own Random: a global random.seed(42) here reset the whole panel's
# RNG on import, so the topic draw and the outro A/B repeated the same sequence every session.
_rng = random.Random(42)
BOKEH_PARTICLES = []
for i in range(20):
    BOKEH_PARTICLES.append({
        'x': _rng.random(),
        'y': _rng.random(),
        'size': _rng.randint(40, 120),
        'speed_x': (_rng.random() - 0.5) * 0.012,
        'speed_y': (_rng.random() - 0.5) * 0.006 - 0.002,
        'alpha': _rng.random() * 0.2 + 0.1,
        'color_shift': _rng.random() * 2 * math.pi,
        'pulse_speed': _rng.random() * 0.4 + 0.2,
    })


def _get_clip_background(w: int, h: int):
    """Get or (re)create the ClipLibraryBackground for current settings."""
    global _clip_bg, _clip_bg_key
    from .clip_background import ClipLibraryBackground

    options = CURRENT_BACKGROUND.get("options") or {}
    clips_dir = options.get("dir")
    if not clips_dir:
        raise ValueError("Background type 'clips' requires options={'dir': <clips directory>}")

    # video_type is part of the key: it selects which rows the readability
    # band covers, so two types sharing a clips directory must not share a
    # cached background sized for the other one's layout.
    video_type = options.get("video_type")
    key = (clips_dir, CURRENT_BACKGROUND["duration"], w, h, video_type,
           options.get("dim"), options.get("scrim"))
    if _clip_bg is None or _clip_bg_key != key:
        if _clip_bg is not None:
            _clip_bg.close()
        _clip_bg = ClipLibraryBackground(
            clips_dir, w, h,
            duration=CURRENT_BACKGROUND["duration"],
            seed=options.get("seed"),
            # DEFAULT 0.0, not 0.35. The flat dim made dark footage black
            # and still left bright footage unreadable; the measured band
            # inside ClipLibraryBackground replaces it. A caller may still
            # pin one explicitly.
            dim=options.get("dim", 0.0),
            video_type=video_type,
            scrim=options.get("scrim"),
        )
        _clip_bg_key = key
    return _clip_bg


def before_fork() -> None:
    """Release what a forked process must not share (STEP 77 §2): an open VideoCapture's file
    descriptor and decoder would be read by every child at once. The clip library itself —
    softened copies, measured scrims — is kept, so the children inherit it instead of each
    building its own; each opens its own capture on its first frame."""
    if _clip_bg is not None:
        _clip_bg.release_captures()


def gradient(w: int, h: int, t: float) -> np.ndarray:
    """Create animated background: the clip library if set, else the legacy gradient."""
    # Clip-library background (real video clips)
    if CURRENT_BACKGROUND["type"] == "clips":
        return _get_clip_background(w, h).get_frame(t)

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

    # Folded, not wrapped (STEP 77 §3): `% 1.0` jumped from the last colour back to the first,
    # a hard diagonal seam; the fold runs 0→1→0 so the gradient stays continuous.
    ratio = 1.0 - np.abs(((y_coords / h) + wave + wave2 * (x_coords / w) + aurora) % 2.0 - 1.0)

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

"""
Text rendering with per-word color, animation, and glow effects.

Provides the TextRenderer class for drawing styled text on PIL images
with outline, glow, karaoke highlighting, and TikTok pop animations.
"""

import math
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from .easing import (
    ease_out_cubic, ease_in_out_sine, ease_out_back,
    tiktok_pop_scale, bounce_offset,
    WORD_HIGHLIGHT_ACTIVE, WORD_HIGHLIGHT_PREVIOUS,
    WORD_FADE_IN, WORD_FADE_OUT,
)


# ============== COLORS ==============
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (255, 215, 0)
COLOR_CYAN = (0, 212, 255)

ENGLISH_WORD_COLOR = (255, 215, 0)   # Yellow
SPANISH_WORD_COLOR = (0, 212, 255)   # Cyan
SPANISH_DIMMED_COLOR = (0, 170, 210) # Dimmed cyan for previous words

# ============== TYPOGRAPHY ==============
SIZE_ENGLISH_WORD = 145
SIZE_MAIN_SPANISH = 90
SIZE_TRANSLATION = 55
ENGLISH_WORD_SCALE = 1.20
OUTLINE_THICK = 12

# Glow
ENGLISH_GLOW_COLOR = (0, 220, 255, 150)
ENGLISH_GLOW_RADIUS = 14

# Animation timing
WORD_FADE_IN = 0.06
WORD_FADE_OUT = 0.20
GROUP_TRANSITION = 0.25

# Emphasis words
EMPHASIS = {
    'no', 'nunca', 'cuidado', 'error', 'ojo',
    'muy', 'siempre', 'realmente', 'verdaderamente',
    'recuerda', 'importante', 'significa', 'diferente',
    'correcta', 'correcto', 'incorrecto',
    'pero', 'sino', 'ejemplo', 'realidad',
}

# Video dimensions
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
MARGIN_X = 80
TEXT_AREA_WIDTH = VIDEO_WIDTH - (MARGIN_X * 2)

# Progress bar
BAR_HEIGHT = 10
BAR_Y = VIDEO_HEIGHT - 70
BAR_MARGIN = 40

# Font cache
_fonts = {}


def _get_font_paths():
    """Return font search paths: bundled → macOS → Linux → Windows."""
    project_root = Path(__file__).resolve().parent.parent.parent
    bundled = project_root / "assets" / "fonts" / "Inter-Bold.ttf"

    paths = [str(bundled)]

    paths += [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        os.path.expanduser("~/Library/Fonts/Inter-Bold.ttf"),
    ]

    paths += [
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]

    paths += [
        "C:\\Windows\\Fonts\\Inter-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    return paths


_font_paths = None


def font(size: int) -> ImageFont.FreeTypeFont:
    """Get or load a font at the given size."""
    global _font_paths
    if size in _fonts:
        return _fonts[size]

    if _font_paths is None:
        _font_paths = _get_font_paths()

    for p in _font_paths:
        try:
            f = ImageFont.truetype(p, size)
            _fonts[size] = f
            return f
        except Exception:
            continue

    f = ImageFont.load_default()
    _fonts[size] = f
    return f


def line_break(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    """Smart line breaking for text."""
    if not text.strip():
        return []

    dummy = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(dummy)

    bbox = draw.textbbox((0, 0), text, font=f)
    if bbox[2] - bbox[0] <= max_w:
        return [text]

    words = text.split()
    lines = []
    current = []

    for word in words:
        test = current + [word]
        bbox = draw.textbbox((0, 0), ' '.join(test), font=f)

        if bbox[2] - bbox[0] <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(' '.join(current))
            current = [word]

    if current:
        lines.append(' '.join(current))
    return lines


def draw_glow(
    img: Image.Image,
    text: str,
    x: int, y: int,
    f: ImageFont.FreeTypeFont,
    glow_color: Tuple[int, int, int],
    glow_radius: int = ENGLISH_GLOW_RADIUS,
    glow_alpha: int = 100
):
    """Draw a glow effect behind text using multiple offset copies."""
    bbox = f.getbbox(text)
    if not bbox:
        return

    for radius in range(glow_radius, 0, -2):
        alpha = int(glow_alpha * (1 - radius / glow_radius) * 0.5)
        if alpha <= 0:
            continue

        glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        for dx in range(-radius, radius + 1, max(1, radius // 2)):
            for dy in range(-radius, radius + 1, max(1, radius // 2)):
                if dx * dx + dy * dy <= radius * radius:
                    glow_draw.text(
                        (x + dx, y + dy),
                        text,
                        font=f,
                        fill=(*glow_color, alpha)
                    )

        img.paste(glow_layer, (0, 0), glow_layer)


def draw_text_solid(
    draw: ImageDraw.Draw,
    text: str, x: int, y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK
) -> Tuple[int, int]:
    """Draw text with thick solid outline."""
    if alpha <= 0:
        return 0, 0

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    out_color = (0, 0, 0, alpha)
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (1, 1), (-1, 1), (1, -1)]

    for dist in [outline, outline - 2, outline - 4]:
        if dist <= 0:
            continue
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    for dist in range(1, min(4, outline), 2):
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    draw.text((x, y), text, font=f, fill=(*color, alpha))

    return w, h


def draw_text_with_glow(
    draw: ImageDraw.Draw,
    img: Image.Image,
    text: str,
    x: int, y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple[int, int, int],
    alpha: int = 255,
    outline: int = OUTLINE_THICK,
    glow: bool = False,
    glow_color: Tuple[int, int, int] = ENGLISH_WORD_COLOR,
    glow_radius: int = ENGLISH_GLOW_RADIUS
) -> Tuple[int, int]:
    """Draw text with optional glow effect for English words."""
    if alpha <= 0:
        return (0, 0)

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    if glow:
        draw_glow(img, text, x, y, f, glow_color, glow_radius, alpha // 3)

    out_color = (0, 0, 0, alpha)
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (1, 1), (-1, 1), (1, -1)]

    for dist in [outline, outline - 2, outline - 4]:
        if dist <= 0:
            continue
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    for dist in range(1, min(4, outline), 2):
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    draw.text((x, y), text, font=f, fill=(*color, alpha))

    return (w, h)


def draw_text_centered(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK,
    max_width: int = TEXT_AREA_WIDTH
) -> int:
    """Draw centered text with line wrapping. Returns total height."""
    if alpha <= 0:
        return 0

    lines = line_break(text, f, max_width)
    line_h = int(f.size * 1.35)
    total_h = 0

    for line_text in lines:
        bbox = draw.textbbox((0, 0), line_text, font=f)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2
        draw_text_solid(draw, line_text, lx, y + total_h, f, color, alpha, outline)
        total_h += line_h

    return total_h


def draw_progress_bar(draw: ImageDraw.Draw, progress: float):
    """Draw progress bar at bottom."""
    bar_w = VIDEO_WIDTH - (BAR_MARGIN * 2)

    draw.rounded_rectangle(
        [BAR_MARGIN, BAR_Y, BAR_MARGIN + bar_w, BAR_Y + BAR_HEIGHT],
        radius=BAR_HEIGHT // 2,
        fill=(255, 255, 255, 80)
    )

    if progress > 0.01:
        fill_w = max(BAR_HEIGHT, int(bar_w * progress))
        draw.rounded_rectangle(
            [BAR_MARGIN, BAR_Y, BAR_MARGIN + fill_w, BAR_Y + BAR_HEIGHT],
            radius=BAR_HEIGHT // 2,
            fill=(100, 255, 150, 255)
        )


def get_word_animation_state(
    t: float,
    word_start: float,
    word_end: float,
    group_start: float,
    group_end: float,
    is_english: bool = False,
    is_emphasis: bool = False
) -> Dict:
    """
    Calculate complete animation state for a word at time t.
    Returns dict with scale, alpha, offset, is_active, brightness.
    """
    state = {
        'scale': 1.0,
        'alpha': 0,
        'offset_x': 0,
        'offset_y': 0,
        'is_active': False,
        'brightness': 1.0,
    }

    if t < group_start:
        return state

    is_current = word_start <= t <= word_end
    is_spoken = t > word_end

    if t >= word_start:
        state['scale'] = tiktok_pop_scale(t, word_start)
        state['alpha'] = int(255 * min(1.0, (t - word_start) / WORD_FADE_IN))

    if is_current:
        state['is_active'] = True
        state['brightness'] = WORD_HIGHLIGHT_ACTIVE
        state['alpha'] = 255

        if is_emphasis:
            bx, by = bounce_offset(t, word_start)
            state['offset_x'] = bx
            state['offset_y'] = by

    elif is_spoken:
        state['brightness'] = WORD_HIGHLIGHT_PREVIOUS
        state['alpha'] = int(255 * WORD_HIGHLIGHT_PREVIOUS)
        state['scale'] = 1.0

    if t > group_end:
        fade_progress = min(1.0, (t - group_end) / WORD_FADE_OUT)
        state['alpha'] = int(state['alpha'] * (1 - ease_out_cubic(fade_progress)))

    return state


def draw_sparkles(draw: ImageDraw.Draw, center_x: int, center_y: int,
                  t: float, start_time: float, radius: int = 150):
    """Draw sparkle/star burst particles around a point."""
    elapsed = t - start_time
    if elapsed < 0:
        return

    num_particles = 12
    particle_life = 1.2

    if elapsed > particle_life:
        return

    progress = elapsed / particle_life

    for i in range(num_particles):
        angle = (i / num_particles) * 2 * math.pi + progress * 0.5
        distance = radius * ease_out_cubic(progress)

        px = center_x + int(math.cos(angle) * distance)
        py = center_y + int(math.sin(angle) * distance)

        alpha = int(255 * (1 - progress))
        if alpha <= 0:
            continue

        if i % 3 == 0:
            size = int(12 * (1 - progress * 0.5))
            draw.polygon([
                (px, py - size), (px + size//3, py - size//3),
                (px + size, py), (px + size//3, py + size//3),
                (px, py + size), (px - size//3, py + size//3),
                (px - size, py), (px - size//3, py - size//3),
            ], fill=(255, 255, 255, alpha))
        elif i % 3 == 1:
            r = int(6 * (1 - progress * 0.5))
            draw.ellipse([px - r, py - r, px + r, py + r],
                        fill=(255, 230, 100, alpha))
        else:
            size = int(8 * (1 - progress * 0.5))
            draw.polygon([
                (px, py - size), (px + size, py),
                (px, py + size), (px - size, py)
            ], fill=(200, 255, 200, alpha))

"""Shared video utilities — font loading, text drawing, data loading, slide_in_x."""

import json
import math
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from animations.easing import ease_out_back, ease_out_cubic
from .constants import (
    VIDEO_WIDTH, OUTLINE_THICK, TEXT_AREA_WIDTH,
    SLIDE_DISTANCE, ENGLISH_GLOW_RADIUS, ENGLISH_WORD_COLOR,
    BAR_HEIGHT, BAR_Y, BAR_MARGIN,
)

# Font cache
_fonts = {}


def _get_font_paths():
    """Return font search paths: bundled → macOS → Linux → Windows."""
    # Bundled font (assets/fonts/ relative to project root)
    project_root = Path(__file__).resolve().parent.parent.parent
    bundled = project_root / "assets" / "fonts" / "Inter-Bold.ttf"

    paths = [str(bundled)]

    # macOS
    paths += [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        os.path.expanduser("~/Library/Fonts/Inter-Bold.ttf"),
    ]

    # Linux
    paths += [
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]

    # Windows
    paths += [
        "C:\\Windows\\Fonts\\Inter-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    return paths


_font_paths = None


def font(size: int) -> ImageFont.FreeTypeFont:
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


def load_data(path: str) -> dict:
    """Load JSON data file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def slide_in_x(t: float, start: float, duration: float = 0.4) -> float:
    """Get X offset for smooth slide-in from right animation with bounce."""
    if t < start:
        return SLIDE_DISTANCE
    elapsed = t - start
    if elapsed >= duration:
        return 0
    progress = elapsed / duration
    eased = ease_out_back(progress)
    return int(SLIDE_DISTANCE * (1 - min(1.0, eased)))


def line_break(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    """Smart line breaking."""
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
    """Draw a glow effect behind text using efficient stroke-based approach."""
    bbox = f.getbbox(text)
    if not bbox:
        return

    # Use a single larger stroke as glow (much faster than multiple layers)
    glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    # Draw glow as a thick semi-transparent stroke
    glow_draw.text(
        (x, y), text, font=f,
        fill=(0, 0, 0, 0),  # Transparent fill
        stroke_width=glow_radius,
        stroke_fill=(*glow_color, glow_alpha // 2)
    )

    img.paste(glow_layer, (0, 0), glow_layer)


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
    """Draw text with optional glow effect. Returns (width, height)."""
    if alpha <= 0:
        return (0, 0)

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    if glow:
        draw_glow(img, text, x, y, f, glow_color, glow_radius, alpha // 3)

    # Use native PIL stroke for outline (much faster than multi-draw)
    draw.text(
        (x, y), text, font=f,
        fill=(*color, alpha),
        stroke_width=outline,
        stroke_fill=(0, 0, 0, alpha)
    )

    return (w, h)


def draw_text_solid(
    draw: ImageDraw.Draw,
    text: str, x: int, y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK
) -> Tuple[int, int]:
    """Draw text with thick solid outline using native PIL stroke."""
    if alpha <= 0:
        return 0, 0

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    # Ensure color has alpha
    if len(color) == 3:
        fill_color = (*color, alpha)
    else:
        fill_color = (*color[:3], alpha)

    # Use native PIL stroke (much faster than multi-draw)
    draw.text(
        (x, y), text, font=f,
        fill=fill_color,
        stroke_width=outline,
        stroke_fill=(0, 0, 0, alpha)
    )

    return w, h


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

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2
        draw_text_solid(draw, line, lx, y + total_h, f, color, alpha, outline)
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


def draw_sparkles(draw: ImageDraw.Draw, center_x: int, center_y: int, t: float, start_time: float, radius: int = 150):
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


def get_word_animation_state(
    t: float,
    word_start: float,
    word_end: float,
    group_start: float,
    group_end: float,
    is_english: bool = False,
    is_emphasis: bool = False
) -> Dict:
    """Calculate complete animation state for a word at time t.

    Uses TikTok-style anticipation: word highlights slightly BEFORE audio starts.
    """
    from animations.easing import (
        tiktok_pop_scale, word_highlight_alpha, bounce_offset,
        WORD_HIGHLIGHT_ACTIVE, WORD_HIGHLIGHT_PREVIOUS,
        WORD_FADE_IN, WORD_FADE_OUT,
    )

    # Anticipation: start animation 80ms before word audio
    ANTICIPATION = 0.08
    anticipated_start = word_start - ANTICIPATION

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

    # Word becomes active slightly before audio (TikTok style)
    is_becoming_active = anticipated_start <= t < word_start
    is_current = word_start <= t <= word_end
    is_spoken = t > word_end

    if t >= anticipated_start:
        state['scale'] = tiktok_pop_scale(t, anticipated_start)
        state['alpha'] = int(255 * min(1.0, (t - anticipated_start) / WORD_FADE_IN))

    if is_becoming_active or is_current:
        state['is_active'] = True
        state['brightness'] = WORD_HIGHLIGHT_ACTIVE
        state['alpha'] = 255

        if is_emphasis and is_current:
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


def draw_gradient_rounded_rect(
    img: Image.Image,
    x1: int, y1: int, x2: int, y2: int,
    radius: int,
    color1: Tuple, color2: Tuple,
    alpha: int = 255,
    vertical: bool = True
):
    """Draw a rounded rectangle with gradient fill."""
    width = x2 - x1
    height = y2 - y1

    grad = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)

    if vertical:
        for i in range(height):
            ratio = i / height
            r = int(color1[0] + (color2[0] - color1[0]) * ratio)
            g = int(color1[1] + (color2[1] - color1[1]) * ratio)
            b = int(color1[2] + (color2[2] - color1[2]) * ratio)
            grad_draw.line([(0, i), (width, i)], fill=(r, g, b, alpha))
    else:
        for i in range(width):
            ratio = i / width
            r = int(color1[0] + (color2[0] - color1[0]) * ratio)
            g = int(color1[1] + (color2[1] - color1[1]) * ratio)
            b = int(color1[2] + (color2[2] - color1[2]) * ratio)
            grad_draw.line([(i, 0), (i, height)], fill=(r, g, b, alpha))

    mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)

    grad.putalpha(mask)
    img.paste(grad, (x1, y1), grad)

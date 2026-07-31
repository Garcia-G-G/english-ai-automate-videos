"""Shared video utilities — font loading, text drawing, data loading, shared helpers."""

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from animations.easing import ease_out_back, ease_out_cubic
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, OUTLINE_THICK, TEXT_AREA_WIDTH,
    SLIDE_DISTANCE, ENGLISH_GLOW_RADIUS, ENGLISH_WORD_COLOR,
    BAR_HEIGHT, BAR_Y, BAR_MARGIN,
)
from config.colors import DIFFICULTY_COLORS, CARD_COLORS

logger = logging.getLogger(__name__)

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


# ── Learning Routes brand faces ──────────────────────────────────────
#
# Manrope (body/UI) and Instrument Serif (headings) are the Learning Routes
# faces. NEITHER was in this repo before Step 4a — the only mention of Manrope
# anywhere was a line in _audit/ROADMAP.md, and no code referenced it. Both are
# now bundled under assets/fonts/ with their OFL licences.

_BRAND_FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
_MANROPE_VF = _BRAND_FONT_DIR / "Manrope[wght].ttf"
_INSTRUMENT_ITALIC = _BRAND_FONT_DIR / "InstrumentSerif-Italic.ttf"

_brand_fonts: dict = {}


class BrandFontMissing(RuntimeError):
    """Raised when a brand face is absent. Never falls back silently."""


def manrope(size: int, weight: str = "SemiBold") -> ImageFont.FreeTypeFont:
    """Manrope at an explicit weight.

    Manrope ships as a VARIABLE font whose default instance is **ExtraLight**
    — the thinnest weight it has. `ImageFont.truetype("Manrope[wght].ttf", n)`
    therefore returns hairline text, which is precisely wrong for a watermark
    that has to survive a bright photo. The weight is always set explicitly
    here; there is no default-instance path.

    Raises rather than substituting another face. A watermark that silently
    renders in Inter is a brand defect that looks like success.
    """
    key = ("manrope", size, weight)
    if key in _brand_fonts:
        return _brand_fonts[key]

    if not _MANROPE_VF.exists():
        raise BrandFontMissing(f"Manrope not found at {_MANROPE_VF}")

    f = ImageFont.truetype(str(_MANROPE_VF), size)
    try:
        f.set_variation_by_name(weight)
    except Exception as exc:                       # noqa: BLE001
        # Old FreeType without variable-font support would leave ExtraLight in
        # place and produce an invisible watermark. Fail loudly instead.
        raise BrandFontMissing(
            f"could not set Manrope weight {weight!r} "
            f"(FreeType {features.version('freetype2')}): {exc}"
        ) from exc

    _brand_fonts[key] = f
    return f


def instrument_serif_italic(size: int) -> ImageFont.FreeTypeFont:
    """Instrument Serif Italic — the Learning Routes heading face."""
    key = ("instrument-italic", size)
    if key in _brand_fonts:
        return _brand_fonts[key]

    if not _INSTRUMENT_ITALIC.exists():
        raise BrandFontMissing(f"Instrument Serif not found at {_INSTRUMENT_ITALIC}")

    f = ImageFont.truetype(str(_INSTRUMENT_ITALIC), size)
    _brand_fonts[key] = f
    return f


def strip_display_quotes(text: str) -> str:
    """Remove the single quotes that mark English terms, for DISPLAY only.

    The quotes are STRUCTURAL, not decorative: the generator prompt requires
    English terms to be single-quoted, and validate_and_clean_script's
    english_phrases scrape reads them back out of full_script. They must stay
    in the data and are only removed at the moment of drawing — which is why
    this lives at the draw site rather than anywhere upstream.

    Applied where the quotes distinguish nothing. It is NOT blanket: the quiz
    QUESTION keeps its quotes, because there the mark is doing real work — it
    is the use-mention distinction, and "¿Qué significa 'fabric' en inglés?"
    is correct Spanish orthography on a channel that teaches language. In the
    four options every entry is quoted, so the mark separates nothing and is
    pure visual noise.

    A precedent already existed at quiz.py:822 and true_false.py:587, applied
    to `explanation` alone; those now route through here so the behaviour is
    one function instead of scattered .replace calls.

    Only DELIMITER quotes are removed. An apostrophe between two letters is a
    contraction — "don't", "it's" — and stripping it would render "dont",
    which is a spelling error on a channel that teaches English. Same
    distinction the english_phrases scraper draws in script_generator.
    """
    if not text:
        return text
    # Mask contractions, drop the remaining quotes, restore.
    masked = re.sub(r"(?<=[A-Za-z])['\u2018\u2019](?=[A-Za-z])", "\x00", text)
    stripped = masked.replace("'", "").replace("\u2018", "").replace("\u2019", "")
    return stripped.replace("\x00", "'")


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


def fit_text_font(text: str, max_font: int, min_font: int, max_width: int, max_height: int = None) -> tuple:
    """Find largest font that fits text within bounds.
    Returns (font_obj, actual_size, lines, total_height)."""
    for size in range(max_font, min_font - 1, -2):
        f = font(size)
        lines = line_break(text, f, max_width)
        line_h = int(size * 1.35)
        total_h = len(lines) * line_h
        if max_height is None or total_h <= max_height:
            return f, size, lines, total_h
    f = font(min_font)
    lines = line_break(text, f, max_width)
    total_h = len(lines) * int(min_font * 1.35)
    return f, min_font, lines, total_h


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


def draw_glass_button(
    img: Image.Image,
    draw: ImageDraw.Draw,
    x: int, y: int,
    w: int, h: int,
    text: str,
    text_font: ImageFont.FreeTypeFont,
    alpha: int = 255,
    state: str = 'normal',
    glow_amount: float = 0.0,
):
    """Draw a glassmorphism-style button with optional glow/sparkle states.

    Args:
        state: 'normal', 'correct', or 'dimmed'
        glow_amount: 0.0–1.0 for glow intensity on correct state
    """
    radius = 22

    # Drop shadow
    shadow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_alpha = int(alpha * 0.35)
    shadow_draw.rounded_rectangle(
        [x + 2, y + 4, x + w + 2, y + h + 4],
        radius=radius, fill=(0, 0, 0, shadow_alpha),
    )
    img.paste(shadow_layer, (0, 0), shadow_layer)

    # Glow halo for correct state
    if state == 'correct' and glow_amount > 0:
        glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        ga = int(50 * glow_amount * (alpha / 255))
        for spread in (12, 8, 4):
            glow_draw.rounded_rectangle(
                [x - spread, y - spread, x + w + spread, y + h + spread],
                radius=radius + spread, fill=(34, 197, 94, ga),
            )
        img.paste(glow_layer, (0, 0), glow_layer)

    # Button fill
    if state == 'correct':
        fill = (34, 197, 94, int(alpha * 0.86))
    elif state == 'dimmed':
        fill = (30, 30, 60, int(alpha * 0.30))
    else:
        fill = (30, 30, 60, int(alpha * 0.70))

    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill)

    # Border (glassmorphism white edge)
    border_alpha = int(alpha * (0.15 if state == 'dimmed' else 0.45))
    draw.rounded_rectangle(
        [x, y, x + w, y + h], radius=radius,
        outline=(255, 255, 255, border_alpha), width=2,
    )

    # Top highlight (1px white line near top edge)
    hl_alpha = int(alpha * (0.05 if state == 'dimmed' else 0.15))
    draw.line(
        [(x + radius, y + 2), (x + w - radius, y + 2)],
        fill=(255, 255, 255, hl_alpha), width=1,
    )

    # Text
    text_alpha = alpha if state != 'dimmed' else int(alpha * 0.4)
    bbox = draw.textbbox((0, 0), text, font=text_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2 - 2

    # Text shadow
    if state != 'dimmed':
        draw.text((tx + 1, ty + 1), text, font=text_font,
                  fill=(0, 0, 0, int(text_alpha * 0.5)),
                  stroke_width=2, stroke_fill=(0, 0, 0, int(text_alpha * 0.3)))

    # Text fill
    if state == 'correct':
        text_color = (255, 255, 255, text_alpha)
    elif state == 'dimmed':
        text_color = (180, 180, 200, text_alpha)
    else:
        text_color = (255, 255, 255, text_alpha)

    draw.text((tx, ty), text, font=text_font, fill=text_color,
              stroke_width=3, stroke_fill=(0, 0, 0, text_alpha))


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


# ── Shared frame helpers ─────────────────────────────────────────

def create_base_frame(t: float) -> Tuple[Image.Image, ImageDraw.Draw]:
    """Create an RGBA frame with the animated gradient background.

    Returns (frame, draw) ready for rendering.
    """
    from .backgrounds import gradient
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg).convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')
    return frame, draw


def finalize_frame(frame: Image.Image, draw: ImageDraw.Draw,
                   t: float, duration: float,
                   words: list = None) -> np.ndarray:
    """Add character, progress bar, and convert to numpy RGB array."""
    # Render animated character with lip-sync
    try:
        from .character import get_character_renderer
        char = get_character_renderer()
        if char:
            char.render(frame, t, words)
    except Exception:
        pass  # Character is optional — never block video rendering

    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    # Brand watermark, LAST so nothing can draw over it.
    #
    # Applied here rather than in each renderer because all seven call this
    # function — one site instead of seven that each have to remember. Import
    # is local to avoid a circular import (brand imports from utils).
    from .brand import draw_watermark
    draw_watermark(frame)

    return np.array(frame.convert('RGB'))


def seg_start(segment_times: Dict, seg_id: str, fallback: float = 0.0) -> float:
    """Extract segment start time from segment_times dict."""
    return segment_times.get(seg_id, {}).get('start', fallback)


def seg_end(segment_times: Dict, seg_id: str, fallback: float = 0.0) -> float:
    """Extract segment end time from segment_times dict."""
    return segment_times.get(seg_id, {}).get('end', fallback)


def log_segment_timestamps(segment_times: Dict, label: str,
                           keys: List[str]) -> None:
    """Log exact segment timestamps (debug level, first frame only)."""
    logger.debug("EXACT %s segment timestamps:", label)
    for seg_id in keys:
        if seg_id in segment_times:
            s = segment_times[seg_id]
            logger.debug("  %s: %.2fs - %.2fs", seg_id, s['start'], s['end'])


def resolve_countdown_number(
    t: float,
    segment_times: Dict,
) -> Tuple[Optional[int], float]:
    """Determine which countdown number to show and its start time.

    Uses exact segment_times when available, returns (None, 0) if no
    countdown should be displayed.

    Returns:
        (number, start_time) — number is 3/2/1 or None.
    """
    cd3 = seg_start(segment_times, 'countdown_3', 0)
    cd2 = seg_start(segment_times, 'countdown_2', 0)
    cd1 = seg_start(segment_times, 'countdown_1', 0)

    if cd3 <= 0:
        return None, 0

    if cd1 > 0 and t >= cd1:
        return 1, cd1
    if cd2 > 0 and t >= cd2:
        return 2, cd2
    if cd3 > 0 and t >= cd3:
        return 3, cd3

    return None, 0


# ── Card / badge / timer drawing helpers ────────────────────────


def draw_rounded_card(
    img: Image.Image,
    x: int, y: int,
    w: int, h: int,
    radius: int = 30,
    fill: Tuple = (255, 255, 255),
    alpha: int = 240,
    shadow: bool = True,
    shadow_offset: int = 6,
    shadow_alpha: int = 80,
):
    """Draw a solid rounded-rectangle card with optional drop shadow.

    Renders onto *img* in-place using alpha compositing.
    """
    # --- Shadow layer ---
    if shadow:
        shadow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        sd.rounded_rectangle(
            [x + shadow_offset, y + shadow_offset,
             x + w + shadow_offset, y + h + shadow_offset],
            radius=radius,
            fill=(0, 0, 0, shadow_alpha),
        )
        img.paste(shadow_layer, (0, 0), shadow_layer)

    # --- Card layer ---
    card_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_layer)
    cd.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=radius,
        fill=(*fill[:3], alpha),
    )
    img.paste(card_layer, (0, 0), card_layer)


def draw_pill_badge(
    img: Image.Image,
    draw: ImageDraw.Draw,
    text: str,
    center_x: int,
    center_y: int,
    font_size: int = 28,
    bg_color: Tuple = (76, 175, 80),
    text_color: Tuple = (255, 255, 255),
    padding_x: int = 24,
    padding_y: int = 10,
) -> Tuple[int, int]:
    """Draw a pill-shaped badge with centred text.

    Returns (pill_width, pill_height).
    """
    f = font(font_size)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pill_w = tw + padding_x * 2
    pill_h = th + padding_y * 2
    pill_radius = pill_h // 2  # fully rounded ends

    px = center_x - pill_w // 2
    py = center_y - pill_h // 2

    # Background pill on a compositing layer
    pill_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill_layer)
    pd.rounded_rectangle(
        [px, py, px + pill_w, py + pill_h],
        radius=pill_radius,
        fill=(*bg_color[:3], 255),
    )
    img.paste(pill_layer, (0, 0), pill_layer)

    # Text centred inside the pill
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 1  # nudge up for optical centering
    draw.text((tx, ty), text, font=f, fill=(*text_color[:3], 255))

    return pill_w, pill_h


def draw_circle_number(
    draw: ImageDraw.Draw,
    number: str,
    center_x: int,
    center_y: int,
    radius: int = 28,
    bg_color: Tuple = (255, 120, 130),
    text_color: Tuple = (255, 255, 255),
    font_size: int = 32,
):
    """Draw a filled circle with a character/number centred inside."""
    draw.ellipse(
        [center_x - radius, center_y - radius,
         center_x + radius, center_y + radius],
        fill=(*bg_color[:3], 255),
    )

    f = font(font_size)
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 1
    draw.text((tx, ty), text, font=f, fill=(*text_color[:3], 255))


def draw_progress_timer_bar(
    draw: ImageDraw.Draw,
    img: Image.Image,
    x: int, y: int,
    width: int, height: int,
    progress: float,
    bg_color: Tuple = (60, 60, 80),
    fill_color: Tuple = (76, 175, 80),
    radius: int = 8,
):
    """Draw a horizontal timer bar that depletes left-to-right.

    *progress* 1.0 = full, 0.0 = empty.  Fill colour shifts
    green → yellow → red as progress decreases.
    """
    # Auto-colour based on remaining progress
    if progress > 0.5:
        bar_color = fill_color  # green by default
    elif progress > 0.25:
        bar_color = (255, 193, 7)   # yellow
    else:
        bar_color = (244, 67, 54)   # red

    # Background track
    draw.rounded_rectangle(
        [x, y, x + width, y + height],
        radius=radius,
        fill=(*bg_color[:3], 180),
    )

    # Filled portion
    fill_w = max(height, int(width * max(0.0, min(1.0, progress))))
    if fill_w > 0:
        bar_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar_layer)
        bd.rounded_rectangle(
            [x, y, x + fill_w, y + height],
            radius=radius,
            fill=(*bar_color[:3], 255),
        )
        img.paste(bar_layer, (0, 0), bar_layer)


def draw_two_column_row(
    draw: ImageDraw.Draw,
    img: Image.Image,
    left_text: str,
    right_text: str,
    y: int,
    row_height: int = 90,
    left_font_size: int = 44,
    right_font_size: int = 44,
    left_color: Tuple = (255, 255, 255),
    right_color: Tuple = (255, 215, 0),
    highlight: bool = False,
    highlight_color: Tuple = (255, 255, 255, 30),
    margin_x: int = 80,
    divider_x: int = 540,
):
    """Draw a two-column vocabulary row with optional highlight stripe.

    Left text is right-aligned to *divider_x*; right text is left-aligned
    from *divider_x*.  A thin vertical divider is drawn between them.
    """
    # Highlight background
    if highlight:
        hl_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(hl_layer)
        hc = highlight_color if len(highlight_color) == 4 else (*highlight_color[:3], 30)
        hd.rectangle(
            [margin_x, y, VIDEO_WIDTH - margin_x, y + row_height],
            fill=hc,
        )
        img.paste(hl_layer, (0, 0), hl_layer)

    # Vertical divider
    divider_color = CARD_COLORS.get('divider', (200, 200, 210))
    divider_pad = 12
    draw.line(
        [(divider_x, y + divider_pad), (divider_x, y + row_height - divider_pad)],
        fill=(*divider_color[:3], 80),
        width=2,
    )

    gap = 24  # horizontal gap between text and divider

    # Left text — right-aligned to divider
    lf = font(left_font_size)
    lbbox = draw.textbbox((0, 0), left_text, font=lf)
    lw = lbbox[2] - lbbox[0]
    lh = lbbox[3] - lbbox[1]
    lx = divider_x - gap - lw
    ly = y + (row_height - lh) // 2 - 1
    draw_text_solid(draw, left_text, max(margin_x, lx), ly, lf, left_color, outline=4)

    # Right text — left-aligned from divider
    rf = font(right_font_size)
    rbbox = draw.textbbox((0, 0), right_text, font=rf)
    rh = rbbox[3] - rbbox[1]
    rx = divider_x + gap
    ry = y + (row_height - rh) // 2 - 1
    draw_text_solid(draw, right_text, rx, ry, rf, right_color, outline=4)


def draw_difficulty_badge(
    draw: ImageDraw.Draw,
    img: Image.Image,
    level: str,
    x: int,
    y: int,
) -> Tuple[int, int]:
    """Draw a coloured difficulty pill badge.

    *level*: ``"facil"`` | ``"medio"`` | ``"dificil"`` | ``"experto"``

    Returns (pill_width, pill_height).
    """
    labels = {
        'facil': 'FÁCIL',
        'medio': 'MEDIO',
        'dificil': 'DIFÍCIL',
        'experto': 'EXPERTO',
    }

    label = labels.get(level, level.upper())
    color = DIFFICULTY_COLORS.get(level, (150, 150, 150))

    return draw_pill_badge(
        img, draw, label, x, y,
        font_size=26,
        bg_color=color,
        text_color=(255, 255, 255),
        padding_x=20,
        padding_y=8,
    )

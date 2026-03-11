"""Karaoke-style educational video renderer.

Shows multiple lines of text with word-by-word highlighting,
inline translations for English words, and smooth TikTok-style animations.
"""

from typing import List, Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_out_back, ease_out_cubic, ease_in_out_sine,
    tiktok_pop_scale, spring_animation,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, TEXT_AREA_WIDTH,
    ENGLISH_WORD_COLOR, SPANISH_WORD_COLOR,
)
from .utils import font, create_base_frame, finalize_frame

# Karaoke-specific constants
FONT_SIZE_MAIN = 52  # Smaller for more text on screen
FONT_SIZE_ENGLISH = 58  # Slightly larger for emphasis
FONT_SIZE_TRANSLATION = 36  # Translation below English words
LINE_HEIGHT = 1.5  # Line spacing multiplier
MAX_LINES = 5  # Maximum lines visible at once

# Animation timing
ANTICIPATION_TIME = 0.08  # Highlight 80ms BEFORE word starts (TikTok style)
POP_DURATION = 0.15  # Duration of pop-in animation
FADE_DURATION = 0.12  # Color transition duration
SCALE_ACTIVE = 1.05  # Scale for active word
SCALE_NORMAL = 1.0

# Cache for computed data (reset per video)
_cache = {
    'lines': None,
    'word_widths': None,
    'words_hash': None
}

# Colors (RGB)
COLOR_ACTIVE = (255, 255, 255)  # Bright white for active Spanish word
COLOR_INACTIVE = (160, 165, 175)  # Dimmed for upcoming words
COLOR_ENGLISH = (255, 215, 0)  # Gold for English words
COLOR_ENGLISH_ACTIVE = (255, 235, 100)  # Brighter gold when active
COLOR_TRANSLATION = (0, 210, 230)  # Cyan for translations
COLOR_PAST = (100, 105, 115)  # Darker for past words


def _blend_colors(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Blend two RGB colors. t=0 returns c1, t=1 returns c2."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def create_frame_karaoke(
    t: float,
    data: Dict,
    duration: float,
) -> np.ndarray:
    """Create frame with karaoke-style word highlighting.

    Args:
        t: Current time in seconds
        data: Dict with 'words', 'translations', 'full_script'
        duration: Total video duration
    """
    frame, draw = create_base_frame(t)

    words = data.get('words', [])
    translations = data.get('translations', {}) or {}
    full_script = data.get('full_script', '')
    # Normalize translation keys to lowercase for case-insensitive lookup
    translations_lower = {k.lower(): v for k, v in translations.items()}

    # Build lines from words (cached for performance)
    words_hash = id(words)
    if _cache['words_hash'] != words_hash:
        _cache['lines'] = _build_display_lines(words, translations)
        _cache['words_hash'] = words_hash
    lines = _cache['lines']

    # Find current word index
    current_idx = _find_current_word_index(words, t)

    # Render lines with highlighting
    _render_karaoke_lines(draw, frame, lines, words, t, current_idx, translations_lower)

    return finalize_frame(frame, draw, t, duration)


def _build_display_lines(
    words: List[Dict],
    translations: Dict,
    max_width: int = TEXT_AREA_WIDTH - 80
) -> List[List[int]]:
    """Build lines of word indices for display.

    Returns list of lines, where each line is a list of word indices.
    """
    if not words:
        return []

    f = font(FONT_SIZE_MAIN)
    f_en = font(FONT_SIZE_ENGLISH)

    lines = []
    current_line = []
    current_width = 0
    space_width = f.getbbox(" ")[2]

    for i, w in enumerate(words):
        word_text = w['word']
        is_english = w.get('is_english', False)

        # Calculate word width
        wf = f_en if is_english else f
        bbox = wf.getbbox(word_text)
        word_width = bbox[2] - bbox[0] if bbox else 0

        # Check if word fits on current line
        needed_width = word_width
        if current_line:
            needed_width += space_width

        if current_width + needed_width > max_width and current_line:
            # Start new line
            lines.append(current_line)
            current_line = [i]
            current_width = word_width
        else:
            current_line.append(i)
            current_width += needed_width

        # Force line break at sentence end
        if w.get('segment_end', False):
            lines.append(current_line)
            current_line = []
            current_width = 0

    if current_line:
        lines.append(current_line)

    return lines


def _find_current_word_index(words: List[Dict], t: float) -> int:
    """Find the index of the word being spoken at time t."""
    for i, w in enumerate(words):
        if w['start'] <= t <= w['end']:
            return i
        if w['start'] > t:
            return max(0, i - 1)
    return len(words) - 1


def _render_karaoke_lines(
    draw: ImageDraw.Draw,
    frame: Image.Image,
    lines: List[List[int]],
    words: List[Dict],
    t: float,
    current_idx: int,
    translations: Dict
):
    """Render karaoke lines with word highlighting."""
    if not lines or not words:
        return

    # Find which line contains the current word
    current_line_idx = 0
    for i, line_indices in enumerate(lines):
        if current_idx in line_indices:
            current_line_idx = i
            break

    # Calculate which lines to show (current line in center)
    start_line = max(0, current_line_idx - MAX_LINES // 2)
    end_line = min(len(lines), start_line + MAX_LINES)

    # Adjust if we're near the end
    if end_line - start_line < MAX_LINES and start_line > 0:
        start_line = max(0, end_line - MAX_LINES)

    visible_lines = lines[start_line:end_line]

    # Calculate vertical positioning
    f = font(FONT_SIZE_MAIN)
    line_height = int(FONT_SIZE_MAIN * LINE_HEIGHT)
    total_height = len(visible_lines) * line_height

    # Add extra space for translations
    for line_indices in visible_lines:
        for idx in line_indices:
            if idx < len(words) and words[idx].get('is_english', False):
                total_height += int(FONT_SIZE_TRANSLATION * 0.8)
                break

    start_y = (VIDEO_HEIGHT - total_height) // 2 - 50

    # Render each visible line
    y = start_y
    for line_num, line_indices in enumerate(visible_lines):
        actual_line_idx = start_line + line_num
        is_current_line = (actual_line_idx == current_line_idx)
        is_past_line = (actual_line_idx < current_line_idx)

        y = _render_line(
            draw, frame, line_indices, words, t, current_idx,
            translations, y, is_current_line, is_past_line
        )

        y += line_height


def _render_line(
    draw: ImageDraw.Draw,
    frame: Image.Image,
    line_indices: List[int],
    words: List[Dict],
    t: float,
    current_idx: int,
    translations: Dict,
    y: int,
    is_current_line: bool,
    is_past_line: bool
) -> int:
    """Render a single line of words. Returns the y position after rendering."""
    if not line_indices:
        return y

    f = font(FONT_SIZE_MAIN)
    f_en = font(FONT_SIZE_ENGLISH)
    f_trans = font(FONT_SIZE_TRANSLATION)

    # Calculate line width for centering
    total_width = 0
    word_widths = []
    space_width = f.getbbox(" ")[2]

    for i, idx in enumerate(line_indices):
        w = words[idx]
        is_english = w.get('is_english', False)
        wf = f_en if is_english else f
        bbox = wf.getbbox(w['word'])
        width = bbox[2] - bbox[0] if bbox else 0
        word_widths.append(width)
        total_width += width
        if i < len(line_indices) - 1:
            total_width += space_width

    # Start x position (centered)
    x = (VIDEO_WIDTH - total_width) // 2

    # Track if line has English words (for translation space)
    has_english = any(words[idx].get('is_english', False) for idx in line_indices)
    max_trans_height = 0

    # Render each word with animations
    for i, idx in enumerate(line_indices):
        w = words[idx]
        word_text = w['word']
        word_start = w.get('start', 0)
        word_end = w.get('end', 0)
        is_english = w.get('is_english', False)

        # Calculate animation state with anticipation
        # Word becomes "active" slightly BEFORE it starts (TikTok style)
        anticipated_start = word_start - ANTICIPATION_TIME
        is_current = (idx == current_idx)
        is_becoming_active = (anticipated_start <= t < word_start)
        is_active = (word_start <= t <= word_end)
        is_past = (t > word_end)

        # Calculate animation progress for pop effect
        if is_becoming_active or (is_active and t < word_start + POP_DURATION):
            pop_progress = min(1.0, (t - anticipated_start) / POP_DURATION)
            scale = SCALE_NORMAL + (SCALE_ACTIVE - SCALE_NORMAL) * ease_out_back(pop_progress)
        elif is_active:
            scale = SCALE_ACTIVE
        else:
            scale = SCALE_NORMAL

        # Calculate color with smooth transitions
        if is_english:
            if is_active or is_becoming_active:
                color = COLOR_ENGLISH_ACTIVE
            else:
                color = COLOR_ENGLISH
            base_alpha = 255
        elif is_active or is_becoming_active:
            # Fade in to active color
            if is_becoming_active:
                fade_progress = (t - anticipated_start) / FADE_DURATION
                fade_progress = min(1.0, fade_progress)
                color = _blend_colors(COLOR_INACTIVE, COLOR_ACTIVE, ease_out_cubic(fade_progress))
            else:
                color = COLOR_ACTIVE
            base_alpha = 255
        elif is_past or is_past_line:
            color = COLOR_PAST
            base_alpha = 180
        else:
            color = COLOR_INACTIVE
            base_alpha = 200 if is_current_line else 150

        # Apply scale to font size
        wf = f_en if is_english else f
        if scale != 1.0:
            scaled_size = int((FONT_SIZE_ENGLISH if is_english else FONT_SIZE_MAIN) * scale)
            wf = font(scaled_size)

        # Calculate position offset for scaled text (keep centered)
        scale_offset_x = int(word_widths[i] * (1 - scale) / 2)
        scale_offset_y = int((FONT_SIZE_MAIN if not is_english else FONT_SIZE_ENGLISH) * (scale - 1) / 2)

        # Draw word with outline
        draw.text(
            (x + scale_offset_x, y - scale_offset_y), word_text, font=wf,
            fill=(*color, base_alpha),
            stroke_width=4,
            stroke_fill=(0, 0, 0, base_alpha)
        )

        # Draw translation below English words
        if is_english:
            trans_key = word_text.lower().strip('.,!?¿¡:;\'"')
            trans = translations.get(trans_key, "")
            if trans:
                trans_text = f"({trans})"
                trans_bbox = f_trans.getbbox(trans_text)
                trans_width = trans_bbox[2] - trans_bbox[0] if trans_bbox else 0
                trans_x = x + (word_widths[i] - trans_width) // 2
                trans_y = y + int(FONT_SIZE_ENGLISH * scale * 1.1)

                # Translation fades in with the word
                trans_alpha = base_alpha if (is_active or is_past) else int(base_alpha * 0.7)

                draw.text(
                    (trans_x, trans_y), trans_text, font=f_trans,
                    fill=(*COLOR_TRANSLATION, trans_alpha),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0, trans_alpha)
                )

                max_trans_height = max(max_trans_height, int(FONT_SIZE_TRANSLATION * 1.2))

        x += word_widths[i] + space_width

    return y + max_trans_height

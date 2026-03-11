"""Vocabulary list video frame generator — two-column Spanish/English with row-by-row highlight."""

import logging
from typing import Dict, List

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_out_back, ease_out_cubic, ease_in_out_sine,
    get_alpha, tiktok_pop_scale,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, COLOR_WHITE, COLOR_YELLOW, TEXT_AREA_WIDTH,
)
from config.layout import (
    CARD_MARGIN_X, CARD_PADDING, CARD_RADIUS, CARD_WIDTH,
    VOCAB_ROW_HEIGHT, VOCAB_DIVIDER_X,
    BAR_Y,
)
from config.colors import CARD_COLORS
from .utils import (
    font, draw_text_solid, draw_text_centered,
    draw_rounded_card, draw_difficulty_badge, fit_text_font,
    create_base_frame, finalize_frame,
    seg_start as _seg_start,
    slide_in_x,
)

logger = logging.getLogger(__name__)

# ── Layout constants ─────────────────────────────────────────────

_TITLE_Y = 100
_TITLE_MAX_FONT = 60
_TITLE_MIN_FONT = 36
_BADGE_X = 900
_BADGE_Y = 110
_CARD_TOP_MIN = 260      # card never above this
_HEADER_H = 70           # coloured header strip inside the card
_ROW_FONT = 42
_HEADER_FONT = 34

# Highlight colour for the currently-active row
_HIGHLIGHT_COLOR = (0, 180, 220, 40)
# Dimmed alpha multiplier for past rows
_DIM_ALPHA = 0.70


# ── Timestamp helpers ────────────────────────────────────────────

def _build_fallback_times(pairs: List[Dict], duration: float) -> Dict:
    """Distribute pairs evenly when no segment_times are provided."""
    n = len(pairs)
    title_dur = min(2.0, duration * 0.12)
    remaining = duration - title_dur - 0.5        # 0.5s tail padding
    per_pair = max(1.5, remaining / max(n, 1))

    st: Dict[str, Dict] = {
        'title': {'start': 0.0, 'end': title_dur},
    }
    cursor = title_dur + 0.3                      # small gap after title
    for i in range(n):
        end = min(cursor + per_pair, duration - 0.2)
        st[f'pair_{i}'] = {'start': cursor, 'end': end}
        cursor = end + 0.15                       # tiny gap between pairs
    return st


# ── Main frame generator ─────────────────────────────────────────

def create_frame_vocabulary(
    t: float,
    data: Dict,
    duration: float,
) -> np.ndarray:
    """Create frame for vocabulary-list video type."""
    frame, draw = create_base_frame(t)

    title = data.get('title', 'Vocabulario del día')
    difficulty = data.get('difficulty', '')
    pairs: List[Dict] = data.get('pairs', [])
    st = data.get('segment_times', {})

    # Fallback if segment_times missing or empty
    if not st:
        st = _build_fallback_times(pairs, duration)
        data['segment_times'] = st

    # Log once
    if t < 0.04:
        logger.info("Vocabulary: %d pairs, difficulty=%s", len(pairs), difficulty or 'none')

    num_rows = len(pairs)

    # ── Title layout: fit title, compute where card starts ───────
    # Use fit_text_font to find the right size for the title
    title_max_w = TEXT_AREA_WIDTH - 160   # leave room for badge
    tf_static, t_size_static, title_lines, title_total_h = fit_text_font(
        title, _TITLE_MAX_FONT, _TITLE_MIN_FONT, title_max_w,
    )
    # Card starts below the title with some spacing
    card_top = max(_CARD_TOP_MIN, _TITLE_Y + title_total_h + 30)

    # ── Card geometry (computed once, stable across frames) ───────
    card_x = CARD_MARGIN_X
    card_inner_h = _HEADER_H + num_rows * VOCAB_ROW_HEIGHT + CARD_PADDING
    card_h = card_inner_h + CARD_PADDING     # top padding is part of header area
    # Clamp so card never overlaps the progress bar
    max_card_h = BAR_Y - card_top - 30
    if card_h > max_card_h:
        card_h = max_card_h

    header_y = card_top + CARD_PADDING // 2
    first_row_y = header_y + _HEADER_H

    # ── Phase 0: Title ───────────────────────────────────────────
    title_start = _seg_start(st, 'title', 0.0)
    title_alpha = get_alpha(t, title_start, 0.35)

    if title_alpha > 0:
        scale = tiktok_pop_scale(t, title_start)
        if scale > 0:
            t_size = max(_TITLE_MIN_FONT, int(t_size_static * scale))
            tf = font(t_size)
            draw_text_centered(
                draw, title, _TITLE_Y, tf,
                COLOR_YELLOW, title_alpha, outline=5,
                max_width=title_max_w,
            )

    # ── Difficulty badge (slides in from right) ──────────────────
    if difficulty:
        badge_appear = title_start + 0.30
        badge_alpha = get_alpha(t, badge_appear, 0.25)
        if badge_alpha > 0:
            badge_offset = slide_in_x(t, badge_appear, 0.35)
            draw_difficulty_badge(
                draw, frame, difficulty,
                _BADGE_X + badge_offset, _BADGE_Y,
            )
            # Re-acquire draw after compositing inside badge
            draw = ImageDraw.Draw(frame, 'RGBA')

    # ── Phase 1: Card fade-in ────────────────────────────────────
    card_appear = title_start + 0.50
    card_alpha_f = min(1.0, max(0.0, (t - card_appear) / 0.30))
    card_alpha = int(255 * ease_out_cubic(card_alpha_f))   # fully opaque to hide ghost text

    if card_alpha > 0:
        draw_rounded_card(
            frame, card_x, card_top, CARD_WIDTH, card_h,
            radius=CARD_RADIUS,
            fill=CARD_COLORS['cream_card'],
            alpha=card_alpha,
            shadow=True,
            shadow_offset=6,
            shadow_alpha=int(80 * card_alpha_f),
        )
        # Re-acquire draw after compositing
        draw = ImageDraw.Draw(frame, 'RGBA')

    # ── Phase 2: Header row ──────────────────────────────────────
    header_appear = card_appear + 0.20
    header_alpha = get_alpha(t, header_appear, 0.20)

    if header_alpha > 0:
        # Coloured header strip
        hdr_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(hdr_layer)
        hd.rounded_rectangle(
            [card_x + 8, header_y, card_x + CARD_WIDTH - 8, header_y + _HEADER_H],
            radius=14,
            fill=(80, 130, 220, header_alpha),
        )
        frame.paste(hdr_layer, (0, 0), hdr_layer)
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Divider X is relative to canvas, not card
        div_x = VOCAB_DIVIDER_X

        # Header labels
        hf = font(_HEADER_FONT)

        es_text = "ESPAÑOL"
        es_bbox = draw.textbbox((0, 0), es_text, font=hf)
        es_w = es_bbox[2] - es_bbox[0]
        # Centre "ESPAÑOL" in the left column (card_x+8 .. div_x)
        left_col_center = card_x + 8 + (div_x - card_x - 8) // 2
        es_x = left_col_center - es_w // 2
        es_y = header_y + (_HEADER_H - (es_bbox[3] - es_bbox[1])) // 2 - 1
        draw_text_solid(draw, es_text, es_x, es_y, hf, COLOR_WHITE, header_alpha, outline=3)

        en_text = "INGLÉS"
        en_bbox = draw.textbbox((0, 0), en_text, font=hf)
        en_w = en_bbox[2] - en_bbox[0]
        right_col_center = div_x + (card_x + CARD_WIDTH - 8 - div_x) // 2
        en_x = right_col_center - en_w // 2
        en_y = es_y
        draw_text_solid(draw, en_text, en_x, en_y, hf, COLOR_YELLOW, header_alpha, outline=3)

        # Thin divider through header
        draw.line(
            [(div_x, header_y + 10), (div_x, header_y + _HEADER_H - 10)],
            fill=(255, 255, 255, int(header_alpha * 0.5)),
            width=2,
        )

    # ── Phase 3: Data rows (one by one, synced to audio) ─────────
    _draw_vocab_rows(
        t, draw, frame,
        pairs, st,
        card_x, first_row_y, card_h, card_alpha_f,
        card_top=card_top,
    )

    return finalize_frame(frame, draw, t, duration)


def _draw_vocab_rows(
    t: float,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    pairs: List[Dict],
    st: Dict,
    card_x: int,
    first_row_y: int,
    card_h: int,
    card_visible: float,
    card_top: int = 290,
):
    """Render vocabulary data rows with highlight and dim animations."""
    if card_visible <= 0:
        return

    num_pairs = len(pairs)
    div_x = VOCAB_DIVIDER_X
    gap = 20          # text-to-divider gap
    left_min_x = card_x + CARD_PADDING // 2
    right_max_x = card_x + CARD_WIDTH - CARD_PADDING // 2

    # Maximum column widths for fit_text_font
    left_col_w = div_x - gap - left_min_x
    right_col_w = right_max_x - div_x - gap

    # Determine which pair is currently active (for highlight logic)
    active_idx = -1
    for i in range(num_pairs):
        pair_start = _seg_start(st, f'pair_{i}', -1)
        if pair_start < 0:
            continue
        if t >= pair_start:
            active_idx = i

    for i, pair in enumerate(pairs):
        seg_key = f'pair_{i}'
        pair_start = _seg_start(st, seg_key, -1)
        if pair_start < 0:
            continue                       # no timestamp → skip

        # Row not yet visible
        if t < pair_start:
            continue

        row_y = first_row_y + i * VOCAB_ROW_HEIGHT
        # Don't draw outside the card
        if row_y + VOCAB_ROW_HEIGHT > card_top + card_h:
            break

        # ── Row alpha / highlight ────────────────────────────────
        # Fade in over 0.25s
        row_age = t - pair_start
        row_alpha_f = min(1.0, row_age / 0.25)
        row_alpha = int(255 * ease_out_cubic(row_alpha_f))

        is_active = (i == active_idx)
        is_past = (i < active_idx)

        if is_past:
            # Smooth dim transition when a row loses focus
            dim_target = _DIM_ALPHA
            # Transition takes 0.3s after losing active status
            next_start = _seg_start(st, f'pair_{i + 1}', t)
            since_lost = t - next_start
            dim_progress = min(1.0, max(0.0, since_lost / 0.30))
            dim_factor = 1.0 - (1.0 - dim_target) * ease_in_out_sine(dim_progress)
            row_alpha = int(row_alpha * dim_factor)

        # ── Highlight strip (active row) ─────────────────────────
        if is_active and row_alpha > 0:
            hl_alpha_raw = min(1.0, row_age / 0.15)
            hl_alpha = int(_HIGHLIGHT_COLOR[3] * ease_in_out_sine(hl_alpha_raw))
            if hl_alpha > 0:
                hl_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
                hd = ImageDraw.Draw(hl_layer)
                hd.rounded_rectangle(
                    [card_x + 6, row_y, card_x + CARD_WIDTH - 6, row_y + VOCAB_ROW_HEIGHT],
                    radius=10,
                    fill=(*_HIGHLIGHT_COLOR[:3], hl_alpha),
                )
                frame.paste(hl_layer, (0, 0), hl_layer)
                draw = ImageDraw.Draw(frame, 'RGBA')

        # ── Alternating subtle tint for even rows ────────────────
        elif not is_active and i % 2 == 0 and row_alpha > 0:
            tint_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
            td = ImageDraw.Draw(tint_layer)
            td.rectangle(
                [card_x + 6, row_y, card_x + CARD_WIDTH - 6, row_y + VOCAB_ROW_HEIGHT],
                fill=(0, 0, 0, 8),
            )
            frame.paste(tint_layer, (0, 0), tint_layer)
            draw = ImageDraw.Draw(frame, 'RGBA')

        if row_alpha <= 0:
            continue

        # ── Slide-in offset ──────────────────────────────────────
        x_off = int(slide_in_x(t, pair_start, 0.30))

        # ── Divider ──────────────────────────────────────────────
        div_pad = 10
        draw.line(
            [(div_x + x_off, row_y + div_pad),
             (div_x + x_off, row_y + VOCAB_ROW_HEIGHT - div_pad)],
            fill=(160, 160, 175, int(row_alpha * 0.35)),
            width=2,
        )

        # ── Spanish text (left column, right-aligned to divider) ─
        es_text = pair.get('spanish', '')
        lf, _, _, _ = fit_text_font(es_text, _ROW_FONT, 28, left_col_w)
        lbbox = draw.textbbox((0, 0), es_text, font=lf)
        lw = lbbox[2] - lbbox[0]
        lh = lbbox[3] - lbbox[1]
        lx = div_x - gap - lw + x_off
        ly = row_y + (VOCAB_ROW_HEIGHT - lh) // 2 - 1
        draw_text_solid(draw, es_text, max(left_min_x, lx), ly, lf,
                        COLOR_WHITE, row_alpha, outline=4)

        # ── English text (right column, left-aligned from divider)
        en_text = pair.get('english', '')
        rf, _, _, _ = fit_text_font(en_text, _ROW_FONT, 28, right_col_w)
        rbbox = draw.textbbox((0, 0), en_text, font=rf)
        rh = rbbox[3] - rbbox[1]
        rx = div_x + gap + x_off
        ry = row_y + (VOCAB_ROW_HEIGHT - rh) // 2 - 1
        draw_text_solid(draw, en_text, rx, ry, rf,
                        COLOR_YELLOW, row_alpha, outline=4)

        # ── Row number circle (left edge) ────────────────────────
        num_r = 16
        num_cx = card_x + 28 + x_off
        num_cy = row_y + VOCAB_ROW_HEIGHT // 2
        num_alpha = int(row_alpha * 0.6)
        if num_alpha > 10:
            draw.ellipse(
                [num_cx - num_r, num_cy - num_r,
                 num_cx + num_r, num_cy + num_r],
                fill=(100, 130, 200, num_alpha),
            )
            nf = font(22)
            nt = str(i + 1)
            nbbox = draw.textbbox((0, 0), nt, font=nf)
            ntw = nbbox[2] - nbbox[0]
            nth = nbbox[3] - nbbox[1]
            draw.text(
                (num_cx - ntw // 2, num_cy - nth // 2 - 1),
                nt, font=nf,
                fill=(255, 255, 255, num_alpha),
            )

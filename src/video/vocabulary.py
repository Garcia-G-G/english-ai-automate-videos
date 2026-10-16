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
    VOCAB_ROW_HEIGHT, VOCAB_DIVIDER_X, VOCAB_CARD_TOP_MIN,
    VOCAB_MAX_ROWS,
    BAR_Y,
)
from config.colors import CARD_COLORS
from .motion import idle_dy, scene_cuts
from .utils import (
    font, draw_text_solid, draw_text_centered,
    draw_rounded_card, draw_difficulty_badge, fit_text_font,
    font_line_height,
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
_CARD_TOP_MIN = VOCAB_CARD_TOP_MIN   # card never above this
_HEADER_H = 70           # coloured header strip inside the card
_ROW_FONT = 42

#: Vertical budget for ONE cell's text block, inside VOCAB_ROW_HEIGHT.
#:
#: 90 minus 12px of air, so two lines can share a row without the blocks of
#: adjacent rows touching. The number is chosen against the font metrics, not
#: picked: two lines at 32px measure exactly 78px of advance and fit; two at
#: 42px measure 104px and do not. That is why a HEIGHT is passed to
#: fit_text_font rather than a line count — the count that fits depends on
#: the size the fit lands on, which is the thing being solved for.
_ROW_TEXT_BUDGET = VOCAB_ROW_HEIGHT - 12

#: The row-number badge, and the gutter the text keeps clear of it.
#:
#: THESE EXIST SO THE COLUMN ORIGIN IS DERIVED RATHER THAN WRITTEN DOWN.
#: The left column used `card_x + CARD_PADDING // 2` — 80px — while the badge
#: occupies 72..104, so the column began 24px INSIDE the circle and any line
#: wider than 376px was drawn over the number. Seven of twelve rows were, by
#: 8 to 19px, and the declared column width (400px) and the usable width
#: (376px) disagreed with nobody to notice.
#:
#: That is the same shape as the quiz card sizing itself against
#: SAFE_AREA_BOTTOM while the watermark sat above it: two things measuring to
#: different boundaries and meeting in the middle. watermark_top() fixed that
#: one by making the obstacle answer for its own extent, and _text_left_edge
#: does the same here — change _NUM_RADIUS or _NUM_CENTRE_DX and the text
#: moves with the badge instead of under it.
_NUM_RADIUS = 16
_NUM_CENTRE_DX = 28
_NUM_GUTTER = 8


def _text_left_edge(card_x: int) -> int:
    """Leftmost x the left column may use: past the badge, plus a gutter.

    The single place that decides where the Spanish column starts. The badge
    is drawn from the same three constants, so the two cannot drift.
    """
    return card_x + _NUM_CENTRE_DX + _NUM_RADIUS + _NUM_GUTTER
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
    presentation=None,
) -> np.ndarray:
    """Create frame for vocabulary-list video type."""
    if presentation is None:
        from studio.renderer_presentation import resolve_presentation
        presentation = resolve_presentation("es")
    frame, draw = create_base_frame(t)

    # No defaults. 'Vocabulario del día' rendered as a real title over
    # somebody else's lesson, and [] rendered an empty one.
    title = data['title']
    pairs: List[Dict] = data['pairs']
    # THE CAP IS ENFORCED HERE. It was declared in config/layout.py and read
    # by nobody, so a deck of 15 drew 15 rows and ran off the card. Truncate
    # loudly rather than silently: a dropped pair is content the learner
    # does not get, and it must be visible in the log.
    if len(pairs) > VOCAB_MAX_ROWS:
        logger.warning(
            "Vocabulary: %d pairs exceeds VOCAB_MAX_ROWS=%d — rendering the "
            "first %d and DROPPING %d. The script should not have produced "
            "more than the card can hold.",
            len(pairs), VOCAB_MAX_ROWS, VOCAB_MAX_ROWS, len(pairs) - VOCAB_MAX_ROWS)
        pairs = pairs[:VOCAB_MAX_ROWS]

    # Genuinely optional — '' hides the difficulty badge.
    difficulty = data.get('difficulty', '')
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
    title_box = fit_text_font(
        title, _TITLE_MAX_FONT, _TITLE_MIN_FONT, title_max_w,
    )
    tf_static, t_size_static, title_lines = (
        title_box.font, title_box.size, title_box.lines)
    # ADVANCE, because the card is STACKED below the title rather than fitted
    # around it. Ink would let the card creep up under a title whose last line
    # happens to carry no descender.
    card_top = max(_CARD_TOP_MIN, _TITLE_Y + title_box.advance_height + 30)

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

    # The card, its header and its rows float together once the card is
    # in. UP only, so the clamp against the progress bar above still holds;
    # 3px of the 30px left between the title and the card is spent at most.
    card_float = int(round(idle_dy(t, card_appear + 0.30)))
    card_top += card_float
    header_y += card_float
    first_row_y += card_float
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

        es_text = presentation.native_heading
        es_bbox = draw.textbbox((0, 0), es_text, font=hf)
        es_w = es_bbox[2] - es_bbox[0]
        # Centre "ESPAÑOL" in the left column (card_x+8 .. div_x)
        left_col_center = card_x + 8 + (div_x - card_x - 8) // 2
        es_x = left_col_center - es_w // 2
        es_y = header_y + (_HEADER_H - (es_bbox[3] - es_bbox[1])) // 2 - 1
        draw_text_solid(draw, es_text, es_x, es_y, hf, COLOR_WHITE, header_alpha, outline=3)

        en_text = presentation.learning_heading
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
        card_top=card_top, presentation=presentation,
    )

    return finalize_frame(frame, draw, t, duration, words=data.get('words', []),
                          scene_cuts=scene_cuts(st))


def _draw_cell(draw, text, *, col_w, budget, row_y, color, alpha,
               align_right_to=None, align_left_from=None, min_x=None):
    """Lay out one table cell and draw THE LINES THE FIT RETURNED.

    THE DEFECT THIS REPLACES. The two call sites here asked fit_text_font how
    the text should be laid out, unpacked it as `lf, _, _, _`, and then drew
    the original unwrapped string. Both failures compounded:

      · No `max_height` was passed, and fit_text_font's guard is
        `if max_height is None or box.advance_height <= max_height`. With
        None the guard is true on the first iteration, so the function
        returned _ROW_FONT — 42px — for every string of any length. The call
        read like a fit and behaved like a constant.
      · `box.lines`, already wrapped to the column by line_break, was thrown
        away and `draw_text_solid` was handed the source string.

    Measured on a real deck at 42px into columns of 400px and 480px: 14 of 24
    cells overflowed, in 9 of 12 rows, the longest by 409px.

    WIDTH ALONE WOULD NOT HAVE FIXED IT. Shrinking to the 28px floor on width
    still leaves four cells over — "Has demostrado una habilidad notable" is
    524px at 28px into a 400px column. The fit has to be two-dimensional, so
    the row's own vertical budget goes in and wrapping is allowed to happen.
    With _ROW_TEXT_BUDGET every cell on that deck resolves, seven of them on
    two lines, none at the floor.

    ALIGNMENT IS PER LINE, NOT PER BLOCK. A block right-aligned by its widest
    line is not right-aligned: its short line would float off the divider. So
    each line is placed on its own measured width.

    VERTICAL CENTRING USES THE REAL BLOCK. (n-1) line advances plus the ink
    of one line, centred in the row. For a single line that reduces to
    exactly the previous arithmetic, so one-line rows do not shift; a
    two-line cell centres its block, and the two columns of a row centre
    independently so a one-line cell beside a two-line one still reads as one
    row.
    """
    box = fit_text_font(text, _ROW_FONT, 28, col_w, budget)
    f, lines = box.font, box.lines
    line_h = font_line_height(f)

    # fit_text_font logs its own overflow with the text and the excess when
    # nothing in the range fits. Nothing is truncated and no row is dropped:
    # a cell that cannot fit is drawn too large and reported, because a
    # silently shortened word is a wrong lesson.
    ink_h = draw.textbbox((0, 0), lines[0], font=f)[3] - \
        draw.textbbox((0, 0), lines[0], font=f)[1]
    block_h = (len(lines) - 1) * line_h + ink_h
    top = row_y + (VOCAB_ROW_HEIGHT - block_h) // 2 - 1

    for index, line in enumerate(lines):
        y = top + index * line_h
        if align_left_from is not None:
            x = align_left_from
        else:
            width = draw.textbbox((0, 0), line, font=f)[2]
            x = align_right_to - width
            if min_x is not None:
                x = max(min_x, x)
        draw_text_solid(draw, line, x, y, f, color, alpha, outline=4)


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
    presentation=None,
):
    """Render vocabulary data rows with highlight and dim animations."""
    if card_visible <= 0:
        return

    num_pairs = len(pairs)
    div_x = VOCAB_DIVIDER_X
    gap = 20          # text-to-divider gap
    # Derived from the badge, not from the card padding — see
    # _text_left_edge. The padding-based origin ran under the number circle.
    left_min_x = _text_left_edge(card_x)
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
        # No default: a blank half-row is a broken lesson, and
        # script_schema.VocabPair requires both sides.
        _draw_cell(
            draw, pair[presentation.native_field],
            col_w=left_col_w, budget=_ROW_TEXT_BUDGET,
            row_y=row_y, align_right_to=div_x - gap + x_off,
            # +x_off so the guard slides with the row: the badge moves
            # with x_off and a floor that did not would let the text pass
            # under it mid-animation.
            min_x=left_min_x + x_off, color=COLOR_WHITE, alpha=row_alpha,
        )

        # ── English text (right column, left-aligned from divider)
        _draw_cell(
            draw, pair[presentation.learning_field],
            col_w=right_col_w, budget=_ROW_TEXT_BUDGET,
            row_y=row_y, align_left_from=div_x + gap + x_off,
            color=COLOR_YELLOW, alpha=row_alpha,
        )

        # ── Row number circle (left edge) ────────────────────────
        num_r = _NUM_RADIUS
        num_cx = card_x + _NUM_CENTRE_DX + x_off
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

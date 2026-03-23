"""Fill-in-the-blank video frame generator — card-based layout."""

import logging
import math
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    get_alpha, glow_intensity, ease_out_cubic,
    tiktok_pop_scale, spring_animation,
)
from .constants import VIDEO_WIDTH, VIDEO_HEIGHT
from config.colors import COUNTDOWN_COLORS, QUIZ_COLORS
from config.layout import (
    CARD_MARGIN_X, CARD_WIDTH, CARD_RADIUS, CARD_PADDING,
    TIMER_BAR_X, TIMER_BAR_Y, TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT,
)
from .utils import (
    font, draw_text_solid, draw_text_centered,
    draw_rounded_card, draw_circle_number, draw_progress_timer_bar,
    draw_pill_badge, draw_sparkles, fit_text_font,
    create_base_frame, finalize_frame,
    seg_start, seg_end, log_segment_timestamps, resolve_countdown_number,
    slide_in_x,
)

logger = logging.getLogger(__name__)

_FB_SEGMENT_KEYS = [
    'sentence', 'options', 'think',
    'countdown_3', 'countdown_2', 'countdown_1',
    'answer', 'explanation',
]

# ── Layout ────────────────────────────────────────────────────────
_CARD_Y = 250                # sentence card top
_OPTIONS_Y = 520             # first option card top
_OPT_W = 860                 # option card width
_OPT_H = 75                  # option card height
_OPT_GAP = 12                # vertical gap between option cards
_OPT_STAGGER = 0.10          # 100ms stagger between options
_COUNTDOWN_CY = 950          # countdown number center Y
_TRANSLATION_CY = 1050       # translation pill center Y
_TEXT_MAX_W = CARD_WIDTH - CARD_PADDING * 2

# ── Colors ────────────────────────────────────────────────────────
_TEXT_DARK = QUIZ_COLORS['text_dark']       # (50, 45, 60)
_BLANK_CYAN = (0, 212, 255)
_CORRECT_GREEN = (30, 160, 70)
_CORRECT_BRIGHT = (50, 220, 100)
_LETTER_COLORS = [
    (255, 120, 130), (100, 160, 230),       # A red-pink, B blue
    (255, 193, 7),   (156, 39, 176),        # C amber,    D purple
]


# ── Helpers ───────────────────────────────────────────────────────

def _find_blank(sentence: str) -> Optional[Tuple[str, str]]:
    """Split sentence at blank marker. Returns (prefix, suffix) or None."""
    if '___' in sentence:
        i = sentence.index('___')
        return sentence[:i], sentence[i + 3:]
    if '_' in sentence:
        i = sentence.index('_')
        end = i
        while end < len(sentence) and sentence[end] == '_':
            end += 1
        return sentence[:i], sentence[end:]
    return None


def _text_w(draw, text, f):
    """Rendered width of text."""
    bb = draw.textbbox((0, 0), text, font=f)
    return bb[2] - bb[0]


def _text_h(draw, text, f):
    """Rendered height of text."""
    bb = draw.textbbox((0, 0), text, font=f)
    return bb[3] - bb[1]


def _draw_countdown_number(draw, frame, number, cx, cy, t, start):
    """Large countdown number with pop + glow, no ring."""
    color = COUNTDOWN_COLORS.get(number, (255, 255, 255))
    scale = tiktok_pop_scale(t, start, duration=0.20)
    if scale <= 0:
        return
    size = max(20, int(160 * scale))
    f = font(size)
    text = str(number)
    bb = draw.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx, ty = cx - tw // 2, cy - th // 2
    for sw, sa in [(8, 40), (4, 70)]:
        draw.text((tx, ty), text, font=f, fill=(0, 0, 0, 0),
                  stroke_width=sw, stroke_fill=(*color, sa))
    draw.text((tx, ty), text, font=f, fill=(*color, 255),
              stroke_width=3, stroke_fill=(0, 0, 0, 180))


# ── Sentence card rendering ──────────────────────────────────────

def _draw_sentence_card(t, draw, frame, sentence, correct, show_answer, answer_time):
    """White card with sentence; blank has pulsing underline or green answer pop."""
    spring = spring_animation(t, 0.0, duration=0.45)
    if spring <= 0:
        return draw

    bounce = int(30 * (1 - spring))
    parts = _find_blank(sentence)

    # Determine display text for card sizing
    if show_answer and parts:
        display = parts[0] + correct + parts[1]
    elif parts:
        display = parts[0] + "______" + parts[1]
    else:
        display = sentence

    sf, sz, lines, total_h = fit_text_font(display, 48, 32, _TEXT_MAX_W)
    card_h = max(140, total_h + CARD_PADDING * 2 + 12)
    card_y = _CARD_Y + bounce

    # White card
    draw_rounded_card(frame, CARD_MARGIN_X, card_y, CARD_WIDTH, card_h,
                      radius=CARD_RADIUS, fill=(255, 255, 255), alpha=235,
                      shadow=True, shadow_offset=6, shadow_alpha=70)
    draw = ImageDraw.Draw(frame, 'RGBA')

    # Cyan accent bar at top of card
    ab = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    ad = ImageDraw.Draw(ab)
    ad.rounded_rectangle(
        [CARD_MARGIN_X + 10, card_y, CARD_MARGIN_X + CARD_WIDTH - 10, card_y + 4],
        radius=2, fill=(*_BLANK_CYAN, 200))
    frame.paste(ab, (0, 0), ab)
    draw = ImageDraw.Draw(frame, 'RGBA')

    text_cy = card_y + 8 + card_h // 2

    # Multi-line or no blank → simple centered rendering
    if len(lines) > 1 or not parts:
        ty = text_cy - total_h // 2
        color = _CORRECT_GREEN if show_answer else _TEXT_DARK
        draw_text_centered(draw, display, ty, sf, color, 255, outline=0,
                           max_width=_TEXT_MAX_W)
        return draw

    # Single-line per-part rendering with blank highlighting
    if show_answer:
        _draw_filled(draw, parts[0], correct, parts[1], sf, text_cy, t, answer_time)
    else:
        _draw_blanked(t, draw, parts[0], parts[1], sf, text_cy)

    return draw


def _draw_blanked(t, draw, prefix, suffix, sf, cy):
    """Sentence with pulsing cyan underline at blank position."""
    blank = "______"
    full = prefix + blank + suffix
    full_w = _text_w(draw, full, sf)
    full_h = _text_h(draw, full, sf)
    bx = (VIDEO_WIDTH - full_w) // 2
    by = cy - full_h // 2

    pre_w = _text_w(draw, prefix, sf) if prefix else 0
    blank_w = _text_w(draw, blank, sf)

    # Prefix in dark
    if prefix:
        draw_text_solid(draw, prefix, bx, by, sf, _TEXT_DARK, 255, outline=0)
    # Blank placeholder (very faint)
    draw_text_solid(draw, blank, bx + pre_w, by, sf, (200, 200, 210), 60, outline=0)
    # Suffix in dark
    if suffix:
        draw_text_solid(draw, suffix, bx + pre_w + blank_w, by, sf,
                        _TEXT_DARK, 255, outline=0)

    # Pulsing cyan underline (2 Hz sine wave, alpha 130–255)
    pulse = 0.5 + 0.5 * math.sin(t * 4 * math.pi)
    ul_alpha = int(130 + 125 * pulse)
    ul_y = by + full_h + 4
    draw.line([(bx + pre_w + 4, ul_y), (bx + pre_w + blank_w - 4, ul_y)],
              fill=(*_BLANK_CYAN, ul_alpha), width=3)


def _draw_filled(draw, prefix, correct, suffix, sf, cy, t, answer_time):
    """Sentence with correct word popping in green."""
    full = prefix + correct + suffix
    full_w = _text_w(draw, full, sf)
    full_h = _text_h(draw, full, sf)
    bx = (VIDEO_WIDTH - full_w) // 2
    by = cy - full_h // 2

    pre_w = _text_w(draw, prefix, sf) if prefix else 0
    word_w = _text_w(draw, correct, sf)

    # Prefix in dark
    if prefix:
        draw_text_solid(draw, prefix, bx, by, sf, _TEXT_DARK, 255, outline=0)

    # Correct word with pop-in animation
    pop = tiktok_pop_scale(t, answer_time, duration=0.25)
    if pop > 0:
        ws = max(20, int(sf.size * pop))
        wf = font(ws)
        ww = _text_w(draw, correct, wf)
        wh = _text_h(draw, correct, wf)
        wx = bx + pre_w + (word_w - ww) // 2
        wy = by + (full_h - wh) // 2
        draw_text_solid(draw, correct, wx, wy, wf, _CORRECT_GREEN, 255, outline=2)

    # Suffix in dark
    if suffix:
        draw_text_solid(draw, suffix, bx + pre_w + word_w, by, sf,
                        _TEXT_DARK, 255, outline=0)


# ── Option cards ─────────────────────────────────────────────────

def _draw_option_cards(t, draw, frame, options, correct, show_answer,
                       options_start, answer_time):
    """4 stacked option cards with circle letters and slide-in."""
    opt_x = (VIDEO_WIDTH - _OPT_W) // 2
    letters = 'ABCD'

    for i, opt in enumerate(options[:4]):
        delay = options_start + i * _OPT_STAGGER
        if t < delay:
            continue

        alpha = get_alpha(t, delay, 0.3)
        y = _OPTIONS_Y + i * (_OPT_H + _OPT_GAP)
        x_off = int(slide_in_x(t, delay, 0.35))

        is_correct = opt == correct and show_answer
        is_wrong = show_answer and not is_correct

        cx = opt_x + x_off
        cy = y

        # Wrong options: fade to 25% and slide 10px outward
        if is_wrong:
            fade = min(1.0, (t - answer_time) / 0.3)
            card_alpha = int(alpha * (1.0 - 0.75 * ease_out_cubic(fade)))
            cx += int(10 * ease_out_cubic(fade))
        else:
            card_alpha = alpha

        if card_alpha <= 5:
            continue

        # Green glow behind correct option
        if is_correct:
            glow = glow_intensity(t, answer_time)
            if glow > 0:
                gl = Image.new('RGBA', frame.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(gl)
                for sp in (10, 6):
                    gd.rounded_rectangle(
                        [cx - sp, cy - sp,
                         cx + _OPT_W + sp, cy + _OPT_H + sp],
                        radius=22 + sp, fill=(50, 220, 100, int(40 * glow)))
                frame.paste(gl, (0, 0), gl)
                draw = ImageDraw.Draw(frame, 'RGBA')

        # Card background
        fill = (220, 255, 230) if is_correct else (255, 255, 255)
        draw_rounded_card(frame, cx, cy, _OPT_W, _OPT_H, radius=22,
                          fill=fill, alpha=int(card_alpha * 0.92),
                          shadow=True, shadow_offset=4,
                          shadow_alpha=int(50 * card_alpha / 255))
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Circle letter (A/B/C/D)
        lc = (_CORRECT_BRIGHT if is_correct else
              (180, 180, 195) if is_wrong else _LETTER_COLORS[i])
        draw_circle_number(draw, letters[i], cx + 45, cy + _OPT_H // 2,
                           radius=22, bg_color=lc, font_size=26)

        # Option text
        of, _, _, _ = fit_text_font(opt, 40, 28, _OPT_W - 120)
        th = _text_h(draw, opt, of)
        tc = ((30, 140, 60) if is_correct else
              (160, 155, 170) if is_wrong else _TEXT_DARK)
        draw_text_solid(draw, opt, cx + 85, cy + (_OPT_H - th) // 2 - 1,
                        of, tc, card_alpha, outline=0)

        # Sparkles on correct answer
        if is_correct:
            draw_sparkles(draw, cx + _OPT_W // 2, cy + _OPT_H // 2,
                          t, answer_time, radius=100)

    return draw


# ── Main entry point ─────────────────────────────────────────────

def create_frame_fill_blank(
    t: float,
    data: Dict,
    duration: float,
) -> np.ndarray:
    """Create frame for fill-in-the-blank video type — card-based layout."""
    frame, draw = create_base_frame(t)

    sentence = data.get('sentence', 'I ___ to school')
    options = data.get('options', ['go', 'went', 'gone', 'going'])
    correct = data.get('correct', options[0] if options else '')
    translation = data.get('translation', '')
    st = data.get('segment_times', {})

    if st:
        options_start = seg_start(st, 'options', duration * 0.20)
        answer_time = seg_start(st, 'answer', duration * 0.75)
    else:
        options_start = duration * 0.20
        answer_time = duration * 0.75

    if t < 0.05 and st:
        log_segment_timestamps(st, 'fill_blank', _FB_SEGMENT_KEYS)

    show_answer = t >= answer_time

    # ── 1. Sentence card with blank highlighting ────────────────────
    draw = _draw_sentence_card(t, draw, frame, sentence, correct,
                               show_answer, answer_time)

    # ── 2. Stacked option cards ─────────────────────────────────────
    if t > options_start:
        draw = _draw_option_cards(t, draw, frame, options, correct,
                                  show_answer, options_start, answer_time)

    # ── 3. Timer bar + countdown number ─────────────────────────────
    cd3 = seg_start(st, 'countdown_3', 0)
    if cd3 > 0 and t >= cd3 and not show_answer:
        cd1_end = seg_end(st, 'countdown_1', answer_time)
        total = cd1_end - cd3
        remaining = max(0, cd1_end - t) / total if total > 0 else 0
        draw_progress_timer_bar(draw, frame, TIMER_BAR_X, TIMER_BAR_Y,
                                TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT, remaining)
        draw = ImageDraw.Draw(frame, 'RGBA')

        number, ns = resolve_countdown_number(t, st)
        if number is not None:
            _draw_countdown_number(draw, frame, number, VIDEO_WIDTH // 2,
                                   _COUNTDOWN_CY, t, ns)
    elif not st:
        # Legacy fallback for old audio without segment_times
        opt_end = duration * 0.55
        timer_end = duration * 0.75
        if opt_end < t < timer_end:
            p = (t - opt_end) / (timer_end - opt_end)
            n = 3 if p < 0.33 else (2 if p < 0.66 else 1)
            _draw_countdown_number(draw, frame, n, VIDEO_WIDTH // 2,
                                   _COUNTDOWN_CY, t, t - 0.05)

    # ── 4. Translation pill badge ───────────────────────────────────
    if show_answer and translation:
        ta = get_alpha(t, answer_time + 0.5, 0.3)
        if ta > 0:
            draw_pill_badge(frame, draw, translation,
                            VIDEO_WIDTH // 2, _TRANSLATION_CY,
                            font_size=30, bg_color=(60, 60, 90),
                            text_color=(220, 220, 240),
                            padding_x=28, padding_y=12)
            draw = ImageDraw.Draw(frame, 'RGBA')

    # Trigger character excitement on answer reveal
    if show_answer and answer_time > 0 and abs(t - answer_time) < 0.05:
        try:
            from .character import get_character_renderer
            char = get_character_renderer()
            if char:
                char.trigger_excitement(t)
        except Exception:
            pass

    return finalize_frame(frame, draw, t, duration, words=data.get('words', []))

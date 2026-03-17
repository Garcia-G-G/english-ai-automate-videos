"""True/false video frame generator — card-based modern TikTok design."""

import math
import logging
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_out_back, ease_out_cubic, ease_out_elastic,
    get_alpha, pulse_scale, glow_intensity,
    spring_animation, tiktok_pop_scale,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, QUIZ_COLORS,
    COLOR_WHITE, COLOR_YELLOW, TEXT_AREA_WIDTH,
    SAFE_AREA_BOTTOM, VISUAL_ANTICIPATION,
)
from config.layout import (
    TF_QUESTION_ZONE_TOP as QUESTION_ZONE_TOP,
    TF_QUESTION_ZONE_BOTTOM as QUESTION_ZONE_BOTTOM,
    TF_QUESTION_ZONE_HEIGHT as QUESTION_ZONE_HEIGHT,
    TF_COUNTDOWN_CENTER_Y as COUNTDOWN_CENTER_Y,
    TF_BUTTONS_ZONE_CENTER as BUTTONS_ZONE_CENTER,
    TF_EXPLANATION_ZONE_TOP as EXPLANATION_ZONE_TOP,
    TF_BTN_WIDTH as BTN_WIDTH,
    TF_BTN_HEIGHT as BTN_HEIGHT,
    TF_BTN_GAP as BTN_GAP,
    TF_BTN_RADIUS as BTN_RADIUS,
    CARD_MARGIN_X, CARD_WIDTH, CARD_RADIUS,
    TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT, TIMER_BAR_Y, TIMER_BAR_X,
)
from config.colors import (
    VERDADERO_GRAD_TOP, VERDADERO_GRAD_BOT,
    FALSO_GRAD_TOP, FALSO_GRAD_BOT,
    NEUTRAL_GRAD_TOP, NEUTRAL_GRAD_BOT,
    COUNTDOWN_COLORS,
)
from config.timing import (
    TF_SLIDE_DURATION as SLIDE_DURATION,
    TF_QUESTION_FADE_DURATION as QUESTION_FADE_DURATION,
)
from .utils import (
    font, line_break, draw_text_solid, draw_text_centered,
    draw_progress_bar, draw_sparkles, draw_gradient_rounded_rect,
    fit_text_font, draw_rounded_card, draw_progress_timer_bar,
    create_base_frame, finalize_frame,
    seg_start as _seg_start, seg_end as _seg_end,
    log_segment_timestamps, resolve_countdown_number,
)

logger = logging.getLogger(__name__)

# Teal accent color for statement card
_ACCENT_TEAL = (0, 180, 200)


def parse_true_false_timestamps(data: Dict) -> Dict:
    """Parse word timestamps for true/false video."""
    words = data.get('words', [])
    duration = data.get('duration', 10)

    ts = {
        'statement_end': 0,
        'options_start': 0,
        'countdown_start': 0,
        'countdown_3': 0,
        'countdown_2': 0,
        'countdown_1': 0,
        'answer_start': 0,
    }

    for i, w in enumerate(words):
        word = w['word'].lower().strip('¿?.,!')
        start = w['start']

        if word in ['verdadero', 'falso'] and ts['options_start'] == 0:
            ts['options_start'] = start
            if i > 0:
                ts['statement_end'] = words[i-1].get('end', start - 0.5)

        if word in ['piensa', 'piensalo'] and ts['countdown_start'] == 0:
            ts['countdown_start'] = start
        if word in ['tres', '3'] and ts['countdown_3'] == 0:
            ts['countdown_3'] = start
        if word in ['dos', '2'] and ts['countdown_2'] == 0:
            ts['countdown_2'] = start
        if word in ['uno', '1'] and ts['countdown_1'] == 0:
            ts['countdown_1'] = start

        if word == 'respuesta' and ts['answer_start'] == 0:
            for j in range(max(0, i-2), i):
                if words[j]['word'].lower() == 'la':
                    ts['answer_start'] = words[j]['start']
                    break
            if ts['answer_start'] == 0:
                ts['answer_start'] = start

    if ts['options_start'] == 0:
        ts['options_start'] = duration * 0.15
    if ts['statement_end'] == 0:
        ts['statement_end'] = ts['options_start'] - 0.5
    if ts['countdown_start'] == 0:
        ts['countdown_start'] = ts['options_start'] + 1.5
    if ts['answer_start'] == 0:
        ts['answer_start'] = duration * 0.40

    return ts


def resolve_true_false_timestamps(data: Dict, duration: float) -> Dict:
    """Ensure segment_times is populated for true/false videos."""
    segment_times = data.get('segment_times', {})

    required = {'options', 'answer'}
    has_segments = bool(segment_times) and required.issubset(segment_times.keys())

    if has_segments:
        logger.info("True/false timestamps: using segment_times (exact)")
        return data

    logger.info("True/false timestamps: falling back to parse_true_false_timestamps")

    ts = parse_true_false_timestamps(data)

    def _entry(start: float, end: float = None) -> Dict:
        if end is None:
            end = start + 0.5
        return {'start': start, 'end': end, 'duration': end - start}

    segment_times = {
        'statement':   _entry(0.0, ts['statement_end']),
        'options':     _entry(ts['options_start']),
        'think':       _entry(ts['countdown_start']),
        'countdown_3': _entry(ts['countdown_3']) if ts['countdown_3'] > 0 else {},
        'countdown_2': _entry(ts['countdown_2']) if ts['countdown_2'] > 0 else {},
        'countdown_1': _entry(ts['countdown_1']) if ts['countdown_1'] > 0 else {},
        'answer':      _entry(ts['answer_start']),
    }

    segment_times = {k: v for k, v in segment_times.items() if v}

    data['segment_times'] = segment_times
    return data


# ── Helper: draw gradient button ──────────────────────────────────

def _draw_button(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    text: str,
    x: int, y: int,
    w: int, h: int,
    grad_top, grad_bot,
    alpha: int = 255,
    border_color=None,
    border_width: int = 0,
    glow_color=None,
    glow_strength: float = 0.0,
):
    """Draw a gradient rounded-rectangle button with text."""
    # Glow behind button
    if glow_color and glow_strength > 0:
        glow_expand = int(12 * glow_strength)
        glow_alpha = int(120 * glow_strength)
        glow_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.rounded_rectangle(
            [x - glow_expand, y - glow_expand,
             x + w + glow_expand, y + h + glow_expand],
            radius=BTN_RADIUS + glow_expand,
            fill=(*glow_color[:3], glow_alpha),
        )
        frame.paste(glow_layer, (0, 0), glow_layer)

    # Drop shadow (skip for faded-out wrong buttons)
    if alpha > 100:
        shadow_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        sa = int(50 * (alpha / 255))
        sd.rounded_rectangle(
            [x + 3, y + 4, x + w + 3, y + h + 4],
            radius=BTN_RADIUS,
            fill=(0, 0, 0, sa),
        )
        frame.paste(shadow_layer, (0, 0), shadow_layer)

    # Gradient fill
    draw_gradient_rounded_rect(
        frame, x, y, x + w, y + h,
        radius=BTN_RADIUS,
        color1=grad_top, color2=grad_bot,
        alpha=alpha,
    )

    # Border
    if border_color and border_width > 0:
        if len(border_color) == 3:
            bc = (*border_color, alpha)
        else:
            bc = (*border_color[:3], min(alpha, border_color[3]))
        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=BTN_RADIUS, fill=None, outline=bc, width=border_width,
        )

    # Text label
    tf = font(52)
    bbox = draw.textbbox((0, 0), text, font=tf)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2 - 2
    draw_text_solid(draw, text, tx, ty, tf, COLOR_WHITE, alpha, outline=5)


# ── Helper: countdown number (no ring) ────────────────────────────

def _draw_countdown_number(
    draw: ImageDraw.Draw,
    number: int,
    center_x: int,
    center_y: int,
    t: float,
    start_time: float,
):
    """Draw large countdown number with pop + glow, no ring."""
    elapsed = t - start_time
    if elapsed < 0:
        return

    # Pop-in with tiktok_pop_scale
    scale = tiktok_pop_scale(t, start_time, duration=0.20)
    if scale <= 0:
        return

    # Gentle pulse after pop-in settles
    if elapsed > 0.20:
        pulse_t = elapsed - 0.20
        scale = 1.0 + 0.04 * math.sin(pulse_t * 5)

    alpha = min(255, int(255 * ease_out_cubic(min(1.0, elapsed / 0.10))))

    color = COUNTDOWN_COLORS.get(number, (255, 255, 255))

    font_size = max(80, int(180 * scale))
    tf = font(font_size)
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=tf)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 5

    # Glow layers (wider strokes at lower alpha)
    for glow_offset in [8, 4]:
        ga = int(alpha * 0.18)
        draw.text(
            (tx, ty), text, font=tf,
            fill=(*color, ga),
            stroke_width=glow_offset + 4,
            stroke_fill=(*color, ga // 2),
        )

    # Shadow
    draw.text(
        (tx + 2, ty + 2), text, font=tf,
        fill=(20, 20, 40, int(alpha * 0.4)),
    )

    # Main number
    draw.text(
        (tx, ty), text, font=tf,
        fill=(255, 255, 255, alpha),
        stroke_width=4,
        stroke_fill=(*color, alpha),
    )


# ── Main frame generator ──────────────────────────────────────────

def create_frame_true_false(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for true/false video type with card-based modern design."""
    frame, draw = create_base_frame(t)

    statement = data.get('statement', 'Statement')
    correct = data.get('correct', True)
    explanation = data.get('explanation', '')

    st = data.get('segment_times', {})

    if t < 0.05 and st:
        log_segment_timestamps(st, 'true/false', [
            'statement', 'options', 'think', 'countdown_3',
            'countdown_2', 'countdown_1', 'answer', 'explanation',
        ])

    # Timestamps
    stmt_end = _seg_end(st, 'statement', duration * 0.15)
    opt_start = _seg_start(st, 'options', stmt_end + 0.3)
    timer_start = _seg_start(st, 'think', opt_start + 1.0)
    countdown_3_start = _seg_start(st, 'countdown_3', 0)
    answer_time = _seg_start(st, 'answer', duration * 0.7)
    explain_start = _seg_start(st, 'explanation', answer_time + 1.5)

    show_answer = t >= answer_time

    # ── Phase 1: Statement in white card ───────────────────────────
    card_padding = 36
    max_text_w = CARD_WIDTH - card_padding * 2
    max_text_h = QUESTION_ZONE_HEIGHT - card_padding * 2

    qf, q_font_size, q_lines, total_text_h = fit_text_font(
        statement, 56, 36, max_text_w, max_text_h,
    )

    line_h = int(q_font_size * 1.4)
    card_inner_h = len(q_lines) * line_h + card_padding * 2
    card_y = QUESTION_ZONE_TOP + (QUESTION_ZONE_HEIGHT - card_inner_h) // 2

    # Spring animation for card pop-in
    card_spring = spring_animation(t, 0.0, duration=0.45)
    card_alpha_raw = get_alpha(t, 0, QUESTION_FADE_DURATION)

    if card_spring > 0 and card_alpha_raw > 0:
        # Scale the card alpha with spring progress
        card_alpha = int(235 * (card_alpha_raw / 255) * min(1.0, card_spring * 1.1))

        # Slight vertical offset during spring (bounce in from above)
        spring_offset = int(30 * (1.0 - min(1.0, card_spring)))
        card_draw_y = card_y - spring_offset

        draw_rounded_card(
            frame, CARD_MARGIN_X, card_draw_y, CARD_WIDTH, card_inner_h,
            radius=CARD_RADIUS,
            fill=(255, 255, 255),
            alpha=card_alpha,
            shadow=True,
            shadow_offset=5,
            shadow_alpha=int(50 * (card_alpha_raw / 255)),
        )

        # Teal accent bar at top of card (4px)
        accent_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        ad = ImageDraw.Draw(accent_layer)
        accent_h = 4
        accent_inset = 20
        ad.rounded_rectangle(
            [CARD_MARGIN_X + accent_inset, card_draw_y + 10,
             CARD_MARGIN_X + CARD_WIDTH - accent_inset, card_draw_y + 10 + accent_h],
            radius=2,
            fill=(*_ACCENT_TEAL, card_alpha),
        )
        frame.paste(accent_layer, (0, 0), accent_layer)

        # Re-acquire draw after compositing
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Dark text on white card
        text_color = QUIZ_COLORS['text_dark']
        text_y = card_draw_y + card_padding
        for line in q_lines:
            bbox = draw.textbbox((0, 0), line, font=qf)
            lw = bbox[2] - bbox[0]
            lx = (VIDEO_WIDTH - lw) // 2
            draw.text((lx, text_y), line, font=qf, fill=(*text_color, card_alpha_raw))
            text_y += line_h

    # ── Phase 2: Buttons slide in ─────────────────────────────────
    if t > opt_start:
        btn_elapsed = t - opt_start

        total_w = BTN_WIDTH * 2 + BTN_GAP
        base_x_left = (VIDEO_WIDTH - total_w) // 2
        base_x_right = base_x_left + BTN_WIDTH + BTN_GAP
        btn_y = BUTTONS_ZONE_CENTER - BTN_HEIGHT // 2

        # VERDADERO slides from LEFT
        left_progress = min(1.0, btn_elapsed / SLIDE_DURATION)
        left_eased = ease_out_back(left_progress)
        left_offset = int(-600 * (1 - left_eased))
        true_x = base_x_left + left_offset
        true_alpha = int(255 * min(1.0, btn_elapsed / 0.3))

        # FALSO slides from RIGHT (slight delay)
        right_delay = 0.08
        right_elapsed = max(0, btn_elapsed - right_delay)
        right_progress = min(1.0, right_elapsed / SLIDE_DURATION)
        right_eased = ease_out_back(right_progress)
        right_offset = int(600 * (1 - right_eased))
        false_x = base_x_right + right_offset
        false_alpha = int(255 * min(1.0, right_elapsed / 0.3))

        # Button labels with emoji
        true_label = "\u2713 VERDADERO"
        false_label = "\u2717 FALSO"

        if show_answer:
            answer_elapsed = t - answer_time

            if correct:
                # VERDADERO is correct
                true_glow = glow_intensity(t, answer_time)
                true_ps = pulse_scale(t, answer_time)
                true_grad_top = VERDADERO_GRAD_TOP
                true_grad_bot = VERDADERO_GRAD_BOT
                true_border = (180, 255, 180)
                true_border_w = max(3, int(5 * true_glow))
                true_glow_c = (100, 255, 140)
                true_glow_s = true_glow * 0.8

                # Wrong fades to 25% + 10px outward slide
                wrong_slide = int(10 * min(1.0, answer_elapsed / 0.4))
                false_alpha = max(40, int(255 * 0.25))
                false_grad_top = (140, 140, 150)
                false_grad_bot = (100, 100, 110)
                false_border = None
                false_border_w = 0
                false_glow_c = None
                false_glow_s = 0
                false_x = base_x_right + wrong_slide

                # Draw wrong button first (behind)
                _draw_button(
                    frame, draw, false_label,
                    false_x, btn_y, BTN_WIDTH, BTN_HEIGHT,
                    false_grad_top, false_grad_bot,
                    alpha=false_alpha,
                )
                draw = ImageDraw.Draw(frame, 'RGBA')

                # Draw correct button with pulse
                scaled_w = int(BTN_WIDTH * true_ps)
                scaled_h = int(BTN_HEIGHT * true_ps)
                scaled_x = base_x_left - (scaled_w - BTN_WIDTH) // 2
                scaled_y = btn_y - (scaled_h - BTN_HEIGHT) // 2
                _draw_button(
                    frame, draw, true_label,
                    scaled_x, scaled_y, scaled_w, scaled_h,
                    true_grad_top, true_grad_bot,
                    alpha=255,
                    border_color=true_border, border_width=true_border_w,
                    glow_color=true_glow_c, glow_strength=true_glow_s,
                )
                draw = ImageDraw.Draw(frame, 'RGBA')

            else:
                # FALSO is correct
                false_glow = glow_intensity(t, answer_time)
                false_ps = pulse_scale(t, answer_time)
                false_grad_top = FALSO_GRAD_TOP
                false_grad_bot = FALSO_GRAD_BOT
                false_border = (255, 180, 180)
                false_border_w = max(3, int(5 * false_glow))
                false_glow_c = (255, 100, 100)
                false_glow_s = false_glow * 0.8

                # Wrong fades to 25% + 10px outward slide
                wrong_slide = int(10 * min(1.0, answer_elapsed / 0.4))
                true_alpha = max(40, int(255 * 0.25))
                true_grad_top = (140, 140, 150)
                true_grad_bot = (100, 100, 110)
                true_border = None
                true_border_w = 0
                true_glow_c = None
                true_glow_s = 0
                true_x = base_x_left - wrong_slide

                # Draw wrong button first (behind)
                _draw_button(
                    frame, draw, true_label,
                    true_x, btn_y, BTN_WIDTH, BTN_HEIGHT,
                    true_grad_top, true_grad_bot,
                    alpha=true_alpha,
                )
                draw = ImageDraw.Draw(frame, 'RGBA')

                # Draw correct button with pulse
                scaled_w = int(BTN_WIDTH * false_ps)
                scaled_h = int(BTN_HEIGHT * false_ps)
                scaled_x = base_x_right - (scaled_w - BTN_WIDTH) // 2
                scaled_y = btn_y - (scaled_h - BTN_HEIGHT) // 2
                _draw_button(
                    frame, draw, false_label,
                    scaled_x, scaled_y, scaled_w, scaled_h,
                    false_grad_top, false_grad_bot,
                    alpha=255,
                    border_color=false_border, border_width=false_border_w,
                    glow_color=false_glow_c, glow_strength=false_glow_s,
                )
                draw = ImageDraw.Draw(frame, 'RGBA')

            # Sparkles on correct button
            if answer_elapsed > 0.2:
                sparkle_cx = (base_x_left if correct else base_x_right) + BTN_WIDTH // 2
                sparkle_cy = btn_y + BTN_HEIGHT // 2
                draw_sparkles(draw, sparkle_cx, sparkle_cy, t, answer_time + 0.2, radius=120)

        else:
            # Before answer: neutral colored buttons with emoji labels
            _draw_button(
                frame, draw, true_label,
                true_x, btn_y, BTN_WIDTH, BTN_HEIGHT,
                NEUTRAL_GRAD_TOP, NEUTRAL_GRAD_BOT,
                alpha=true_alpha,
                border_color=(255, 255, 255), border_width=3,
            )
            draw = ImageDraw.Draw(frame, 'RGBA')

            _draw_button(
                frame, draw, false_label,
                false_x, btn_y, BTN_WIDTH, BTN_HEIGHT,
                NEUTRAL_GRAD_TOP, NEUTRAL_GRAD_BOT,
                alpha=false_alpha,
                border_color=(255, 255, 255), border_width=3,
            )
            draw = ImageDraw.Draw(frame, 'RGBA')

    # ── Phase 3: Countdown (timer bar + large number, no ring) ─────
    show_countdown = countdown_3_start > 0 and t >= countdown_3_start and not show_answer

    if show_countdown:
        # Timer bar depleting at bottom
        countdown_total = answer_time - countdown_3_start
        if countdown_total > 0:
            time_in_countdown = t - countdown_3_start
            timer_progress = max(0.0, 1.0 - time_in_countdown / countdown_total)
        else:
            timer_progress = 0.0

        draw_progress_timer_bar(
            draw, frame,
            TIMER_BAR_X, TIMER_BAR_Y,
            TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT,
            timer_progress,
        )
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Large countdown number
        number, num_start = resolve_countdown_number(t, st)
        if number is not None:
            _draw_countdown_number(
                draw, number, VIDEO_WIDTH // 2, COUNTDOWN_CENTER_Y,
                t, num_start,
            )

    # ── Phase 4: Explanation in card with slide-up ─────────────────
    if show_answer and explanation:
        exp_delay = 0.6
        exp_appear = answer_time + exp_delay
        exp_alpha = get_alpha(t, exp_appear, 0.35)

        if exp_alpha > 0:
            # Slide-up from bottom
            slide_elapsed = t - exp_appear
            slide_progress = min(1.0, max(0.0, slide_elapsed / 0.4))
            slide_offset = int(60 * (1.0 - ease_out_cubic(slide_progress)))

            exp_y_base = EXPLANATION_ZONE_TOP
            exp_y = exp_y_base + slide_offset
            exp_padding = 28
            max_exp_w = CARD_WIDTH - exp_padding * 2
            max_exp_h = SAFE_AREA_BOTTOM - exp_y - exp_padding * 2

            clean_exp = explanation.replace("'", "").strip()
            ef, exp_font_size, exp_lines, exp_text_h = fit_text_font(
                clean_exp, 42, 28, max_exp_w, max_exp_h,
            )
            exp_line_h = int(exp_font_size * 1.4)
            exp_height = len(exp_lines) * exp_line_h + exp_padding * 2

            # Light card
            card_a = int(220 * (exp_alpha / 255))
            draw_rounded_card(
                frame, CARD_MARGIN_X, exp_y, CARD_WIDTH, exp_height,
                radius=20,
                fill=(240, 250, 248),   # Very light teal tint
                alpha=card_a,
                shadow=True,
                shadow_offset=4,
                shadow_alpha=int(45 * (exp_alpha / 255)),
            )
            draw = ImageDraw.Draw(frame, 'RGBA')

            # Small teal accent at top of card
            acc_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
            acd = ImageDraw.Draw(acc_layer)
            acc_w = 50
            acc_h = 4
            acc_x = (VIDEO_WIDTH - acc_w) // 2
            acd.rounded_rectangle(
                [acc_x, exp_y + 8, acc_x + acc_w, exp_y + 8 + acc_h],
                radius=2,
                fill=(*_ACCENT_TEAL, exp_alpha),
            )
            frame.paste(acc_layer, (0, 0), acc_layer)
            draw = ImageDraw.Draw(frame, 'RGBA')

            # Dark text on light card
            text_color = QUIZ_COLORS['text_dark']
            text_y = exp_y + exp_padding
            for line in exp_lines:
                bbox = draw.textbbox((0, 0), line, font=ef)
                lw = bbox[2] - bbox[0]
                lx = (VIDEO_WIDTH - lw) // 2
                draw.text((lx, text_y), line, font=ef, fill=(*text_color, exp_alpha))
                text_y += exp_line_h

    return finalize_frame(frame, draw, t, duration, words=data.get('words', []))

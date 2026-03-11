"""Quiz video frame generator — question, options, countdown, answer reveal."""

import math
import logging
from typing import List, Dict, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_out_cubic, ease_out_elastic, ease_in_out_sine,
    get_alpha, get_scale, pulse_scale, glow_intensity,
    tiktok_pop_scale,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, QUIZ_COLORS, COLOR_WHITE, COLOR_YELLOW,
    FONT_SIZE_QUESTION, TEXT_AREA_WIDTH,
    SAFE_AREA_TOP, SAFE_AREA_BOTTOM, VISUAL_ANTICIPATION,
)
from config.layout import (
    QUIZ_QUESTION_ZONE_TOP as QUESTION_ZONE_TOP,
    QUIZ_QUESTION_ZONE_BOTTOM as QUESTION_ZONE_BOTTOM,
    QUIZ_OPTIONS_ZONE_TOP as OPTIONS_ZONE_TOP,
    QUIZ_OPTIONS_ZONE_BOTTOM as OPTIONS_ZONE_BOTTOM,
    QUIZ_COUNTDOWN_ZONE_TOP as COUNTDOWN_ZONE_TOP,
    CARD_MARGIN_X, CARD_RADIUS, CARD_WIDTH,
    TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT, TIMER_BAR_Y, TIMER_BAR_X,
)
from config.colors import COUNTDOWN_COLORS, DIFFICULTY_COLORS
from .utils import (
    font, line_break, draw_text_solid, draw_text_centered,
    draw_progress_bar, draw_sparkles, slide_in_x,
    fit_text_font,
    draw_rounded_card, draw_circle_number, draw_progress_timer_bar,
    draw_difficulty_badge,
    create_base_frame, finalize_frame,
    seg_start as _seg_start, seg_end as _seg_end,
    log_segment_timestamps, resolve_countdown_number,
)

logger = logging.getLogger(__name__)


def find_word_time(words: List[Dict], target: str, start_from: int = 0) -> Tuple[Optional[float], int]:
    """Find the timestamp when a specific word is spoken."""
    target_lower = target.lower().strip('.,!?')
    for i in range(start_from, len(words)):
        word = words[i]['word'].lower().strip('.,!?')
        if word == target_lower:
            return words[i]['start'], i
    return None, start_from


def find_phrase_time(words: List[Dict], phrase: str, start_from: int = 0) -> Optional[float]:
    """Find when a phrase starts in the word list."""
    phrase_words = phrase.lower().split()
    if not phrase_words:
        return None

    first_word = phrase_words[0].strip('.,!?')
    time, _ = find_word_time(words, first_word, start_from)
    return time


def parse_quiz_timestamps(words: List[Dict]) -> Dict[str, float]:
    """Parse TTS timestamps to find key moments in quiz audio."""
    timestamps = {
        'question_start': 0.0,
        'question_end': 0.0,
        'options_start': 0.0,
        'option_a': 0.0,
        'option_b': 0.0,
        'option_c': 0.0,
        'option_d': 0.0,
        'think_start': 0.0,
        'countdown_3': 0.0,
        'countdown_2': 0.0,
        'countdown_1': 0.0,
        'answer_start': 0.0,
        'explanation_start': 0.0,
    }

    if not words:
        return timestamps

    timestamps['question_start'] = words[0]['start']

    for i, w in enumerate(words):
        word_lower = w['word'].lower()
        if word_lower in ['inglés', 'ingles', 'english']:
            timestamps['question_end'] = w['end']
            break

    answer_boundary = 999.0
    for i, w in enumerate(words):
        if w['word'].lower() == 'la' and i + 1 < len(words):
            if words[i + 1]['word'].lower() in ['respuesta', 'answer']:
                answer_boundary = w['start']
                break
        if w['word'].lower() in ['correcta', 'correct']:
            answer_boundary = w['start']
            break

    for i, w in enumerate(words):
        word = w['word'].upper().strip('.,!?:;')
        start = w['start']

        if start < timestamps['question_end'] or start >= answer_boundary:
            continue

        if word == 'A' and timestamps['option_a'] == 0:
            timestamps['option_a'] = start
        elif word == 'B' and timestamps['option_b'] == 0:
            timestamps['option_b'] = start
        elif word == 'C' and timestamps['option_c'] == 0:
            timestamps['option_c'] = start
        elif word == 'D' and timestamps['option_d'] == 0:
            timestamps['option_d'] = start
        elif word in ['SE', 'SI', 'SEA', 'CEE', 'THEY', 'THE'] and timestamps['option_c'] == 0:
            timestamps['option_c'] = start

    piensa_time = answer_boundary
    for i, w in enumerate(words):
        if w['word'].lower() in ['piensa', 'piensalo', 'think']:
            piensa_time = w['start']
            break

    if timestamps['option_a'] > 0 and piensa_time > timestamps['option_a']:
        options_duration = piensa_time - timestamps['option_a']
        gap = options_duration / 4

        if 0.8 <= gap <= 2.5:
            if timestamps['option_b'] == 0:
                timestamps['option_b'] = timestamps['option_a'] + gap
            if timestamps['option_c'] == 0:
                timestamps['option_c'] = timestamps['option_a'] + gap * 2
            if timestamps['option_d'] == 0:
                timestamps['option_d'] = timestamps['option_a'] + gap * 3

    detected = []
    if timestamps['option_a'] > 0: detected.append(('A', timestamps['option_a']))
    if timestamps['option_b'] > 0: detected.append(('B', timestamps['option_b']))
    if timestamps['option_c'] > 0: detected.append(('C', timestamps['option_c']))
    if timestamps['option_d'] > 0: detected.append(('D', timestamps['option_d']))

    if len(detected) >= 2:
        detected.sort(key=lambda x: x[1])
        total_gap = detected[-1][1] - detected[0][1]
        num_gaps = ord(detected[-1][0]) - ord(detected[0][0])
        avg_gap = total_gap / max(num_gaps, 1) if num_gaps > 0 else 1.0

        avg_gap = max(0.8, min(1.8, avg_gap))

        if timestamps['option_a'] > 0:
            if timestamps['option_b'] == 0:
                timestamps['option_b'] = timestamps['option_a'] + avg_gap
            if timestamps['option_c'] == 0:
                timestamps['option_c'] = timestamps['option_a'] + avg_gap * 2
            if timestamps['option_d'] == 0:
                timestamps['option_d'] = timestamps['option_a'] + avg_gap * 3

    if timestamps['option_a'] == 0:
        base_time = timestamps['question_end'] if timestamps['question_end'] > 0 else 1.5
        timestamps['option_a'] = base_time + 0.3
    if timestamps['option_b'] == 0:
        timestamps['option_b'] = timestamps['option_a'] + 1.0
    if timestamps['option_c'] == 0:
        timestamps['option_c'] = timestamps['option_b'] + 1.0
    if timestamps['option_d'] == 0:
        timestamps['option_d'] = timestamps['option_c'] + 1.0

    if timestamps['option_b'] > 0 and timestamps['option_b'] <= timestamps['option_a']:
        timestamps['option_b'] = timestamps['option_a'] + 1.2
    if timestamps['option_c'] > 0 and timestamps['option_c'] <= timestamps['option_b']:
        timestamps['option_c'] = timestamps['option_b'] + 1.2
    if timestamps['option_d'] > 0 and timestamps['option_d'] <= timestamps['option_c']:
        timestamps['option_d'] = timestamps['option_c'] + 1.2

    for i, w in enumerate(words):
        word_lower = w['word'].lower()
        if word_lower in ['piensalo', 'piensa', 'think', 'bien']:
            if w['start'] > timestamps['option_d']:
                timestamps['think_start'] = w['start']
                break

    for i, w in enumerate(words):
        word_lower = w['word'].lower().strip('.,!?')
        start = w['start']

        if timestamps['think_start'] > 0 and start < timestamps['think_start']:
            continue

        if word_lower in ['tres', 'three', '3'] and timestamps['countdown_3'] == 0:
            timestamps['countdown_3'] = start
        elif word_lower in ['dos', 'two', '2'] and timestamps['countdown_2'] == 0:
            timestamps['countdown_2'] = start
        elif word_lower in ['uno', 'one', '1'] and timestamps['countdown_1'] == 0:
            timestamps['countdown_1'] = start

    for i, w in enumerate(words):
        word_lower = w['word'].lower()

        if word_lower == 'la' and i + 1 < len(words):
            next_word = words[i + 1]['word'].lower()
            if next_word in ['respuesta', 'answer']:
                timestamps['answer_start'] = w['start']
                for j in range(i + 3, min(i + 12, len(words))):
                    if words[j]['word'].lower() in ['significa', 'means', 'es', 'como']:
                        timestamps['explanation_start'] = words[j]['start']
                        break
                break

        elif word_lower == 'correcta' and timestamps['answer_start'] == 0:
            for j in range(max(0, i - 3), i):
                if words[j]['word'].lower() in ['la', 'es']:
                    timestamps['answer_start'] = words[j]['start']
                    break
            if timestamps['answer_start'] == 0:
                timestamps['answer_start'] = w['start']

    return timestamps


def draw_quiz_timeline(draw: ImageDraw.Draw, progress: float, is_countdown: bool = False):
    """Draw animated timeline at top of quiz."""
    timeline_y = 100
    timeline_h = 8
    timeline_margin = 50

    bar_w = VIDEO_WIDTH - (timeline_margin * 2)

    draw.rounded_rectangle(
        [timeline_margin, timeline_y, timeline_margin + bar_w, timeline_y + timeline_h],
        radius=timeline_h // 2,
        fill=(255, 255, 255, 100)
    )

    if progress > 0.01:
        fill_w = max(timeline_h, int(bar_w * progress))

        if is_countdown:
            if progress < 0.33:
                color = (100, 220, 160, 255)
            elif progress < 0.66:
                color = (255, 200, 100, 255)
            else:
                color = (255, 130, 130, 255)
        else:
            color = (255, 150, 180, 255)

        draw.rounded_rectangle(
            [timeline_margin, timeline_y, timeline_margin + fill_w, timeline_y + timeline_h],
            radius=timeline_h // 2,
            fill=color
        )

        dot_x = timeline_margin + fill_w
        dot_r = 12
        pulse = 1.0 + 0.15 * math.sin(progress * 20)
        actual_r = int(dot_r * pulse)
        draw.ellipse(
            [dot_x - actual_r, timeline_y + timeline_h//2 - actual_r,
             dot_x + actual_r, timeline_y + timeline_h//2 + actual_r],
            fill=color
        )


# ── Upgraded rendering functions ─────────────────────────────────


def draw_quiz_question_box(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    question: str,
    y: int,
    alpha: int = 255,
    max_height: int = None,
    accent_color: Tuple = None,
):
    """Draw a white card question box with dark text and optional accent bar."""
    box_padding = 40
    max_width = CARD_WIDTH - box_padding * 2

    if max_height is None:
        max_height = QUESTION_ZONE_BOTTOM - y - 40

    # Dynamic font sizing (min 40px per spec)
    ef, font_size, lines, text_h = fit_text_font(
        question, 52, 40, max_width, max_height - box_padding * 2
    )

    line_height = int(font_size * 1.4)
    box_height = len(lines) * line_height + box_padding * 2

    # White rounded card with shadow
    card_alpha = int(235 * (alpha / 255))
    draw_rounded_card(
        frame, CARD_MARGIN_X, y, CARD_WIDTH, box_height,
        radius=CARD_RADIUS,
        fill=(255, 255, 255),
        alpha=card_alpha,
        shadow=True,
        shadow_offset=5,
        shadow_alpha=int(60 * (alpha / 255)),
    )

    # Colored accent bar on left side
    if accent_color:
        accent_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        ad = ImageDraw.Draw(accent_layer)
        accent_w = 8
        accent_pad = 14
        ad.rounded_rectangle(
            [CARD_MARGIN_X + accent_pad, y + accent_pad,
             CARD_MARGIN_X + accent_pad + accent_w, y + box_height - accent_pad],
            radius=4,
            fill=(*accent_color[:3], alpha),
        )
        frame.paste(accent_layer, (0, 0), accent_layer)

    # Re-acquire draw after card compositing
    draw = ImageDraw.Draw(frame, 'RGBA')

    # Dark text, centered
    text_color = QUIZ_COLORS['text_dark']
    text_y = y + box_padding
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=ef)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2
        draw.text((lx, text_y), line, font=ef, fill=(*text_color, alpha))
        text_y += line_height

    return y + box_height


def draw_quiz_option_card(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    letter: str,
    text: str,
    x: int, y: int,
    width: int, height: int,
    alpha: int = 255,
    x_offset: int = 0,
    is_correct: bool = False,
    is_wrong: bool = False,
    show_result: bool = False,
    glow: float = 0.0,
    pulse_val: float = 1.0,
):
    """Draw a quiz option as a rounded card with circle letter."""
    if alpha <= 0:
        return draw

    actual_x = x + x_offset
    circle_r = 26
    circle_margin = 18
    text_left = circle_margin + circle_r * 2 + 18

    # Determine colors based on state
    if show_result and is_correct:
        card_fill = (225, 250, 232)    # Light green tint
        card_alpha = alpha
        circle_bg = QUIZ_COLORS['correct_green']
        text_color = QUIZ_COLORS['text_dark']
    elif show_result and is_wrong:
        card_fill = (240, 238, 245)    # Light grey-purple
        card_alpha = int(alpha * 0.40)
        circle_bg = QUIZ_COLORS['wrong_fade']
        text_color = QUIZ_COLORS['wrong_text']
    else:
        card_fill = (255, 255, 255)
        card_alpha = int(alpha * 0.92)
        circle_bg = QUIZ_COLORS['letter_circle']
        text_color = QUIZ_COLORS['text_dark']

    # Correct answer glow
    if show_result and is_correct and glow > 0:
        glow_alpha = int(35 * glow)
        for g in range(3, 0, -1):
            expand = g * 5
            glow_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            gd.rounded_rectangle(
                [actual_x - expand, y - expand,
                 actual_x + width + expand, y + height + expand],
                radius=22 + expand,
                fill=(*QUIZ_COLORS['correct_glow'], glow_alpha // g),
            )
            frame.paste(glow_layer, (0, 0), glow_layer)

    # Apply pulse scaling for correct answer
    draw_x, draw_y, draw_w, draw_h = actual_x, y, width, height
    if pulse_val != 1.0:
        cx = actual_x + width // 2
        cy = y + height // 2
        draw_w = int(width * pulse_val)
        draw_h = int(height * pulse_val)
        draw_x = cx - draw_w // 2
        draw_y = cy - draw_h // 2

    # Card background
    draw_rounded_card(
        frame, draw_x, draw_y, draw_w, draw_h,
        radius=22,
        fill=card_fill,
        alpha=card_alpha,
        shadow=not (show_result and is_wrong),
        shadow_offset=4,
        shadow_alpha=int(40 * (alpha / 255)),
    )

    # Re-acquire draw after compositing
    draw = ImageDraw.Draw(frame, 'RGBA')

    # Circle letter
    circle_x = draw_x + circle_margin + circle_r
    circle_y = draw_y + draw_h // 2

    draw_circle_number(
        draw, letter, circle_x, circle_y,
        radius=circle_r,
        bg_color=circle_bg,
        text_color=(255, 255, 255),
        font_size=32,
    )

    # Option text
    tf = font(40)
    text_start_x = draw_x + text_left
    max_text_w = draw_w - text_left - 24

    # Truncate if needed
    display_text = text
    bbox = draw.textbbox((0, 0), display_text, font=tf)
    text_w = bbox[2] - bbox[0]
    while text_w > max_text_w and len(display_text) > 3:
        display_text = display_text[:-4] + "..."
        bbox = draw.textbbox((0, 0), display_text, font=tf)
        text_w = bbox[2] - bbox[0]

    text_h = bbox[3] - bbox[1]
    text_y = draw_y + (draw_h - text_h) // 2 - 2

    draw.text(
        (text_start_x, text_y), display_text, font=tf,
        fill=(*text_color[:3], alpha),
    )

    return draw


def draw_countdown_number(
    draw: ImageDraw.Draw,
    number: int,
    center_x: int,
    center_y: int,
    t: float,
    start_time: float,
    countdown_interval: float = 1.5,
):
    """Draw animated countdown number with pop-in and glow (no ring)."""
    elapsed = t - start_time
    if elapsed < 0:
        return

    # Pop-in animation (clamped to avoid oversized rendering)
    pop_duration = 0.2
    if elapsed < pop_duration:
        progress = elapsed / pop_duration
        scale = min(1.15, 0.5 + 0.5 * ease_out_elastic(progress))
    else:
        # Gentle pulse
        pulse_t = elapsed - pop_duration
        scale = 1.0 + 0.04 * math.sin(pulse_t * 5)

    # Fade in
    alpha = min(255, int(255 * ease_out_cubic(min(1.0, elapsed / 0.1))))

    # Colors per number
    color = COUNTDOWN_COLORS.get(number, (255, 255, 255))

    # Number text (scale affects size)
    font_size = max(60, int(140 * scale))
    tf = font(font_size)
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=tf)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 5

    # Glow layers
    for glow_offset in [6, 3]:
        glow_alpha = int(alpha * 0.20)
        draw.text(
            (tx, ty), text, font=tf,
            fill=(*color, glow_alpha),
            stroke_width=glow_offset + 3,
            stroke_fill=(*color, glow_alpha // 2),
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


def resolve_quiz_timestamps(data: Dict, duration: float) -> Dict:
    """Build segment_times for quiz data, using exact TTS segments when
    available and falling back to keyword-based parsing otherwise.

    This function normalises the two different timestamp sources into
    a single ``segment_times`` dict that ``create_frame_quiz`` consumes.

    Returns:
        The *same* ``data`` dict, with ``segment_times`` guaranteed to
        be populated.
    """
    segment_times = data.get('segment_times', {})

    # Check whether segment_times has the critical keys we need
    required = {'option_a', 'answer'}
    has_segments = bool(segment_times) and required.issubset(segment_times.keys())

    if has_segments:
        logger.info("Quiz timestamps: using segment_times (exact)")
        return data

    # --- Fallback: derive segment_times from parse_quiz_timestamps ---
    logger.info("Quiz timestamps: falling back to parse_quiz_timestamps (keyword search)")

    words = data.get('words', [])
    ts = parse_quiz_timestamps(words)

    def _entry(start: float, end: float = None) -> Dict:
        if end is None:
            end = start + 0.5
        return {'start': start, 'end': end, 'duration': end - start}

    segment_times = {
        'question':    _entry(ts['question_start'], ts['question_end'] or ts['question_start'] + 2.0),
        'option_a':    _entry(ts['option_a']),
        'option_b':    _entry(ts['option_b']),
        'option_c':    _entry(ts['option_c']),
        'option_d':    _entry(ts['option_d']),
        'think':       _entry(ts['think_start']) if ts['think_start'] > 0 else _entry(ts['option_d'] + 1.0),
        'countdown_3': _entry(ts['countdown_3']) if ts['countdown_3'] > 0 else {},
        'countdown_2': _entry(ts['countdown_2']) if ts['countdown_2'] > 0 else {},
        'countdown_1': _entry(ts['countdown_1']) if ts['countdown_1'] > 0 else {},
        'answer':      _entry(ts['answer_start']),
        'explanation':  _entry(ts['explanation_start']) if ts.get('explanation_start', 0) > 0 else _entry(ts['answer_start'] + 1.5),
    }

    # Remove empty entries (countdown might not be detected)
    segment_times = {k: v for k, v in segment_times.items() if v}

    data['segment_times'] = segment_times
    return data


def create_frame_quiz(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for quiz video using EXACT segment timestamps."""
    frame, draw = create_base_frame(t)

    question = data.get('question', 'Question?')
    options = data.get('options', {})
    correct = data.get('correct', 'A')
    explanation = data.get('explanation', '')
    difficulty = data.get('difficulty', '')
    question_number = data.get('question_number', '')

    st = data.get('segment_times', {})

    if t < 0.05 and st:
        log_segment_timestamps(st, 'quiz', [
            'question', 'transition', 'option_a', 'option_b', 'option_c', 'option_d',
            'think', 'countdown_3', 'countdown_2', 'countdown_1', 'answer', 'explanation',
        ])

    question_visible = t >= 0

    # Bug A2 fix: Visual appears VISUAL_ANTICIPATION seconds BEFORE audio
    show_option_a = t >= _seg_start(st, 'option_a', 999) - VISUAL_ANTICIPATION
    show_option_b = t >= _seg_start(st, 'option_b', 999) - VISUAL_ANTICIPATION
    show_option_c = t >= _seg_start(st, 'option_c', 999) - VISUAL_ANTICIPATION
    show_option_d = t >= _seg_start(st, 'option_d', 999) - VISUAL_ANTICIPATION

    think_start = _seg_start(st, 'think', duration * 0.5)
    show_timer = t >= think_start - VISUAL_ANTICIPATION

    countdown_start = _seg_start(st, 'countdown_3', think_start + 0.5)

    answer_time = _seg_start(st, 'answer', duration * 0.7)
    show_answer = t >= answer_time - VISUAL_ANTICIPATION

    explanation_time = _seg_start(st, 'explanation', answer_time + 1.5)
    show_explanation = t >= explanation_time

    # ── 1. Difficulty badge (top-right, pop-in at 0.3s) ─────────
    if difficulty and t >= 0.3:
        badge_scale = tiktok_pop_scale(t, 0.3)
        if badge_scale > 0:
            badge_alpha = get_alpha(t, 0.3, 0.2)
            if badge_alpha > 0:
                draw_difficulty_badge(draw, frame, difficulty, 880, 100)
                draw = ImageDraw.Draw(frame, 'RGBA')

    # ── 2. Question number ("Pregunta X") ───────────────────────
    question_y = QUESTION_ZONE_TOP
    if question_number and question_visible:
        q_num_alpha = get_alpha(t, 0, 0.3)
        qn_text = f"Pregunta {question_number}"
        qnf = font(32)
        bbox = draw.textbbox((0, 0), qn_text, font=qnf)
        qnw = bbox[2] - bbox[0]
        qnx = (VIDEO_WIDTH - qnw) // 2
        draw_text_solid(draw, qn_text, qnx, question_y, qnf, COLOR_WHITE, q_num_alpha, outline=4)
        question_y += 50  # Push question box down below the label

    # ── 3. Question box (white card with accent bar) ────────────
    if question_visible:
        q_alpha = get_alpha(t, 0, 0.4)
        clean_question = question.replace('¿', '').replace('?', '?')
        max_question_height = QUESTION_ZONE_BOTTOM - question_y - 20

        accent = DIFFICULTY_COLORS.get(difficulty) if difficulty else None
        draw_quiz_question_box(frame, draw, clean_question, question_y, q_alpha, max_question_height, accent)
        draw = ImageDraw.Draw(frame, 'RGBA')

    # ── 4. Options (individual rounded cards with stagger) ──────
    opt_card_w = CARD_WIDTH
    opt_card_h = 85
    opt_gap = 15
    opt_x = CARD_MARGIN_X
    opt_start_y = OPTIONS_ZONE_TOP + 30

    option_data = [
        ('A', _seg_start(st, 'option_a', 999), show_option_a),
        ('B', _seg_start(st, 'option_b', 999), show_option_b),
        ('C', _seg_start(st, 'option_c', 999), show_option_c),
        ('D', _seg_start(st, 'option_d', 999), show_option_d),
    ]

    STAGGER = 0.12  # 120ms between each option appearing

    for i, (letter, start_time, should_show) in enumerate(option_data):
        if not should_show:
            continue

        opt_text = options.get(letter, f"Option {letter}")
        y_pos = opt_start_y + i * (opt_card_h + opt_gap)

        # Stagger: each option appears STAGGER seconds after the previous
        stagger_time = start_time
        opt_alpha = get_alpha(t, stagger_time, 0.25) if stagger_time < 999 else 255
        x_offset = slide_in_x(t, stagger_time, 0.4) if stagger_time < 999 else 0

        is_correct = (letter == correct)
        is_wrong = not is_correct

        glow_val = 0.0
        pulse_val = 1.0
        if show_answer and is_correct:
            glow_val = glow_intensity(t, answer_time)
            # Gentler pulse: 1.0 -> 1.03
            elapsed_ans = t - answer_time
            pulse_val = 1.0 + 0.03 * math.sin(elapsed_ans * math.pi * 3.3)

        draw = draw_quiz_option_card(
            frame, draw, letter, opt_text,
            opt_x, y_pos, opt_card_w, opt_card_h,
            alpha=opt_alpha,
            x_offset=x_offset,
            is_correct=is_correct,
            is_wrong=is_wrong,
            show_result=show_answer,
            glow=glow_val,
            pulse_val=pulse_val if (show_answer and is_correct) else 1.0,
        )

        if show_answer and is_correct:
            sparkle_center_x = VIDEO_WIDTH // 2
            sparkle_center_y = y_pos + opt_card_h // 2
            draw_sparkles(draw, sparkle_center_x, sparkle_center_y, t, answer_time, radius=200)

    # ── 5. Countdown: "Piensa bien" + timer bar + numbers ───────

    # "Piensa bien" text
    if show_timer and not show_answer and t < countdown_start:
        think_alpha = get_alpha(t, think_start - VISUAL_ANTICIPATION, 0.3)
        think_y = COUNTDOWN_ZONE_TOP

        tf = font(48)
        think_text = "¡Piensa bien!"
        bbox = draw.textbbox((0, 0), think_text, font=tf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2
        draw_text_solid(draw, think_text, tx, think_y, tf, COLOR_YELLOW, think_alpha, outline=5)

    # Horizontal timer bar (replaces circular ring)
    if show_timer and not show_answer and t >= countdown_start - VISUAL_ANTICIPATION:
        countdown_total = answer_time - countdown_start
        if countdown_total > 0:
            time_in_countdown = t - countdown_start
            timer_progress = max(0.0, 1.0 - time_in_countdown / countdown_total)
        else:
            timer_progress = 0.0

        draw_progress_timer_bar(
            draw, frame,
            TIMER_BAR_X, TIMER_BAR_Y,
            TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT,
            timer_progress,
        )
        # Re-acquire draw after timer bar compositing
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Large countdown numbers (with pop + glow, NO ring)
        timer_center_x = VIDEO_WIDTH // 2
        timer_center_y = COUNTDOWN_ZONE_TOP + 100

        timer_num, num_start = resolve_countdown_number(t, st)

        if timer_num is None:
            # Fallback: evenly divide countdown period
            if countdown_total > 0:
                interval = countdown_total / 3
                time_in_cd = t - countdown_start

                if time_in_cd >= 2 * interval:
                    timer_num = 1
                    num_start = countdown_start + 2 * interval
                elif time_in_cd >= interval:
                    timer_num = 2
                    num_start = countdown_start + interval
                elif time_in_cd >= 0:
                    timer_num = 3
                    num_start = countdown_start

        if timer_num:
            draw_countdown_number(draw, timer_num, timer_center_x, timer_center_y, t, num_start)

    # ── 6. Answer reveal + explanation card ─────────────────────

    # "Respuesta: X" text
    if show_answer and not show_explanation:
        reveal_alpha = get_alpha(t, answer_time, 0.3)
        reveal_y = COUNTDOWN_ZONE_TOP + 20

        rf = font(48)
        reveal_text = f"Respuesta: {correct}"
        bbox = draw.textbbox((0, 0), reveal_text, font=rf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2

        draw_text_solid(draw, reveal_text, tx, reveal_y, rf,
                       QUIZ_COLORS['correct_green'], reveal_alpha, outline=5)

    # Explanation — light card with slide-up animation
    if show_explanation and explanation:
        exp_alpha = get_alpha(t, explanation_time, 0.4)

        # Slide-up: starts 60px below final position, eases up
        slide_elapsed = t - explanation_time
        slide_progress = min(1.0, max(0.0, slide_elapsed / 0.4))
        slide_offset = int(60 * (1.0 - ease_out_cubic(slide_progress)))

        exp_y_base = COUNTDOWN_ZONE_TOP + 10
        exp_y = exp_y_base + slide_offset
        exp_padding = 28
        max_exp_w = CARD_WIDTH - exp_padding * 2
        max_exp_h = SAFE_AREA_BOTTOM - exp_y - exp_padding * 2

        clean_exp = explanation.replace("'", "").strip()
        ef, exp_font_size, exp_lines, exp_text_h = fit_text_font(
            clean_exp, 42, 28, max_exp_w, max_exp_h
        )
        exp_line_h = int(exp_font_size * 1.4)
        exp_height = len(exp_lines) * exp_line_h + exp_padding * 2

        # Light card background
        card_alpha = int(240 * (exp_alpha / 255))
        draw_rounded_card(
            frame, CARD_MARGIN_X, exp_y, CARD_WIDTH, exp_height,
            radius=20,
            fill=(245, 255, 248),   # Very light green tint
            alpha=card_alpha,
            shadow=True,
            shadow_offset=4,
            shadow_alpha=int(50 * (exp_alpha / 255)),
        )
        draw = ImageDraw.Draw(frame, 'RGBA')

        # Small green accent bar at top of card
        accent_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
        ad = ImageDraw.Draw(accent_layer)
        accent_w = 60
        accent_h = 5
        accent_x = (VIDEO_WIDTH - accent_w) // 2
        ad.rounded_rectangle(
            [accent_x, exp_y + 10, accent_x + accent_w, exp_y + 10 + accent_h],
            radius=3,
            fill=(*QUIZ_COLORS['correct_green'], exp_alpha),
        )
        frame.paste(accent_layer, (0, 0), accent_layer)
        draw = ImageDraw.Draw(frame, 'RGBA')

        text_y = exp_y + exp_padding
        text_color = QUIZ_COLORS['text_dark']
        for line in exp_lines:
            bbox = draw.textbbox((0, 0), line, font=ef)
            lw = bbox[2] - bbox[0]
            lx = (VIDEO_WIDTH - lw) // 2
            draw.text((lx, text_y), line, font=ef, fill=(*text_color, exp_alpha))
            text_y += exp_line_h

    # ── Timeline at top + progress bar at bottom ────────────────
    progress = min(1.0, t / duration)
    is_in_countdown = show_timer and not show_answer
    draw_quiz_timeline(draw, progress, is_countdown=is_in_countdown)

    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))

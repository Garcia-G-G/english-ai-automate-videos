"""Quiz video frame generator — question, options, countdown, answer reveal."""

import math
import logging
from typing import List, Dict, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_out_cubic, ease_out_elastic,
    get_alpha, get_scale, pulse_scale, glow_intensity,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, QUIZ_COLORS, COLOR_WHITE, COLOR_YELLOW,
    FONT_SIZE_QUESTION, TEXT_AREA_WIDTH,
)
from .backgrounds import gradient
from .utils import (
    font, line_break, draw_text_solid, draw_text_centered,
    draw_progress_bar, draw_sparkles, slide_in_x,
    draw_gradient_rounded_rect,
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


def draw_quiz_option_box_v2(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    letter: str,
    text: str,
    x: int, y: int,
    width: int, height: int,
    alpha: int = 255,
    scale: float = 1.0,
    x_offset: int = 0,
    is_correct: bool = False,
    is_wrong: bool = False,
    show_result: bool = False,
    glow: float = 0.0
):
    """Draw a professional quiz option box."""
    if alpha <= 0 or scale <= 0:
        return

    actual_x = x + x_offset

    circle_r = max(8, int(32 * scale))
    circle_x = actual_x + circle_r - 5
    circle_y = y + height // 2

    pill_x = actual_x + circle_r + 5
    pill_width = width - circle_r - 10

    if scale != 1.0 and scale < 1.0:
        center_x = pill_x + pill_width // 2
        center_y = y + height // 2
        scaled_w = int(pill_width * scale)
        scaled_h = int(height * scale)
        pill_x = center_x - scaled_w // 2
        y = center_y - scaled_h // 2
        pill_width = scaled_w
        height = scaled_h
        circle_x = pill_x - 5
        circle_y = y + height // 2

    if show_result and is_correct:
        bg_color = QUIZ_COLORS['correct_green']
        letter_bg = QUIZ_COLORS['correct_green']
        letter_inner = (255, 255, 255)
        text_color = QUIZ_COLORS['text_dark']

        if glow > 0:
            glow_alpha = int(60 * glow)
            for g in range(5, 0, -1):
                glow_expand = g * 6
                draw.rounded_rectangle(
                    [pill_x - glow_expand, y - glow_expand,
                     pill_x + pill_width + glow_expand, y + height + glow_expand],
                    radius=height // 2 + glow_expand,
                    fill=(*QUIZ_COLORS['correct_glow'], glow_alpha // g)
                )
    elif show_result and is_wrong:
        bg_color = QUIZ_COLORS['wrong_fade']
        letter_bg = QUIZ_COLORS['wrong_fade']
        letter_inner = (240, 238, 245)
        text_color = QUIZ_COLORS['wrong_text']
        alpha = int(alpha * 0.7)
    else:
        bg_color = QUIZ_COLORS['option_bg']
        letter_bg = QUIZ_COLORS['letter_circle']
        letter_inner = (255, 255, 255)
        text_color = COLOR_WHITE

    if not (show_result and is_wrong):
        for i in range(4, 0, -1):
            shadow_alpha = int(25 * (1 - i/4))
            draw.rounded_rectangle(
                [pill_x + 2, y + i + 2, pill_x + pill_width + 2, y + height + i + 2],
                radius=height // 2,
                fill=(80, 70, 100, shadow_alpha)
            )

    draw.rounded_rectangle(
        [pill_x, y, pill_x + pill_width, y + height],
        radius=height // 2,
        fill=(*bg_color, alpha)
    )

    border_r = circle_r + 4
    draw.ellipse(
        [circle_x - border_r, circle_y - border_r,
         circle_x + border_r, circle_y + border_r],
        fill=(255, 255, 255, alpha)
    )

    draw.ellipse(
        [circle_x - circle_r, circle_y - circle_r,
         circle_x + circle_r, circle_y + circle_r],
        fill=(*letter_bg, alpha)
    )

    if not (show_result and is_correct):
        inner_r = circle_r - 6
        if inner_r > 4:
            draw.ellipse(
                [circle_x - inner_r, circle_y - inner_r,
                 circle_x + inner_r, circle_y + inner_r],
                fill=(*letter_inner, alpha)
            )

    lf = font(max(16, int(38 * scale)))

    if show_result and is_correct:
        display_char = letter
        l_color = COLOR_WHITE
        lf = font(max(20, int(44 * scale)))
    else:
        display_char = letter
        l_color = letter_bg

    bbox = draw.textbbox((0, 0), display_char, font=lf)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]

    draw.text(
        (circle_x - lw // 2, circle_y - lh // 2 - 2),
        display_char, font=lf, fill=(*l_color, alpha)
    )

    tf = font(max(20, int(44 * scale)))
    bbox = draw.textbbox((0, 0), text, font=tf)
    text_w = bbox[2] - bbox[0]

    display_text = text
    max_text_w = pill_width - 40
    while text_w > max_text_w and len(display_text) > 3:
        display_text = display_text[:-4] + "..."
        bbox = draw.textbbox((0, 0), display_text, font=tf)
        text_w = bbox[2] - bbox[0]

    text_x = pill_x + (pill_width - text_w) // 2
    text_y = y + (height - (bbox[3] - bbox[1])) // 2 - 3

    shadow_color = (60, 50, 80)
    draw.text((text_x + 1, text_y + 1), display_text, font=tf,
              fill=(*shadow_color, int(alpha * 0.25)))
    draw.text((text_x, text_y), display_text, font=tf,
              fill=(*text_color, alpha))


def draw_quiz_question_box(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    question: str,
    y: int,
    alpha: int = 255
):
    """Draw a gradient question box."""
    box_padding = 40
    box_margin = 50

    qf = font(52)
    lines = line_break(question, qf, VIDEO_WIDTH - box_margin * 2 - box_padding * 2)
    line_height = int(52 * 1.4)
    text_height = len(lines) * line_height

    box_height = text_height + box_padding * 2
    box_x = box_margin
    box_y = y
    box_width = VIDEO_WIDTH - box_margin * 2

    draw_gradient_rounded_rect(
        frame,
        box_x, box_y,
        box_x + box_width, box_y + box_height,
        radius=25,
        color1=QUIZ_COLORS['question_grad_start'],
        color2=QUIZ_COLORS['question_grad_end'],
        alpha=alpha,
        vertical=False
    )

    text_y = box_y + box_padding
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=qf)
        text_w = bbox[2] - bbox[0]
        text_x = (VIDEO_WIDTH - text_w) // 2

        shadow_color = (80, 50, 100)
        draw.text((text_x + 1, text_y + 1), line, font=qf, fill=(*shadow_color, int(alpha * 0.3)))
        draw.text((text_x, text_y), line, font=qf, fill=(255, 255, 255, alpha))
        text_y += line_height

    return box_y + box_height


def draw_countdown_number(
    draw: ImageDraw.Draw,
    number: int,
    center_x: int,
    center_y: int,
    t: float,
    start_time: float
):
    """Draw animated countdown number with bounce animation."""
    elapsed = t - start_time
    anim_duration = 0.35

    if elapsed < 0:
        return

    if elapsed < anim_duration:
        progress = elapsed / anim_duration
        scale = 1.6 - 0.6 * ease_out_elastic(progress)
    else:
        pulse = 1.0 + 0.03 * math.sin((elapsed - anim_duration) * 6)
        scale = pulse

    alpha = min(255, int(255 * ease_out_cubic(min(1.0, elapsed / 0.12))))

    if number == 3:
        bg_color = (100, 220, 160)
    elif number == 2:
        bg_color = (255, 200, 100)
    else:
        bg_color = (255, 130, 130)

    box_size = int(160 * scale)
    box_x = center_x - box_size // 2
    box_y = center_y - box_size // 2

    glow_size = int(box_size * 1.2)
    glow_x = center_x - glow_size // 2
    glow_y = center_y - glow_size // 2
    glow_alpha = int(alpha * 0.3)
    draw.rounded_rectangle(
        [glow_x, glow_y, glow_x + glow_size, glow_y + glow_size],
        radius=30,
        fill=(*bg_color, glow_alpha)
    )

    shadow_offset = 4
    draw.rounded_rectangle(
        [box_x + shadow_offset, box_y + shadow_offset,
         box_x + box_size + shadow_offset, box_y + box_size + shadow_offset],
        radius=28,
        fill=(80, 60, 100, int(alpha * 0.25))
    )

    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_size, box_y + box_size],
        radius=28,
        fill=(*bg_color, alpha)
    )

    tf = font(max(50, int(110 * scale)))
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=tf)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 5

    draw.text((tx + 2, ty + 2), text, font=tf, fill=(50, 40, 60, int(alpha * 0.3)))
    draw.text((tx, ty), text, font=tf, fill=(255, 255, 255, alpha))


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
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    question = data.get('question', 'Question?')
    options = data.get('options', {})
    correct = data.get('correct', 'A')
    explanation = data.get('explanation', '')

    segment_times = data.get('segment_times', {})

    def seg_start(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('start', fallback)

    def seg_end(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('end', fallback)

    if t < 0.05 and segment_times:
        logger.debug("EXACT segment timestamps (no estimation):")
        for seg_id in ['question', 'transition', 'option_a', 'option_b', 'option_c', 'option_d',
                       'think', 'countdown_3', 'countdown_2', 'countdown_1', 'answer', 'explanation']:
            if seg_id in segment_times:
                s = segment_times[seg_id]
                logger.debug(f"{seg_id}: {s['start']:.2f}s - {s['end']:.2f}s")

    question_visible = t >= 0

    show_option_a = t >= seg_start('option_a', 999)
    show_option_b = t >= seg_start('option_b', 999)
    show_option_c = t >= seg_start('option_c', 999)
    show_option_d = t >= seg_start('option_d', 999)

    think_start = seg_start('think', duration * 0.5)
    show_timer = t >= think_start

    countdown_start = seg_start('countdown_3', think_start + 0.5)

    answer_time = seg_start('answer', duration * 0.7)
    show_answer = t >= answer_time

    explanation_time = seg_start('explanation', answer_time + 1.5)
    show_explanation = t >= explanation_time

    # Draw question box
    if question_visible:
        q_alpha = get_alpha(t, 0, 0.4)
        clean_question = question.replace('¿', '').replace('?', '?')
        draw_quiz_question_box(frame, draw, clean_question, 180, q_alpha)
        draw = ImageDraw.Draw(frame, 'RGBA')

    # Draw soft cream background for options area
    options_bg_y = 420
    options_bg_height = 500
    light_bg = QUIZ_COLORS['light_bg']
    draw.rounded_rectangle(
        [30, options_bg_y, VIDEO_WIDTH - 30, options_bg_y + options_bg_height],
        radius=30,
        fill=(*light_bg, 200)
    )

    # Draw options
    opt_w = VIDEO_WIDTH - 120
    opt_h = 80
    opt_gap = 22
    opt_start_y = 460

    option_data = [
        ('A', seg_start('option_a', 999), show_option_a),
        ('B', seg_start('option_b', 999), show_option_b),
        ('C', seg_start('option_c', 999), show_option_c),
        ('D', seg_start('option_d', 999), show_option_d),
    ]

    for i, (letter, start_time, should_show) in enumerate(option_data):
        if not should_show:
            continue

        opt_text = options.get(letter, f"Option {letter}")
        y_pos = opt_start_y + i * (opt_h + opt_gap)

        opt_alpha = get_alpha(t, start_time, 0.25) if start_time < 999 else 255
        opt_scale = get_scale(t, start_time, 0.3) if start_time < 999 else 1.0
        x_offset = slide_in_x(t, start_time, 0.4) if start_time < 999 else 0

        is_correct = (letter == correct)
        is_wrong = not is_correct

        glow_val = 0.0
        if show_answer and is_correct:
            glow_val = glow_intensity(t, answer_time)
            opt_scale = pulse_scale(t, answer_time, 0.8)

        draw_quiz_option_box_v2(
            frame, draw, letter, opt_text,
            60, y_pos, opt_w, opt_h,
            alpha=opt_alpha,
            scale=min(1.0, opt_scale) if not (show_answer and is_correct) else opt_scale,
            x_offset=x_offset,
            is_correct=is_correct,
            is_wrong=is_wrong,
            show_result=show_answer,
            glow=glow_val
        )

        if show_answer and is_correct:
            sparkle_center_x = VIDEO_WIDTH // 2
            sparkle_center_y = y_pos + opt_h // 2
            draw_sparkles(draw, sparkle_center_x, sparkle_center_y, t, answer_time, radius=200)

    # "Piensa bien" text
    if show_timer and not show_answer and t < countdown_start:
        think_alpha = get_alpha(t, think_start, 0.3)
        think_y = 920

        tf = font(48)
        think_text = "¡Piensa bien!"
        bbox = draw.textbbox((0, 0), think_text, font=tf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2
        draw_text_solid(draw, think_text, tx, think_y, tf, COLOR_YELLOW, think_alpha, outline=5)

    # Countdown timer
    if show_timer and not show_answer and t >= countdown_start:
        timer_center_x = VIDEO_WIDTH // 2
        timer_center_y = 1000

        cd3_start = seg_start('countdown_3', 0)
        cd2_start = seg_start('countdown_2', 0)
        cd1_start = seg_start('countdown_1', 0)

        if cd3_start > 0 and cd2_start > 0 and cd1_start > 0:
            if t >= cd1_start:
                timer_num = 1
                num_start = cd1_start
            elif t >= cd2_start:
                timer_num = 2
                num_start = cd2_start
            elif t >= cd3_start:
                timer_num = 3
                num_start = cd3_start
            else:
                timer_num = None
                num_start = 0
        else:
            countdown_total = answer_time - countdown_start
            interval = countdown_total / 3
            time_in_countdown = t - countdown_start

            if time_in_countdown >= 2 * interval:
                timer_num = 1
                num_start = countdown_start + 2 * interval
            elif time_in_countdown >= interval:
                timer_num = 2
                num_start = countdown_start + interval
            elif time_in_countdown >= 0:
                timer_num = 3
                num_start = countdown_start
            else:
                timer_num = None
                num_start = 0

        if timer_num:
            draw_countdown_number(draw, timer_num, timer_center_x, timer_center_y, t, num_start)

    # Answer reveal
    if show_answer and not show_explanation:
        reveal_alpha = get_alpha(t, answer_time, 0.3)
        reveal_y = 950

        rf = font(48)
        reveal_text = f"Respuesta: {correct}"
        bbox = draw.textbbox((0, 0), reveal_text, font=rf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2

        draw_text_solid(draw, reveal_text, tx, reveal_y, rf,
                       QUIZ_COLORS['correct_green'], reveal_alpha, outline=5)

    # Explanation
    if show_explanation and explanation:
        exp_alpha = get_alpha(t, explanation_time, 0.4)

        exp_y = 920
        exp_padding = 30
        ef = font(42)

        clean_exp = explanation.replace("'", "").strip()
        exp_lines = line_break(clean_exp, ef, VIDEO_WIDTH - 140)
        exp_line_h = int(42 * 1.4)
        exp_height = len(exp_lines) * exp_line_h + exp_padding * 2

        exp_bg = QUIZ_COLORS['correct_green']
        draw.rounded_rectangle(
            [60, exp_y, VIDEO_WIDTH - 60, exp_y + exp_height],
            radius=20,
            fill=(*exp_bg, int(exp_alpha * 0.85))
        )

        text_y = exp_y + exp_padding
        text_color = QUIZ_COLORS['text_dark']
        for line in exp_lines:
            bbox = draw.textbbox((0, 0), line, font=ef)
            lw = bbox[2] - bbox[0]
            lx = (VIDEO_WIDTH - lw) // 2
            draw.text((lx + 1, text_y + 1), line, font=ef, fill=(50, 80, 60, int(exp_alpha * 0.3)))
            draw.text((lx, text_y), line, font=ef, fill=(*text_color, exp_alpha))
            text_y += exp_line_h

    # Timeline at top
    progress = min(1.0, t / duration)
    is_in_countdown = show_timer and not show_answer
    draw_quiz_timeline(draw, progress, is_countdown=is_in_countdown)

    # Progress bar at bottom
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))

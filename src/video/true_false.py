"""True/false video frame generator."""

import logging
from typing import Dict, List

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import get_alpha
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, QUIZ_COLORS,
    COLOR_WHITE, COLOR_YELLOW, FONT_SIZE_QUESTION, TEXT_AREA_WIDTH,
)
from .backgrounds import gradient
from .utils import font, draw_text_solid, draw_text_centered, draw_progress_bar
from .quiz import draw_countdown_number

logger = logging.getLogger(__name__)


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
    """Ensure segment_times is populated for true/false videos.

    Uses exact TTS segment timestamps when available, falls back to
    keyword-based parsing of Whisper word timestamps otherwise.
    """
    segment_times = data.get('segment_times', {})

    required = {'options', 'answer'}
    has_segments = bool(segment_times) and required.issubset(segment_times.keys())

    if has_segments:
        logger.info("True/false timestamps: using segment_times (exact)")
        return data

    logger.info("True/false timestamps: falling back to parse_true_false_timestamps (keyword search)")

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


def create_frame_true_false(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for true/false video type using EXACT segment timestamps."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    statement = data.get('statement', 'Statement')
    correct = data.get('correct', True)
    explanation = data.get('explanation', '')

    segment_times = data.get('segment_times', {})

    def seg_start(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('start', fallback)

    def seg_end(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('end', fallback)

    if t < 0.05 and segment_times:
        logger.debug("EXACT true/false segment timestamps:")
        for seg_id in ['statement', 'options', 'think', 'countdown_3', 'countdown_2', 'countdown_1', 'answer', 'explanation']:
            if seg_id in segment_times:
                s = segment_times[seg_id]
                logger.debug(f"{seg_id}: {s['start']:.2f}s - {s['end']:.2f}s")

    stmt_end = seg_end('statement', duration * 0.15)
    opt_start = seg_start('options', stmt_end + 0.3)
    timer_start = seg_start('think', opt_start + 1.0)
    answer_time = seg_start('answer', duration * 0.7)

    show_answer = t >= answer_time

    # Statement
    sf = font(FONT_SIZE_QUESTION)
    s_alpha = get_alpha(t, 0, 0.3)
    draw_text_centered(draw, statement, 350, sf, COLOR_YELLOW, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)

    # True/False options
    if t > opt_start:
        opt_alpha = get_alpha(t, opt_start, 0.3)

        btn_w = 400
        btn_h = 120
        gap = 60
        total_w = btn_w * 2 + gap
        start_x = (VIDEO_WIDTH - total_w) // 2
        btn_y = 700

        # TRUE button
        true_correct = correct is True and show_answer

        if true_correct:
            true_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
            true_border = (*QUIZ_COLORS['correct_glow'], opt_alpha)
        elif show_answer and not correct:
            true_bg = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.5))
            true_border = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.7))
        else:
            true_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
            true_border = (255, 255, 255, int(opt_alpha * 0.9))

        draw.rounded_rectangle(
            [start_x, btn_y, start_x + btn_w, btn_y + btn_h],
            radius=25, fill=true_bg, outline=true_border, width=4
        )

        tf = font(56)
        true_text = "VERDADERO"
        tbbox = draw.textbbox((0, 0), true_text, font=tf)
        ttw = tbbox[2] - tbbox[0]
        ttx = start_x + (btn_w - ttw) // 2
        draw_text_solid(draw, true_text, ttx, btn_y + 30, tf, COLOR_WHITE, opt_alpha, outline=5)

        # FALSE button
        false_x = start_x + btn_w + gap
        false_correct = correct is False and show_answer

        if false_correct:
            false_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
            false_border = (*QUIZ_COLORS['correct_glow'], opt_alpha)
        elif show_answer and correct:
            false_bg = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.5))
            false_border = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.7))
        else:
            false_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
            false_border = (255, 255, 255, int(opt_alpha * 0.9))

        draw.rounded_rectangle(
            [false_x, btn_y, false_x + btn_w, btn_y + btn_h],
            radius=25, fill=false_bg, outline=false_border, width=4
        )

        false_text = "FALSO"
        fbbox = draw.textbbox((0, 0), false_text, font=tf)
        ftw = fbbox[2] - fbbox[0]
        ftx = false_x + (btn_w - ftw) // 2
        draw_text_solid(draw, false_text, ftx, btn_y + 30, tf, COLOR_WHITE, opt_alpha, outline=5)

    # Timer
    countdown_3_start = seg_start('countdown_3', 0)
    show_countdown = countdown_3_start > 0 and t >= countdown_3_start and not show_answer

    if show_countdown:
        cd3_start = seg_start('countdown_3', 0)
        cd2_start = seg_start('countdown_2', 0)
        cd1_start = seg_start('countdown_1', 0)

        number = None
        num_start = 0

        if cd1_start > 0 and t >= cd1_start:
            number = 1
            num_start = cd1_start
        elif cd2_start > 0 and t >= cd2_start:
            number = 2
            num_start = cd2_start
        elif cd3_start > 0 and t >= cd3_start:
            number = 3
            num_start = cd3_start

        if number is not None:
            draw_countdown_number(draw, number, VIDEO_WIDTH // 2, 920, t, num_start)

    # Answer explanation
    if show_answer and explanation:
        exp_alpha = get_alpha(t, answer_time + 0.5, 0.3)
        ef = font(48)
        clean_exp = explanation.replace("'", "").strip()
        draw_text_centered(draw, clean_exp, 950, ef, COLOR_WHITE, exp_alpha, outline=4, max_width=TEXT_AREA_WIDTH - 80)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))

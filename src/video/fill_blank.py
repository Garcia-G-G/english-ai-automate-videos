"""Fill-in-the-blank video frame generator."""

from typing import Dict

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import get_alpha
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, QUIZ_COLORS,
    COLOR_WHITE, COLOR_YELLOW, COLOR_GREEN,
    FONT_SIZE_TIMER, TEXT_AREA_WIDTH,
)
from .backgrounds import gradient
from .utils import font, draw_text_solid, draw_text_centered, draw_progress_bar


def create_frame_fill_blank(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for fill-in-the-blank video type."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    sentence = data.get('sentence', 'I ___ to school')
    options = data.get('options', ['go', 'went', 'gone', 'going'])
    correct = data.get('correct', options[0] if options else '')
    translation = data.get('translation', '')

    sent_end = duration * 0.20
    opt_end = duration * 0.55
    timer_end = duration * 0.75

    # Sentence with blank
    sf = font(72)
    s_alpha = get_alpha(t, 0, 0.3)

    show_answer = t > timer_end
    if show_answer:
        display_sentence = sentence.replace('___', correct).replace('_', correct)
        draw_text_centered(draw, display_sentence, 350, sf, COLOR_GREEN, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)
    else:
        draw_text_centered(draw, sentence, 350, sf, COLOR_YELLOW, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)

    # Options (2x2 grid)
    if t > sent_end:
        opt_alpha = get_alpha(t, sent_end, 0.3)
        opt_w = 450
        opt_h = 100
        gap = 30
        start_x = (VIDEO_WIDTH - (opt_w * 2 + gap)) // 2
        start_y = 600

        for i, opt in enumerate(options[:4]):
            row = i // 2
            col = i % 2
            x = start_x + col * (opt_w + gap)
            y = start_y + row * (opt_h + gap)

            is_correct = (opt == correct) and show_answer

            if is_correct:
                box_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
                box_border = (*QUIZ_COLORS['correct_green'], opt_alpha)
            else:
                box_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
                box_border = (255, 255, 255, int(opt_alpha * 0.6))

            draw.rounded_rectangle(
                [x, y, x + opt_w, y + opt_h],
                radius=20, fill=box_bg, outline=box_border, width=3
            )

            of = font(56)
            bbox = draw.textbbox((0, 0), opt, font=of)
            ow = bbox[2] - bbox[0]
            ox = x + (opt_w - ow) // 2
            oy = y + 20
            color = COLOR_GREEN if is_correct else COLOR_WHITE
            draw_text_solid(draw, opt, ox, oy, of, color, opt_alpha, outline=4)

    # Timer
    if opt_end < t < timer_end:
        timer_progress = (t - opt_end) / (timer_end - opt_end)
        if timer_progress < 0.33:
            number = 3
        elif timer_progress < 0.66:
            number = 2
        else:
            number = 1

        tf = font(FONT_SIZE_TIMER)
        text = str(number)
        bbox = draw.textbbox((0, 0), text, font=tf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2
        draw_text_solid(draw, text, tx, 900, tf, COLOR_YELLOW, 255, outline=10)

    # Translation
    if show_answer and translation:
        t_alpha = get_alpha(t, timer_end + 0.5, 0.3)
        tf = font(44)
        draw_text_centered(draw, f"({translation})", 1000, tf, (220, 220, 240), t_alpha, outline=4)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))

"""Pronunciation video frame generator."""

from typing import Dict

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import get_alpha
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT,
    COLOR_WHITE, COLOR_YELLOW, COLOR_RED, COLOR_GREEN,
    FONT_SIZE_BIG_WORD, TEXT_AREA_WIDTH,
)
from .backgrounds import gradient
from .utils import font, draw_text_centered, draw_progress_bar


def create_frame_pronunciation(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for pronunciation video type."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    word = data.get('word', 'word')
    phonetic = data.get('phonetic', '')
    common_mistake = data.get('common_mistake', '')
    tip = data.get('tip', '')
    translation = data.get('translation', '')

    word_phase = duration * 0.25
    mistake_phase = duration * 0.50
    phonetic_phase = duration * 0.80

    ZONE_TITLE_Y = 300
    ZONE_TRANSLATION_Y = 470
    ZONE_QUESTION_Y = 570
    ZONE_INCORRECT_LABEL_Y = 670
    ZONE_INCORRECT_TEXT_Y = 740
    ZONE_CORRECT_LABEL_Y = 1050
    ZONE_CORRECT_TEXT_Y = 1130
    ZONE_CORRECT_FINAL_LABEL_Y = 670
    ZONE_CORRECT_FINAL_TEXT_Y = 770
    ZONE_TIP_Y = 950

    # Big word
    wf = font(FONT_SIZE_BIG_WORD)
    w_alpha = get_alpha(t, 0, 0.3)
    draw_text_centered(draw, word, ZONE_TITLE_Y, wf, COLOR_YELLOW, w_alpha, outline=10)

    # Translation
    if translation:
        tf = font(48)
        draw_text_centered(draw, f"({translation})", ZONE_TRANSLATION_Y, tf, (200, 200, 220), int(w_alpha * 0.8), outline=4)

    # Question
    if t < mistake_phase:
        qf = font(56)
        draw_text_centered(draw, "Como se pronuncia?", ZONE_QUESTION_Y, qf, COLOR_WHITE, w_alpha, outline=5)

    # Common mistake
    if word_phase < t < phonetic_phase:
        m_alpha = get_alpha(t, word_phase, 0.3)
        mf = font(64)
        draw_text_centered(draw, "Incorrecto:", ZONE_INCORRECT_LABEL_Y, font(40), COLOR_RED, m_alpha, outline=4)
        draw_text_centered(draw, common_mistake, ZONE_INCORRECT_TEXT_Y, mf, COLOR_RED, m_alpha, outline=6)

    # Correct phonetic
    if t > mistake_phase:
        p_alpha = get_alpha(t, mistake_phase, 0.3)
        pf = font(72)

        if t < phonetic_phase:
            label_y = ZONE_CORRECT_LABEL_Y
            text_y = ZONE_CORRECT_TEXT_Y
        else:
            label_y = ZONE_CORRECT_FINAL_LABEL_Y
            text_y = ZONE_CORRECT_FINAL_TEXT_Y

        draw_text_centered(draw, "Correcto:", label_y, font(40), COLOR_GREEN, p_alpha, outline=4)
        draw_text_centered(draw, phonetic, text_y, pf, COLOR_GREEN, p_alpha, outline=6)

    # Tip
    if t > phonetic_phase and tip:
        tip_alpha = get_alpha(t, phonetic_phase, 0.3)
        tipf = font(44)
        draw_text_centered(draw, tip, ZONE_TIP_Y, tipf, COLOR_WHITE, tip_alpha, outline=4, max_width=TEXT_AREA_WIDTH - 100)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))

"""Pronunciation video frame generator."""

from typing import Dict

import numpy as np

from animations.easing import get_alpha
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT,
    COLOR_WHITE, COLOR_YELLOW, COLOR_RED, COLOR_GREEN,
    FONT_SIZE_BIG_WORD, TEXT_AREA_WIDTH,
)
from config.layout import (
    PRON_TITLE_Y, PRON_TRANSLATION_Y, PRON_QUESTION_Y,
    PRON_INCORRECT_LABEL_Y, PRON_INCORRECT_TEXT_Y,
    PRON_CORRECT_LABEL_Y, PRON_CORRECT_TEXT_Y,
    PRON_CORRECT_FINAL_LABEL_Y, PRON_CORRECT_FINAL_TEXT_Y,
    PRON_TIP_Y,
)
from .utils import font, draw_text_centered, create_base_frame, finalize_frame


def _word_font_size(word: str) -> int:
    """Dynamic font size for the big word — shrink for long words."""
    n = len(word)
    if n <= 8:
        return FONT_SIZE_BIG_WORD          # 160
    elif n <= 12:
        return int(FONT_SIZE_BIG_WORD * 0.75)  # 120
    else:
        return int(FONT_SIZE_BIG_WORD * 0.55)  # 88


def create_frame_pronunciation(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for pronunciation video type."""
    frame, draw = create_base_frame(t)

    word = data.get('word', 'word')
    phonetic = data.get('phonetic', '')
    common_mistake = data.get('common_mistake', '')
    tip = data.get('tip', '')
    translation = data.get('translation', '')

    max_w = TEXT_AREA_WIDTH - 80

    word_phase = duration * 0.25
    mistake_phase = duration * 0.50
    phonetic_phase = duration * 0.80

    # Big word — dynamic font size
    wf = font(_word_font_size(word))
    w_alpha = get_alpha(t, 0, 0.3)
    draw_text_centered(draw, word, PRON_TITLE_Y, wf, COLOR_YELLOW, w_alpha, outline=6, max_width=max_w)

    # Translation
    if translation:
        tf = font(48)
        draw_text_centered(draw, f"({translation})", PRON_TRANSLATION_Y, tf, (200, 200, 220), int(w_alpha * 0.8), outline=4, max_width=max_w)

    # Question — visible until mistake_phase
    if t < mistake_phase:
        qf = font(56)
        draw_text_centered(draw, "Como se pronuncia?", PRON_QUESTION_Y, qf, COLOR_WHITE, w_alpha, outline=5, max_width=max_w)

    # Common mistake — fades in at word_phase, gradually fades out toward phonetic_phase
    if word_phase < t < phonetic_phase:
        m_alpha = get_alpha(t, word_phase, 0.3)
        # Gradual fade out: fully visible at mistake_phase, fully gone at phonetic_phase
        fade_out = max(0, 1.0 - ((t - mistake_phase) / (phonetic_phase - mistake_phase)))
        m_alpha = int(m_alpha * fade_out)
        mf = font(52)
        draw_text_centered(draw, "Incorrecto:", PRON_INCORRECT_LABEL_Y, font(40), COLOR_RED, m_alpha, outline=4, max_width=max_w)
        draw_text_centered(draw, common_mistake, PRON_INCORRECT_TEXT_Y, mf, COLOR_RED, m_alpha, outline=6, max_width=max_w)

    # Correct phonetic
    if t > mistake_phase:
        p_alpha = get_alpha(t, mistake_phase, 0.3)
        pf = font(60)

        if t < phonetic_phase:
            label_y = PRON_CORRECT_LABEL_Y
            text_y = PRON_CORRECT_TEXT_Y
        else:
            label_y = PRON_CORRECT_FINAL_LABEL_Y
            text_y = PRON_CORRECT_FINAL_TEXT_Y

        draw_text_centered(draw, "Correcto:", label_y, font(40), COLOR_GREEN, p_alpha, outline=4, max_width=max_w)
        draw_text_centered(draw, phonetic, text_y, pf, COLOR_GREEN, p_alpha, outline=6, max_width=max_w)

    # Tip
    if t > phonetic_phase and tip:
        tip_alpha = get_alpha(t, phonetic_phase, 0.3)
        tipf = font(44)
        draw_text_centered(draw, tip, PRON_TIP_Y, tipf, COLOR_WHITE, tip_alpha, outline=4, max_width=max_w)

    return finalize_frame(frame, draw, t, duration, words=data.get('words', []))

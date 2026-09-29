"""Pronunciation video frame generator."""

import logging
from typing import Dict

import numpy as np

from animations.easing import get_alpha

logger = logging.getLogger(__name__)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT,
    COLOR_WHITE, COLOR_YELLOW, COLOR_RED, COLOR_GREEN,
    FONT_SIZE_BIG_WORD, TEXT_AREA_WIDTH,
)
from config.layout import PRON_TITLE_Y
from .brand import watermark_top
from .motion import apply_transition, entrance, idle_dy
from .utils import (font, font_line_height, line_break, fit_text_font,
                    draw_text_centered, create_base_frame, finalize_frame)

# ── THE LAYOUT IS A STACK, NOT TEN COORDINATES ───────────────────────────
#
# It used to be PRON_TITLE_Y 250, PRON_TRANSLATION_Y 430, PRON_QUESTION_Y
# 530, and seven more — a layout that assumed every element is one line of a
# size nobody had measured. The word's slot was 180px and ONE line of the
# largest bucket is 194px, so the biggest word overflowed by exactly 14px
# every time, for every short word. Twenty-five of the 56 words in
# content/topics/pronunciation.json are in that bucket — knight, beach,
# sheet, think — and eight more collided by wrapping. 34 of 56, and the
# WORST CASE WAS THE SHORTEST WORD, which is the reverse of what the broken
# frame suggested.
#
# Replacing the numbers with different numbers reproduces the bug at a
# different size, so each element's Y now comes from the measured bottom of
# the one above it plus a gap. Nothing below is a position; the only
# position in this file is where the stack starts.

#: Where the stack begins. The one remaining Y, and it is an origin rather
#: than a placement.
_STACK_TOP = PRON_TITLE_Y

#: Air between two stacked blocks.
_GAP = 24

#: The word's size is FITTED into the space the stack leaves it, never
#: bucketed on len(word) — a character count cannot know the rendered
#: height, which is precisely how 194px ended up in a 180px slot.
_WORD_MAX = FONT_SIZE_BIG_WORD
_WORD_MIN = 72

#: Every other element keeps the size it had; only its position is derived.
_SIZE_TRANSLATION = 48
_SIZE_QUESTION = 56
_SIZE_LABEL = 40
_SIZE_MISTAKE = 52
_SIZE_PHONETIC = 60
_SIZE_TIP = 44


def _block_height(text: str, size: int, max_w: int) -> int:
    """The vertical space one drawn block will occupy, measured."""
    if not text:
        return 0
    f = font(size)
    return len(line_break(text, f, max_w)) * font_line_height(f)


def _word_size(word: str, followers, max_w: int) -> int:
    """Largest size at which the word fits what the stack leaves it.

    `followers` is every phase's list of (text, size) that sits BELOW the
    word. The budget is the floor minus the tallest of those, so the word
    keeps ONE size for the whole video — a hero that resized as the phases
    changed would be worse than the overlap this replaces.

    The floor is watermark_top(), not SAFE_AREA_BOTTOM. This renderer
    budgeted against nothing at all; of the six only quiz and true_false
    used the mark. It does not fire on today's content — it is the guard for
    the day a phonetic runs three lines.
    """
    worst = 0
    for phase in followers:
        height = sum(_block_height(text, size, max_w) for text, size in phase)
        worst = max(worst, height + _GAP * len(phase))
    budget = watermark_top() - _STACK_TOP - worst

    # Width used to be re-checked here, in a loop of this function's own.
    # It is fit_text_font's guard now — the trap was the shared function's,
    # not this caller's, and nine call sites across six renderers were
    # sitting on it. See utils.fit_text_font.
    box = fit_text_font(word, _WORD_MAX, _WORD_MIN, max_w, budget)
    if box.size <= _WORD_MIN and (box.width > max_w
                                  or box.advance_height > budget):
        # fit_text_font logs the axis and the excess. This adds the WORD,
        # because from here the answer is the content, not the layout.
        logger.warning("pronunciation: %r is the word that did not fit", word)
    return box.size


def create_frame_pronunciation(
    t: float,
    data: Dict,
    duration: float,
    presentation=None,
) -> np.ndarray:
    """Create frame for pronunciation video type."""
    if presentation is None:
        from studio.renderer_presentation import resolve_presentation
        presentation = resolve_presentation("es")
    frame, draw = create_base_frame(t)

    # No defaults. `word` fell back to the literal string "word", producing
    # a lesson on how to pronounce the word "word".
    word = data['word']
    phonetic = data['phonetic']

    # Genuinely optional — each '' hides its panel. Absence renders less; it
    # never fabricates a lesson.
    common_mistake = data.get('common_mistake', '')
    tip = data.get('tip', '')
    translation = data.get('translation', '')

    max_w = TEXT_AREA_WIDTH - 80

    word_phase = duration * 0.25
    mistake_phase = duration * 0.50
    phonetic_phase = duration * 0.80

    # ── What sits below the word, per phase ──────────────────────────
    # The word is sized against the tallest of these so it keeps one size
    # for the whole video. The four lists mirror the draw conditions below
    # exactly; if one changes, the other must.
    translation_text = f"({translation})" if translation else ""
    mistake_label = presentation.pronunciation_incorrect
    correct_label = presentation.pronunciation_correct
    question_text = presentation.pronunciation_prompt

    followers = [
        # A: word, translation, question
        [(translation_text, _SIZE_TRANSLATION), (question_text, _SIZE_QUESTION)],
        # B: + the mistake block, question still up
        [(translation_text, _SIZE_TRANSLATION), (question_text, _SIZE_QUESTION),
         (mistake_label, _SIZE_LABEL), (common_mistake, _SIZE_MISTAKE)],
        # C: question gone, mistake fading, phonetic arrives beneath it
        [(translation_text, _SIZE_TRANSLATION),
         (mistake_label, _SIZE_LABEL), (common_mistake, _SIZE_MISTAKE),
         (correct_label, _SIZE_LABEL), (phonetic, _SIZE_PHONETIC)],
        # D: mistake gone, phonetic rises, tip appears
        [(translation_text, _SIZE_TRANSLATION),
         (correct_label, _SIZE_LABEL), (phonetic, _SIZE_PHONETIC),
         (tip, _SIZE_TIP)],
    ]
    word_size = _word_size(word, followers, max_w)

    # ── The stack ────────────────────────────────────────────────────
    # The stack rises in at the start and then floats as one block. Floats
    # UP only, and the entrance's rise is spent in the first 0.4s while
    # only the short phase-A stack is on screen, so the word size's
    # fit against the tallest phase still holds.
    word_pop, stack_rise = entrance(t, 0.0)
    cursor = _STACK_TOP + int(round(stack_rise + idle_dy(t, 0.42)))

    def place(text, size, color, alpha, outline=6):
        """Draw one block at the cursor and advance past it.

        A block with no text or no alpha occupies nothing — that is what
        makes the phonetic rise when the mistake fades, with no second set
        of coordinates for its two positions.
        """
        nonlocal cursor
        if not text or alpha <= 0:
            return
        draw_text_centered(draw, text, cursor, font(size), color, alpha,
                           outline=outline, max_width=max_w)
        cursor += _block_height(text, size, max_w) + _GAP

    w_alpha = get_alpha(t, 0, 0.3)
    # The word pops from 90%. Never larger than its fitted size, beyond a
    # rounding pixel: the spring's overshoot is a fraction of a percent.
    place(word, max(1, int(round(word_size * min(1.0, word_pop)))),
          COLOR_YELLOW, w_alpha)
    place(translation_text, _SIZE_TRANSLATION, (200, 200, 220),
          int(w_alpha * 0.8), outline=4)

    # Question — visible until mistake_phase
    if t < mistake_phase:
        place(question_text, _SIZE_QUESTION, COLOR_WHITE, w_alpha, outline=5)

    # Common mistake — fades in at word_phase, out toward phonetic_phase
    if word_phase < t < phonetic_phase:
        m_alpha = get_alpha(t, word_phase, 0.3)
        fade_out = max(0, 1.0 - ((t - mistake_phase) / (phonetic_phase - mistake_phase)))
        m_alpha = int(m_alpha * fade_out)
        place(mistake_label, _SIZE_LABEL, COLOR_RED, m_alpha, outline=4)
        place(common_mistake, _SIZE_MISTAKE, COLOR_RED, m_alpha)

    # Correct phonetic — ONE rule, not two coordinate pairs. It sits below
    # the mistake while the mistake is on screen and rises when it is not,
    # because a block with zero alpha advances the cursor by nothing.
    if t > mistake_phase:
        p_alpha = get_alpha(t, mistake_phase, 0.3)
        place(correct_label, _SIZE_LABEL, COLOR_GREEN, p_alpha, outline=4)
        place(phonetic, _SIZE_PHONETIC, COLOR_GREEN, p_alpha)

    # Tip
    if t > phonetic_phase and tip:
        place(tip, _SIZE_TIP, COLOR_WHITE, get_alpha(t, phonetic_phase, 0.3),
              outline=4)

    # Sections here are phases of the duration, not segments, so the
    # transitions fire on the same three times the draw logic above uses.
    # Applied here rather than through finalize_frame's scene_cuts: same
    # effect, and it keeps finalize_frame's call identical for the tests
    # that stand in for it.
    apply_transition(frame, t, [word_phase, mistake_phase, phonetic_phase])
    return finalize_frame(frame, draw, t, duration, words=data.get('words', []))

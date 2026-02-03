"""Educational video frame generator — word-by-word karaoke sync."""

import re
from typing import List, Dict

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_in_out_sine, tiktok_pop_scale,
    WORD_FADE_IN, WORD_FADE_OUT,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, TEXT_AREA_WIDTH,
    ENGLISH_WORD_COLOR, SPANISH_WORD_COLOR, ENGLISH_WORD_SCALE,
    ENGLISH_GLOW_RADIUS, GROUP_TRANSITION, EMPHASIS,
    SIZE_MAIN_SPANISH, SIZE_ENGLISH_WORD, SIZE_TRANSLATION,
)
from .backgrounds import gradient
from .utils import (
    font, line_break, draw_text_with_glow, draw_text_solid,
    draw_progress_bar, get_word_animation_state,
)


def add_sentence_boundaries(words: List[Dict], full_script: str = None) -> List[Dict]:
    """Add segment_id and segment_end markers to words using full_script punctuation."""
    if not words:
        return words

    if words[0].get('segment_id') is not None:
        return words

    if full_script:
        sentences = re.split(r'(?<=[.!?¿¡])\s+', full_script.strip())
        script_word_map = []
        for sent_idx, sentence in enumerate(sentences):
            sent_words = sentence.split()
            for wi, sw in enumerate(sent_words):
                is_last = (wi == len(sent_words) - 1)
                cleaned = sw.strip("'\".,!?¿¡:;()[]")
                script_word_map.append({
                    'clean': cleaned.lower(),
                    'sentence_id': sent_idx,
                    'is_sentence_end': is_last
                })

        script_idx = 0
        for word in words:
            word_clean = word['word'].strip("'\".,!?¿¡:;()[]").lower()

            best_match = None
            for j in range(script_idx, min(script_idx + 5, len(script_word_map))):
                if script_word_map[j]['clean'] == word_clean:
                    best_match = j
                    break

            if best_match is not None:
                word['segment_id'] = script_word_map[best_match]['sentence_id']
                word['segment_end'] = script_word_map[best_match]['is_sentence_end']
                script_idx = best_match + 1
            else:
                if script_idx > 0 and script_idx <= len(script_word_map):
                    prev = script_word_map[min(script_idx - 1, len(script_word_map) - 1)]
                    word['segment_id'] = prev['sentence_id']
                    word['segment_end'] = False
                else:
                    word['segment_id'] = 0
                    word['segment_end'] = False
    else:
        for word in words:
            word['segment_id'] = 0
            word['segment_end'] = False

    return words


def create_frame_educational(
    t: float,
    groups: List[Dict],
    duration: float,
    translations: Dict = None
) -> np.ndarray:
    """Create frame for educational video type — TikTok viral quality."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    translations = translations or {}

    active = None
    fade_out_group = None

    for g in groups:
        if g['start'] <= t <= g['end']:
            active = g
            break

    if active is None:
        for g in groups:
            if g['end'] < t <= g['end'] + GROUP_TRANSITION:
                fade_out_group = g
                break

    if fade_out_group:
        _render_group_tiktok(t, fade_out_group, draw, frame, translations, is_fading_out=True)

    if active:
        _render_group_tiktok(t, active, draw, frame, translations, is_fading_out=False)

    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))


def _render_group_tiktok(
    t: float,
    group: Dict,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    translations: Dict,
    is_fading_out: bool = False
):
    """Render a word group with TikTok-viral animations."""
    text = group['text']
    is_en = group['english']
    start = group['start']
    end = group['end']
    words = group.get('words', [])

    group_alpha = 255
    if is_fading_out:
        fade_progress = min(1.0, (t - end) / GROUP_TRANSITION)
        eased = ease_in_out_sine(fade_progress)
        group_alpha = int(255 * (1 - eased))

    if group_alpha <= 0:
        return

    if is_en:
        base_size = SIZE_ENGLISH_WORD
    else:
        base_size = SIZE_MAIN_SPANISH

    f = font(base_size)

    lines = line_break(text, f, TEXT_AREA_WIDTH - 60)
    line_h = int(base_size * 1.4)
    total_h = len(lines) * line_h

    trans = ""
    if is_en:
        trans = translations.get(text.lower().strip(), "")
        if trans:
            tf = font(SIZE_TRANSLATION)
            trans_lines = line_break(f"({trans})", tf, TEXT_AREA_WIDTH - 80)
            total_h += len(trans_lines) * int(SIZE_TRANSLATION * 1.3) + 50

    base_y = (VIDEO_HEIGHT - total_h) // 2 - 40
    cur_y = base_y

    if words and not is_en:
        _render_spanish_karaoke(t, words, start, end, group_alpha, draw, frame, cur_y, base_size, is_fading_out)
    elif is_en:
        _render_english_hero(t, text, start, end, group_alpha, draw, frame, cur_y, translations, is_fading_out)
    else:
        _render_text_simple(t, text, start, end, group_alpha, draw, frame, cur_y, base_size, is_en, is_fading_out)


def _render_spanish_karaoke(
    t: float,
    words: List[Dict],
    group_start: float,
    group_end: float,
    group_alpha: int,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    base_y: int,
    base_size: int,
    is_fading_out: bool
):
    """Render Spanish text with word-by-word karaoke highlighting."""
    f = font(base_size)

    word_texts = [w['word'] for w in words]
    full_text = ' '.join(word_texts)

    lines = line_break(full_text, f, TEXT_AREA_WIDTH - 60)
    line_h = int(base_size * 1.4)

    word_idx = 0
    cur_y = base_y

    for line in lines:
        line_words = line.split()
        if not line_words:
            cur_y += line_h
            continue

        bbox = draw.textbbox((0, 0), line, font=f)
        line_w = bbox[2] - bbox[0]
        start_x = (VIDEO_WIDTH - line_w) // 2

        wx = start_x

        for display_word in line_words:
            if word_idx >= len(words):
                break

            word_data = words[word_idx]
            word_start = word_data['start']
            word_end = word_data['end']
            is_english_word = word_data.get('is_english', False)
            clean_word = display_word.lower().strip('.,!?¿¡:;\'\"')
            is_emphasis = clean_word in EMPHASIS

            state = get_word_animation_state(
                t, word_start, word_end, group_start, group_end,
                is_english=is_english_word, is_emphasis=is_emphasis
            )

            word_alpha = int(state['alpha'] * group_alpha / 255)

            if word_alpha > 0:
                if is_english_word:
                    word_color = ENGLISH_WORD_COLOR
                    word_font_size = int(base_size * ENGLISH_WORD_SCALE)
                    use_glow = True
                elif state['is_active']:
                    word_color = SPANISH_WORD_COLOR
                    word_font_size = base_size
                    use_glow = False
                else:
                    word_color = (0, 170, 210)
                    word_font_size = base_size
                    use_glow = False

                wf = font(word_font_size)

                if state['scale'] != 1.0 and state['scale'] > 0:
                    scaled_size = int(word_font_size * state['scale'])
                    wf = font(max(10, scaled_size))

                offset_x = state['offset_x']
                offset_y = state['offset_y']

                if use_glow and not is_fading_out:
                    draw_text_with_glow(
                        draw, frame, display_word,
                        wx + offset_x, cur_y + offset_y,
                        wf, word_color, word_alpha,
                        outline=10, glow=True,
                        glow_color=ENGLISH_WORD_COLOR
                    )
                else:
                    draw_text_solid(
                        draw, display_word,
                        wx + offset_x, cur_y + offset_y,
                        wf, word_color, word_alpha,
                        outline=8
                    )

            bbox = draw.textbbox((0, 0), display_word, font=f)
            word_w = bbox[2] - bbox[0]

            if word_alpha > 0:
                if is_english_word:
                    word_w = int(word_w * ENGLISH_WORD_SCALE)
                elif is_emphasis:
                    word_w = int(word_w * 1.08)

            space_bbox = draw.textbbox((0, 0), " ", font=f)
            space_w = space_bbox[2] - space_bbox[0]
            wx += word_w + space_w

            word_idx += 1

        cur_y += line_h


def _render_english_hero(
    t: float,
    text: str,
    start: float,
    end: float,
    group_alpha: int,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    base_y: int,
    translations: Dict,
    is_fading_out: bool
):
    """Render English text as the hero element."""
    scale = tiktok_pop_scale(t, start)
    alpha = group_alpha

    if scale <= 0 or alpha <= 0:
        return

    eng_size = int(SIZE_ENGLISH_WORD * scale)
    ef = font(eng_size)

    lines = line_break(text, ef, TEXT_AREA_WIDTH - 80)
    line_h = int(eng_size * 1.3)

    cur_y = base_y

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=ef)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2

        if not is_fading_out:
            draw_text_with_glow(
                draw, frame, line,
                lx, cur_y, ef,
                ENGLISH_WORD_COLOR, alpha,
                outline=12, glow=True,
                glow_color=ENGLISH_WORD_COLOR,
                glow_radius=12
            )
        else:
            draw_text_solid(draw, line, lx, cur_y, ef, ENGLISH_WORD_COLOR, alpha, outline=10)

        cur_y += line_h

    trans = translations.get(text.lower().strip(), "")
    if trans:
        cur_y += 30
        tf = font(SIZE_TRANSLATION)
        trans_text = f"({trans})"
        trans_lines = line_break(trans_text, tf, TEXT_AREA_WIDTH - 100)
        trans_line_h = int(SIZE_TRANSLATION * 1.3)

        for tline in trans_lines:
            bbox = draw.textbbox((0, 0), tline, font=tf)
            tw = bbox[2] - bbox[0]
            tx = (VIDEO_WIDTH - tw) // 2
            draw_text_solid(draw, tline, tx, cur_y, tf, (220, 220, 240), int(alpha * 0.85), outline=4)
            cur_y += trans_line_h


def _render_text_simple(
    t: float,
    text: str,
    start: float,
    end: float,
    group_alpha: int,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    base_y: int,
    base_size: int,
    is_english: bool,
    is_fading_out: bool
):
    """Simple text rendering fallback when no word timing available."""
    scale = tiktok_pop_scale(t, start)
    alpha = group_alpha

    if scale <= 0 or alpha <= 0:
        return

    fsize = int(base_size * scale)
    f = font(fsize)

    lines = line_break(text, f, TEXT_AREA_WIDTH - 60)
    line_h = int(fsize * 1.4)
    cur_y = base_y

    color = ENGLISH_WORD_COLOR if is_english else SPANISH_WORD_COLOR

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2

        if is_english and not is_fading_out:
            draw_text_with_glow(
                draw, frame, line, lx, cur_y, f,
                color, alpha, outline=10, glow=True
            )
        else:
            draw_text_solid(draw, line, lx, cur_y, f, color, alpha, outline=8)

        cur_y += line_h

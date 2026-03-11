"""Educational video frame generator — word-by-word karaoke sync."""

import re
from typing import List, Dict

import numpy as np
from PIL import Image, ImageDraw

from animations.easing import (
    ease_in_out_sine, ease_out_back, tiktok_pop_scale,
    WORD_FADE_IN, WORD_FADE_OUT,
)
from .constants import (
    VIDEO_WIDTH, VIDEO_HEIGHT, TEXT_AREA_WIDTH,
    ENGLISH_WORD_COLOR, ENGLISH_WORD_SCALE,
    ENGLISH_GLOW_RADIUS, GROUP_TRANSITION, EMPHASIS,
    SIZE_MAIN_SPANISH, SIZE_ENGLISH_WORD, SIZE_TRANSLATION,
    SAFE_AREA_TOP, SAFE_AREA_BOTTOM,
)
from .utils import (
    font, line_break, draw_text_with_glow, draw_text_solid,
    draw_rounded_card, slide_in_x,
    get_word_animation_state, fit_text_font,
    create_base_frame, finalize_frame,
)
from config.layout import CARD_MARGIN_X, CARD_PADDING, CARD_RADIUS, CARD_WIDTH
from config.colors import CARD_COLORS

# ── Spanish word colors (on cream card background) ────────────────
_SPANISH_ACTIVE = (0, 120, 200)      # dark blue — pops on cream
_SPANISH_UPCOMING = (60, 70, 90)     # dark grey — readable on cream
_SPANISH_PAST = (130, 140, 160)      # medium grey — subtle on cream

# ── Translation styling (inside dark glassmorphism card) ─────────
_TRANS_SIZE = 48
_TRANS_COLOR = (230, 235, 250)       # bright on dark card background


def add_sentence_boundaries(words: List[Dict], full_script: str = None) -> List[Dict]:
    """Add segment_id and segment_end markers to words using full_script punctuation."""
    if not words:
        return words

    if words[0].get('segment_id') is not None:
        return words

    if full_script:
        # Split on sentence-ending punctuation followed by whitespace,
        # OR on whitespace before sentence-starting punctuation ¿¡
        sentences = re.split(r'(?<=[.!?])\s+|\s+(?=[¿¡])', full_script.strip())
        # Clean up: remove empty strings and strip whitespace
        sentences = [s.strip() for s in sentences if s.strip()]
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
    data: Dict,
    duration: float,
) -> np.ndarray:
    """Create frame for educational video type — TikTok viral quality."""
    frame, draw = create_base_frame(t)

    groups = data.get('_groups', [])
    translations = data.get('translations', {}) or {}

    active = None
    fade_out_group = None

    for g in groups:
        if g['start'] <= t <= g['end']:
            active = g
            break

    # Only search for fade-out if no active group, and within transition window
    if active is None:
        for g in groups:
            if g['end'] < t <= g['end'] + GROUP_TRANSITION:
                fade_out_group = g
                break

    if fade_out_group:
        _render_group_tiktok(t, fade_out_group, draw, frame, translations, is_fading_out=True)

    if active:
        _render_group_tiktok(t, active, draw, frame, translations, is_fading_out=False)

    return finalize_frame(frame, draw, t, duration)


def _lookup_translation(en_clean: str, translations: Dict, words: List[Dict] = None) -> str:
    """Look up translation using normalized exact match only.

    Avoids aggressive fuzzy/substring matching which causes wrong translations.
    Normalizes both sides (strip punctuation, lowercase) then requires exact match.
    """
    if not translations or not en_clean:
        return ""

    # Build normalized lookup table
    norm_map = {}
    for key, value in translations.items():
        key_norm = re.sub(r'[^\w\s-]', '', key).strip().lower()
        if key_norm:
            norm_map[key_norm] = value

    # Direct match on the full English text
    if en_clean in norm_map:
        return norm_map[en_clean]

    # Try matching the full translation key against the English text
    # Only match if the key words form a complete match (not substring)
    en_words_set = set(en_clean.split())
    for key_norm, value in norm_map.items():
        key_words_set = set(key_norm.split())
        # Match if one is a subset of the other AND they share >50% of words
        overlap = en_words_set & key_words_set
        bigger = max(len(en_words_set), len(key_words_set))
        if overlap and len(overlap) / bigger >= 0.6:
            return value

    return ""


def _render_group_tiktok(
    t: float,
    group: Dict,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    translations: Dict,
    is_fading_out: bool = False
):
    """Render a word group with TikTok-viral animations inside a rounded card.

    Groups with English words get a second dark card below with the
    highlighted English word + translation.
    """
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

    if group_alpha <= 2:
        return

    # ── Slide-out to the left during fade-out ──
    slide_out_x = 0
    if is_fading_out:
        fade_progress = min(1.0, (t - end) / GROUP_TRANSITION)
        slide_out_x = int(-300 * ease_in_out_sine(fade_progress))

    # Dynamic font size — shrink for long text, max 2 lines
    max_w = CARD_WIDTH - CARD_PADDING * 2 - 40
    max_h = int(SIZE_MAIN_SPANISH * 1.4 * 2.2)
    _, base_size, lines, _ = fit_text_font(text, SIZE_MAIN_SPANISH, 42, max_w, max_h)
    base_size = max(42, min(SIZE_MAIN_SPANISH, base_size))

    f = font(base_size)
    line_h = int(base_size * 1.4)
    text_h = len(lines) * line_h

    # ── Detect English content + translation for second card ──
    has_en_words = any(w.get('is_english', False) for w in words) if words else is_en
    en_display_text = ""
    trans_text = ""
    if has_en_words and translations:
        en_display_text = ' '.join(
            w['word'] for w in words if w.get('is_english', False)
        ) if words else text
        en_clean = re.sub(r'[^\w\s-]', '', en_display_text).strip().lower()
        trans_text = _lookup_translation(en_clean, translations, words if words else None)

    # ── Main card height (text only — no translation) ──
    main_card_h = text_h + CARD_PADDING * 2

    # ── English card dimensions ──
    _EN_CARD_W = CARD_WIDTH - 120
    _EN_CARD_PAD = 30
    _EN_CARD_GAP = 20
    en_card_h = 0

    if has_en_words and (en_display_text or trans_text):
        en_font_size = _english_hero_size(en_display_text) if en_display_text else 80
        en_f = font(en_font_size)
        en_lines = line_break(en_display_text, en_f, _EN_CARD_W - _EN_CARD_PAD * 2 - 30) if en_display_text else []
        en_text_h = len(en_lines) * int(en_font_size * 1.3)

        trans_h = 0
        if trans_text:
            tf = font(_TRANS_SIZE)
            t_lines = line_break(f"({trans_text})", tf, _EN_CARD_W - _EN_CARD_PAD * 2 - 30)
            trans_h = len(t_lines) * int(_TRANS_SIZE * 1.3) + 12  # 12px gap

        en_card_h = en_text_h + trans_h + _EN_CARD_PAD * 2

    # ── Total height for centering both cards ──
    total_h = main_card_h
    if en_card_h > 0:
        total_h += _EN_CARD_GAP + en_card_h

    # Spring bounce animation for main card entrance
    _BOUNCE_DURATION = 0.45
    bounce_offset_y = 0
    elapsed = t - start
    if elapsed < _BOUNCE_DURATION and not is_fading_out:
        progress = max(0.0, min(1.0, elapsed / _BOUNCE_DURATION))
        eased = ease_out_back(progress)
        bounce_offset_y = int(30 * (1 - eased))

    # Vertical centering with clamping
    safe_h = SAFE_AREA_BOTTOM - SAFE_AREA_TOP
    card_y = SAFE_AREA_TOP + (safe_h - total_h) // 2 + bounce_offset_y
    card_y = max(SAFE_AREA_TOP, card_y)
    if card_y + total_h > SAFE_AREA_BOTTOM:
        card_y = SAFE_AREA_BOTTOM - total_h

    if words:
        # ── Cream card for karaoke groups ──
        card_alpha = int(235 * group_alpha / 255)
        cream_card = CARD_COLORS['cream_card']
        draw_rounded_card(
            frame, CARD_MARGIN_X + slide_out_x, card_y, CARD_WIDTH, main_card_h,
            radius=CARD_RADIUS,
            fill=cream_card,
            alpha=card_alpha,
            shadow=True,
            shadow_offset=5,
            shadow_alpha=60,
        )
        cur_y = card_y + CARD_PADDING
        _render_spanish_karaoke(t, words, start, end, group_alpha, draw, frame, cur_y, base_size, is_fading_out, slide_out_x)

        # English highlight card below
        if en_card_h > 0:
            _render_english_card(
                t, start, group_alpha, draw, frame,
                en_display_text, trans_text,
                card_y + main_card_h + _EN_CARD_GAP,
                _EN_CARD_W, en_card_h, _EN_CARD_PAD,
                is_fading_out, slide_out_x,
            )

    elif is_en:
        # ── Hero draws its own glassmorphism card (no cream card) ──
        _render_english_hero(t, text, start, end, group_alpha, draw, frame, card_y, total_h, translations, is_fading_out, slide_out_x)

    else:
        # ── Cream card for plain Spanish text ──
        card_alpha = int(235 * group_alpha / 255)
        cream_card = CARD_COLORS['cream_card']
        draw_rounded_card(
            frame, CARD_MARGIN_X + slide_out_x, card_y, CARD_WIDTH, main_card_h,
            radius=CARD_RADIUS,
            fill=cream_card,
            alpha=card_alpha,
            shadow=True,
            shadow_offset=5,
            shadow_alpha=60,
        )
        cur_y = card_y + CARD_PADDING
        _render_text_simple(t, text, start, end, group_alpha, draw, frame, cur_y, base_size, is_en, is_fading_out, slide_out_x)


def _english_hero_size(text: str) -> int:
    """Cap English hero font size based on word count."""
    wc = len(text.split())
    if wc > 3:
        return 80
    if wc > 1:
        return 90
    return 100


def _render_english_card(
    t: float,
    group_start: float,
    group_alpha: int,
    draw: ImageDraw.Draw,
    frame: Image.Image,
    en_text: str,
    trans_text: str,
    card_y: int,
    card_w: int,
    card_h: int,
    pad: int,
    is_fading_out: bool,
    offset_x: int = 0,
):
    """Draw a dark glassmorphism card highlighting the English word + translation.

    Slides in from the right 0.15s after the main card appears.
    During fade-out, follows the parent slide-out via offset_x.
    """
    _EN_CARD_DELAY = 0.15
    appear_time = group_start + _EN_CARD_DELAY

    # Slide-in from right (returns x offset that goes 300→0)
    x_offset = slide_in_x(t, appear_time, 0.4)

    # Not visible yet
    if x_offset >= 300:
        return

    card_x = (VIDEO_WIDTH - card_w) // 2 + int(x_offset) + offset_x
    card_alpha = int(200 * group_alpha / 255)

    # Dark card background
    draw_rounded_card(
        frame, card_x, card_y, card_w, card_h,
        radius=20,
        fill=(20, 20, 40),
        alpha=card_alpha,
        shadow=True,
        shadow_offset=4,
        shadow_alpha=50,
    )

    # Accent bar — 4px vertical line on the left inside the card
    accent_alpha = int(group_alpha * 0.9)
    accent_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent_layer)
    accent_draw.rounded_rectangle(
        [card_x + 8, card_y + 10, card_x + 12, card_y + card_h - 10],
        radius=2,
        fill=(*ENGLISH_WORD_COLOR[:3], accent_alpha),
    )
    frame.paste(accent_layer, (0, 0), accent_layer)

    # English word — centered, with glow
    cur_y = card_y + pad
    if en_text:
        en_font_size = _english_hero_size(en_text)
        ef = font(en_font_size)
        en_lines = line_break(en_text, ef, card_w - pad * 2 - 30)
        en_line_h = int(en_font_size * 1.3)

        for eline in en_lines:
            bbox = draw.textbbox((0, 0), eline, font=ef)
            ew = bbox[2] - bbox[0]
            ex = card_x + (card_w - ew) // 2

            if not is_fading_out:
                draw_text_with_glow(
                    draw, frame, eline, ex, cur_y, ef,
                    ENGLISH_WORD_COLOR, group_alpha,
                    outline=4, glow=True,
                    glow_color=ENGLISH_WORD_COLOR,
                    glow_radius=4,
                )
            else:
                draw_text_solid(
                    draw, eline, ex, cur_y, ef,
                    ENGLISH_WORD_COLOR, group_alpha, outline=4,
                )
            cur_y += en_line_h

    # Translation — centered below English word
    if trans_text:
        cur_y += 12
        tf = font(_TRANS_SIZE)
        t_display = f"({trans_text})"
        t_lines = line_break(t_display, tf, card_w - pad * 2 - 30)
        t_line_h = int(_TRANS_SIZE * 1.3)

        for tline in t_lines:
            bbox = draw.textbbox((0, 0), tline, font=tf)
            tw = bbox[2] - bbox[0]
            tx = card_x + (card_w - tw) // 2
            draw_text_solid(
                draw, tline, tx, cur_y, tf,
                _TRANS_COLOR, int(group_alpha * 0.9), outline=2,
            )
            cur_y += t_line_h


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
    is_fading_out: bool,
    offset_x: int = 0,
):
    """Render text with word-by-word karaoke highlighting (Spanish + inline English).

    Text is drawn inside the card area — max width constrained to CARD_WIDTH - padding.
    Translation is handled by the English card (not rendered here).
    """
    f = font(base_size)
    text_max_w = CARD_WIDTH - CARD_PADDING * 2 - 40

    word_texts = [w['word'] for w in words]
    full_text = ' '.join(word_texts)

    lines = line_break(full_text, f, text_max_w)
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
        start_x = (VIDEO_WIDTH - line_w) // 2 + offset_x

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
                    word_font_size = base_size
                    use_glow = True
                    outline = 5
                elif state['is_active']:
                    word_color = _SPANISH_ACTIVE
                    word_font_size = base_size
                    use_glow = False
                    outline = 2
                elif t > word_end:
                    word_color = _SPANISH_PAST
                    word_font_size = base_size
                    use_glow = False
                    outline = 2
                else:
                    word_color = _SPANISH_UPCOMING
                    word_font_size = base_size
                    use_glow = False
                    outline = 2

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
                        outline=5, glow=True,
                        glow_color=ENGLISH_WORD_COLOR
                    )
                else:
                    draw_text_solid(
                        draw, display_word,
                        wx + offset_x, cur_y + offset_y,
                        wf, word_color, word_alpha,
                        outline=outline
                    )

            bbox = draw.textbbox((0, 0), display_word, font=f)
            word_w = bbox[2] - bbox[0]

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
    available_h: int,
    translations: Dict,
    is_fading_out: bool,
    offset_x: int = 0,
):
    """Render English hero word inside a large glassmorphism card.

    The card and content scale together via tiktok_pop_scale for a
    punchy pop-in entrance.
    """
    scale = tiktok_pop_scale(t, start)
    alpha = group_alpha

    if scale <= 0 or alpha <= 0:
        return

    # ── Measure content at natural size (scale=1.0) ──
    hero_base = _english_hero_size(text)
    ef_natural = font(hero_base)
    card_inner_w = CARD_WIDTH - CARD_PADDING * 2 - 40
    en_lines = line_break(text, ef_natural, card_inner_w)
    en_line_h = int(hero_base * 1.3)
    en_text_h = len(en_lines) * en_line_h

    lookup = re.sub(r'[^\w\s-]', '', text).strip().lower()
    trans = _lookup_translation(lookup, translations)

    trans_h = 0
    if trans:
        tf_natural = font(_TRANS_SIZE)
        t_lines = line_break(f"({trans})", tf_natural, card_inner_w)
        trans_h = len(t_lines) * int(_TRANS_SIZE * 1.3) + 16  # 16px gap

    # 4px accent bar + 10px padding
    accent_bar_h = 4 + 10
    content_h = accent_bar_h + en_text_h + trans_h
    natural_card_h = content_h + CARD_PADDING * 2
    natural_card_w = CARD_WIDTH

    # ── Apply scale ──
    s_card_w = int(natural_card_w * scale)
    s_card_h = int(natural_card_h * scale)
    s_card_x = (VIDEO_WIDTH - s_card_w) // 2 + offset_x
    # Center within the available vertical space
    s_card_y = base_y + (available_h - s_card_h) // 2

    card_alpha = int(210 * alpha / 255)

    # ── Shadow ──
    draw_rounded_card(
        frame, s_card_x, s_card_y, s_card_w, s_card_h,
        radius=25,
        fill=(15, 15, 35),
        alpha=card_alpha,
        shadow=True,
        shadow_offset=8,
        shadow_alpha=80,
    )

    # ── Subtle white border ──
    border_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    border_draw.rounded_rectangle(
        [s_card_x, s_card_y, s_card_x + s_card_w, s_card_y + s_card_h],
        radius=25,
        outline=(255, 255, 255, int(30 * alpha / 255)),
        width=2,
    )
    frame.paste(border_layer, (0, 0), border_layer)

    # ── Accent bar — horizontal 4px at top ──
    bar_alpha = int(alpha * 0.9)
    bar_layer = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar_layer)
    bar_x1 = s_card_x + 10
    bar_x2 = s_card_x + s_card_w - 10
    bar_y1 = s_card_y + 10
    bar_draw.rounded_rectangle(
        [bar_x1, bar_y1, bar_x2, bar_y1 + 4],
        radius=2,
        fill=(*ENGLISH_WORD_COLOR[:3], bar_alpha),
    )
    frame.paste(bar_layer, (0, 0), bar_layer)

    # ── English word — scaled font, centered inside card ──
    eng_size = int(hero_base * scale)
    ef = font(max(10, eng_size))
    s_line_h = int(eng_size * 1.3)
    cur_y = s_card_y + int(CARD_PADDING * scale) + int(accent_bar_h * scale)

    s_inner_w = s_card_w - int(CARD_PADDING * 2 * scale) - 20
    scaled_lines = line_break(text, ef, max(100, s_inner_w))

    for line in scaled_lines:
        bbox = draw.textbbox((0, 0), line, font=ef)
        lw = bbox[2] - bbox[0]
        lx = s_card_x + (s_card_w - lw) // 2

        if not is_fading_out:
            draw_text_with_glow(
                draw, frame, line, lx, cur_y, ef,
                ENGLISH_WORD_COLOR, alpha,
                outline=4, glow=True,
                glow_color=ENGLISH_WORD_COLOR,
                glow_radius=4,
            )
        else:
            draw_text_solid(draw, line, lx, cur_y, ef, ENGLISH_WORD_COLOR, alpha, outline=4)

        cur_y += s_line_h

    # ── Translation — scaled, centered below ──
    if trans:
        cur_y += int(16 * scale)
        t_size = max(10, int(_TRANS_SIZE * scale))
        tf = font(t_size)
        t_display = f"({trans})"
        t_line_h = int(t_size * 1.3)
        t_lines = line_break(t_display, tf, max(100, s_inner_w))

        for tline in t_lines:
            bbox = draw.textbbox((0, 0), tline, font=tf)
            tw = bbox[2] - bbox[0]
            tx = s_card_x + (s_card_w - tw) // 2
            draw_text_solid(draw, tline, tx, cur_y, tf,
                            _TRANS_COLOR, int(alpha * 0.9), outline=2)
            cur_y += t_line_h


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
    is_fading_out: bool,
    offset_x: int = 0,
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

    color = ENGLISH_WORD_COLOR if is_english else _SPANISH_ACTIVE

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2 + offset_x

        if is_english and not is_fading_out:
            draw_text_with_glow(
                draw, frame, line, lx, cur_y, f,
                color, alpha, outline=4, glow=True
            )
        else:
            draw_text_solid(draw, line, lx, cur_y, f, color, alpha, outline=2)

        cur_y += line_h

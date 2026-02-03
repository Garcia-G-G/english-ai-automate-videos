"""
Animation system for English AI Videos.

Provides professional TikTok-style text animations:
- Easing functions (ease-out-back, spring, bounce)
- Text rendering with per-word color/animation
- Subtitle processing with sentence boundary respect
"""

from .easing import (
    ease_out_back, ease_out_cubic, ease_out_quad,
    ease_in_out_cubic, ease_in_out_quad, ease_in_out_sine,
    ease_out_elastic, ease_out_bounce,
    spring_animation, tiktok_pop_scale,
    word_highlight_alpha, bounce_offset,
    pulse_scale, glow_intensity, get_alpha, get_scale,
)

from .subtitle_processor import SubtitleProcessor, clean_word_for_display

from .styles import (
    AnimationStyle, CleanPopStyle, EnergeticStyle, KaraokeStyle,
    STYLES, get_style,
)

from .text_renderer import (
    font, line_break,
    draw_text_solid, draw_text_with_glow, draw_text_centered,
    draw_glow, draw_progress_bar, draw_sparkles,
    get_word_animation_state,
    ENGLISH_WORD_COLOR, SPANISH_WORD_COLOR, SPANISH_DIMMED_COLOR,
    COLOR_WHITE, COLOR_YELLOW, COLOR_CYAN,
    SIZE_ENGLISH_WORD, SIZE_MAIN_SPANISH, SIZE_TRANSLATION,
    ENGLISH_WORD_SCALE, OUTLINE_THICK,
    EMPHASIS, VIDEO_WIDTH, VIDEO_HEIGHT, TEXT_AREA_WIDTH,
    MARGIN_X, GROUP_TRANSITION,
)

__all__ = [
    # Easing
    'ease_out_back', 'ease_out_cubic', 'ease_out_quad',
    'ease_in_out_cubic', 'ease_in_out_quad', 'ease_in_out_sine',
    'ease_out_elastic', 'ease_out_bounce',
    'spring_animation', 'tiktok_pop_scale',
    'word_highlight_alpha', 'bounce_offset',
    'pulse_scale', 'glow_intensity', 'get_alpha', 'get_scale',
    # Subtitle processing
    'SubtitleProcessor', 'clean_word_for_display',
    # Text rendering
    'font', 'line_break',
    'draw_text_solid', 'draw_text_with_glow', 'draw_text_centered',
    'draw_glow', 'draw_progress_bar', 'draw_sparkles',
    'get_word_animation_state',
    # Constants
    'ENGLISH_WORD_COLOR', 'SPANISH_WORD_COLOR', 'SPANISH_DIMMED_COLOR',
    'COLOR_WHITE', 'COLOR_YELLOW', 'COLOR_CYAN',
    'SIZE_ENGLISH_WORD', 'SIZE_MAIN_SPANISH', 'SIZE_TRANSLATION',
    'ENGLISH_WORD_SCALE', 'OUTLINE_THICK',
    'EMPHASIS', 'VIDEO_WIDTH', 'VIDEO_HEIGHT', 'TEXT_AREA_WIDTH',
    'MARGIN_X', 'GROUP_TRANSITION',
    # Animation styles
    'AnimationStyle', 'CleanPopStyle', 'EnergeticStyle', 'KaraokeStyle',
    'STYLES', 'get_style',
]

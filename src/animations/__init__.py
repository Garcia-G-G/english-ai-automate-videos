"""
Animation system for English AI Videos.

Provides professional TikTok-style text animations:
- Easing functions (ease-out-back, spring, bounce)
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
]

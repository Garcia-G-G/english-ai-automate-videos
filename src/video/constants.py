"""Video constants — re-exports from config/ for backward compatibility.

All canonical values live in src/config/.  This file re-exports them so
existing ``from .constants import ...`` statements keep working.
"""

# Re-export everything from config modules
from config.colors import (  # noqa: F401
    WHITE as COLOR_WHITE,
    YELLOW as COLOR_YELLOW,
    RED as COLOR_RED,
    GREEN as COLOR_GREEN,
    BLUE as COLOR_BLUE,
    ORANGE as COLOR_ORANGE,
    CORRECT_GREEN as COLOR_CORRECT,
    WRONG_RED as COLOR_WRONG,
    CYAN as COLOR_CYAN,
    ENGLISH_COLOR as COLOR_ENGLISH,
    SPANISH_COLOR as COLOR_SPANISH,
    ENGLISH_WORD_COLOR,
    SPANISH_WORD_COLOR,
    ENGLISH_GLOW_COLOR,
    ENGLISH_YELLOW,
    ENGLISH_GRADIENT_START,
    ENGLISH_GRADIENT_END,
    GRADIENT_COLORS,
    QUIZ_COLORS,
)

from config.layout import (  # noqa: F401
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    FPS,
    MARGIN_X,
    TEXT_AREA_WIDTH,
    SAFE_AREA_TOP,
    SAFE_AREA_BOTTOM,
    SAFE_AREA_HEIGHT,
    TEXT_CENTER_Y,
    MAX_CHARS_PER_LINE,
    MAX_LINES_PER_SUBTITLE,
    MIN_GAP_BETWEEN_SUBTITLES,
    BAR_HEIGHT,
    BAR_Y,
    BAR_MARGIN,
    OPTION_STAGGER,
    SLIDE_DISTANCE,
)

from config.typography import (  # noqa: F401
    FONT_SIZE_ENGLISH,
    FONT_SIZE_SPANISH,
    FONT_SIZE_TRANS,
    FONT_SIZE_QUESTION,
    FONT_SIZE_OPTION,
    FONT_SIZE_TIMER,
    FONT_SIZE_BIG_WORD,
    SIZE_MAIN_SPANISH,
    SIZE_ENGLISH_WORD,
    SIZE_TRANSLATION,
    SIZE_CONTEXT,
    OUTLINE_THICK,
    ENGLISH_WORD_SCALE,
    ENGLISH_GLOW_RADIUS,
)

from config.timing import (  # noqa: F401
    POP_DURATION,
    FADE_IN,
    FADE_OUT,
    CROSSFADE_OVERLAP,
    BOUNCE,
    MIN_DISPLAY,
    ANTICIPATION_MS,
    VISUAL_ANTICIPATION,
    GROUP_TRANSITION,
    EMPHASIS,
)

# math is no longer needed here; remove the stale import

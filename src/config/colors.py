"""Unified color palette for all video types.

Single source of truth — every module imports colors from here.
"""

# ── General palette ──────────────────────────────────────────────
WHITE = (255, 255, 255)
YELLOW = (255, 215, 0)
RED = (255, 60, 60)
GREEN = (50, 255, 100)
BLUE = (100, 150, 255)
ORANGE = (255, 165, 0)
CYAN = (0, 212, 255)

# Semantic aliases
CORRECT_GREEN = (50, 255, 100)
WRONG_RED = (255, 80, 80)
ENGLISH_COLOR = (255, 215, 0)
SPANISH_COLOR = (0, 212, 255)

# ── English word styling ─────────────────────────────────────────
ENGLISH_WORD_COLOR = (255, 215, 0)
SPANISH_WORD_COLOR = (0, 212, 255)
SPANISH_DIMMED_COLOR = (0, 170, 210)
ENGLISH_GLOW_COLOR = (0, 220, 255, 150)

# Alternative English colors
ENGLISH_YELLOW = (255, 220, 0)
ENGLISH_GRADIENT_START = (255, 220, 0)
ENGLISH_GRADIENT_END = (255, 150, 0)

# ── Background gradient ──────────────────────────────────────────
GRADIENT_COLORS = [
    [(255, 100, 180), (180, 80, 220), (80, 100, 220)],
    [(255, 120, 200), (200, 60, 200), (100, 80, 240)],
    [(240, 80, 160), (160, 60, 200), (60, 80, 200)],
]

# ── Quiz pastel palette ──────────────────────────────────────────
QUIZ_COLORS = {
    'question_grad_start': (255, 130, 170),
    'question_grad_end': (150, 140, 255),
    'option_bg': (100, 160, 230),
    'option_bg_alt': (130, 180, 240),
    'letter_circle': (255, 120, 130),
    'letter_border': (255, 255, 255),
    'correct_green': (100, 220, 160),
    'correct_glow': (140, 235, 180),
    'wrong_fade': (190, 185, 205),
    'wrong_text': (130, 125, 145),
    'countdown_bg': (255, 190, 160),
    'countdown_text': (100, 70, 60),
    'light_bg': (255, 252, 248),
    'text_dark': (50, 45, 60),
    'text_medium': (90, 85, 100),
}

# ── True/False button gradients ──────────────────────────────────
VERDADERO_GRAD_TOP = (76, 175, 80)       # #4CAF50
VERDADERO_GRAD_BOT = (46, 125, 50)       # #2E7D32
FALSO_GRAD_TOP = (244, 67, 54)           # #F44336
FALSO_GRAD_BOT = (198, 40, 40)           # #C62828
NEUTRAL_GRAD_TOP = (100, 160, 230)
NEUTRAL_GRAD_BOT = (70, 120, 190)

# ── Karaoke colors ───────────────────────────────────────────────
KARAOKE_ACTIVE = (255, 255, 255)
KARAOKE_INACTIVE = (160, 165, 175)
KARAOKE_ENGLISH = (255, 215, 0)
KARAOKE_ENGLISH_ACTIVE = (255, 235, 100)
KARAOKE_TRANSLATION = (0, 210, 230)
KARAOKE_PAST = (100, 105, 115)

# ── Countdown ring colors ────────────────────────────────────────
COUNTDOWN_COLORS = {
    3: (100, 220, 160),   # Green
    2: (255, 200, 100),   # Yellow
    1: (255, 100, 100),   # Red
}

# ── Card / panel colors ─────────────────────────────────────────
CARD_COLORS = {
    'white_card': (255, 255, 255),
    'cream_card': (255, 252, 245),
    'dark_card': (30, 30, 45),
    'shadow': (0, 0, 0),
    'divider': (200, 200, 210),
    'highlight_row': (255, 255, 255, 25),
}

# ── Difficulty badge colors ─────────────────────────────────────
DIFFICULTY_COLORS = {
    'facil': (76, 175, 80),
    'medio': (255, 193, 7),
    'dificil': (255, 87, 34),
    'experto': (211, 47, 47),
}

# ── Generic badge colors ────────────────────────────────────────
BADGE_COLORS = {
    'green': (76, 175, 80),
    'blue': (66, 133, 244),
    'orange': (255, 152, 0),
    'red': (244, 67, 54),
    'purple': (156, 39, 176),
}

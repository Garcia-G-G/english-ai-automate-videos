"""Video constants — colors, sizes, quiz palette, animation timing."""

import math

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# Layout
MARGIN_X = 80
TEXT_AREA_WIDTH = VIDEO_WIDTH - (MARGIN_X * 2)

# Gradient - vibrant pink/purple/blue
GRADIENT_COLORS = [
    [(255, 100, 180), (180, 80, 220), (80, 100, 220)],
    [(255, 120, 200), (200, 60, 200), (100, 80, 240)],
    [(240, 80, 160), (160, 60, 200), (60, 80, 200)],
]

# Colors - General
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (255, 215, 0)
COLOR_RED = (255, 60, 60)
COLOR_GREEN = (50, 255, 100)
COLOR_BLUE = (100, 150, 255)
COLOR_ORANGE = (255, 165, 0)
COLOR_CORRECT = (50, 255, 100)
COLOR_WRONG = (255, 80, 80)
COLOR_CYAN = (0, 212, 255)
COLOR_ENGLISH = (255, 215, 0)
COLOR_SPANISH = (0, 212, 255)

# Quiz-specific colors - BEAUTIFUL PASTEL PALETTE
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

# Typography
FONT_SIZE_ENGLISH = 140
FONT_SIZE_SPANISH = 90
FONT_SIZE_TRANS = 56
FONT_SIZE_QUESTION = 76
FONT_SIZE_OPTION = 58
FONT_SIZE_TIMER = 220
FONT_SIZE_BIG_WORD = 160
OUTLINE_THICK = 12

# Animation
POP_DURATION = 0.22
FADE_IN = 0.25
FADE_OUT = 0.40
CROSSFADE_OVERLAP = 0.15
BOUNCE = 1.18
MIN_DISPLAY = 0.9

# English word styling
ENGLISH_WORD_COLOR = (255, 215, 0)
SPANISH_WORD_COLOR = (0, 212, 255)
ENGLISH_WORD_SCALE = 1.20
ENGLISH_GLOW_COLOR = (0, 220, 255, 150)
ENGLISH_GLOW_RADIUS = 14

# Alternative English colors
ENGLISH_YELLOW = (255, 220, 0)
ENGLISH_GRADIENT_START = (255, 220, 0)
ENGLISH_GRADIENT_END = (255, 150, 0)

# Smooth transition timing
GROUP_TRANSITION = 0.25

# Visual hierarchy sizes
SIZE_MAIN_SPANISH = 90
SIZE_ENGLISH_WORD = 145
SIZE_TRANSLATION = 55
SIZE_CONTEXT = 75

# Staggered animation delays for options
OPTION_STAGGER = 0.15
SLIDE_DISTANCE = 300

# Progress bar
BAR_HEIGHT = 10
BAR_Y = VIDEO_HEIGHT - 70
BAR_MARGIN = 40

# Emphasis words
EMPHASIS = {
    'no', 'nunca', 'cuidado', 'error', 'ojo',
    'muy', 'siempre', 'realmente', 'verdaderamente',
    'recuerda', 'importante', 'significa', 'diferente',
    'correcta', 'correcto', 'incorrecto', 'significa',
    'pero', 'sino', 'ejemplo', 'realidad',
}

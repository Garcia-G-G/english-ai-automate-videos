"""Unified layout constants for all video types.

All zone positions are expressed as fractions or pixel values relative to
the 1080x1920 TikTok portrait canvas.
"""

# ── Canvas ────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# ── Global safe areas ────────────────────────────────────────────
MARGIN_X = 80
TEXT_AREA_WIDTH = VIDEO_WIDTH - (MARGIN_X * 2)
SAFE_AREA_TOP = int(VIDEO_HEIGHT * 0.15)       # 15% from top
SAFE_AREA_BOTTOM = int(VIDEO_HEIGHT * 0.85)    # 15% from bottom
SAFE_AREA_HEIGHT = SAFE_AREA_BOTTOM - SAFE_AREA_TOP
TEXT_CENTER_Y = VIDEO_HEIGHT // 2 - 40         # Slightly above center

# ── Subtitle formatting (BBC guidelines) ─────────────────────────
MAX_CHARS_PER_LINE = 40
MAX_LINES_PER_SUBTITLE = 2
MIN_GAP_BETWEEN_SUBTITLES = 0.25  # 250ms

# ── Progress bar ──────────────────────────────────────────────────
BAR_HEIGHT = 10
BAR_Y = VIDEO_HEIGHT - 70
BAR_MARGIN = 40

# ── Quiz layout zones ────────────────────────────────────────────
QUIZ_QUESTION_ZONE_TOP = SAFE_AREA_TOP
QUIZ_QUESTION_ZONE_BOTTOM = int(VIDEO_HEIGHT * 0.40)
QUIZ_OPTIONS_ZONE_TOP = int(VIDEO_HEIGHT * 0.42)
QUIZ_OPTIONS_ZONE_BOTTOM = int(VIDEO_HEIGHT * 0.72)
QUIZ_COUNTDOWN_ZONE_TOP = int(VIDEO_HEIGHT * 0.75)

# ── True/false layout zones ──────────────────────────────────────
TF_QUESTION_ZONE_TOP = int(VIDEO_HEIGHT * 0.10)
TF_QUESTION_ZONE_BOTTOM = int(VIDEO_HEIGHT * 0.38)
TF_QUESTION_ZONE_HEIGHT = TF_QUESTION_ZONE_BOTTOM - TF_QUESTION_ZONE_TOP
TF_COUNTDOWN_CENTER_Y = int(VIDEO_HEIGHT * 0.44)
TF_BUTTONS_ZONE_CENTER = int(VIDEO_HEIGHT * 0.56)
TF_EXPLANATION_ZONE_TOP = int(VIDEO_HEIGHT * 0.70)

# True/false button dimensions
TF_BTN_WIDTH = 420
TF_BTN_HEIGHT = 130
TF_BTN_GAP = 70
TF_BTN_RADIUS = 30

# ── Fill-in-the-blank layout ─────────────────────────────────────
FB_SENTENCE_Y = 350
FB_OPTIONS_START_Y = 600
FB_COUNTDOWN_CENTER_Y = 920
FB_TRANSLATION_Y = 1000

# ── Pronunciation layout zones ───────────────────────────────────
# Spread out to prevent overlap with large/wrapped text.
# Phases: title+translation+question → incorrect → correct (moves up) + tip
PRON_TITLE_Y = 250
PRON_TRANSLATION_Y = 430
PRON_QUESTION_Y = 530
PRON_INCORRECT_LABEL_Y = 650
PRON_INCORRECT_TEXT_Y = 720
PRON_CORRECT_LABEL_Y = 1000
PRON_CORRECT_TEXT_Y = 1080
PRON_CORRECT_FINAL_LABEL_Y = 650
PRON_CORRECT_FINAL_TEXT_Y = 750
PRON_TIP_Y = 900

# ── Card dimensions ──────────────────────────────────────────────
CARD_MARGIN_X = 60
CARD_PADDING = 40
CARD_RADIUS = 30
CARD_WIDTH = VIDEO_WIDTH - 2 * CARD_MARGIN_X  # 960px

# ── Two-column vocabulary ────────────────────────────────────────
VOCAB_ROW_HEIGHT = 90
VOCAB_DIVIDER_X = 500
VOCAB_START_Y = 350
VOCAB_MAX_ROWS = 12

# ── Timer bar ────────────────────────────────────────────────────
TIMER_BAR_WIDTH = 800
TIMER_BAR_HEIGHT = 12
TIMER_BAR_Y = 1750
TIMER_BAR_X = (VIDEO_WIDTH - 800) // 2  # centered

# ── Staggered animation ──────────────────────────────────────────
OPTION_STAGGER = 0.15
SLIDE_DISTANCE = 300

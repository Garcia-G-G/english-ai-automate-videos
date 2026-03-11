"""Unified timing constants for all video types.

Animation durations, TTS pauses, visual anticipation.
"""

# ── Word animation (TikTok style) ────────────────────────────────
POP_DURATION = 0.18           # 180ms pop animation
FADE_IN = 0.15                # 150ms fade-in
FADE_OUT = 0.35               # 350ms fade-out
CROSSFADE_OVERLAP = 0.10      # 100ms overlap for smooth transitions
BOUNCE = 1.12                 # 112% overshoot (sweet spot for TikTok)
MIN_DISPLAY = 0.8             # Minimum display time in seconds

# Pre-roll: Display text BEFORE audio for perfect sync
ANTICIPATION_MS = 80          # 80ms pre-roll (Netflix standard: 1-2 frames)

# Visual anticipation — show element this many seconds before audio starts
# Bug A2 fix: 150ms for quiz/true_false/fill_blank timed reveals
VISUAL_ANTICIPATION = 0.15

# Smooth group transitions (educational)
GROUP_TRANSITION = 0.20

# ── Karaoke animation timing ─────────────────────────────────────
KARAOKE_ANTICIPATION_TIME = 0.08
KARAOKE_POP_DURATION = 0.15
KARAOKE_FADE_DURATION = 0.12
KARAOKE_SCALE_ACTIVE = 1.05
KARAOKE_SCALE_NORMAL = 1.0

# ── True/false slide timing ──────────────────────────────────────
TF_SLIDE_DURATION = 0.5
TF_QUESTION_FADE_DURATION = 0.4

# ── TTS pauses (single source of truth) ──────────────────────────
PAUSE_AFTER_QUESTION = 0.5
PAUSE_AFTER_OPTION = 0.6
PAUSE_AFTER_THINK = 1.5       # Gap after "piensa bien" before countdown
PAUSE_AFTER_COUNTDOWN = 1.0   # Between countdown numbers
PAUSE_AFTER_LAST_COUNT = 1.0  # Dramatic pause before answer reveal
PAUSE_AFTER_ANSWER = 0.4
PAUSE_AFTER_EXPLANATION = 0.5

# ── Emphasis words (Spanish words that get bounce animation) ─────
EMPHASIS = {
    'no', 'nunca', 'cuidado', 'error', 'ojo',
    'muy', 'siempre', 'realmente', 'verdaderamente',
    'recuerda', 'importante', 'significa', 'diferente',
    'correcta', 'correcto', 'incorrecto', 'significa',
    'pero', 'sino', 'ejemplo', 'realidad',
}

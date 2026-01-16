#!/usr/bin/env python3
"""
Video Generator for English AI Videos - Multi-Type Support
Supports: educational, quiz, true_false, fill_blank, pronunciation

Video Types:
- educational: Word-by-word sync with audio (original)
- quiz: Question → Options A/B/C/D → Timer → Answer reveal
- true_false: Statement → ✓/✗ options → Timer → Answer reveal
- fill_blank: Sentence with ___ → Options → Answer reveal
- pronunciation: Word → Phonetic → Common mistake → Correct
"""

import argparse
import json
import math
import os
import re
import sys
from typing import List, Dict, Tuple, Optional

from moviepy import VideoClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np


# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
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
COLOR_YELLOW = (255, 230, 0)
COLOR_RED = (255, 60, 60)
COLOR_GREEN = (50, 255, 100)
COLOR_BLUE = (100, 150, 255)
COLOR_ORANGE = (255, 165, 0)
COLOR_CORRECT = (50, 255, 100)
COLOR_WRONG = (255, 80, 80)

# Quiz-specific colors - BEAUTIFUL PASTEL PALETTE (no harsh black)
QUIZ_COLORS = {
    # Question box gradient - vibrant pink to soft purple
    'question_grad_start': (255, 130, 170),    # Vibrant pink #FF82AA
    'question_grad_end': (150, 140, 255),      # Soft purple #968CFF

    # Option buttons - pleasant sky blue
    'option_bg': (100, 160, 230),              # Sky blue #64A0E6
    'option_bg_alt': (130, 180, 240),          # Lighter sky blue

    # Letter circles - warm coral
    'letter_circle': (255, 120, 130),          # Warm coral #FF7882
    'letter_border': (255, 255, 255),          # White border

    # Correct answer - fresh mint green
    'correct_green': (100, 220, 160),          # Fresh mint #64DCA0
    'correct_glow': (140, 235, 180),           # Lighter mint for glow

    # Wrong answers - soft lavender (not gray)
    'wrong_fade': (190, 185, 205),             # Soft lavender
    'wrong_text': (130, 125, 145),             # Muted text

    # Countdown - warm peach
    'countdown_bg': (255, 190, 160),           # Warm peach #FFBEA0
    'countdown_text': (100, 70, 60),           # Warm brown text

    # Background for options area - soft cream white
    'light_bg': (255, 252, 248),               # Warm cream #FFFCF8

    # Text colors (avoid pure black)
    'text_dark': (50, 45, 60),                 # Soft dark
    'text_medium': (90, 85, 100),              # Medium
}

# Typography - EXTRA BOLD for maximum sharpness
FONT_SIZE_ENGLISH = 140
FONT_SIZE_SPANISH = 90
FONT_SIZE_TRANS = 56
FONT_SIZE_QUESTION = 76  # Slightly larger
FONT_SIZE_OPTION = 58    # Slightly larger
FONT_SIZE_TIMER = 220
FONT_SIZE_BIG_WORD = 160
OUTLINE_THICK = 12  # VERY bold for sharp crisp text

# Animation - SMOOTH AND DYNAMIC
POP_DURATION = 0.22  # Pop-in duration
FADE_IN = 0.25  # Longer for smoother entrance
FADE_OUT = 0.40  # Longer for smoother exit (was 0.30)
CROSSFADE_OVERLAP = 0.15  # Start next word before previous fades out
BOUNCE = 1.18  # Bounce amount
MIN_DISPLAY = 0.9

# Staggered animation delays for options
OPTION_STAGGER = 0.15  # Delay between each option appearing
SLIDE_DISTANCE = 300  # How far options slide in from

# Progress bar
BAR_HEIGHT = 10
BAR_Y = VIDEO_HEIGHT - 70
BAR_MARGIN = 40

# Emphasis words
EMPHASIS = {'no', 'nunca', 'siempre', 'muy', 'roja', 'correcta',
            'error', 'recuerda', 'importante', 'cuidado', 'doble'}

_fonts = {}


def font(size: int) -> ImageFont.FreeTypeFont:
    if size in _fonts:
        return _fonts[size]

    paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]

    for p in paths:
        try:
            f = ImageFont.truetype(p, size)
            _fonts[size] = f
            return f
        except:
            continue

    f = ImageFont.load_default()
    _fonts[size] = f
    return f


# ============== ANIMATED BACKGROUND SYSTEM ==============
# OPTIMIZED with numpy vectorization for fast rendering

import random
random.seed(42)  # Consistent particle positions

# Bokeh particle system - fewer, larger particles for performance
BOKEH_PARTICLES = []
for i in range(20):  # Reduced for performance
    BOKEH_PARTICLES.append({
        'x': random.random(),
        'y': random.random(),
        'size': random.randint(40, 120),  # Larger particles
        'speed_x': (random.random() - 0.5) * 0.012,
        'speed_y': (random.random() - 0.5) * 0.006 - 0.002,
        'alpha': random.random() * 0.2 + 0.1,
        'color_shift': random.random() * 2 * math.pi,
        'pulse_speed': random.random() * 0.4 + 0.2,
    })


def gradient(w: int, h: int, t: float) -> np.ndarray:
    """Create VIBRANT ANIMATED background - OPTIMIZED with numpy."""

    # ===== BASE GRADIENT WITH COLOR BREATHING =====
    idx = int(t / 5) % len(GRADIENT_COLORS)
    nxt = (idx + 1) % len(GRADIENT_COLORS)
    blend = (t % 5) / 5

    pal = GRADIENT_COLORS[idx]
    npal = GRADIENT_COLORS[nxt]

    # Color breathing - subtle pulsing
    breath = 1.0 + 0.06 * math.sin(t * 0.8)

    colors = np.array([
        [min(255, int((pal[i][j] + (npal[i][j] - pal[i][j]) * blend) * breath))
         for j in range(3)] for i in range(3)
    ], dtype=np.float32)

    # ===== VECTORIZED GRADIENT WITH WAVE =====
    y_coords = np.arange(h).reshape(-1, 1)
    x_coords = np.arange(w).reshape(1, -1)

    # Animated wave distortion
    wave = math.sin(t * 0.3) * 0.08
    wave2 = math.sin(t * 0.5 + 1.5) * 0.04

    # Aurora wave effect (vectorized)
    aurora = (
        30 * np.sin(y_coords * 0.008 + t * 0.4) +
        20 * np.sin(y_coords * 0.012 + t * 0.6 + 1.5) +
        40 * np.sin(y_coords * 0.005 + t * 0.3 + 3.0)
    ) / h * 0.08

    # Calculate gradient ratio
    ratio = ((y_coords / h) + wave + wave2 * (x_coords / w) + aurora) % 1.0

    # Create gradient image
    img = np.zeros((h, w, 3), dtype=np.float32)

    # Interpolate colors based on ratio
    mask1 = ratio < 0.5
    r1 = ratio * 2
    r2 = (ratio - 0.5) * 2

    for c in range(3):
        img[:, :, c] = np.where(
            mask1,
            colors[0, c] + (colors[1, c] - colors[0, c]) * r1,
            colors[1, c] + (colors[2, c] - colors[1, c]) * r2
        )

    # ===== FLOATING BOKEH PARTICLES (optimized) =====
    for particle in BOKEH_PARTICLES:
        # Animate position with wrapping
        px = (particle['x'] + particle['speed_x'] * t * 50) % 1.0
        py = (particle['y'] + particle['speed_y'] * t * 50) % 1.0

        cx = int(px * w)
        cy = int(py * h)

        # Pulsing size and alpha
        pulse = 1.0 + 0.25 * math.sin(t * particle['pulse_speed'] * 2 + particle['color_shift'])
        size = int(particle['size'] * pulse)
        alpha = particle['alpha'] * (0.7 + 0.3 * math.sin(t * particle['pulse_speed'] + particle['color_shift']))

        # Color shift
        hue = t * 0.3 + particle['color_shift']
        p_color = np.array([
            220 + 35 * math.sin(hue),
            190 + 40 * math.sin(hue + 2),
            230 + 25 * math.cos(hue)
        ], dtype=np.float32)

        # Create bokeh circle mask (vectorized)
        y_min, y_max = max(0, cy - size), min(h, cy + size + 1)
        x_min, x_max = max(0, cx - size), min(w, cx + size + 1)

        if y_max > y_min and x_max > x_min:
            yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            mask = dist <= size

            # Gaussian falloff for soft bokeh
            falloff = np.exp(-2.5 * (dist / max(size, 1)) ** 2)
            blend_alpha = alpha * falloff * mask

            for c in range(3):
                img[y_min:y_max, x_min:x_max, c] = (
                    img[y_min:y_max, x_min:x_max, c] * (1 - blend_alpha) +
                    p_color[c] * blend_alpha
                )

    # ===== LIGHT LEAKS (vectorized) =====
    yy_full, xx_full = np.ogrid[0:h, 0:w]

    # Light leak 1 - warm, top right area
    lx1 = w * (0.75 + 0.15 * math.sin(t * 0.2))
    ly1 = h * (0.18 + 0.08 * math.sin(t * 0.25 + 1))
    lr1 = max(w, h) * 0.55

    dist1 = np.sqrt((xx_full - lx1) ** 2 + (yy_full - ly1) ** 2)
    mask1 = dist1 < lr1
    intensity1 = 0.1 * ((1 - dist1 / lr1) ** 2) * mask1

    img[:, :, 0] += 255 * intensity1
    img[:, :, 1] += 190 * intensity1
    img[:, :, 2] += 160 * intensity1

    # Light leak 2 - cool, bottom left area
    lx2 = w * (0.25 + 0.12 * math.sin(t * 0.18 + 2))
    ly2 = h * (0.82 + 0.06 * math.sin(t * 0.22))
    lr2 = max(w, h) * 0.45

    dist2 = np.sqrt((xx_full - lx2) ** 2 + (yy_full - ly2) ** 2)
    mask2 = dist2 < lr2
    intensity2 = 0.07 * ((1 - dist2 / lr2) ** 2) * mask2

    img[:, :, 0] += 140 * intensity2
    img[:, :, 1] += 170 * intensity2
    img[:, :, 2] += 255 * intensity2

    # ===== SHIMMER/SPARKLE OVERLAY =====
    # Add subtle animated shimmer across the frame
    shimmer = 8 * np.sin(y_coords * 0.02 + x_coords * 0.01 + t * 2)
    shimmer += 5 * np.sin(y_coords * 0.015 - x_coords * 0.008 + t * 1.5 + 1)

    img[:, :, 0] += shimmer
    img[:, :, 1] += shimmer * 0.9
    img[:, :, 2] += shimmer * 1.1

    return np.clip(img, 0, 255).astype(np.uint8)


def ease_out_back(t: float) -> float:
    """Ease out with slight overshoot."""
    c = 1.70158
    return 1 + (c + 1) * pow(t - 1, 3) + c * pow(t - 1, 2)


def ease_out_cubic(t: float) -> float:
    return 1 - pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def ease_out_elastic(t: float) -> float:
    """Elastic ease out for bouncy effects."""
    if t == 0 or t == 1:
        return t
    p = 0.3
    s = p / 4
    return pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / p) + 1


def ease_in_out_quad(x: float) -> float:
    """Smooth ease in-out for seamless transitions."""
    if x < 0.5:
        return 2 * x * x
    return 1 - pow(-2 * x + 2, 2) / 2


def ease_in_out_sine(x: float) -> float:
    """Very smooth sine-based ease in-out."""
    return -(math.cos(math.pi * x) - 1) / 2


def ease_out_bounce(t: float) -> float:
    """Bounce ease out."""
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


def pulse_scale(t: float, start: float, duration: float = 0.6) -> float:
    """Pulsing scale effect (1.0 -> 1.08 -> 1.0) for correct answer."""
    if t < start:
        return 1.0
    elapsed = t - start
    cycle = elapsed % duration
    progress = cycle / duration
    # Smooth pulse using sine wave
    return 1.0 + 0.08 * math.sin(progress * math.pi * 2)


def glow_intensity(t: float, start: float) -> float:
    """Glowing intensity that pulses."""
    if t < start:
        return 0.0
    elapsed = t - start
    # Fade in then pulse
    if elapsed < 0.3:
        return elapsed / 0.3
    # Continuous pulse
    return 0.7 + 0.3 * math.sin((elapsed - 0.3) * 4)


def slide_in_x(t: float, start: float, duration: float = 0.4) -> float:
    """Get X offset for smooth slide-in from right animation with bounce."""
    if t < start:
        return SLIDE_DISTANCE  # Start off screen to the right
    elapsed = t - start
    if elapsed >= duration:
        return 0
    progress = elapsed / duration
    # Use bounce for more playful motion
    eased = ease_out_back(progress)
    return int(SLIDE_DISTANCE * (1 - min(1.0, eased)))


def get_alpha(t: float, start: float, fade_duration: float = 0.2) -> int:
    """Get alpha for fade-in effect."""
    if t < start:
        return 0
    elapsed = t - start
    if elapsed >= fade_duration:
        return 255
    return int(255 * ease_out_cubic(elapsed / fade_duration))


def get_scale(t: float, start: float, duration: float = 0.2) -> float:
    """Get scale for pop-in effect."""
    if t < start:
        return 0
    elapsed = t - start
    if elapsed >= duration:
        return 1.0
    progress = elapsed / duration
    return ease_out_back(progress)


def draw_sparkles(draw: ImageDraw.Draw, center_x: int, center_y: int, t: float, start_time: float, radius: int = 150):
    """Draw sparkle/star burst particles around a point for celebratory effect."""
    elapsed = t - start_time
    if elapsed < 0:
        return

    # Particle properties
    num_particles = 12
    particle_life = 1.2  # seconds

    if elapsed > particle_life:
        return

    progress = elapsed / particle_life

    for i in range(num_particles):
        # Each particle has unique angle
        angle = (i / num_particles) * 2 * math.pi + progress * 0.5
        # Expand outward over time
        distance = radius * ease_out_cubic(progress)

        px = center_x + int(math.cos(angle) * distance)
        py = center_y + int(math.sin(angle) * distance)

        # Fade out as particles expand
        alpha = int(255 * (1 - progress))
        if alpha <= 0:
            continue

        # Alternate between star shapes
        if i % 3 == 0:
            # Star shape (4-point)
            size = int(12 * (1 - progress * 0.5))
            draw.polygon([
                (px, py - size), (px + size//3, py - size//3),
                (px + size, py), (px + size//3, py + size//3),
                (px, py + size), (px - size//3, py + size//3),
                (px - size, py), (px - size//3, py - size//3),
            ], fill=(255, 255, 255, alpha))
        elif i % 3 == 1:
            # Small circle
            r = int(6 * (1 - progress * 0.5))
            draw.ellipse([px - r, py - r, px + r, py + r],
                        fill=(255, 230, 100, alpha))  # Golden
        else:
            # Diamond
            size = int(8 * (1 - progress * 0.5))
            draw.polygon([
                (px, py - size), (px + size, py),
                (px, py + size), (px - size, py)
            ], fill=(200, 255, 200, alpha))  # Light green


def line_break(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    """Smart line breaking."""
    if not text.strip():
        return []

    dummy = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(dummy)

    bbox = draw.textbbox((0, 0), text, font=f)
    if bbox[2] - bbox[0] <= max_w:
        return [text]

    words = text.split()
    lines = []
    current = []

    for word in words:
        test = current + [word]
        bbox = draw.textbbox((0, 0), ' '.join(test), font=f)

        if bbox[2] - bbox[0] <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(' '.join(current))
            current = [word]

    if current:
        lines.append(' '.join(current))
    return lines


def draw_text_solid(
    draw: ImageDraw.Draw,
    text: str, x: int, y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK
) -> Tuple[int, int]:
    """Draw text with thick solid outline."""
    if alpha <= 0:
        return 0, 0

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    out_color = (0, 0, 0, alpha)
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (1, 1), (-1, 1), (1, -1)]

    for dist in [outline, outline - 2, outline - 4]:
        if dist <= 0:
            continue
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    for dist in range(1, min(4, outline), 2):
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    draw.text((x, y), text, font=f, fill=(*color, alpha))

    return w, h


def draw_text_centered(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK,
    max_width: int = TEXT_AREA_WIDTH
) -> int:
    """Draw centered text with line wrapping. Returns total height."""
    if alpha <= 0:
        return 0

    lines = line_break(text, f, max_width)
    line_h = int(f.size * 1.35)
    total_h = 0

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        lw = bbox[2] - bbox[0]
        lx = (VIDEO_WIDTH - lw) // 2
        draw_text_solid(draw, line, lx, y + total_h, f, color, alpha, outline)
        total_h += line_h

    return total_h


def draw_progress_bar(draw: ImageDraw.Draw, progress: float):
    """Draw progress bar at bottom."""
    bar_w = VIDEO_WIDTH - (BAR_MARGIN * 2)

    draw.rounded_rectangle(
        [BAR_MARGIN, BAR_Y, BAR_MARGIN + bar_w, BAR_Y + BAR_HEIGHT],
        radius=BAR_HEIGHT // 2,
        fill=(255, 255, 255, 80)
    )

    if progress > 0.01:
        fill_w = max(BAR_HEIGHT, int(bar_w * progress))
        draw.rounded_rectangle(
            [BAR_MARGIN, BAR_Y, BAR_MARGIN + fill_w, BAR_Y + BAR_HEIGHT],
            radius=BAR_HEIGHT // 2,
            fill=(100, 255, 150, 255)
        )


def draw_quiz_timeline(draw: ImageDraw.Draw, progress: float, is_countdown: bool = False):
    """Draw animated timeline at top of quiz - slides from left to right.

    Args:
        progress: 0.0 to 1.0 progress through video
        is_countdown: True if in countdown phase (changes color)
    """
    timeline_y = 100
    timeline_h = 8
    timeline_margin = 50

    bar_w = VIDEO_WIDTH - (timeline_margin * 2)

    # Background track
    draw.rounded_rectangle(
        [timeline_margin, timeline_y, timeline_margin + bar_w, timeline_y + timeline_h],
        radius=timeline_h // 2,
        fill=(255, 255, 255, 100)
    )

    if progress > 0.01:
        fill_w = max(timeline_h, int(bar_w * progress))

        # Color based on phase
        if is_countdown:
            # Gradient from green to red during countdown
            if progress < 0.33:
                color = (100, 220, 160, 255)  # Green
            elif progress < 0.66:
                color = (255, 200, 100, 255)  # Yellow
            else:
                color = (255, 130, 130, 255)  # Red
        else:
            color = (255, 150, 180, 255)  # Pink for normal progress

        draw.rounded_rectangle(
            [timeline_margin, timeline_y, timeline_margin + fill_w, timeline_y + timeline_h],
            radius=timeline_h // 2,
            fill=color
        )

        # Animated dot at end of progress
        dot_x = timeline_margin + fill_w
        dot_r = 12
        # Pulse effect
        pulse = 1.0 + 0.15 * math.sin(progress * 20)
        actual_r = int(dot_r * pulse)
        draw.ellipse(
            [dot_x - actual_r, timeline_y + timeline_h//2 - actual_r,
             dot_x + actual_r, timeline_y + timeline_h//2 + actual_r],
            fill=color
        )


# ============================================================
# QUIZ VIDEO TYPE - Timestamp-synced
# ============================================================

def find_word_time(words: List[Dict], target: str, start_from: int = 0) -> Tuple[Optional[float], int]:
    """Find the timestamp when a specific word is spoken."""
    target_lower = target.lower().strip('.,!?')
    for i in range(start_from, len(words)):
        word = words[i]['word'].lower().strip('.,!?')
        if word == target_lower:
            return words[i]['start'], i
    return None, start_from


def find_phrase_time(words: List[Dict], phrase: str, start_from: int = 0) -> Optional[float]:
    """Find when a phrase starts in the word list."""
    phrase_words = phrase.lower().split()
    if not phrase_words:
        return None

    first_word = phrase_words[0].strip('.,!?')
    time, _ = find_word_time(words, first_word, start_from)
    return time


def parse_quiz_timestamps(words: List[Dict]) -> Dict[str, float]:
    """Parse TTS timestamps to find key moments in quiz audio.

    CRITICAL: This function must provide EXACT timestamps for perfect audio-visual sync.
    Whisper may miss single letters (A, B, C, D) - we use multiple detection strategies.
    """
    timestamps = {
        'question_start': 0.0,
        'question_end': 0.0,
        'options_start': 0.0,
        'option_a': 0.0,
        'option_b': 0.0,
        'option_c': 0.0,
        'option_d': 0.0,
        'think_start': 0.0,
        'countdown_3': 0.0,
        'countdown_2': 0.0,
        'countdown_1': 0.0,
        'answer_start': 0.0,
        'explanation_start': 0.0,
    }

    if not words:
        return timestamps

    timestamps['question_start'] = words[0]['start']

    # Find where question ends (usually at "inglés" or before first option)
    for i, w in enumerate(words):
        word_lower = w['word'].lower()
        if word_lower in ['inglés', 'ingles', 'english']:
            timestamps['question_end'] = w['end']
            break

    # First, find where "La respuesta" starts - letters after this are NOT options
    answer_boundary = 999.0
    for i, w in enumerate(words):
        if w['word'].lower() == 'la' and i + 1 < len(words):
            if words[i + 1]['word'].lower() in ['respuesta', 'answer']:
                answer_boundary = w['start']
                break
        if w['word'].lower() in ['correcta', 'correct']:
            answer_boundary = w['start']
            break

    # === PHASE 1: Detect option letters directly ===
    for i, w in enumerate(words):
        word = w['word'].upper().strip('.,!?:;')
        start = w['start']

        # Only consider letters AFTER the question and BEFORE the answer reveal
        if start < timestamps['question_end'] or start >= answer_boundary:
            continue

        if word == 'A' and timestamps['option_a'] == 0:
            timestamps['option_a'] = start
        elif word == 'B' and timestamps['option_b'] == 0:
            timestamps['option_b'] = start
        elif word == 'C' and timestamps['option_c'] == 0:
            timestamps['option_c'] = start
        elif word == 'D' and timestamps['option_d'] == 0:
            timestamps['option_d'] = start
        # Whisper sometimes transcribes "C" as "Se", "Si", "They"
        elif word in ['SE', 'SI', 'SEA', 'CEE', 'THEY', 'THE'] and timestamps['option_c'] == 0:
            timestamps['option_c'] = start

    # === PHASE 2: Find "Piensa bien" to know where options end ===
    piensa_time = answer_boundary  # Use answer boundary as fallback
    for i, w in enumerate(words):
        if w['word'].lower() in ['piensa', 'piensalo', 'think']:
            piensa_time = w['start']
            break

    # === PHASE 3: Smart estimation of missing options ===
    # If we have Option A and know when options end, we can estimate B, C, D
    if timestamps['option_a'] > 0 and piensa_time > timestamps['option_a']:
        options_duration = piensa_time - timestamps['option_a']
        # 4 options, so divide by 4 for equal spacing (but Option A is already placed)
        gap = options_duration / 4

        # Only fill in if not already detected and gap is reasonable (0.8-2.5s)
        if 0.8 <= gap <= 2.5:
            if timestamps['option_b'] == 0:
                timestamps['option_b'] = timestamps['option_a'] + gap
            if timestamps['option_c'] == 0:
                timestamps['option_c'] = timestamps['option_a'] + gap * 2
            if timestamps['option_d'] == 0:
                timestamps['option_d'] = timestamps['option_a'] + gap * 3

    # === PHASE 4: Fallback using detected options ===
    detected = []
    if timestamps['option_a'] > 0: detected.append(('A', timestamps['option_a']))
    if timestamps['option_b'] > 0: detected.append(('B', timestamps['option_b']))
    if timestamps['option_c'] > 0: detected.append(('C', timestamps['option_c']))
    if timestamps['option_d'] > 0: detected.append(('D', timestamps['option_d']))

    if len(detected) >= 2:
        detected.sort(key=lambda x: x[1])
        total_gap = detected[-1][1] - detected[0][1]
        num_gaps = ord(detected[-1][0]) - ord(detected[0][0])
        avg_gap = total_gap / max(num_gaps, 1) if num_gaps > 0 else 1.0

        # Fill in based on average gap (use reasonable bounds)
        avg_gap = max(0.8, min(1.8, avg_gap))

        if timestamps['option_a'] > 0:
            if timestamps['option_b'] == 0:
                timestamps['option_b'] = timestamps['option_a'] + avg_gap
            if timestamps['option_c'] == 0:
                timestamps['option_c'] = timestamps['option_a'] + avg_gap * 2
            if timestamps['option_d'] == 0:
                timestamps['option_d'] = timestamps['option_a'] + avg_gap * 3

    # === PHASE 5: Ultimate fallback - fixed gaps ===
    if timestamps['option_a'] == 0:
        base_time = timestamps['question_end'] if timestamps['question_end'] > 0 else 1.5
        timestamps['option_a'] = base_time + 0.3
    if timestamps['option_b'] == 0:
        timestamps['option_b'] = timestamps['option_a'] + 1.0
    if timestamps['option_c'] == 0:
        timestamps['option_c'] = timestamps['option_b'] + 1.0
    if timestamps['option_d'] == 0:
        timestamps['option_d'] = timestamps['option_c'] + 1.0

    # NOTE: No compression! Let the video be as long as the audio needs.
    # The audio timestamps from Whisper are authoritative - respect them.
    # Only ensure options are in strictly increasing order (fix invalid data, not compress)
    if timestamps['option_b'] > 0 and timestamps['option_b'] <= timestamps['option_a']:
        timestamps['option_b'] = timestamps['option_a'] + 1.2
    if timestamps['option_c'] > 0 and timestamps['option_c'] <= timestamps['option_b']:
        timestamps['option_c'] = timestamps['option_b'] + 1.2
    if timestamps['option_d'] > 0 and timestamps['option_d'] <= timestamps['option_c']:
        timestamps['option_d'] = timestamps['option_c'] + 1.2

    # === PHASE 4: Find thinking prompt ===
    for i, w in enumerate(words):
        word_lower = w['word'].lower()
        if word_lower in ['piensalo', 'piensa', 'think', 'bien']:
            # Make sure it's after all options
            if w['start'] > timestamps['option_d']:
                timestamps['think_start'] = w['start']
                break

    # === PHASE 5: Find countdown (EXACT timestamps) ===
    for i, w in enumerate(words):
        word_lower = w['word'].lower().strip('.,!?')
        start = w['start']

        # Only look for countdown after thinking prompt
        if timestamps['think_start'] > 0 and start < timestamps['think_start']:
            continue

        if word_lower in ['tres', 'three', '3'] and timestamps['countdown_3'] == 0:
            timestamps['countdown_3'] = start
        elif word_lower in ['dos', 'two', '2'] and timestamps['countdown_2'] == 0:
            timestamps['countdown_2'] = start
        elif word_lower in ['uno', 'one', '1'] and timestamps['countdown_1'] == 0:
            timestamps['countdown_1'] = start

    # === PHASE 6: Find answer reveal (EXACT timestamp) ===
    for i, w in enumerate(words):
        word_lower = w['word'].lower()

        # Look for "La respuesta" pattern
        if word_lower == 'la' and i + 1 < len(words):
            next_word = words[i + 1]['word'].lower()
            if next_word in ['respuesta', 'answer']:
                timestamps['answer_start'] = w['start']
                # Find explanation start
                for j in range(i + 3, min(i + 12, len(words))):
                    if words[j]['word'].lower() in ['significa', 'means', 'es', 'como']:
                        timestamps['explanation_start'] = words[j]['start']
                        break
                break

        # Fallback: look for "correcta"
        elif word_lower == 'correcta' and timestamps['answer_start'] == 0:
            # Go back to find "La" or "es"
            for j in range(max(0, i - 3), i):
                if words[j]['word'].lower() in ['la', 'es']:
                    timestamps['answer_start'] = words[j]['start']
                    break
            if timestamps['answer_start'] == 0:
                timestamps['answer_start'] = w['start']

    return timestamps


def draw_gradient_rounded_rect(
    img: Image.Image,
    x1: int, y1: int, x2: int, y2: int,
    radius: int,
    color1: Tuple, color2: Tuple,
    alpha: int = 255,
    vertical: bool = True
):
    """Draw a rounded rectangle with gradient fill."""
    width = x2 - x1
    height = y2 - y1

    # Create gradient image
    grad = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)

    if vertical:
        for i in range(height):
            ratio = i / height
            r = int(color1[0] + (color2[0] - color1[0]) * ratio)
            g = int(color1[1] + (color2[1] - color1[1]) * ratio)
            b = int(color1[2] + (color2[2] - color1[2]) * ratio)
            grad_draw.line([(0, i), (width, i)], fill=(r, g, b, alpha))
    else:
        for i in range(width):
            ratio = i / width
            r = int(color1[0] + (color2[0] - color1[0]) * ratio)
            g = int(color1[1] + (color2[1] - color1[1]) * ratio)
            b = int(color1[2] + (color2[2] - color1[2]) * ratio)
            grad_draw.line([(i, 0), (i, height)], fill=(r, g, b, alpha))

    # Create rounded mask
    mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)

    grad.putalpha(mask)
    img.paste(grad, (x1, y1), grad)


def draw_shadow(
    draw: ImageDraw.Draw,
    x1: int, y1: int, x2: int, y2: int,
    radius: int,
    shadow_offset: int = 4,
    shadow_blur: int = 8,
    shadow_alpha: int = 60
):
    """Draw a subtle shadow behind an element."""
    # Simple shadow approximation with multiple offset rectangles
    for i in range(shadow_blur, 0, -2):
        alpha = int(shadow_alpha * (1 - i / shadow_blur))
        draw.rounded_rectangle(
            [x1 + shadow_offset, y1 + shadow_offset + i,
             x2 + shadow_offset, y2 + shadow_offset + i],
            radius=radius,
            fill=(80, 60, 100, alpha)  # Soft purple shadow, not black
        )


def draw_quiz_option_box_v2(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    letter: str,
    text: str,
    x: int, y: int,
    width: int, height: int,
    alpha: int = 255,
    scale: float = 1.0,
    x_offset: int = 0,
    is_correct: bool = False,
    is_wrong: bool = False,
    show_result: bool = False,
    glow: float = 0.0
):
    """Draw a professional quiz option box matching reference designs.

    Reference style: Letter circle overlaps left edge of pill, white border around circle.
    """
    if alpha <= 0 or scale <= 0:
        return

    # Apply animations
    actual_x = x + x_offset

    # Circle properties - overlapping left edge like reference
    circle_r = max(8, int(32 * scale))
    circle_x = actual_x + circle_r - 5  # Overlap left edge
    circle_y = y + height // 2

    # Pill starts after circle overlap
    pill_x = actual_x + circle_r + 5
    pill_width = width - circle_r - 10

    # Apply scale from center for pill only
    if scale != 1.0 and scale < 1.0:
        center_x = pill_x + pill_width // 2
        center_y = y + height // 2
        scaled_w = int(pill_width * scale)
        scaled_h = int(height * scale)
        pill_x = center_x - scaled_w // 2
        y = center_y - scaled_h // 2
        pill_width = scaled_w
        height = scaled_h
        circle_x = pill_x - 5
        circle_y = y + height // 2

    # Determine colors based on state - PASTEL PALETTE
    if show_result and is_correct:
        bg_color = QUIZ_COLORS['correct_green']
        letter_bg = QUIZ_COLORS['correct_green']
        letter_inner = (255, 255, 255)
        text_color = QUIZ_COLORS['text_dark']

        # Draw soft glow effect
        if glow > 0:
            glow_alpha = int(60 * glow)  # Softer glow
            for g in range(5, 0, -1):
                glow_expand = g * 6
                draw.rounded_rectangle(
                    [pill_x - glow_expand, y - glow_expand,
                     pill_x + pill_width + glow_expand, y + height + glow_expand],
                    radius=height // 2 + glow_expand,
                    fill=(*QUIZ_COLORS['correct_glow'], glow_alpha // g)
                )
    elif show_result and is_wrong:
        bg_color = QUIZ_COLORS['wrong_fade']  # Soft muted lavender
        letter_bg = QUIZ_COLORS['wrong_fade']
        letter_inner = (240, 238, 245)  # Very light lavender
        text_color = QUIZ_COLORS['wrong_text']
        alpha = int(alpha * 0.7)  # Gentle fade
    else:
        bg_color = QUIZ_COLORS['option_bg']  # Pastel blue
        letter_bg = QUIZ_COLORS['letter_circle']  # Soft coral
        letter_inner = (255, 255, 255)  # White inner
        text_color = COLOR_WHITE

    # Draw soft shadow for depth (not black - soft purple-gray)
    if not (show_result and is_wrong):
        for i in range(4, 0, -1):
            shadow_alpha = int(25 * (1 - i/4))
            draw.rounded_rectangle(
                [pill_x + 2, y + i + 2, pill_x + pill_width + 2, y + height + i + 2],
                radius=height // 2,
                fill=(80, 70, 100, shadow_alpha)  # Soft purple shadow
            )

    # Draw main pill background
    draw.rounded_rectangle(
        [pill_x, y, pill_x + pill_width, y + height],
        radius=height // 2,
        fill=(*bg_color, alpha)
    )

    # Letter circle - white border, colored fill, white letter
    # Outer white border
    border_r = circle_r + 4
    draw.ellipse(
        [circle_x - border_r, circle_y - border_r,
         circle_x + border_r, circle_y + border_r],
        fill=(255, 255, 255, alpha)
    )

    # Colored fill
    draw.ellipse(
        [circle_x - circle_r, circle_y - circle_r,
         circle_x + circle_r, circle_y + circle_r],
        fill=(*letter_bg, alpha)
    )

    # Inner white circle (if not correct state)
    if not (show_result and is_correct):
        inner_r = circle_r - 6
        if inner_r > 4:
            draw.ellipse(
                [circle_x - inner_r, circle_y - inner_r,
                 circle_x + inner_r, circle_y + inner_r],
                fill=(*letter_inner, alpha)
            )

    # Letter text - always show the letter (no checkmark to avoid font issues)
    lf = font(max(16, int(38 * scale)))

    # Keep showing the letter, but use white for correct answers
    if show_result and is_correct:
        display_char = letter  # Keep the letter visible (A, B, C, or D)
        l_color = COLOR_WHITE
        # Use slightly larger font for emphasis
        lf = font(max(20, int(44 * scale)))
    else:
        display_char = letter
        l_color = letter_bg

    bbox = draw.textbbox((0, 0), display_char, font=lf)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]

    draw.text(
        (circle_x - lw // 2, circle_y - lh // 2 - 2),
        display_char, font=lf, fill=(*l_color, alpha)
    )

    # Option text - centered in pill
    tf = font(max(20, int(44 * scale)))
    bbox = draw.textbbox((0, 0), text, font=tf)
    text_w = bbox[2] - bbox[0]

    # Truncate if needed
    display_text = text
    max_text_w = pill_width - 40
    while text_w > max_text_w and len(display_text) > 3:
        display_text = display_text[:-4] + "..."
        bbox = draw.textbbox((0, 0), display_text, font=tf)
        text_w = bbox[2] - bbox[0]

    text_x = pill_x + (pill_width - text_w) // 2
    text_y = y + (height - (bbox[3] - bbox[1])) // 2 - 3

    # Draw text with soft shadow (not black)
    shadow_color = (60, 50, 80)  # Soft purple-gray shadow
    draw.text((text_x + 1, text_y + 1), display_text, font=tf,
              fill=(*shadow_color, int(alpha * 0.25)))
    draw.text((text_x, text_y), display_text, font=tf,
              fill=(*text_color, alpha))


def draw_quiz_question_box(
    frame: Image.Image,
    draw: ImageDraw.Draw,
    question: str,
    y: int,
    alpha: int = 255
):
    """Draw a gradient question box matching reference designs."""
    # Question box dimensions
    box_padding = 40
    box_margin = 50

    # Measure text to size box
    qf = font(52)
    lines = line_break(question, qf, VIDEO_WIDTH - box_margin * 2 - box_padding * 2)
    line_height = int(52 * 1.4)
    text_height = len(lines) * line_height

    box_height = text_height + box_padding * 2
    box_x = box_margin
    box_y = y
    box_width = VIDEO_WIDTH - box_margin * 2

    # Draw gradient rounded rectangle for question
    draw_gradient_rounded_rect(
        frame,
        box_x, box_y,
        box_x + box_width, box_y + box_height,
        radius=25,
        color1=QUIZ_COLORS['question_grad_start'],
        color2=QUIZ_COLORS['question_grad_end'],
        alpha=alpha,
        vertical=False  # Horizontal gradient like references
    )

    # Draw question text
    text_y = box_y + box_padding
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=qf)
        text_w = bbox[2] - bbox[0]
        text_x = (VIDEO_WIDTH - text_w) // 2

        # Soft shadow (not black - purple tint)
        shadow_color = (80, 50, 100)
        draw.text((text_x + 1, text_y + 1), line, font=qf, fill=(*shadow_color, int(alpha * 0.3)))
        # Main text
        draw.text((text_x, text_y), line, font=qf, fill=(255, 255, 255, alpha))
        text_y += line_height

    return box_y + box_height


def draw_countdown_number(
    draw: ImageDraw.Draw,
    number: int,
    center_x: int,
    center_y: int,
    t: float,
    start_time: float
):
    """Draw animated countdown number with DRAMATIC bounce animation."""
    elapsed = t - start_time
    anim_duration = 0.35

    if elapsed < 0:
        return

    # DRAMATIC scale animation: 1.6 -> 1.0 with elastic bounce
    if elapsed < anim_duration:
        progress = elapsed / anim_duration
        # Big pop: 1.6 -> 1.0 with elastic overshoot
        scale = 1.6 - 0.6 * ease_out_elastic(progress)
    else:
        # Gentle pulse after settling
        pulse = 1.0 + 0.03 * math.sin((elapsed - anim_duration) * 6)
        scale = pulse

    # Quick fade in
    alpha = min(255, int(255 * ease_out_cubic(min(1.0, elapsed / 0.12))))

    # Urgency color: green(3) -> yellow(2) -> red(1)
    if number == 3:
        bg_color = (100, 220, 160)  # Mint green - plenty of time
    elif number == 2:
        bg_color = (255, 200, 100)  # Golden yellow - hurry up
    else:
        bg_color = (255, 130, 130)  # Soft red - last chance!

    # Box dimensions - bigger for impact
    box_size = int(160 * scale)
    box_x = center_x - box_size // 2
    box_y = center_y - box_size // 2

    # Glow effect for urgency
    glow_size = int(box_size * 1.2)
    glow_x = center_x - glow_size // 2
    glow_y = center_y - glow_size // 2
    glow_alpha = int(alpha * 0.3)
    draw.rounded_rectangle(
        [glow_x, glow_y, glow_x + glow_size, glow_y + glow_size],
        radius=30,
        fill=(*bg_color, glow_alpha)
    )

    # Soft shadow
    shadow_offset = 4
    draw.rounded_rectangle(
        [box_x + shadow_offset, box_y + shadow_offset,
         box_x + box_size + shadow_offset, box_y + box_size + shadow_offset],
        radius=28,
        fill=(80, 60, 100, int(alpha * 0.25))
    )

    # Main rounded square background
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_size, box_y + box_size],
        radius=28,
        fill=(*bg_color, alpha)
    )

    # Draw number - BOLD and centered
    tf = font(max(50, int(110 * scale)))
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=tf)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = center_x - tw // 2
    ty = center_y - th // 2 - 5

    # White text with subtle shadow for pop
    draw.text((tx + 2, ty + 2), text, font=tf, fill=(50, 40, 60, int(alpha * 0.3)))
    draw.text((tx, ty), text, font=tf, fill=(255, 255, 255, alpha))


def create_frame_quiz(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for quiz video using EXACT segment timestamps.

    This uses the new segment-based architecture where timestamps are KNOWN,
    not estimated. Each visual element appears exactly when its audio segment starts.
    """

    # ALWAYS start with gradient background
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    # Get quiz data
    question = data.get('question', 'Question?')
    options = data.get('options', {})
    correct = data.get('correct', 'A')
    explanation = data.get('explanation', '')

    # === GET EXACT SEGMENT TIMESTAMPS ===
    # These are KNOWN values from TTS generation, not estimates
    segment_times = data.get('segment_times', {})

    # Helper to get segment time with fallback
    def seg_start(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('start', fallback)

    def seg_end(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('end', fallback)

    # DEBUG: Print timestamps once per video (at t=0)
    if t < 0.05 and segment_times:
        print(f"\nEXACT segment timestamps (no estimation):")
        for seg_id in ['question', 'transition', 'option_a', 'option_b', 'option_c', 'option_d',
                       'think', 'countdown_3', 'countdown_2', 'countdown_1', 'answer', 'explanation']:
            if seg_id in segment_times:
                s = segment_times[seg_id]
                print(f"  {seg_id}: {s['start']:.2f}s - {s['end']:.2f}s")

    # === CALCULATE SYNC POINTS FROM EXACT TIMESTAMPS ===
    # Question is always visible from start
    question_visible = t >= 0

    # Options appear EXACTLY when their audio segment starts
    show_option_a = t >= seg_start('option_a', 999)
    show_option_b = t >= seg_start('option_b', 999)
    show_option_c = t >= seg_start('option_c', 999)
    show_option_d = t >= seg_start('option_d', 999)

    # "Piensa bien" appears when think segment starts
    think_start = seg_start('think', duration * 0.5)
    show_timer = t >= think_start

    # Countdown starts when countdown_3 segment starts
    countdown_start = seg_start('countdown_3', think_start + 0.5)

    # Answer appears when answer segment starts - NO GUESSING
    answer_time = seg_start('answer', duration * 0.7)
    show_answer = t >= answer_time

    # Explanation appears when explanation segment starts
    explanation_time = seg_start('explanation', answer_time + 1.5)
    show_explanation = t >= explanation_time

    # ========== DRAW QUESTION BOX ==========
    if question_visible:
        q_alpha = get_alpha(t, 0, 0.4)
        # Clean question text
        clean_question = question.replace('¿', '').replace('?', '?')
        draw_quiz_question_box(frame, draw, clean_question, 180, q_alpha)
        # Refresh draw object after pasting gradient
        draw = ImageDraw.Draw(frame, 'RGBA')

    # ========== DRAW SOFT CREAM BACKGROUND FOR OPTIONS AREA ==========
    options_bg_y = 420
    options_bg_height = 500
    light_bg = QUIZ_COLORS['light_bg']
    draw.rounded_rectangle(
        [30, options_bg_y, VIDEO_WIDTH - 30, options_bg_y + options_bg_height],
        radius=30,
        fill=(*light_bg, 200)  # Soft cream background
    )

    # ========== DRAW OPTIONS ==========
    opt_w = VIDEO_WIDTH - 120
    opt_h = 80
    opt_gap = 22
    opt_start_y = 460

    # Use EXACT segment start times for each option
    option_data = [
        ('A', seg_start('option_a', 999), show_option_a),
        ('B', seg_start('option_b', 999), show_option_b),
        ('C', seg_start('option_c', 999), show_option_c),
        ('D', seg_start('option_d', 999), show_option_d),
    ]

    for i, (letter, start_time, should_show) in enumerate(option_data):
        if not should_show:
            continue

        opt_text = options.get(letter, f"Option {letter}")
        y_pos = opt_start_y + i * (opt_h + opt_gap)

        # Animation calculations using EXACT start times
        opt_alpha = get_alpha(t, start_time, 0.25) if start_time < 999 else 255
        opt_scale = get_scale(t, start_time, 0.3) if start_time < 999 else 1.0
        x_offset = slide_in_x(t, start_time, 0.4) if start_time < 999 else 0

        is_correct = (letter == correct)
        is_wrong = not is_correct

        # Calculate glow for correct answer
        glow = 0.0
        if show_answer and is_correct:
            glow = glow_intensity(t, answer_time)
            # Pulse scale for correct answer
            opt_scale = pulse_scale(t, answer_time, 0.8)

        draw_quiz_option_box_v2(
            frame, draw, letter, opt_text,
            60, y_pos, opt_w, opt_h,
            alpha=opt_alpha,
            scale=min(1.0, opt_scale) if not (show_answer and is_correct) else opt_scale,
            x_offset=x_offset,
            is_correct=is_correct,
            is_wrong=is_wrong,
            show_result=show_answer,
            glow=glow
        )

        # Draw sparkles around correct answer
        if show_answer and is_correct:
            sparkle_center_x = VIDEO_WIDTH // 2
            sparkle_center_y = y_pos + opt_h // 2
            draw_sparkles(draw, sparkle_center_x, sparkle_center_y, t, answer_time, radius=200)

    # ========== DRAW "PIENSA BIEN" TEXT ==========
    if show_timer and not show_answer and t < countdown_start:
        think_alpha = get_alpha(t, think_start, 0.3)
        think_y = 920

        tf = font(48)
        think_text = "¡Piensa bien!"
        bbox = draw.textbbox((0, 0), think_text, font=tf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2
        draw_text_solid(draw, think_text, tx, think_y, tf, COLOR_YELLOW, think_alpha, outline=5)

    # ========== DRAW COUNTDOWN TIMER ==========
    # Use EXACT segment timestamps - no estimation
    if show_timer and not show_answer and t >= countdown_start:
        timer_center_x = VIDEO_WIDTH // 2
        timer_center_y = 1000

        # Get EXACT countdown times from segments
        cd3_start = seg_start('countdown_3', 0)
        cd2_start = seg_start('countdown_2', 0)
        cd1_start = seg_start('countdown_1', 0)

        # Determine which number to show based on EXACT timestamps
        if cd3_start > 0 and cd2_start > 0 and cd1_start > 0:
            # Use exact segment timestamps
            if t >= cd1_start:
                timer_num = 1
                num_start = cd1_start
            elif t >= cd2_start:
                timer_num = 2
                num_start = cd2_start
            elif t >= cd3_start:
                timer_num = 3
                num_start = cd3_start
            else:
                timer_num = None
                num_start = 0
        else:
            # Fallback for legacy audio without segments
            countdown_total = answer_time - countdown_start
            interval = countdown_total / 3
            time_in_countdown = t - countdown_start

            if time_in_countdown >= 2 * interval:
                timer_num = 1
                num_start = countdown_start + 2 * interval
            elif time_in_countdown >= interval:
                timer_num = 2
                num_start = countdown_start + interval
            elif time_in_countdown >= 0:
                timer_num = 3
                num_start = countdown_start
            else:
                timer_num = None
                num_start = 0

        if timer_num:
            draw_countdown_number(draw, timer_num, timer_center_x, timer_center_y, t, num_start)

    # ========== DRAW ANSWER REVEAL ==========
    if show_answer and not show_explanation:
        reveal_alpha = get_alpha(t, answer_time, 0.3)
        reveal_y = 950

        rf = font(48)
        reveal_text = f"Respuesta: {correct}"
        bbox = draw.textbbox((0, 0), reveal_text, font=rf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2

        # Green text for answer
        draw_text_solid(draw, reveal_text, tx, reveal_y, rf,
                       QUIZ_COLORS['correct_green'], reveal_alpha, outline=5)

    # ========== DRAW EXPLANATION ==========
    if show_explanation and explanation:
        exp_alpha = get_alpha(t, explanation_time, 0.4)

        # Draw explanation box
        exp_y = 920
        exp_padding = 30
        ef = font(42)

        clean_exp = explanation.replace("'", "").strip()
        exp_lines = line_break(clean_exp, ef, VIDEO_WIDTH - 140)
        exp_line_h = int(42 * 1.4)
        exp_height = len(exp_lines) * exp_line_h + exp_padding * 2

        # Soft pastel background for explanation (mint green to match correct answer)
        exp_bg = QUIZ_COLORS['correct_green']
        draw.rounded_rectangle(
            [60, exp_y, VIDEO_WIDTH - 60, exp_y + exp_height],
            radius=20,
            fill=(*exp_bg, int(exp_alpha * 0.85))
        )

        # Draw explanation text
        text_y = exp_y + exp_padding
        text_color = QUIZ_COLORS['text_dark']
        for line in exp_lines:
            bbox = draw.textbbox((0, 0), line, font=ef)
            lw = bbox[2] - bbox[0]
            lx = (VIDEO_WIDTH - lw) // 2
            # Soft shadow (not black)
            draw.text((lx + 1, text_y + 1), line, font=ef, fill=(50, 80, 60, int(exp_alpha * 0.3)))
            draw.text((lx, text_y), line, font=ef, fill=(*text_color, exp_alpha))
            text_y += exp_line_h

    # ========== TIMELINE AT TOP ==========
    progress = min(1.0, t / duration)
    # Determine if we're in countdown phase for color change
    is_in_countdown = show_timer and not show_answer
    draw_quiz_timeline(draw, progress, is_countdown=is_in_countdown)

    # ========== PROGRESS BAR AT BOTTOM ==========
    draw_progress_bar(draw, progress)

    # Convert to RGB (removes alpha channel issues)
    return np.array(frame.convert('RGB'))


# ============================================================
# EDUCATIONAL VIDEO TYPE (original word-by-word sync)
# ============================================================

def group_words(words: List[Dict]) -> List[Dict]:
    """Group words into display phrases."""
    if not words:
        return []

    connectors = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del',
                  'en', 'con', 'por', 'para', 'que', 'se', 'no', 'es',
                  'muy', 'más', 'o', 'y', 'a', 'al', 'su', 'sus'}
    starters = {'sabías', 'muchos', 'en', 'por', 'si', 'recuerda',
                'conocías', 'cuéntame'}

    gap_th = 0.35
    max_words = 7

    groups = []
    current = []
    i = 0

    while i < len(words):
        w = words[i]
        text = w['word']
        lower = text.lower().strip('.,!?¿¡')
        is_en = w.get('is_english', False)

        if is_en:
            if current:
                groups.append(current)
                current = []
            en_group = []
            while i < len(words) and words[i].get('is_english', False):
                en_group.append(words[i])
                i += 1
            groups.append(en_group)
            continue

        should_break = False

        if current:
            prev = current[-1]
            gap = w['start'] - prev['end']
            prev_text = prev['word']

            if gap > gap_th:
                should_break = True
            if prev_text.endswith(('.', '!', '?')):
                should_break = True
            if text[0].isupper() and lower in starters:
                should_break = True
            if len(current) >= max_words and lower not in connectors:
                should_break = True

        if should_break:
            groups.append(current)
            current = []

        current.append(w)
        i += 1

    if current:
        groups.append(current)

    result = []
    for g in groups:
        if not g:
            continue

        start = g[0]['start']
        end = g[-1]['end']

        # Fix zero-duration timestamps (Whisper quirk)
        # Use absolute minimum (1 frame = 33ms) - quick flash, don't block next words
        if end <= start:
            end = start + 0.033  # 1 frame flash for zero-duration words

        has_en = any(x.get('is_english', False) for x in g)
        text = ' '.join(x['word'] for x in g)

        result.append({
            'words': g,
            'text': text,
            'start': start,
            'end': end,
            'english': has_en,
        })

    # CRITICAL: Fix overlaps - groups must be sequential with no overlap
    # Sort by start time first to handle same-start-time groups
    result.sort(key=lambda x: (x['start'], 0 if x['english'] else 1))  # English first if same start

    # Handle same-start-time groups: show English words THEN Spanish context
    # Use MINIMAL gaps to keep sync tight
    filtered = []
    for i, g in enumerate(result):
        if i == 0:
            filtered.append(g)
            continue

        prev = filtered[-1]
        # If this group TRULY overlaps previous (starts BEFORE prev ends)
        # Use small tolerance to catch same-timestamp cases
        if g['start'] < prev['end'] - 0.01:
            if prev['english'] and not g['english']:
                # Previous is English, current is Spanish
                # Shift Spanish to start immediately after English (no gap)
                g['start'] = prev['end']
                if g['end'] <= g['start']:
                    g['end'] = g['start'] + 0.5
                filtered.append(g)
            elif g['english'] and not prev['english']:
                # Current is English, previous is Spanish - swap order
                filtered[-1] = g
                prev['start'] = g['end']
                if prev['end'] <= prev['start']:
                    prev['end'] = prev['start'] + 0.5
                filtered.append(prev)
            else:
                # Both same type - keep longer one
                if g['end'] - g['start'] > prev['end'] - prev['start']:
                    filtered[-1] = g
            continue

        filtered.append(g)

    result = filtered

    # Fix end times: no overlap, no gaps, just seamless transitions
    for i in range(len(result)):
        if i < len(result) - 1:
            next_start = result[i + 1]['start']
            # End exactly when next starts (seamless, no gap)
            if result[i]['end'] > next_start:
                result[i]['end'] = next_start

            # Ensure minimum visible duration (1 frame = 33ms)
            if result[i]['end'] <= result[i]['start']:
                result[i]['end'] = result[i]['start'] + 0.033

    return result


def create_frame_educational(
    t: float,
    groups: List[Dict],
    duration: float,
    translations: Dict = None
) -> np.ndarray:
    """Create frame for educational video type."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    translations = translations or {}

    # PRIORITY 1: Find group currently being spoken (voice says these words NOW)
    active = None
    for g in groups:
        if g['start'] <= t <= g['end']:
            active = g
            break

    # PRIORITY 2: Only if nothing actively spoken, show fade-out of previous group
    if active is None:
        for g in groups:
            if g['end'] < t <= g['end'] + FADE_OUT:
                active = g
                break

    if active:
        text = active['text']
        is_en = active['english']
        start = active['start']
        end = active['end']

        scale = get_scale(t, start, POP_DURATION)
        alpha = get_alpha(t, start, FADE_IN)

        # Fade out with smooth easing
        if t > end:
            fade_progress = min(1.0, (t - end) / FADE_OUT)
            # Use smooth sine-based fade for less jarring transitions
            eased_fade = ease_in_out_sine(fade_progress)
            alpha = int(255 * (1 - eased_fade))

        if alpha > 0 and scale > 0:
            if is_en:
                fsize = int(FONT_SIZE_ENGLISH * min(1.0, scale))
            else:
                fsize = int(FONT_SIZE_SPANISH * min(1.0, scale))

            f = font(fsize)
            lines = line_break(text, f, TEXT_AREA_WIDTH - 40)

            line_h = int(fsize * 1.35)
            total_h = len(lines) * line_h

            # Translation for English phrases
            trans = ""
            if is_en:
                trans = translations.get(text.lower().strip(), "")
                if trans:
                    tf = font(FONT_SIZE_TRANS)
                    trans_lines = line_break(f"({trans})", tf, TEXT_AREA_WIDTH - 60)
                    total_h += len(trans_lines) * int(FONT_SIZE_TRANS * 1.3) + 40

            base_y = (VIDEO_HEIGHT - total_h) // 2 - 30
            cur_y = base_y

            if is_en:
                # HUGE yellow English text
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=f)
                    lw = bbox[2] - bbox[0]
                    lx = (VIDEO_WIDTH - lw) // 2
                    draw_text_solid(draw, line, lx, cur_y, f, COLOR_YELLOW, alpha, outline=8)
                    cur_y += line_h
            else:
                # Spanish text - white with emphasis words in yellow
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=f)
                    lw = bbox[2] - bbox[0]
                    lx = (VIDEO_WIDTH - lw) // 2

                    wx = lx
                    for word in line.split():
                        clean = word.lower().strip('.,!?¿¡:;')

                        if clean in EMPHASIS:
                            wf = font(int(fsize * 1.05))
                            wc = COLOR_YELLOW
                        else:
                            wf = f
                            wc = COLOR_WHITE

                        ww, _ = draw_text_solid(draw, word, wx, cur_y, wf, wc, alpha)

                        sp_bbox = draw.textbbox((0, 0), " ", font=f)
                        wx += ww + (sp_bbox[2] - sp_bbox[0])

                    cur_y += line_h

            # Translation with line wrapping
            if trans:
                cur_y += 20
                tf = font(FONT_SIZE_TRANS)
                trans_text = f"({trans})"
                trans_lines = line_break(trans_text, tf, TEXT_AREA_WIDTH - 60)
                trans_line_h = int(FONT_SIZE_TRANS * 1.3)

                for tline in trans_lines:
                    bbox = draw.textbbox((0, 0), tline, font=tf)
                    tw = bbox[2] - bbox[0]
                    tx = (VIDEO_WIDTH - tw) // 2
                    draw_text_solid(draw, tline, tx, cur_y, tf, (220, 220, 240), int(alpha * 0.9), outline=4)
                    cur_y += trans_line_h

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))


# ============================================================
# TRUE/FALSE VIDEO TYPE
# ============================================================

def parse_true_false_timestamps(data: Dict) -> Dict:
    """
    Parse word timestamps for true/false video.

    Finds:
    - When "Verdadero" appears (options show)
    - When countdown/timer starts (Tres or Piensa)
    - When "respuesta" appears (answer reveal)
    """
    words = data.get('words', [])
    duration = data.get('duration', 10)

    ts = {
        'statement_end': 0,
        'options_start': 0,
        'countdown_start': 0,
        'countdown_3': 0,
        'countdown_2': 0,
        'countdown_1': 0,
        'answer_start': 0,
    }

    for i, w in enumerate(words):
        word = w['word'].lower().strip('¿?.,!')
        start = w['start']

        # Find when options appear (Verdadero/falso question)
        if word in ['verdadero', 'falso'] and ts['options_start'] == 0:
            ts['options_start'] = start
            # Statement ends just before this
            if i > 0:
                ts['statement_end'] = words[i-1].get('end', start - 0.5)

        # Find countdown
        if word in ['piensa', 'piensalo'] and ts['countdown_start'] == 0:
            ts['countdown_start'] = start
        if word in ['tres', '3'] and ts['countdown_3'] == 0:
            ts['countdown_3'] = start
        if word in ['dos', '2'] and ts['countdown_2'] == 0:
            ts['countdown_2'] = start
        if word in ['uno', '1'] and ts['countdown_1'] == 0:
            ts['countdown_1'] = start

        # Find answer reveal ("La respuesta")
        if word == 'respuesta' and ts['answer_start'] == 0:
            # Go back to find "La"
            for j in range(max(0, i-2), i):
                if words[j]['word'].lower() == 'la':
                    ts['answer_start'] = words[j]['start']
                    break
            if ts['answer_start'] == 0:
                ts['answer_start'] = start

    # Fallbacks based on duration if not found
    if ts['options_start'] == 0:
        ts['options_start'] = duration * 0.15
    if ts['statement_end'] == 0:
        ts['statement_end'] = ts['options_start'] - 0.5
    if ts['countdown_start'] == 0:
        ts['countdown_start'] = ts['options_start'] + 1.5
    if ts['answer_start'] == 0:
        ts['answer_start'] = duration * 0.40

    return ts


def create_frame_true_false(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for true/false video type using EXACT segment timestamps."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    statement = data.get('statement', 'Statement')
    correct = data.get('correct', True)
    explanation = data.get('explanation', '')

    # === GET EXACT SEGMENT TIMESTAMPS ===
    segment_times = data.get('segment_times', {})

    def seg_start(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('start', fallback)

    def seg_end(seg_id: str, fallback: float = 0.0) -> float:
        return segment_times.get(seg_id, {}).get('end', fallback)

    # DEBUG: Print timestamps once
    if t < 0.05 and segment_times:
        print(f"\nEXACT true/false segment timestamps:")
        for seg_id in ['statement', 'options', 'think', 'countdown_3', 'countdown_2', 'countdown_1', 'answer', 'explanation']:
            if seg_id in segment_times:
                s = segment_times[seg_id]
                print(f"  {seg_id}: {s['start']:.2f}s - {s['end']:.2f}s")

    # Use EXACT segment timestamps
    stmt_end = seg_end('statement', duration * 0.15)
    opt_start = seg_start('options', stmt_end + 0.3)
    timer_start = seg_start('think', opt_start + 1.0)
    answer_time = seg_start('answer', duration * 0.7)

    # Global show_answer (used in multiple sections)
    show_answer = t >= answer_time

    # Statement
    sf = font(FONT_SIZE_QUESTION)
    s_alpha = get_alpha(t, 0, 0.3)
    draw_text_centered(draw, statement, 350, sf, COLOR_YELLOW, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)

    # True/False options - show when audio says "Verdadero o falso"
    if t > opt_start:
        opt_alpha = get_alpha(t, opt_start, 0.3)

        btn_w = 400
        btn_h = 120
        gap = 60
        total_w = btn_w * 2 + gap
        start_x = (VIDEO_WIDTH - total_w) // 2
        btn_y = 700

        # TRUE button - pastel style
        true_correct = correct is True and show_answer

        if true_correct:
            true_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
            true_border = (*QUIZ_COLORS['correct_glow'], opt_alpha)
        elif show_answer and not correct:
            true_bg = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.5))
            true_border = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.7))
        else:
            true_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
            true_border = (255, 255, 255, int(opt_alpha * 0.9))

        draw.rounded_rectangle(
            [start_x, btn_y, start_x + btn_w, btn_y + btn_h],
            radius=25, fill=true_bg, outline=true_border, width=4
        )

        tf = font(56)
        true_text = "VERDADERO"
        tbbox = draw.textbbox((0, 0), true_text, font=tf)
        ttw = tbbox[2] - tbbox[0]
        ttx = start_x + (btn_w - ttw) // 2
        draw_text_solid(draw, true_text, ttx, btn_y + 30, tf, COLOR_WHITE, opt_alpha, outline=5)

        # FALSE button - pastel style
        false_x = start_x + btn_w + gap
        false_correct = correct is False and show_answer

        if false_correct:
            false_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
            false_border = (*QUIZ_COLORS['correct_glow'], opt_alpha)
        elif show_answer and correct:
            false_bg = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.5))
            false_border = (*QUIZ_COLORS['wrong_fade'], int(opt_alpha * 0.7))
        else:
            false_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
            false_border = (255, 255, 255, int(opt_alpha * 0.9))

        draw.rounded_rectangle(
            [false_x, btn_y, false_x + btn_w, btn_y + btn_h],
            radius=25, fill=false_bg, outline=false_border, width=4
        )

        false_text = "FALSO"
        fbbox = draw.textbbox((0, 0), false_text, font=tf)
        ftw = fbbox[2] - fbbox[0]
        ftx = false_x + (btn_w - ftw) // 2
        draw_text_solid(draw, false_text, ftx, btn_y + 30, tf, COLOR_WHITE, opt_alpha, outline=5)

    # Timer - show countdown synced with EXACT segment timestamps
    countdown_3_start = seg_start('countdown_3', 0)
    show_countdown = countdown_3_start > 0 and t >= countdown_3_start and not show_answer

    if show_countdown:
        # Use EXACT segment timestamps for countdown
        cd3_start = seg_start('countdown_3', 0)
        cd2_start = seg_start('countdown_2', 0)
        cd1_start = seg_start('countdown_1', 0)

        number = None
        num_start = 0

        if cd1_start > 0 and t >= cd1_start:
            number = 1
            num_start = cd1_start
        elif cd2_start > 0 and t >= cd2_start:
            number = 2
            num_start = cd2_start
        elif cd3_start > 0 and t >= cd3_start:
            number = 3
            num_start = cd3_start

        if number is not None:
            draw_countdown_number(draw, number, VIDEO_WIDTH // 2, 920, t, num_start)

    # Answer explanation - show after answer is revealed
    if show_answer and explanation:
        exp_alpha = get_alpha(t, answer_time + 0.5, 0.3)
        ef = font(48)
        clean_exp = explanation.replace("'", "").strip()
        draw_text_centered(draw, clean_exp, 950, ef, COLOR_WHITE, exp_alpha, outline=4, max_width=TEXT_AREA_WIDTH - 80)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))


# ============================================================
# FILL IN THE BLANK VIDEO TYPE
# ============================================================

def create_frame_fill_blank(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for fill-in-the-blank video type."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    sentence = data.get('sentence', 'I ___ to school')
    options = data.get('options', ['go', 'went', 'gone', 'going'])
    correct = data.get('correct', options[0] if options else '')
    translation = data.get('translation', '')

    # Timeline
    sent_end = duration * 0.20
    opt_end = duration * 0.55
    timer_end = duration * 0.75

    # Sentence with blank
    sf = font(72)
    s_alpha = get_alpha(t, 0, 0.3)

    show_answer = t > timer_end
    if show_answer:
        display_sentence = sentence.replace('___', correct).replace('_', correct)
        draw_text_centered(draw, display_sentence, 350, sf, COLOR_GREEN, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)
    else:
        draw_text_centered(draw, sentence, 350, sf, COLOR_YELLOW, s_alpha, outline=6, max_width=TEXT_AREA_WIDTH - 60)

    # Options (2x2 grid)
    if t > sent_end:
        opt_alpha = get_alpha(t, sent_end, 0.3)
        opt_w = 450
        opt_h = 100
        gap = 30
        start_x = (VIDEO_WIDTH - (opt_w * 2 + gap)) // 2
        start_y = 600

        for i, opt in enumerate(options[:4]):
            row = i // 2
            col = i % 2
            x = start_x + col * (opt_w + gap)
            y = start_y + row * (opt_h + gap)

            is_correct = (opt == correct) and show_answer

            if is_correct:
                box_bg = (*QUIZ_COLORS['correct_green'], int(opt_alpha * 0.9))
                box_border = (*QUIZ_COLORS['correct_green'], opt_alpha)
            else:
                # Use pastel blue instead of black for non-correct options
                box_bg = (*QUIZ_COLORS['option_bg'], int(opt_alpha * 0.85))
                box_border = (255, 255, 255, int(opt_alpha * 0.6))

            draw.rounded_rectangle(
                [x, y, x + opt_w, y + opt_h],
                radius=20, fill=box_bg, outline=box_border, width=3
            )

            of = font(56)
            bbox = draw.textbbox((0, 0), opt, font=of)
            ow = bbox[2] - bbox[0]
            ox = x + (opt_w - ow) // 2
            oy = y + 20
            color = COLOR_GREEN if is_correct else COLOR_WHITE
            draw_text_solid(draw, opt, ox, oy, of, color, opt_alpha, outline=4)

    # Timer
    if opt_end < t < timer_end:
        timer_progress = (t - opt_end) / (timer_end - opt_end)
        if timer_progress < 0.33:
            number = 3
        elif timer_progress < 0.66:
            number = 2
        else:
            number = 1

        tf = font(FONT_SIZE_TIMER)
        text = str(number)
        bbox = draw.textbbox((0, 0), text, font=tf)
        tw = bbox[2] - bbox[0]
        tx = (VIDEO_WIDTH - tw) // 2
        draw_text_solid(draw, text, tx, 900, tf, COLOR_YELLOW, 255, outline=10)

    # Translation
    if show_answer and translation:
        t_alpha = get_alpha(t, timer_end + 0.5, 0.3)
        tf = font(44)
        draw_text_centered(draw, f"({translation})", 1000, tf, (220, 220, 240), t_alpha, outline=4)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))


# ============================================================
# PRONUNCIATION VIDEO TYPE
# ============================================================

def create_frame_pronunciation(
    t: float,
    data: Dict,
    duration: float
) -> np.ndarray:
    """Create frame for pronunciation video type."""
    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    word = data.get('word', 'word')
    phonetic = data.get('phonetic', '')
    common_mistake = data.get('common_mistake', '')
    tip = data.get('tip', '')
    translation = data.get('translation', '')

    # Timeline
    word_phase = duration * 0.25
    mistake_phase = duration * 0.50
    phonetic_phase = duration * 0.80

    # Big word (always visible)
    wf = font(FONT_SIZE_BIG_WORD)
    w_alpha = get_alpha(t, 0, 0.3)
    draw_text_centered(draw, word, 400, wf, COLOR_YELLOW, w_alpha, outline=10)

    # Translation under word
    if translation:
        tf = font(48)
        draw_text_centered(draw, f"({translation})", 580, tf, (200, 200, 220), int(w_alpha * 0.8), outline=4)

    # "¿Cómo se pronuncia?"
    if t < mistake_phase:
        qf = font(56)
        draw_text_centered(draw, "Como se pronuncia?", 680, qf, COLOR_WHITE, w_alpha, outline=5)

    # Common mistake
    if word_phase < t < phonetic_phase:
        m_alpha = get_alpha(t, word_phase, 0.3)
        mf = font(72)
        draw_text_centered(draw, "Incorrecto:", 750, font(44), COLOR_RED, m_alpha, outline=4)
        draw_text_centered(draw, common_mistake, 820, mf, COLOR_RED, m_alpha, outline=6)

    # Correct phonetic
    if t > mistake_phase:
        p_alpha = get_alpha(t, mistake_phase, 0.3)
        pf = font(80)

        y_offset = 750 if t > phonetic_phase else 930

        draw_text_centered(draw, "Correcto:", y_offset, font(44), COLOR_GREEN, p_alpha, outline=4)
        draw_text_centered(draw, phonetic, y_offset + 70, pf, COLOR_GREEN, p_alpha, outline=6)

    # Tip
    if t > phonetic_phase and tip:
        tip_alpha = get_alpha(t, phonetic_phase, 0.3)
        tipf = font(48)
        draw_text_centered(draw, tip, 1080, tipf, COLOR_WHITE, tip_alpha, outline=4, max_width=TEXT_AREA_WIDTH - 100)

    # Progress bar
    progress = min(1.0, t / duration)
    draw_progress_bar(draw, progress)

    return np.array(frame.convert('RGB'))


# ============================================================
# MAIN VIDEO GENERATOR
# ============================================================

def load_data(path: str) -> dict:
    """Load JSON data file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_video(
    audio_path: str,
    data_path: str,
    output_path: str,
    video_type: str = None,
    fps: int = FPS
) -> str:
    """Generate video based on type."""

    print(f"Loading audio: {audio_path}")
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    print(f"Loading data: {data_path}")
    data = load_data(data_path)

    # Determine video type
    if video_type is None:
        video_type = data.get('type', 'educational')

    print(f"Video type: {video_type}")
    print(f"Duration: {duration:.2f}s")

    # Create appropriate frame generator
    if video_type == 'educational':
        words = data.get('words', [])
        if not words:
            print("Error: No word timestamps found for educational video!")
            return None

        groups = group_words(words)
        translations = data.get('translations', {})
        print(f"Phrase groups: {len(groups)}")

        def frame_gen(t):
            return create_frame_educational(t, groups, duration, translations)

    elif video_type == 'quiz':
        print(f"Question: {data.get('question', 'N/A')}")
        print(f"Options: {data.get('options', {})}")
        print(f"Correct: {data.get('correct', 'N/A')}")

        # Show parsed timestamps
        words = data.get('words', [])
        if words:
            ts = parse_quiz_timestamps(words)
            print(f"Parsed timestamps:")
            print(f"  Question: {ts['question_start']:.2f}s")
            print(f"  Option A: {ts['option_a']:.2f}s")
            print(f"  Option B: {ts['option_b']:.2f}s")
            print(f"  Option C: {ts['option_c']:.2f}s")
            print(f"  Option D: {ts['option_d']:.2f}s")
            print(f"  Countdown 3: {ts['countdown_3']:.2f}s")
            print(f"  Answer: {ts['answer_start']:.2f}s")

        def frame_gen(t):
            return create_frame_quiz(t, data, duration)

    elif video_type == 'true_false':
        print(f"Statement: {data.get('statement', 'N/A')}")
        print(f"Correct: {data.get('correct', 'N/A')}")

        def frame_gen(t):
            return create_frame_true_false(t, data, duration)

    elif video_type == 'fill_blank':
        print(f"Sentence: {data.get('sentence', 'N/A')}")
        print(f"Options: {data.get('options', [])}")
        print(f"Correct: {data.get('correct', 'N/A')}")

        def frame_gen(t):
            return create_frame_fill_blank(t, data, duration)

    elif video_type == 'pronunciation':
        print(f"Word: {data.get('word', 'N/A')}")
        print(f"Phonetic: {data.get('phonetic', 'N/A')}")

        def frame_gen(t):
            return create_frame_pronunciation(t, data, duration)

    else:
        print(f"Unknown video type: {video_type}")
        return None

    print("\nGenerating video frames...")

    video = VideoClip(frame_gen, duration=duration)
    video = video.with_fps(fps)
    video = video.with_audio(audio)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"Writing video: {output_path}")
    video.write_videofile(
        output_path,
        fps=fps,
        codec='libx264',
        audio_codec='aac',
        preset='medium',
        threads=4,
        logger='bar'
    )

    print(f"\nVideo created: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate TikTok-style video (multi-type)")
    parser.add_argument("-a", "--audio", required=True, help="MP3 audio file")
    parser.add_argument("-d", "--data", help="JSON data file (defaults to audio path with .json)")
    parser.add_argument("-o", "--output", default="output/video/output.mp4", help="Output MP4")
    parser.add_argument("-t", "--type", choices=['educational', 'quiz', 'true_false', 'fill_blank', 'pronunciation'],
                        help="Video type (auto-detected from data if not specified)")
    parser.add_argument("--fps", type=int, default=FPS, help="FPS")

    args = parser.parse_args()

    if not args.data:
        args.data = args.audio.rsplit('.', 1)[0] + '.json'

    if not os.path.exists(args.audio):
        print(f"Error: Audio not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.data):
        print(f"Error: Data file not found: {args.data}", file=sys.stderr)
        sys.exit(1)

    generate_video(args.audio, args.data, args.output, args.type, args.fps)


if __name__ == "__main__":
    main()

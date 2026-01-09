#!/usr/bin/env python3
"""
Video Generator for English AI Videos - TikTok Style
Version 10: Based on reference channel analysis

KEY LEARNINGS FROM REFERENCES:
- MASSIVE text (fills screen)
- THICK solid black outlines (6-8px)
- NO soft glow - clean solid outlines
- NO random particles - clean backgrounds
- Vibrant gradient (pink/purple/blue)
- Yellow for English keywords
- High contrast colors
"""

import argparse
import json
import math
import os
import sys
from typing import List, Dict, Tuple

from moviepy import VideoClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np


# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
MARGIN_X = 80
TEXT_AREA_WIDTH = VIDEO_WIDTH - (MARGIN_X * 2)

# Gradient - vibrant pink/purple/blue like references
GRADIENT_COLORS = [
    [(255, 100, 180), (180, 80, 220), (80, 100, 220)],   # Pink -> Purple -> Blue
    [(255, 120, 200), (200, 60, 200), (100, 80, 240)],   # Hot pink -> Purple
    [(240, 80, 160), (160, 60, 200), (60, 80, 200)],     # Magenta -> Deep purple
]

# Colors - HIGH CONTRAST like references
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (255, 230, 0)        # Bright yellow
COLOR_RED = (255, 60, 60)           # Emphasis red
COLOR_GREEN = (50, 255, 100)        # Correct green

# Typography - MASSIVE like references
FONT_SIZE_ENGLISH = 140             # HUGE for English words
FONT_SIZE_SPANISH = 90              # Large for Spanish
FONT_SIZE_TRANS = 56                # Translation text
OUTLINE_THICK = 7                   # THICK solid outline

# Animation
POP_DURATION = 0.18
FADE_IN = 0.1
FADE_OUT = 0.08
BOUNCE = 1.15
MIN_DISPLAY = 0.6

# Progress bar
BAR_HEIGHT = 10
BAR_Y = VIDEO_HEIGHT - 70
BAR_MARGIN = 40

# Emphasis words (shown in yellow)
EMPHASIS = {'no', 'nunca', 'siempre', 'muy', 'roja', 'correcta',
            'error', 'recuerda', 'importante', 'cuidado', 'doble'}

# Translations for English phrases
TRANSLATIONS = {
    "embarrassed": "avergonzado",
    "pregnant": "embarazada",
    "i was so embarrassed when i forgot her name": "Estaba tan avergonzado cuando olvidé su nombre",
}

_fonts = {}


def font(size: int) -> ImageFont.FreeTypeFont:
    if size in _fonts:
        return _fonts[size]

    # Prefer Impact or bold fonts like references use
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


def gradient(w: int, h: int, t: float) -> np.ndarray:
    """Create vibrant animated gradient like reference channels."""
    idx = int(t / 5) % len(GRADIENT_COLORS)
    nxt = (idx + 1) % len(GRADIENT_COLORS)
    blend = (t % 5) / 5

    pal = GRADIENT_COLORS[idx]
    npal = GRADIENT_COLORS[nxt]

    colors = []
    for i in range(3):
        c = [int(pal[i][j] + (npal[i][j] - pal[i][j]) * blend) for j in range(3)]
        colors.append(c)

    wave = math.sin(t * 0.3) * 0.08
    img = np.zeros((h, w, 3), dtype=np.uint8)

    for y in range(h):
        ratio = ((y / h) + wave) % 1.0
        if ratio < 0.5:
            r = ratio * 2
            c1, c2 = colors[0], colors[1]
        else:
            r = (ratio - 0.5) * 2
            c1, c2 = colors[1], colors[2]

        color = [int(c1[i] + (c2[i] - c1[i]) * r) for i in range(3)]
        img[y, :] = color

    return img


def ease_back(t: float) -> float:
    c = 1.70158
    return 1 + (c + 1) * pow(t - 1, 3) + c * pow(t - 1, 2)


def ease_cubic(t: float) -> float:
    return 1 - pow(1 - t, 3)


def pop_scale(t: float, start: float) -> float:
    if t < start:
        return 0
    elapsed = t - start
    if elapsed >= POP_DURATION:
        return 1.0
    p = elapsed / POP_DURATION
    if p < 0.5:
        return 0.5 + 0.65 * ease_back(p / 0.5)
    else:
        return BOUNCE - (BOUNCE - 1.0) * ease_cubic((p - 0.5) / 0.5)


def opacity(t: float, start: float, end: float) -> int:
    if t < start:
        return 0
    elif t < start + FADE_IN:
        return int(255 * ease_cubic((t - start) / FADE_IN))
    elif t < end:
        return 255
    elif t < end + FADE_OUT:
        return int(255 * (1 - (t - end) / FADE_OUT))
    return 0


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
        min_t = max(MIN_DISPLAY, len(g) * 0.1)
        if end - start < min_t:
            end = start + min_t

        has_en = any(x.get('is_english', False) for x in g)
        text = ' '.join(x['word'] for x in g)

        result.append({
            'words': g,
            'text': text,
            'start': start,
            'end': end,
            'english': has_en,
        })

    return result


def draw_text_solid(
    draw: ImageDraw.Draw,
    text: str, x: int, y: int,
    f: ImageFont.FreeTypeFont,
    color: Tuple,
    alpha: int = 255,
    outline: int = OUTLINE_THICK
) -> Tuple[int, int]:
    """Draw text with THICK SOLID outline - OPTIMIZED for speed."""

    bbox = draw.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    # OPTIMIZED: Use 8 cardinal directions at each distance level
    out_color = (0, 0, 0, alpha)
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (1, 1), (-1, 1), (1, -1)]

    # Draw outline at key distances only (faster but still thick)
    for dist in [outline, outline - 2, outline - 4]:
        if dist <= 0:
            continue
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    # Fill in the inner outline for solid look
    for dist in range(1, min(4, outline), 2):
        for dx, dy in directions:
            draw.text((x + dx * dist, y + dy * dist), text, font=f, fill=out_color)

    # Main text on top
    draw.text((x, y), text, font=f, fill=(*color, alpha))

    return w, h


def draw_english_huge(
    draw: ImageDraw.Draw,
    text: str,
    center_x: int, y: int,
    f: ImageFont.FreeTypeFont,
    alpha: int = 255
) -> int:
    """Draw English text HUGE with yellow color and thick outline."""

    lines = line_break(text, f, TEXT_AREA_WIDTH - 40)
    line_h = int(f.size * 1.3)
    total_h = len(lines) * line_h

    cur_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        lw = bbox[2] - bbox[0]
        lx = center_x - lw // 2

        # Yellow text with thick black outline
        draw_text_solid(draw, line, lx, cur_y, f, COLOR_YELLOW, alpha, outline=8)
        cur_y += line_h

    return total_h


def translation(phrase: str) -> str:
    return TRANSLATIONS.get(phrase.lower().strip(), "")


def create_frame(
    t: float,
    groups: List[Dict],
    duration: float
) -> np.ndarray:

    bg = gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)
    frame = Image.fromarray(bg, 'RGB').convert('RGBA')
    draw = ImageDraw.Draw(frame, 'RGBA')

    active = None
    for g in groups:
        if g['start'] <= t <= g['end'] + FADE_OUT:
            active = g
            break

    if active:
        text = active['text']
        is_en = active['english']
        start = active['start']
        end = active['end']

        scale = pop_scale(t, start)
        alpha = opacity(t, start, end)

        if alpha > 0 and scale > 0:
            if is_en:
                fsize = int(FONT_SIZE_ENGLISH * scale)
            else:
                fsize = int(FONT_SIZE_SPANISH * scale)

            f = font(fsize)
            lines = line_break(text, f, TEXT_AREA_WIDTH - 40)

            line_h = int(fsize * 1.35)
            total_h = len(lines) * line_h

            # Translation for English phrases
            trans = ""
            if is_en:
                trans = translation(text.lower().strip())
                if trans:
                    tf = font(FONT_SIZE_TRANS)
                    trans_lines = line_break(f"({trans})", tf, TEXT_AREA_WIDTH - 60)
                    total_h += len(trans_lines) * int(FONT_SIZE_TRANS * 1.3) + 40

            base_y = (VIDEO_HEIGHT - total_h) // 2 - 30
            cur_y = base_y

            if is_en:
                # HUGE yellow English text
                text_h = draw_english_huge(draw, text, VIDEO_WIDTH // 2, cur_y, f, alpha)
                cur_y += text_h + 30
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
    bar_w = VIDEO_WIDTH - (BAR_MARGIN * 2)
    progress = min(1.0, t / duration)

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

    return np.array(frame.convert('RGB'))


def generate_video(
    audio_path: str,
    timestamps_path: str,
    output_path: str,
    fps: int = FPS
) -> str:
    print(f"Loading audio: {audio_path}")
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    print(f"Loading timestamps: {timestamps_path}")
    data = load_timestamps(timestamps_path)
    words = data.get('words', [])

    if not words:
        print("Error: No word timestamps found!")
        return None

    print(f"Duration: {duration:.2f}s, Words: {len(words)}")

    groups = group_words(words)
    print(f"Phrase groups: {len(groups)}")

    for i, g in enumerate(groups):
        en = ' [EN]' if g['english'] else ''
        print(f"  {i+1:2}. \"{g['text']}\"{en}")

    print("\nGenerating video frames...")

    def frame_gen(t):
        return create_frame(t, groups, duration)

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


def load_timestamps(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Generate TikTok-style video")
    parser.add_argument("-a", "--audio", required=True, help="MP3 audio")
    parser.add_argument("-t", "--timestamps", help="JSON timestamps")
    parser.add_argument("-o", "--output", default="output/video/output.mp4", help="Output MP4")
    parser.add_argument("--fps", type=int, default=FPS, help="FPS")

    args = parser.parse_args()

    if not args.timestamps:
        args.timestamps = args.audio.rsplit('.', 1)[0] + '.json'

    if not os.path.exists(args.audio):
        print(f"Error: Audio not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.timestamps):
        print(f"Error: Timestamps not found: {args.timestamps}", file=sys.stderr)
        sys.exit(1)

    generate_video(args.audio, args.timestamps, args.output, args.fps)


if __name__ == "__main__":
    main()

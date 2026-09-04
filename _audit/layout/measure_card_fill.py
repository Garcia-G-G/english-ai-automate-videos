#!/usr/bin/env python3
"""How full is the card, over the life of a phrase?

    python3 _audit/layout/measure_card_fill.py

The operator's complaint is a big empty slab with one word in the corner.
That is not a card-size bug on its own — a card sized to its text looks
exactly right once the text is there. It is a mismatch in TIME: the card is
sized for the whole phrase from the first frame, and the words arrive one at
a time over the next few seconds.

So the thing to measure is not the card's height but the fraction of it that
carries ink, sampled through the phrase. Reported per video type, because the
three types the operator groups together draw their content by three
different mechanisms.

Card is found by colour (light, near-neutral, the cream/white fills), ink by
darkness inside it. Both are deliberately crude: the question is "is two
thirds of this empty", not "what is the exact glyph coverage".
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)

import video as videomod          # noqa: E402
import video.character as ch      # noqa: E402

SAMPLE_FPS = 4
BG = "static_ocean"

CASES = [
    ("educational", "output/audio/educational/giving_compliments_20260817_154739.json",
     "output/audio/educational/giving_compliments_20260817_154739.mp3",
     "create_frame_educational"),
    ("pronunciation", "output/smoke/pronunciation.json", "output/smoke/pronunciation.mp3",
     "create_frame_pronunciation"),
    ("vocabulary", "output/smoke/vocabulary.json", "output/smoke/vocabulary.mp3",
     "create_frame_vocabulary"),
]


def card_fill(frame: np.ndarray):
    """(card_height, ink_height, empty_fraction) for the largest card, or None."""
    a = frame[:, :, :3].astype(int)
    lum = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    card = (lum > 195) & (sat < 45)

    rows = card.sum(axis=1)
    wide = rows > 400                      # a card spans most of the width
    runs, start = [], None
    for i, v in enumerate(wide):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(wide)))
    if not runs:
        return None
    top, bottom = max(runs, key=lambda r: r[1] - r[0])
    # A real content card. Below this it is a pill, a badge or the edge of
    # the English hero card, none of which the emptiness question is about.
    if bottom - top < 150:
        return None

    cols = np.where(card[top:bottom].sum(axis=0) > (bottom - top) * 0.5)[0]
    if len(cols) < 50:
        return None
    left, right = cols.min(), cols.max()

    # Inset past the card's own border and shadow, which are dark enough to
    # read as ink and would otherwise report every card as completely full.
    pad_y, pad_x = 14, 24
    if bottom - top <= pad_y * 2 or right - left <= pad_x * 2:
        return None
    inner = a[top + pad_y:bottom - pad_y, left + pad_x:right - pad_x]
    ilum = inner.mean(axis=2)
    isat = inner.max(axis=2) - inner.min(axis=2)
    ink = (ilum < 170) | (isat > 60)       # dark glyphs or coloured words
    ink_rows = np.where(ink.sum(axis=1) > 20)[0]
    ink_h = (ink_rows.max() - ink_rows.min()) if len(ink_rows) else 0

    card_h = (bottom - pad_y) - (top + pad_y)
    return card_h, int(ink_h), 1.0 - (ink_h / card_h if card_h else 0)


def run(video_type, data_path, audio_path, fn_name):
    ch._renderer = None
    ch._renderer_resolved = True
    captured = []
    original = getattr(videomod, fn_name)

    def spy(t, data, duration, *a, **kw):
        frame = original(t, data, duration, *a, **kw)
        captured.append((round(float(t), 2), np.asarray(frame)))
        return frame

    setattr(videomod, fn_name, spy)
    try:
        videomod.generate_video(
            audio_path=str(ROOT / audio_path), data_path=str(ROOT / data_path),
            output_path=f"/tmp/fill_{video_type}.mp4",
            video_type=video_type, fps=SAMPLE_FPS, background=BG)
    finally:
        setattr(videomod, fn_name, original)

    out = []
    for t, frame in captured:
        r = card_fill(frame)
        if r:
            out.append((t, *r))
    return out


def main():
    print(f"{'type':14s} {'frames':>7s} {'w/ card':>8s} {'median':>8s} {'worst':>8s} "
          f"{'>50% empty':>11s} {'card h range':>16s}")
    print("-" * 80)
    for vt, dp, ap, fn in CASES:
        rows = run(vt, dp, ap, fn)
        if not rows:
            print(f"{vt:14s} no card detected")
            continue
        empties = np.array([e for _, _, _, e in rows])
        heights = [h for _, h, _, _ in rows]
        over = int((empties > 0.5).sum())
        print(f"{vt:14s} {len(rows):7d} {len(rows):8d} "
              f"{np.median(empties):7.0%} {empties.max():8.0%} "
              f"{f'{over}/{len(rows)}':>11s} "
              f"{f'{min(heights)}..{max(heights)}':>16s}")


if __name__ == "__main__":
    main()

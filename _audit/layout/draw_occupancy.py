#!/usr/bin/env python3
"""Render the row-occupancy map measured by measure_layout.py.

One column per video type. Each column is the full 1920px canvas squashed
to fit; a row's bar length is how much content that row carries, summed
over every sampled frame. Dead bands read as gaps.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.layout import SAFE_AREA_BOTTOM, SAFE_AREA_TOP, VIDEO_HEIGHT  # noqa: E402

COL_W, COL_GAP, PLOT_H, TOP_PAD, LEFT_PAD = 190, 34, 900, 74, 96
BG = (18, 20, 26)
INK = (120, 200, 255)
BAND = (38, 44, 58)
TEXT = (228, 232, 240)
DIM = (130, 140, 158)

MARKERS = [
    (SAFE_AREA_TOP, "SAFE_AREA_TOP 288", (90, 220, 150)),
    (SAFE_AREA_BOTTOM, "SAFE_AREA_BOTTOM 1632", (90, 220, 150)),
    (1447, "mascot top 1447", (255, 170, 70)),
    (1561, "watermark 1561", (255, 110, 130)),
    (1750, "TIMER_BAR_Y 1750", (200, 130, 255)),
    (1850, "BAR_Y 1850", (200, 130, 255)),
]


def main():
    prof = np.load(ROOT / "_audit/layout/row_profiles.npy", allow_pickle=True).item()
    types = list(prof)
    W = LEFT_PAD + len(types) * (COL_W + COL_GAP) + 330
    H = TOP_PAD + PLOT_H + 60
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def fnt(sz, bold=False):
        for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
                  else "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/System/Library/Fonts/Helvetica.ttc"):
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                continue
        return ImageFont.load_default()

    f_hd, f_sm, f_ti = fnt(17, True), fnt(12), fnt(20, True)

    d.text((LEFT_PAD, 22), "Content occupancy by row — 1080x1920 canvas, "
           "content isolated by background subtraction", font=f_ti, fill=TEXT)
    d.text((LEFT_PAD, 48), "bar length = content pixels in that row, summed over "
           "sampled frames. mascot forced OFF.", font=f_sm, fill=DIM)

    def y2px(y):
        return TOP_PAD + int(y / VIDEO_HEIGHT * PLOT_H)

    # Safe-band shading behind every column.
    for i in range(len(types)):
        x0 = LEFT_PAD + i * (COL_W + COL_GAP)
        d.rectangle([x0, y2px(SAFE_AREA_TOP), x0 + COL_W, y2px(SAFE_AREA_BOTTOM)],
                    fill=BAND)

    for i, t in enumerate(types):
        x0 = LEFT_PAD + i * (COL_W + COL_GAP)
        r = prof[t].astype(float)
        peak = r.max() or 1.0
        for py in range(PLOT_H):
            lo = int(py / PLOT_H * VIDEO_HEIGHT)
            hi = max(lo + 1, int((py + 1) / PLOT_H * VIDEO_HEIGHT))
            v = r[lo:hi].max() / peak
            if v > 0.002:
                d.line([(x0, TOP_PAD + py), (x0 + int(COL_W * v), TOP_PAD + py)],
                       fill=INK)
        d.rectangle([x0, TOP_PAD, x0 + COL_W, TOP_PAD + PLOT_H],
                    outline=(70, 78, 95))
        d.text((x0, TOP_PAD - 22), t, font=f_hd, fill=TEXT)

    # Marker rules across the whole plot.
    right = LEFT_PAD + len(types) * (COL_W + COL_GAP) - COL_GAP
    for y, label, col in MARKERS:
        py = y2px(y)
        for x in range(LEFT_PAD, right, 7):
            d.line([(x, py), (x + 3, py)], fill=col)
        d.text((right + 12, py - 7), label, font=f_sm, fill=col)

    for y in (0, 480, 960, 1440, 1920):
        d.text((10, y2px(y) - 7), f"y {y}", font=f_sm, fill=DIM)

    out = ROOT / "_audit/layout/occupancy.png"
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()

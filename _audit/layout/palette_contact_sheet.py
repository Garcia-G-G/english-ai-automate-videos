#!/usr/bin/env python3
"""Contact sheet of every generated palette, on a real card, at judging size.

    python3 _audit/layout/palette_contact_sheet.py

All 60, not a sample — a sample lets the bad ones hide, and the point of the
sheet is to cull. Each tile is a real frame: the palette rendered through the
same gradient path the renderer uses, with the same cream card, the same
corner radius and shadow, and identical text on every one, so the only thing
varying between tiles is the palette.

Tiles are small on purpose. These are judged as thumbnails on a phone, and a
palette that looks rich at 1080px can read as brown sludge at 170px.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)

from backgrounds import BACKGROUND_PRESETS                      # noqa: E402
from config.colors import CARD_COLORS                           # noqa: E402
from config.layout import (                                     # noqa: E402
    CARD_MARGIN_X, CARD_PADDING, CARD_RADIUS, CARD_WIDTH,
    SAFE_AREA_BOTTOM, SAFE_AREA_TOP, VIDEO_HEIGHT, VIDEO_WIDTH,
)
from video import prepare_background_cache                     # noqa: E402
from video.backgrounds import (                                # noqa: E402
    set_background, gradient, get_background_generator,
)
from video.utils import (                                       # noqa: E402
    draw_rounded_card, fit_text_font, font_line_height,
)

#: The same line on every tile. Bilingual on purpose — it carries both the
#: dark Spanish grey and the blue English highlight, which are the two colours
#: that have to survive whatever is behind them.
SAMPLE_TEXT = "aprende ingles hoy"
HIGHLIGHT = "hoy"

TILE_W = 170
COLS = 10
LABEL_H = 15
GAP = 6

_SPANISH = (60, 70, 90)
_ENGLISH = (0, 120, 200)


def render_tile(preset: str) -> Image.Image:
    """One real frame for `preset`, shrunk to tile size."""
    set_background(preset=preset, duration=10.0)
    # Warm the cache the way generate_video does, or every tile shows
    # whichever preset happened to be rendered first.
    generator = get_background_generator()
    if generator:
        prepare_background_cache(generator, preset, 10.0)
    bg = np.asarray(gradient(VIDEO_WIDTH, VIDEO_HEIGHT, 0.0))
    frame = Image.fromarray(bg[:, :, :3]).convert("RGBA")

    box = fit_text_font(SAMPLE_TEXT, 72, 42, CARD_WIDTH - CARD_PADDING * 2 - 40)
    line_h = font_line_height(box.font)
    card_h = len(box.lines) * line_h + CARD_PADDING * 2
    card_y = SAFE_AREA_TOP + (SAFE_AREA_BOTTOM - SAFE_AREA_TOP - card_h) // 2

    draw_rounded_card(frame, CARD_MARGIN_X, card_y, CARD_WIDTH, card_h,
                      radius=CARD_RADIUS, fill=CARD_COLORS["cream_card"],
                      alpha=235, shadow=True, shadow_offset=5, shadow_alpha=60)

    d = ImageDraw.Draw(frame, "RGBA")
    y = card_y + CARD_PADDING
    for line in box.lines:
        words = line.split()
        widths = [d.textbbox((0, 0), w + " ", font=box.font)[2] for w in words]
        x = (VIDEO_WIDTH - sum(widths)) // 2
        for w, wid in zip(words, widths):
            colour = _ENGLISH if w.strip(".,!¡") == HIGHLIGHT else _SPANISH
            d.text((x, y), w, font=box.font, fill=(*colour, 255))
            x += wid
        y += line_h

    h = int(TILE_W * VIDEO_HEIGHT / VIDEO_WIDTH)
    return frame.convert("RGB").resize((TILE_W, h), Image.LANCZOS)


def main():
    names = sorted(k for k in BACKGROUND_PRESETS if k.startswith("gen_"))
    print(f"rendering {len(names)} generated palettes ...")

    tiles = []
    for i, name in enumerate(names, 1):
        tiles.append((name, render_tile(name)))
        if i % 10 == 0:
            print(f"  {i}/{len(names)}", flush=True)

    tw, th = tiles[0][1].size
    rows = -(-len(tiles) // COLS)
    W = COLS * tw + (COLS + 1) * GAP
    H = rows * (th + LABEL_H + GAP) + GAP + 34
    sheet = Image.new("RGB", (W, H), (14, 16, 20))
    d = ImageDraw.Draw(sheet)

    def fnt(size, bold=False):
        for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
                  else "/System/Library/Fonts/Supplemental/Arial.ttf",):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
        return ImageFont.load_default()

    d.text((GAP, 9), f"All {len(names)} generated palettes — same card, same text, "
                     f"tile width {TILE_W}px", font=fnt(15, True), fill=(232, 236, 246))

    for i, (name, tile) in enumerate(tiles):
        r, c = divmod(i, COLS)
        x = GAP + c * (tw + GAP)
        y = 34 + GAP + r * (th + LABEL_H + GAP)
        sheet.paste(tile, (x, y))
        d.text((x + 2, y + th + 2), name, font=fnt(11), fill=(190, 196, 208))

    out = ROOT / "_audit" / "layout" / "frames" / "palettes_all60.png"
    sheet.save(out)
    print(f"wrote {out}  {sheet.size}")


if __name__ == "__main__":
    main()

"""The notebook kit: every mark the notebook Shorts draw, drawn properly (STEP 77 §1).

One place for paper, binding, pencil, tick, cross, circle, strike, highlighter, countdown
dots, sticky note, tier pill, title stroke, Bubi sticker and the brand footer.

DRAWN AT 4×, DOWNSAMPLED ONCE. PIL draws lines, arcs, polygons and ellipses without
anti-aliasing, so a tick or a ring edge came out as a staircase of 0/255 alpha. Every shape
here is painted at SS× into a sprite covering just its own box — in exact (fractional) layer
coordinates, so nothing moves — and brought down with LANCZOS. Text is already anti-aliased
by FreeType and is drawn at 1×.

CACHED. A sprite is keyed by everything that changes it: its geometry (rounded to 1/SS px),
its colour and, for the animated ones, its progress quantised to a step that is invisible
on screen. A static page is painted once per video.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
BRAND_PATH = ROOT / "assets" / "branding" / "english-unlimited" / "brand.json"
EMOJI_FONT = ROOT / "assets" / "fonts" / "NotoColorEmoji.ttf"
BUBI = ROOT / "assets" / "branding" / "english-unlimited" / "simbolo_512.png"

#: Supersampling factor.
SS = 4
#: Noto Color Emoji is a bitmap (CBDT) font with ONE strike; FreeType only rasterises that size.
EMOJI_STRIKE = 109

Colour = Tuple[int, int, int, int]


def hex_colour(value: str, alpha: int = 255) -> Colour:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


@lru_cache(maxsize=1)
def brand() -> dict:
    with open(BRAND_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def colour(name: str, alpha: int = 255) -> Colour:
    return hex_colour(brand()["color"][name], alpha)


#: ONE paper for the page and the outro card (STEP 77 §1): the brief's warm off-white.
PAPER = hex_colour("#FBF8F0")


def on_paper(c: Colour, k: float) -> Colour:
    """`c` laid over the paper at strength k, as an OPAQUE colour."""
    k = 0.0 if k < 0 else (1.0 if k > 1 else k)
    return tuple(int(round(PAPER[i] * (1 - k) + c[i] * k)) for i in range(3)) + (255,)


@lru_cache(maxsize=64)
def fredoka(size: int, weight: str = "display") -> ImageFont.FreeTypeFont:
    """The brand display face. Raises rather than substituting: a notebook lettered in
    another face is a brand defect that looks like success."""
    return ImageFont.truetype(str(ROOT / brand()["font"][weight]["file"]), size)


# ── the supersampling core ───────────────────────────────────────────

Painter = Callable[[ImageDraw.ImageDraw, Callable[[float, float], Tuple[float, float]], float], None]


def _q(v: float) -> float:
    return round(v * SS) / SS


#: (key, box) -> (sprite, origin). Keyed only by what the shape IS: the painter is a closure
#: and a new one each call, so it cannot be part of the key.
_SPRITES: dict = {}
_SPRITES_MAX = 6000


def _render(box: Tuple[float, float, float, float], painter: Painter) -> Tuple[Image.Image, Tuple[int, int]]:
    x0, y0, x1, y1 = box
    ox, oy = math.floor(x0), math.floor(y0)
    w, h = max(1, math.ceil(x1) - ox), max(1, math.ceil(y1) - oy)
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big, "RGBA")

    def at(x: float, y: float) -> Tuple[float, float]:
        return ((x - ox) * SS, (y - oy) * SS)

    painter(draw, at, SS)
    return big.resize((w, h), Image.LANCZOS), (ox, oy)


def paint(layer: Image.Image, box: Sequence[float], painter: Painter, key) -> None:
    """Paint `painter(draw, at, k)` into `layer`, supersampled, inside `box` (layer coords).
    `at(x, y)` maps layer coordinates to the big sprite; `k` multiplies stroke widths.
    `key` must name everything the painter draws besides the box."""
    b = tuple(_q(v) for v in box)
    hit = _SPRITES.get((key, b))
    if hit is None:
        if len(_SPRITES) >= _SPRITES_MAX:
            _SPRITES.clear()
        hit = _SPRITES[(key, b)] = _render(b, painter)
    img, (ox, oy) = hit
    if ox >= 0 and oy >= 0:
        layer.alpha_composite(img, (ox, oy))
    else:
        _composite_clipped(layer, img, ox, oy)


def _composite_clipped(layer: Image.Image, img: Image.Image, ox: int, oy: int) -> None:
    cx, cy = max(0, -ox), max(0, -oy)
    layer.alpha_composite(img.crop((cx, cy, img.size[0], img.size[1])), (ox + cx, oy + cy))


def _lines(draw, at, k, pts, colour_: Colour, width: float) -> None:
    pts = [at(*p) for p in pts]
    draw.line(pts, fill=colour_, width=max(1, int(round(width * k))), joint="curve")
    r = width * k / 2                                    # round caps, so a stroke ends soft
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=colour_)


def _bbox(pts: Iterable[Tuple[float, float]], pad: float):
    xs, ys = zip(*pts)
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


# ── page, binding, rules, title ──────────────────────────────────────

def page(layer: Image.Image, x: float, y: float, w: float, h: float, radius: int = 28,
         outline: int = 6, shadow: Tuple[int, int] = (8, 8), fill: Colour = None) -> None:
    """Hard sticker shadow, then the outlined page."""
    fill = fill or PAPER
    ink = colour("ink")

    def painter(draw, at, k):
        sx, sy = shadow
        draw.rounded_rectangle([*at(x + sx, y + sy), *at(x + w + sx, y + h + sy)], radius=radius * k, fill=ink)
        draw.rounded_rectangle([*at(x, y), *at(x + w, y + h)], radius=radius * k, fill=fill,
                               outline=ink, width=int(outline * k))
    paint(layer, (x - 1, y - 1, x + w + shadow[0] + 1, y + h + shadow[1] + 1), painter,
          ("page", w, h, radius, outline, shadow, fill))


def rings(layer: Image.Image, x: float, top: float, bottom: float, n: int = 18) -> None:
    """Spiral binding: a punched hole and an ink-outlined wire loop per ring, the loop
    wrapping over the page's left edge."""
    ink, wire = colour("ink"), (178, 174, 166, 255)

    def painter(draw, at, k):
        step = (bottom - top) / (n - 1)
        for j in range(n):
            y = top + step * j
            hx, hy = at(x, y)
            draw.ellipse([hx - 9 * k, hy - 9 * k, hx + 9 * k, hy + 9 * k], fill=ink)
            box = [hx - 62 * k, hy - 17 * k, hx + 4 * k, hy + 13 * k]
            draw.arc(box, start=150, end=390, fill=ink, width=int(11 * k))
            draw.arc(box, start=158, end=382, fill=wire, width=int(5 * k))
    paint(layer, (x - 64, top - 20, x + 12, bottom + 20), painter, ("rings", n))


def rule(layer: Image.Image, x0: float, x1: float, y: float, width: float, c: Colour) -> None:
    """A horizontal ruled line (square ends), centred on y."""
    def painter(draw, at, k):
        draw.rectangle([*at(x0, y - width / 2), *at(x1, y + width / 2)], fill=c)
    paint(layer, (x0 - 1, y - width / 2 - 1, x1 + 1, y + width / 2 + 1), painter, ("rule", x1 - x0, width, c))


def marker_stroke(layer: Image.Image, pts: List[Tuple[float, float]], width: float, c: Colour) -> None:
    """A felt-marker stroke along `pts` (the title underline)."""
    tpts = tuple(pts)
    paint(layer, _bbox(pts, width), lambda d, at, k: _lines(d, at, k, tpts, c, width), ("marker", tpts, width, c))


# ── marks: tick, cross, circle, strike, dots ─────────────────────────

TICK_SIZE = 34


def tick(layer: Image.Image, x: float, cy: float, scale: float, size: float = TICK_SIZE,
         progress: float = 1.0) -> None:
    """A ✓: ink under green. `scale` grows it (a pop); `progress` draws it along its path."""
    if scale <= 0 or progress <= 0:
        return
    s = size * scale
    path = [(x, cy), (x + s * 0.38, cy + s * 0.38), (x + s, cy - s * 0.5)]
    pts = _partial(path, progress)
    w_ink, w_col = 13 * scale, 7 * scale

    def painter(draw, at, k):
        _lines(draw, at, k, pts, colour("ink"), w_ink)
        _lines(draw, at, k, pts, colour("correct"), w_col)
    paint(layer, _bbox(pts, w_ink), painter, ("tick", round(scale, 3), round(progress, 3), round(size, 2)))


def _partial(path: List[Tuple[float, float]], p: float) -> Tuple[Tuple[float, float], ...]:
    """The first fraction p of a polyline, by length."""
    if p >= 1.0:
        return tuple(path)
    seg = [math.dist(a, b) for a, b in zip(path, path[1:])]
    left = sum(seg) * max(0.0, p)
    out = [path[0]]
    for (a, b), d in zip(zip(path, path[1:]), seg):
        if left >= d:
            out.append(b)
            left -= d
            continue
        f = left / d if d else 0.0
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        break
    if len(out) == 1:
        out.append(out[0])
    return tuple(out)


CROSS_SIZE = 28


def cross(layer: Image.Image, x: float, cy: float, scale: float, size: float = CROSS_SIZE) -> None:
    """An ✗: ink under red."""
    if scale <= 0:
        return
    s = size * scale
    x0, y0 = x + (size - s) / 2, cy - s / 2
    strokes = (((x0, y0), (x0 + s, y0 + s)), ((x0 + s, y0), (x0, y0 + s)))
    w_ink, w_col = 13 * scale, 7 * scale

    def painter(draw, at, k):
        for a, b in strokes:
            _lines(draw, at, k, (a, b), colour("ink"), w_ink)
            _lines(draw, at, k, (a, b), colour("error"), w_col)
    paint(layer, (x0 - w_ink, y0 - w_ink, x0 + s + w_ink, y0 + s + w_ink), painter, ("cross", round(scale, 3)))


def circle(layer: Image.Image, box: Tuple[float, float, float, float], p: float) -> None:
    """A loop drawn by hand around box, p of the way: it starts top-left and overshoots a
    little, with a slow wobble so it does not look like a stamp. Ink under green."""
    if p <= 0:
        return
    p = round(p * 96) / 96                                  # 96 steps: one frame of a 3 s loop
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    sweep, a0 = 2 * math.pi * 1.08 * p, -math.pi * 0.7
    steps = max(2, int(96 * p))
    pts = []
    for j in range(steps + 1):
        a = a0 + sweep * j / steps
        wob = 1.0 + 0.05 * math.sin(3 * a + 0.6) + 0.04 * (a - a0) / (2 * math.pi)
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
    pts = tuple(pts)

    def painter(draw, at, k):
        _lines(draw, at, k, pts, colour("ink"), 10)
        _lines(draw, at, k, pts, colour("correct"), 5)
    paint(layer, _bbox(pts, 10), painter, ("circle", p))


def strike(layer: Image.Image, x0: float, x1: float, cy: float, p: float) -> None:
    """A red stroke through the wrong option, left to right, ink under red."""
    if p <= 0:
        return
    p = round(p * 96) / 96
    pts = ((x0 - 6, cy + 3), (x0 - 6 + (x1 - x0 + 12) * p, cy - 3 * (2 * p - 1)))

    def painter(draw, at, k):
        _lines(draw, at, k, pts, colour("ink"), 7)
        _lines(draw, at, k, pts, colour("error"), 3)
    paint(layer, _bbox(pts, 7), painter, ("strike", p))


def dots(layer: Image.Image, x0: float, cy: float, p: float, c: Colour = None) -> None:
    """Three countdown dots that empty over the think pause: «your turn», not dead air."""
    c = c or colour("english_blue")
    r = 11
    # Eighths: a dot empties over a third of the pause, so a step is ~2 frames and 1 px of
    # its 9 px fill; coarser steps let the page memo reuse a think pause's frames.
    fills = tuple(round(max(0.0, min(1.0, (1.0 - p) * 3 - (2 - j))) * 8) / 8 for j in range(3))

    def painter(draw, at, k):
        for j, left in enumerate(fills):
            x, y = at(x0 + j * 40, cy)
            draw.ellipse([x - r * k, y - r * k, x + r * k, y + r * k], outline=c, width=int(4 * k))
            if left > 0:
                ir = (r - 2) * left * k
                draw.ellipse([x - ir, y - ir, x + ir, y + ir], fill=c)
    paint(layer, (x0 - r - 2, cy - r - 2, x0 + 80 + r + 2, cy + r + 2), painter, ("dots", fills, c))


def highlighter(layer: Image.Image, box: Tuple[float, float, float, float], alpha: float,
                c: Colour = None, radius: int = 18) -> None:
    """The row highlight: a rounded marker band at `alpha` over the paper."""
    if alpha <= 0:
        return
    alpha = round(alpha * 32) / 32
    c = c or colour("brand_yellow")
    fill = (c[0], c[1], c[2], int(round(255 * alpha)))
    x0, y0, x1, y1 = box

    def painter(draw, at, k):
        draw.rounded_rectangle([*at(x0, y0), *at(x1, y1)], radius=radius * k, fill=fill)
    paint(layer, (x0 - 1, y0 - 1, x1 + 1, y1 + 1), painter, ("hl", fill, radius))


def arrow(img: Image.Image, x: float, y: float, length: float, c: Colour) -> None:
    """A right arrow (Fredoka has no «→»): a stroke and a head."""
    def painter(draw, at, k):
        draw.line([at(x, y), at(x + length - 14, y)], fill=c, width=int(8 * k))
        draw.polygon([at(x + length, y), at(x + length - 20, y - 14), at(x + length - 20, y + 14)], fill=c)
    paint(img, (x - 1, y - 16, x + length + 1, y + 16), painter, ("arrow", length, c))


# ── sprites: pencil, pill, notes, Bubi, footer ───────────────────────

#: Degrees BELOW horizontal: tip upper-left, body trailing down-right (rows fill top to
#: bottom, so the body lies over rows not yet written).
PENCIL_ANGLE = 38


@lru_cache(maxsize=1)
def pencil() -> Tuple[Image.Image, Tuple[int, int]]:
    """The pencil, tilted, and where its tip sits inside the image (the canvas centre:
    drawn horizontally with the tip there, then rotated about it at SS×)."""
    ink, yellow = colour("ink"), colour("brand_yellow")
    wood, pink, metal = (236, 196, 140, 255), (232, 128, 140, 255), (178, 174, 166, 255)
    size = 560
    k = SS
    c = size * k // 2
    big = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big, "RGBA")
    h = 40 * k
    cone, body, ferrule, eraser = 54 * k, 170 * k, 24 * k, 30 * k
    x = c
    d.polygon([(x, c), (x + cone, c - h / 2), (x + cone, c + h / 2)], fill=wood)
    d.polygon([(x, c), (x + 17 * k, c - h / 2 * 17 / 54), (x + 17 * k, c + h / 2 * 17 / 54)], fill=ink)
    x += cone
    d.rectangle([x, c - h / 2, x + body, c + h / 2], fill=yellow, outline=ink, width=4 * k)
    d.line([(x, c), (x + body, c)], fill=(214, 182, 80, 255), width=3 * k)
    x += body
    d.rectangle([x, c - h / 2, x + ferrule, c + h / 2], fill=metal, outline=ink, width=4 * k)
    x += ferrule
    d.rounded_rectangle([x - 2 * k, c - h / 2, x + eraser, c + h / 2], radius=10 * k, fill=pink,
                        outline=ink, width=4 * k)
    d.line([(c, c), (c + cone, c - h / 2)], fill=ink, width=4 * k)
    d.line([(c, c), (c + cone, c + h / 2)], fill=ink, width=4 * k)
    big = big.rotate(-PENCIL_ANGLE, resample=Image.BICUBIC, center=(c, c))
    return big.resize((size, size), Image.LANCZOS), (size // 2, size // 2)


@lru_cache(maxsize=16)
def pill(width: int, height: int, fill: Colour) -> Image.Image:
    """A vertical rounded pill, ink-outlined (the tier labels' shape, without its word)."""
    img = Image.new("RGBA", ((width + 4) * SS, (height + 4) * SS), (0, 0, 0, 0))
    ImageDraw.Draw(img, "RGBA").rounded_rectangle([2 * SS, 2 * SS, (width + 1) * SS, (height + 1) * SS],
                                                  radius=width // 2 * SS, fill=fill, outline=colour("ink"),
                                                  width=3 * SS)
    return img.resize((width + 4, height + 4), Image.LANCZOS)


@lru_cache(maxsize=16)
def note_card(width: int, height: int, fill: Colour = None, outline: int = 4,
              shadow: Tuple[int, int] = (8, 8)) -> Image.Image:
    """A sticky note: hard ink shadow, outlined square card. Text goes on after."""
    fill = fill or colour("brand_yellow")
    ink = colour("ink")
    W, H = width + shadow[0] + 2, height + shadow[1] + 2
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([shadow[0] * SS, shadow[1] * SS, (width + shadow[0]) * SS - 1, (height + shadow[1]) * SS - 1], fill=ink)
    d.rectangle([0, 0, width * SS - 1, height * SS - 1], fill=fill, outline=ink, width=outline * SS)
    return img.resize((W, H), Image.LANCZOS)


@lru_cache(maxsize=16)
def bubi(width: int) -> Image.Image:
    """Bubi (the brand symbol), cropped to his visible pixels, `width` px wide."""
    src = Image.open(BUBI).convert("RGBA")
    src = src.crop(src.getchannel("A").getbbox())
    return src.resize((width, max(1, round(src.height * width / src.width))), Image.LANCZOS)


@lru_cache(maxsize=8)
def bubi_sticker(width: int, border: int = 10, shadow: Tuple[int, int] = (6, 6)) -> Image.Image:
    """Bubi as a die-cut sticker: a white border following his outline, a hard ink shadow."""
    from PIL import ImageFilter
    b = bubi(width)
    pad = border + max(shadow) + 2
    canvas = Image.new("RGBA", (b.width + 2 * pad, b.height + 2 * pad), (0, 0, 0, 0))
    mask = Image.new("L", canvas.size, 0)
    mask.paste(b.getchannel("A"), (pad, pad))
    grown = mask.filter(ImageFilter.MaxFilter(2 * border + 1)).filter(ImageFilter.GaussianBlur(1.2))
    shadow_img = Image.new("RGBA", canvas.size, colour("ink"))
    shadow_img.putalpha(grown)
    canvas.alpha_composite(shadow_img, shadow)
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    white.putalpha(grown)
    canvas.alpha_composite(white)
    canvas.alpha_composite(b, (pad, pad))
    return canvas


FOOTER_TEXT = "learningroutes.com"


@lru_cache(maxsize=4)
def footer(size: int = 34) -> Image.Image:
    """The brand footer: Bubi mini + «learningroutes.com» in Fredoka, ink on transparent."""
    f = fredoka(size, "display_medium")
    b = bubi(int(size * 1.4))
    tw = int(math.ceil(f.getlength(FOOTER_TEXT)))
    gap = size // 3
    h = max(b.height, size + 12)
    img = Image.new("RGBA", (b.width + gap + tw + 4, h), (0, 0, 0, 0))
    img.alpha_composite(b, (0, (h - b.height) // 2))
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    ImageDraw.Draw(img).text((b.width + gap, h / 2 - (top + bottom) / 2), FOOTER_TEXT, font=f,
                             fill=colour("secondary_text"))
    return img


# ── emoji ────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _emoji_strike(emoji: str) -> Image.Image:
    f = ImageFont.truetype(str(EMOJI_FONT), EMOJI_STRIKE)
    canvas = Image.new("RGBA", (EMOJI_STRIKE * 2, EMOJI_STRIKE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((EMOJI_STRIKE // 2, EMOJI_STRIKE // 2), emoji, font=f, embedded_color=True)
    box = canvas.getbbox()
    if box is None:
        raise ValueError(f"emoji {emoji!r} rendered nothing")
    return canvas.crop(box)


@lru_cache(maxsize=256)
def emoji(char: str, size: int) -> Image.Image:
    """The emoji fitted into a size × size square, aspect kept."""
    src = _emoji_strike(char)
    scale = size / max(src.size)
    w, h = max(1, round(src.size[0] * scale)), max(1, round(src.size[1] * scale))
    return src.resize((w, h), Image.LANCZOS)

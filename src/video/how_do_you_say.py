"""how_do_you_say — "¿Cómo se dice…?": a notebook page, ten words, a pencil.

Per item: the row lights up -> the voice says the Spanish word -> 1.8 s of
silence, the viewer's turn -> the voice says the English word twice -> the
English is written in beside the Spanish while the pencil moves along it.
Then the recap reads all ten, and each word pulses as it is reached.

EVERYTHING IS A PURE FUNCTION OF t. The compositor may ask for frames in any
order and a render must be byte-reproducible, so the pencil's position, the
highlighter, the reveal mask and the pulses are all computed from t and the
measured segment_times -- no state carried between frames.

NO TIMING IS INVENTED. The reveal runs over the FIRST "Family." of en_i, which
the audio generator measures inside the clip and records as `reveal_end`.
A script without segment_times raises: a renderer that guessed would draw a
confident lesson out of sync with its own voice.

BRAND v2 "Pegatina", read from brand.json rather than restated here: Fredoka
Bold, brand yellow, English blue, ink, sticker outline and a hard shadow.
"""

from __future__ import annotations

import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .constants import VIDEO_WIDTH, VIDEO_HEIGHT
from .motion import clamp01
from .utils import create_base_frame, finalize_frame

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
BRAND_PATH = ROOT / "assets" / "branding" / "english-unlimited" / "brand.json"
EMOJI_FONT = ROOT / "assets" / "fonts" / "NotoColorEmoji.ttf"

#: Noto Color Emoji is a bitmap (CBDT) font with ONE strike. FreeType only
#: rasterises it at that size; anything else raises. Render here, resize.
EMOJI_STRIKE = 109


def _hex(value: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


@lru_cache(maxsize=1)
def brand() -> dict:
    with open(BRAND_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _color(name: str, alpha: int = 255):
    return _hex(brand()["color"][name], alpha)


def _on_paper(color, k: float):
    """`color` laid over the paper at strength k, as an OPAQUE colour.

    Drawing a translucent fill onto the RGBA page layer replaces the paper's
    alpha rather than blending into it, so the background shows through the
    page wherever a highlighter or a ruled line was drawn. Blending against
    the paper here keeps the page solid.
    """
    k = clamp01(k)
    return tuple(int(round(PAPER[c] * (1 - k) + color[c] * k)) for c in range(3)) + (255,)


INK = _hex("#1C1812")              # replaced from brand.json at first use
PAPER = _hex("#FBF8F0")            # the brief's off-white, warmer than `paper`


@lru_cache(maxsize=64)
def fredoka(size: int, weight: str = "display") -> ImageFont.FreeTypeFont:
    """The brand display face. Raises rather than substituting: a notebook
    lettered in Inter is a brand defect that looks like success."""
    return ImageFont.truetype(str(ROOT / brand()["font"][weight]["file"]), size)


# ── Geometry (canvas pixels) ─────────────────────────────────────────
#
# The page is laid out in its OWN coordinates and the whole layer is tilted
# once at the end, so every element below is placed as if the page were
# straight. length_spec reads the column widths from here.

#: 1340 tall so the tilted page, shadow included, ends above the watermark
#: scrim's top (clip_contrast.mark_rect, row 1475): every type's text band
#: must, or the mark's treatment double-darkens it.
PAGE_W, PAGE_H = 860, 1340
PAGE_X = (VIDEO_WIDTH - PAGE_W) // 2           # 110
#: test_how_do_you_say pins both edges against the registry's text_band.
PAGE_Y = 104
PAGE_RADIUS = 28
PAGE_OUTLINE = 6
SHADOW = (8, 8)
#: Degrees, counter-clockwise, fixed for the whole video. The brief allows
#: up to 1.5; one degree reads as "placed by hand" without making the rows
#: visibly climb.
TILT_DEG = 1.0
#: Room around the page inside the layer, for the rings that hang off the
#: left edge, the shadow and the rotation's corners.
PAD = 64

RINGS = 18
RING_X = 34                                    # the punched hole, page-local

TITLE_TEXT = "How do you say?"
TITLE_SIZE = 76
TITLE_Y = 34
THEME_SIZE = 40
THEME_Y = 146

ROWS_TOP = 222
ROWS_BOTTOM = PAGE_H - 30
ROW_PITCH = 108                                # ten rows fill ROWS_TOP..BOTTOM

EMOJI_SIZE = 90
EMOJI_X = 76

#: The two word columns. Their widths are what length_spec measures a word
#: against, at WORD_FONT_MAX shrinking to WORD_FONT_MIN.
SPANISH_X = 184
SPANISH_W = 296
ENGLISH_X = 496
ENGLISH_W = 304
WORD_FONT_MAX = 58
WORD_FONT_MIN = 42

TICK_GAP = 10
TICK_SIZE = 34

# ── Motion constants (seconds) ───────────────────────────────────────
HIGHLIGHT_FADE = 0.25
EMOJI_POP = 0.30
EMOJI_POP_FROM = 0.85
PENCIL_MOVE = 0.35
TICK_POP = 0.25
PULSE_HALF = 0.20
PULSE_SCALE = 0.08


# ── Text fitting, shared with length_spec ────────────────────────────

def fit_word(text: str, width: int, font_max: int = None,
             font_min: int = None) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    """(font, size, drawn width) of the largest size at which `text` fits
    `width` on ONE line, or the floor size when nothing does.

    The single place that decides how big a word is drawn. length_spec calls
    it too, so the check and the frame cannot disagree about what fits.
    """
    font_max = WORD_FONT_MAX if font_max is None else font_max
    font_min = WORD_FONT_MIN if font_min is None else font_min
    for size in range(font_max, font_min - 1, -2):
        f = fredoka(size)
        w = int(math.ceil(f.getlength(text)))
        if w <= width:
            return f, size, w
    f = fredoka(font_min)
    return f, font_min, int(math.ceil(f.getlength(text)))


def column_width(field: str) -> int:
    return {"spanish": SPANISH_W, "english": ENGLISH_W}[field]


def row_centres(n: int) -> List[int]:
    """Page-local y of each row's centre. Fewer than ten rows are centred in
    the same band at the same pitch, so a row looks the same in every video."""
    block = n * ROW_PITCH
    top = ROWS_TOP + ((ROWS_BOTTOM - ROWS_TOP) - block) // 2
    return [top + ROW_PITCH * i + ROW_PITCH // 2 for i in range(n)]


def _text_y(f: ImageFont.FreeTypeFont, centre: int) -> int:
    """Top y that puts the font's cap-height block on `centre`."""
    ascent, _descent = f.getmetrics()
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    return int(centre - (top + bottom) / 2)


# ── Emoji ────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _emoji_strike(emoji: str) -> Image.Image:
    f = ImageFont.truetype(str(EMOJI_FONT), EMOJI_STRIKE)
    canvas = Image.new("RGBA", (EMOJI_STRIKE * 2, EMOJI_STRIKE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((EMOJI_STRIKE // 2, EMOJI_STRIKE // 2), emoji,
                                font=f, embedded_color=True)
    box = canvas.getbbox()
    if box is None:
        raise ValueError(f"emoji {emoji!r} rendered nothing")
    return canvas.crop(box)


@lru_cache(maxsize=256)
def emoji_image(emoji: str, size: int) -> Image.Image:
    """The emoji fitted into a size x size square, aspect kept."""
    src = _emoji_strike(emoji)
    scale = size / max(src.size)
    w, h = max(1, round(src.size[0] * scale)), max(1, round(src.size[1] * scale))
    return src.resize((w, h), Image.LANCZOS)


# ── Easing ───────────────────────────────────────────────────────────

def ease_out_cubic(p: float) -> float:
    p = clamp01(p)
    return 1.0 - (1.0 - p) ** 3


def ease_in_out(p: float) -> float:
    p = clamp01(p)
    return 3 * p * p - 2 * p * p * p


# ── Timing, read from segment_times ──────────────────────────────────

class Timeline:
    """The measured boundaries this video renders from, by item."""

    def __init__(self, data: Dict, duration: float):
        st = data.get("segment_times")
        if not st:
            raise KeyError(
                "how_do_you_say needs segment_times; it has no fallback, "
                "because a guessed timeline draws the lesson out of sync")
        self.n = len(data["items"])
        self.duration = duration
        self.es, self.think, self.en, self.reveal_end = [], [], [], []
        for i in range(1, self.n + 1):
            es, th, en = st[f"es_{i}"], st[f"think_{i}"], st[f"en_{i}"]
            self.es.append((float(es["start"]), float(es["end"])))
            self.think.append((float(th["start"]), float(th["end"])))
            self.en.append((float(en["start"]), float(en["end"])))
            # The FIRST take's end, measured in the clip. Absent only on an
            # artifact older than this renderer, where the whole first half
            # of en_i is the honest stand-in.
            self.reveal_end.append(float(en.get("reveal_end",
                                               (float(en["start"]) + float(en["end"])) / 2)))
        self.recap = (float(st["recap"]["start"]), float(st["recap"]["end"]))
        self.outro = (float(st["outro"]["start"]), float(st["outro"]["end"]))

    def active(self, t: float) -> Optional[int]:
        """Index of the row the lesson is on, or None before/after the items."""
        if t < self.es[0][0] or t >= self.recap[0]:
            return None
        current = 0
        for i, (start, _end) in enumerate(self.es):
            if t >= start:
                current = i
        return current

    def reveal(self, i: int, t: float) -> float:
        """0..1 of item i's English word written in."""
        start, end = self.en[i][0], self.reveal_end[i]
        if t < start:
            return 0.0
        if end <= start:
            return 1.0
        return clamp01((t - start) / (end - start))


def _recap_word_times(recap_text: str, items: List[Dict],
                      span: Tuple[float, float]) -> List[Optional[float]]:
    """When the recap voice reaches each English word.

    PROPORTIONAL BY CHARACTER inside the recap segment: the ElevenLabs path
    returns no word timings, and the brief names this as the fallback. Each
    word is searched for AFTER the previous one, so a word that also appears
    inside the lead-in sentence is not matched there.
    """
    text = recap_text or ""
    lowered = text.lower()
    total = max(1, len(text))
    start, end = span
    out, cursor = [], 0
    for item in items:
        word = item["english"].lower()
        idx = lowered.find(word, cursor)
        if idx < 0:
            out.append(None)
            continue
        cursor = idx + len(word)
        centre = (idx + len(word) / 2) / total
        out.append(start + centre * (end - start))
    return out


# ── Static page (cached) ─────────────────────────────────────────────

LAYER_W, LAYER_H = PAGE_W + 2 * PAD, PAGE_H + 2 * PAD


def _p(x: float, y: float) -> Tuple[float, float]:
    """Page-local -> layer coordinates."""
    return x + PAD, y + PAD


def _draw_rings(draw: ImageDraw.ImageDraw, top: int, bottom: int) -> None:
    """Spiral binding: a punched hole and an ink-outlined wire loop per ring,
    the loop wrapping over the page's left edge."""
    ink = _color("ink")
    wire = (178, 174, 166, 255)
    step = (bottom - top) / (RINGS - 1)
    for k in range(RINGS):
        y = top + step * k
        hx, hy = _p(RING_X, y)
        draw.ellipse([hx - 9, hy - 9, hx + 9, hy + 9], fill=ink)
        # the loop: from the hole, out past the edge and back
        box = [hx - 62, hy - 17, hx + 4, hy + 13]
        draw.arc(box, start=150, end=390, fill=ink, width=11)
        draw.arc(box, start=158, end=382, fill=wire, width=5)


@lru_cache(maxsize=4)
def _static_page(items_key: Tuple[Tuple[str, str], ...], theme: str) -> Image.Image:
    """Paper, binding, title, theme, ruled lines. Nothing that changes."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    _draw_paper(draw)

    # ruled lines, one under each row, in the brand's sky blue
    sky = _on_paper(_color("sky"), 0.6)
    for cy in row_centres(len(items_key)):
        ly = cy + ROW_PITCH // 2 - 6
        draw.line([_p(60, ly), _p(PAGE_W - 30, ly)], fill=sky, width=3)

    _draw_title(draw, TITLE_TEXT, theme, fredoka(TITLE_SIZE), _color("english_blue"))
    _draw_rings(draw, 40, PAGE_H - 40)
    return layer


def _draw_paper(draw: ImageDraw.ImageDraw) -> None:
    """Hard sticker shadow, then the outlined page."""
    ink = _color("ink")
    x0, y0 = _p(0, 0)
    x1, y1 = _p(PAGE_W, PAGE_H)
    draw.rounded_rectangle([x0 + SHADOW[0], y0 + SHADOW[1], x1 + SHADOW[0], y1 + SHADOW[1]],
                           radius=PAGE_RADIUS, fill=ink)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=PAGE_RADIUS, fill=PAPER,
                           outline=ink, width=PAGE_OUTLINE)


def _draw_title(draw: ImageDraw.ImageDraw, title: str, theme: str,
                tf: ImageFont.FreeTypeFont, color) -> None:
    """Title centred right of the binding over a yellow marker stroke, theme under it.
    English is blue (brand rule); a Spanish title is ink."""
    ink = _color("ink")
    yellow = _color("brand_yellow")
    tw = tf.getlength(title)
    cx = (64 + PAGE_W) / 2
    tx = cx - tw / 2
    # hand-drawn underline: a brand-yellow marker stroke that wobbles once
    uy = TITLE_Y + 92
    pts = []
    for s in range(41):
        u = s / 40
        pts.append(_p(tx - 8 + u * (tw + 16), uy + 5 * math.sin(u * math.pi * 1.5) - 3 * u))
    draw.line(pts, fill=yellow, width=18, joint="curve")
    draw.text(_p(tx, TITLE_Y), title, font=tf, fill=color)

    thf = fredoka(THEME_SIZE, "display_medium")
    thw = thf.getlength(theme)
    draw.text(_p(cx - thw / 2, THEME_Y), theme, font=thf, fill=ink)


@lru_cache(maxsize=4)
def _static_words(items_key: Tuple[Tuple[str, str], ...]) -> Image.Image:
    """The Spanish column, visible from the first frame."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    ink = _color("ink")
    for (spanish, _emoji), cy in zip(items_key, row_centres(len(items_key))):
        f, _size, _w = fit_word(spanish, SPANISH_W)
        draw.text(_p(SPANISH_X, _text_y(f, cy)), spanish, font=f, fill=ink)
    return layer


@lru_cache(maxsize=32)
def _word_image(text: str, width: int, color: Tuple[int, int, int, int]) -> Image.Image:
    """An English word on its own transparent strip, for masking and pulses."""
    f, _size, w = fit_word(text, width)
    ascent, descent = f.getmetrics()
    img = Image.new("RGBA", (w + 8, ascent + descent + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2, 2), text, font=f, fill=color)
    return img


def _word_offset_y(text: str, width: int, centre: int) -> int:
    f, _size, _w = fit_word(text, width)
    return _text_y(f, centre) - 2


# ── Pencil ───────────────────────────────────────────────────────────

#: Degrees BELOW horizontal: tip upper-left, body trailing down-right.
#: Rows fill top to bottom, so the body lies over rows not yet written. With
#: the body up-right (the first render) it sat on the previous row's English
#: word whenever the tip rested -- "grandmother" vanished under it at item 8.
PENCIL_ANGLE = 38


@lru_cache(maxsize=1)
def pencil_image() -> Tuple[Image.Image, Tuple[int, int]]:
    """The pencil, tilted, and where its tip sits inside the image.

    Drawn horizontally with the tip at the canvas centre, then rotated about
    that centre, so the tip does not move and needs no trigonometry.
    """
    ink = _color("ink")
    yellow = _color("brand_yellow")
    wood = (236, 196, 140, 255)
    pink = (232, 128, 140, 255)
    metal = (178, 174, 166, 255)
    size = 560
    c = size // 2
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    h = 40                                  # body thickness
    cone, body, ferrule, eraser = 54, 170, 24, 30
    x = c
    # wood cone with the graphite tip
    d.polygon([(x, c), (x + cone, c - h / 2), (x + cone, c + h / 2)], fill=wood,
              outline=ink)
    d.polygon([(x, c), (x + 17, c - h / 2 * 17 / cone), (x + 17, c + h / 2 * 17 / cone)],
              fill=ink)
    x += cone
    d.rectangle([x, c - h / 2, x + body, c + h / 2], fill=yellow, outline=ink, width=4)
    d.line([(x, c), (x + body, c)], fill=(214, 182, 80, 255), width=3)
    x += body
    d.rectangle([x, c - h / 2, x + ferrule, c + h / 2], fill=metal, outline=ink, width=4)
    x += ferrule
    d.rounded_rectangle([x - 2, c - h / 2, x + eraser, c + h / 2], radius=10, fill=pink,
                        outline=ink, width=4)
    # the cone's outline drawn last so the body's edge does not cut it
    d.line([(c, c), (c + cone, c - h / 2)], fill=ink, width=4)
    d.line([(c, c), (c + cone, c + h / 2)], fill=ink, width=4)
    rotated = img.rotate(-PENCIL_ANGLE, resample=Image.BICUBIC, center=(c, c))
    return rotated, (c, c)


def _pencil_targets(tl: Timeline, items: List[Dict], centres: List[int]):
    """Rest point per item: (start of the English column, end of its word)."""
    starts, ends = [], []
    for item, cy in zip(items, centres):
        _f, _s, w = fit_word(item["english"], ENGLISH_W)
        base = cy + 26
        starts.append((ENGLISH_X, base))
        ends.append((ENGLISH_X + w, base))
    return starts, ends


#: Right of the title, body running off the page's right edge, so at rest it
#: covers neither the title nor the first row.
PENCIL_PARK_INTRO = (PAGE_W - 105, TITLE_Y + 20)
PENCIL_PARK_RECAP = PENCIL_PARK_INTRO        # back by the title, off the rows


def pencil_position(t: float, tl: Timeline, items: List[Dict],
                    centres: List[int]) -> Tuple[float, float]:
    """Page-local tip position at t. Pure function of t."""
    starts, ends = _pencil_targets(tl, items, centres)

    def glide(a, b, t0):
        p = ease_in_out((t - t0) / PENCIL_MOVE)
        return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)

    pos = PENCIL_PARK_INTRO
    for i in range(tl.n):
        es0 = tl.es[i][0]
        if t < es0:
            return pos
        prev = pos
        if t < tl.en[i][0]:
            return glide(prev, starts[i], es0)
        p = tl.reveal(i, t)
        pos = (starts[i][0] + (ends[i][0] - starts[i][0]) * p, starts[i][1])
        if p < 1.0:
            return pos
        pos = ends[i]
    if t < tl.recap[0]:
        return pos
    return glide(pos, PENCIL_PARK_RECAP, tl.recap[0])


# ── Frame ────────────────────────────────────────────────────────────

def _draw_tick(layer: Image.Image, x: float, cy: int, scale: float) -> None:
    if scale <= 0:
        return
    s = TICK_SIZE * scale
    draw = ImageDraw.Draw(layer, "RGBA")
    pts = [(x, cy), (x + s * 0.38, cy + s * 0.38), (x + s, cy - s * 0.5)]
    pts = [_p(px, py) for px, py in pts]
    draw.line(pts, fill=_color("ink"), width=max(1, int(13 * scale)), joint="curve")
    draw.line(pts, fill=_color("correct"), width=max(1, int(7 * scale)), joint="curve")


def _draw_countdown(layer: Image.Image, cy: int, p: float) -> None:
    """Three dots in the English column that empty over the think pause, so
    the silence reads as "your turn" and not as dead air."""
    draw = ImageDraw.Draw(layer, "RGBA")
    blue = _color("english_blue")
    r = 11
    for j in range(3):
        # mid-column: the pencil rests at the column's start during the pause
        cx = ENGLISH_X + 110 + j * 40
        x, y = _p(cx, cy)
        # dot j empties when the remaining time passes (3 - j) / 3
        left = clamp01((1.0 - p) * 3 - (2 - j))
        draw.ellipse([x - r, y - r, x + r, y + r], outline=blue, width=4)
        if left > 0:
            ir = (r - 2) * left
            draw.ellipse([x - ir, y - ir, x + ir, y + ir], fill=blue)


def create_frame_how_do_you_say(t: float, data: Dict, duration: float,
                                presentation=None) -> np.ndarray:
    """One frame of a how_do_you_say video."""
    items: List[Dict] = data["items"]
    tl = data.get("_hdys_timeline")
    if tl is None:
        tl = Timeline(data, duration)
        data["_hdys_timeline"] = tl
    n = len(items)
    centres = row_centres(n)
    key = tuple((it["spanish"], it["emoji"]) for it in items)

    frame, _draw = create_base_frame(t)
    layer = _static_page(key, data["theme"]).copy()
    draw = ImageDraw.Draw(layer, "RGBA")

    # 1. highlighter behind the active row (and fading out of the last one)
    yellow = _color("brand_yellow")
    for i in range(n):
        start = tl.es[i][0]
        nxt = tl.es[i + 1][0] if i + 1 < n else tl.recap[0]
        if t < start or t >= nxt + HIGHLIGHT_FADE:
            continue
        a = clamp01((t - start) / HIGHLIGHT_FADE)
        if t >= nxt:
            a *= 1.0 - clamp01((t - nxt) / HIGHLIGHT_FADE)
        if a <= 0:
            continue
        cy = centres[i]
        x0, y0 = _p(56, cy - ROW_PITCH // 2 + 6)
        x1, y1 = _p(PAGE_W - 22, cy + ROW_PITCH // 2 - 10)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=18,
                               fill=_on_paper(yellow, 0.7 * a))

    # 2. emoji, popping on its row's es_i
    for i, item in enumerate(items):
        scale = 1.0
        es0 = tl.es[i][0]
        if es0 <= t < es0 + EMOJI_POP:
            scale = EMOJI_POP_FROM + (1.0 - EMOJI_POP_FROM) * ease_out_cubic((t - es0) / EMOJI_POP)
        size = max(1, round(EMOJI_SIZE * scale))
        img = emoji_image(item["emoji"], size)
        ex, ey = _p(EMOJI_X + (EMOJI_SIZE - img.size[0]) / 2,
                    centres[i] - img.size[1] / 2)
        layer.alpha_composite(img, (int(round(ex)), int(round(ey))))

    # 3. the Spanish column, static
    layer.alpha_composite(_static_words(key))

    # 4. countdown dots, English reveal, ticks, recap pulses
    blue = _color("english_blue")
    pulses = _recap_word_times(data.get("recap", ""), items, tl.recap)
    for i, item in enumerate(items):
        cy = centres[i]
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown(layer, cy, (t - th0) / max(1e-6, th1 - th0))

        p = tl.reveal(i, t)
        if p <= 0:
            continue
        word = _word_image(item["english"], ENGLISH_W, blue)
        wy = _word_offset_y(item["english"], ENGLISH_W, cy)
        if p < 1.0:
            cut = int(round(word.size[0] * p))
            if cut > 0:
                layer.alpha_composite(word.crop((0, 0, cut, word.size[1])),
                                      tuple(int(v) for v in _p(ENGLISH_X - 2, wy)))
            continue

        s = 1.0
        tc = pulses[i]
        if tc is not None and abs(t - tc) < PULSE_HALF:
            s = 1.0 + PULSE_SCALE * math.cos((t - tc) / PULSE_HALF * math.pi / 2) ** 2
        if s != 1.0:
            big = word.resize((max(1, round(word.size[0] * s)),
                               max(1, round(word.size[1] * s))), Image.LANCZOS)
            dx = (big.size[0] - word.size[0]) / 2
            dy = (big.size[1] - word.size[1]) / 2
            layer.alpha_composite(big, tuple(int(round(v)) for v in
                                             _p(ENGLISH_X - 2 - dx, wy - dy)))
        else:
            layer.alpha_composite(word, tuple(int(v) for v in _p(ENGLISH_X - 2, wy)))

        _f, _s, w = fit_word(item["english"], ENGLISH_W)
        tick_t = tl.reveal_end[i]
        _draw_tick(layer, ENGLISH_X + w + TICK_GAP, cy,
                   ease_out_cubic((t - tick_t) / TICK_POP) if t >= tick_t else 0.0)

    # 5. the pencil, on top of everything on the page
    pencil, (pcx, pcy) = pencil_image()
    px, py = pencil_position(t, tl, items, centres)
    lx, ly = _p(px, py)
    layer.alpha_composite(pencil, (int(round(lx - pcx)), int(round(ly - pcy))))

    # 6. tilt the whole page once, then place it
    tilted = layer.rotate(TILT_DEG, resample=Image.BICUBIC)
    frame.alpha_composite(tilted, (PAGE_X - PAD, PAGE_Y - PAD))

    return finalize_frame(frame, ImageDraw.Draw(frame, "RGBA"), t, duration,
                          scene_cuts=[tl.recap[0]])


# ═════════════════════════════════════════════════════════════════════
# THE LEVEL MODES (STEP 58): level_test and say_it_level on the same page.
#
# The whole list is on the page from frame 1 -- the hook the how_do_you_say
# Shorts proved. Each row holds two lines: the prompt (on the page from the
# start) and, under it, the answer, written in while the voice says it.
# Rows 1-3 / 4-7 / 8-10 are the three tiers, labelled in the margin; after
# row 10 a sticky note gives the verdict. Pure function of t, measured
# segment_times or a refusal, exactly as above.
# ═════════════════════════════════════════════════════════════════════

#: Which field is the prompt (line 1, from frame 1) and which is written in.
LEVEL_MODES = {
    "level_test":   {"prompt": "english", "answer": "spanish"},
    "say_it_level": {"prompt": "spanish", "answer": "english"},
    # STEP 61: the answer is derived (tf_answer) and comes into focus instead of being written.
    "true_false_level": {"prompt": "statement", "answer": None},
}
#: Rows that open a tier, 0-based, and the tiers' bands and words.
TIER_STARTS = (3, 7)
TIERS = (("BÁSICO", "correct", 0, 3), ("INTERMEDIO", "brand_yellow", 3, 7),
         ("EXPERTO", "error", 7, 10))

NUM_CX = 122                     # row number, centred here
NUM_SIZE = 46
LABEL_X0, LABEL_X1 = 50, 86      # the tier pill, in the margin right of the rings
LABEL_SIZE = 26
#: One text column for both lines; length_spec measures every prompt and
#: answer against it. Right edge leaves room for the tick.
LINE_X = 166
LINE_W = PAGE_W - 30 - (TICK_GAP + TICK_SIZE) - LINE_X          # 620
LINE_FONT_MAX = 46
LINE_FONT_MIN = 34
LINE1_DY, LINE2_DY = -23, 25     # line centres from the row centre

#: The say_it_level note over the title: the tip and the other right answer.
NOTE_X, NOTE_Y, NOTE_W, NOTE_H = 96, 16, 740, 196
NOTE_PAD = 22
NOTE_FONT = 34
NOTE_LINES = 3                   # tip up to two lines + «También: …»
NOTE_POP = 0.25
NOTE_LEAD = "También: "
NOTE_LEAD_W = 156                # NOTE_LEAD at NOTE_FONT plus a little air; length_spec reads it

#: The verdict note over the lower rows.
VERDICT_X, VERDICT_Y, VERDICT_W, VERDICT_H = 120, PAGE_H - 470, 640, 400
VERDICT_SIZE = 64
VERDICT_ROT = -3.0
LABEL_PULSE = 0.22
#: Where the pencil waits while the viewer thinks: the right end of the answer line, its
#: body off the page, so it covers none of the prompts the viewer is reading.
PENCIL_WAIT_X = PAGE_W - 70
#: Parked right of the theme line: a level title is wider than "How do you say?".
LEVEL_PENCIL_PARK = (PAGE_W - 70, THEME_Y + 24)


#: true_false_level: every row shows the SAME grey placeholder, blurred, until its answer.
#: Blurring the real answer leaked its colour and length (the first mock): a hint.
TF_PLACEHOLDER = "VERDADERO · FALSO"
BLUR_MAX = 14                    # px at frame 0
BLUR_STEP = 2                    # radius steps, so the strip cache stays small
BLUR_PAD = 2 * BLUR_MAX          # room for the blur around a strip
CROSS_SIZE = 28


def tf_answer(item: Dict) -> Tuple[str, str]:
    """(text, colour name) of a true_false_level answer line."""
    if item["truth"]:
        return "VERDADERO", "correct"
    return f"FALSO · {item['correction']}", "error"


def fit_line(text: str, size: int = LINE_FONT_MAX) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    return fit_word(text, LINE_W, size, LINE_FONT_MIN)


def page_size(texts: Tuple[str, ...]) -> int:
    """One size for a whole column of lines: the largest at which every one fits, so ten
    rows do not each pick their own and the page reads as one hand."""
    return min(fit_line(text)[1] for text in texts)


def note_lines(tip: Optional[str], alt: Optional[str]) -> List[Tuple[str, str]]:
    """[(kind, text)] the note draws: the tip wrapped to the note, then the alternative.
    length_spec reads the same wrap, so a tip that needs a third line is caught there."""
    f = fredoka(NOTE_FONT, "display_medium")
    width = NOTE_W - 2 * NOTE_PAD
    out = []
    if tip:
        line = ""
        for word in tip.split():
            trial = f"{line} {word}".strip()
            if line and f.getlength(trial) > width:
                out.append(("tip", line))
                line = word
            else:
                line = trial
        out.append(("tip", line))
    if alt:
        out.append(("alt", alt))
    return out


class LevelTimeline:
    """intro, [prompt_i], think_i, answer_i, tier_4, tier_8, verdict, outro."""

    def __init__(self, data: Dict, duration: float):
        st = data.get("segment_times")
        if not st:
            raise KeyError(f"{data.get('type')} needs segment_times; it has no fallback, "
                           "because a guessed timeline draws the lesson out of sync")
        self.n = len(data["items"])
        self.duration = duration

        def span(key):
            return float(st[key]["start"]), float(st[key]["end"])

        self.think = [span(f"think_{i}") for i in range(1, self.n + 1)]
        self.answer = [span(f"answer_{i}") for i in range(1, self.n + 1)]
        # The row lights up with its prompt; an unspoken prompt starts at its pause.
        self.row = [span(f"prompt_{i}")[0] if f"prompt_{i}" in st else self.think[i - 1][0]
                    for i in range(1, self.n + 1)]
        self.tier = {i: span(f"tier_{i + 1}") for i in TIER_STARTS if f"tier_{i + 1}" in st}
        self.verdict = span("verdict")
        self.outro = span("outro")

    def row_end(self, i: int) -> float:
        return self.row[i + 1] if i + 1 < self.n else self.verdict[0]

    def reveal(self, i: int, t: float) -> float:
        start, end = self.answer[i]
        if t < start:
            return 0.0
        return 1.0 if end <= start else clamp01((t - start) / (end - start))


@lru_cache(maxsize=4)
def _static_level_page(n: int, title: str, theme: str) -> Image.Image:
    """Paper, binding, title, theme and the ruled lines; the two that close a tier
    are drawn thicker in the next tier's colour."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    _draw_paper(draw)
    sky = _on_paper(_color("sky"), 0.6)
    closes = {t[2]: t[1] for t in TIERS[1:]}           # row count -> colour of the tier it opens
    for i, cy in enumerate(row_centres(n)):
        ly = cy + ROW_PITCH // 2 - 6
        if i + 1 in closes:                            # sticker rule: ink under the colour
            draw.line([_p(LABEL_X1 + 6, ly), _p(PAGE_W - 30, ly)], fill=_color("ink"), width=11)
            draw.line([_p(LABEL_X1 + 8, ly), _p(PAGE_W - 32, ly)], fill=_color(closes[i + 1]), width=6)
        else:
            draw.line([_p(LABEL_X1 + 6, ly), _p(PAGE_W - 30, ly)], fill=sky, width=3)
    # a Spanish title is ink; English is always blue (brand rule)
    _draw_title(draw, title, theme, fit_word(title, PAGE_W - 140, TITLE_SIZE, 56)[0], _color("ink"))
    _draw_rings(draw, 40, PAGE_H - 40)
    return layer


@lru_cache(maxsize=4)
def _static_level_text(prompts: Tuple[str, ...], prompt_blue: bool) -> Image.Image:
    """The row numbers and every prompt: on the page from the first frame."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    nf = fredoka(NUM_SIZE)
    color = _color("english_blue" if prompt_blue else "ink")
    size = page_size(prompts)
    for i, (text, cy) in enumerate(zip(prompts, row_centres(len(prompts)))):
        num = str(i + 1)
        draw.text(_p(NUM_CX - nf.getlength(num) / 2, _text_y(nf, cy)), num, font=nf,
                  fill=_color("secondary_text"))
        f = fit_line(text, size)[0]
        draw.text(_p(LINE_X, _text_y(f, cy + LINE1_DY)), text, font=f, fill=color)
    return layer


@lru_cache(maxsize=32)
def _line_image(text: str, size: int, color: Tuple[int, int, int, int]) -> Image.Image:
    """An answer on its own transparent strip, for the reveal mask."""
    f, _size, w = fit_line(text, size)
    ascent, descent = f.getmetrics()
    img = Image.new("RGBA", (w + 8, ascent + descent + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2, 2), text, font=f, fill=color)
    return img


@lru_cache(maxsize=64)
def _blurred_line(text: str, size: int, color: Tuple[int, int, int, int], radius: int) -> Image.Image:
    """A line on a padded strip, Gaussian-blurred on the strip (never the frame)."""
    line = _line_image(text, size, color)
    img = Image.new("RGBA", (line.size[0] + 2 * BLUR_PAD, line.size[1] + 2 * BLUR_PAD), (0, 0, 0, 0))
    img.alpha_composite(line, (BLUR_PAD, BLUR_PAD))
    return img.filter(ImageFilter.GaussianBlur(radius)) if radius > 0 else img


def _faded(img: Image.Image, a: float) -> Image.Image:
    if a >= 1.0:
        return img
    out = img.copy()
    out.putalpha(img.split()[3].point(lambda v: int(v * a)))
    return out


def _draw_cross(layer: Image.Image, x: float, cy: int, scale: float) -> None:
    """An ✗ drawn like _draw_tick: an ink stroke under a red one."""
    if scale <= 0:
        return
    s = CROSS_SIZE * scale
    draw = ImageDraw.Draw(layer, "RGBA")
    x0, y0 = x + (CROSS_SIZE - s) / 2, cy - s / 2
    for a, b in (((x0, y0), (x0 + s, y0 + s)), ((x0 + s, y0), (x0, y0 + s))):
        draw.line([_p(*a), _p(*b)], fill=_color("ink"), width=max(1, int(13 * scale)))
        draw.line([_p(*a), _p(*b)], fill=_color("error"), width=max(1, int(7 * scale)))


def _draw_tf_answers(layer: Image.Image, t: float, tl: "LevelTimeline", items: List[Dict],
                     centres: List[int]) -> None:
    """The placeholder cross-fades to the real answer while the blur goes BLUR_MAX -> 0."""
    lines = [tf_answer(it) for it in items]
    size = page_size(tuple(text for text, _c in lines) + (TF_PLACEHOLDER,))
    grey = _color("secondary_text")
    for i, (text, color_name) in enumerate(lines):
        cy = centres[i] + LINE2_DY
        f = fit_line(text, size)[0]
        at = tuple(int(v) for v in _p(LINE_X - 2 - BLUR_PAD, _text_y(f, cy) - 2 - BLUR_PAD))
        p = tl.reveal(i, t)
        radius = int(round(BLUR_MAX * (1.0 - p) / BLUR_STEP)) * BLUR_STEP
        if p < 1.0:
            layer.alpha_composite(_faded(_blurred_line(TF_PLACEHOLDER, size, grey, radius), 1.0 - p), at)
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, LINE_X + 110, cy, (t - th0) / max(1e-6, th1 - th0))
        if p <= 0:
            continue
        layer.alpha_composite(_faded(_blurred_line(text, size, _color(color_name), radius), p), at)
        if p >= 1.0:
            mark_t = tl.answer[i][1]
            scale = ease_out_cubic((t - mark_t) / TICK_POP) if t >= mark_t else 0.0
            x = LINE_X + fit_line(text, size)[2] + TICK_GAP
            (_draw_tick if items[i]["truth"] else _draw_cross)(layer, x, cy, scale)


def _draw_countdown_at(layer: Image.Image, x0: float, cy: float, p: float) -> None:
    """_draw_countdown's three dots, at a given x."""
    draw = ImageDraw.Draw(layer, "RGBA")
    blue = _color("english_blue")
    r = 11
    for j in range(3):
        x, y = _p(x0 + j * 40, cy)
        left = clamp01((1.0 - p) * 3 - (2 - j))
        draw.ellipse([x - r, y - r, x + r, y + r], outline=blue, width=4)
        if left > 0:
            ir = (r - 2) * left
            draw.ellipse([x - ir, y - ir, x + ir, y + ir], fill=blue)


@lru_cache(maxsize=8)
def _tier_pill(word: str, color_name: str, height: int) -> Image.Image:
    """A vertical pill in the tier's colour with its word read bottom to top."""
    w = LABEL_X1 - LABEL_X0
    pill = Image.new("RGBA", (w + 4, height + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(pill, "RGBA")
    d.rounded_rectangle([2, 2, w + 1, height + 1], radius=w // 2, fill=_color(color_name),
                        outline=_color("ink"), width=3)
    f = fredoka(LABEL_SIZE)
    text = Image.new("RGBA", (int(f.getlength(word)) + 4, LABEL_SIZE + 10), (0, 0, 0, 0))
    ink_on = color_name == "brand_yellow"           # yellow is never under paper-coloured text
    ImageDraw.Draw(text).text((2, 2), word, font=f, fill=_color("ink") if ink_on else PAPER)
    text = text.rotate(90, expand=True, resample=Image.BICUBIC)
    pill.alpha_composite(text, ((pill.size[0] - text.size[0]) // 2 + 1,
                                (pill.size[1] - text.size[1]) // 2))
    return pill


def _draw_arrow(draw: ImageDraw.ImageDraw, x: float, y: float, length: float, color) -> None:
    """Fredoka has no «→»: a stroke and a head."""
    draw.line([(x, y), (x + length - 14, y)], fill=color, width=8)
    draw.polygon([(x + length, y), (x + length - 20, y - 14), (x + length - 20, y + 14)], fill=color)


@lru_cache(maxsize=1)
def _verdict_note() -> Image.Image:
    """«3 → básico · 7 → intermedio · 10 → experto», one tier per line, on a sticky note."""
    ink = _color("ink")
    note = Image.new("RGBA", (VERDICT_W + SHADOW[0] + 4, VERDICT_H + SHADOW[1] + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(note, "RGBA")
    d.rectangle([SHADOW[0], SHADOW[1], VERDICT_W + SHADOW[0], VERDICT_H + SHADOW[1]], fill=ink)
    d.rectangle([0, 0, VERDICT_W, VERDICT_H], fill=_color("brand_yellow"), outline=ink, width=5)
    f = fredoka(VERDICT_SIZE)
    for k, (num, (word, color, _a, _b)) in enumerate(zip(("3", "7", "10"), TIERS)):
        cy = 80 + k * 120
        y = _text_y(f, cy)
        d.text((48, y), num, font=f, fill=ink)
        _draw_arrow(d, 150, cy, 70, ink)
        d.text((250, y), word.lower(), font=f, fill=_color(color) if color != "brand_yellow" else ink)
    return note.rotate(VERDICT_ROT, expand=True, resample=Image.BICUBIC)


def _draw_note(layer: Image.Image, lines: List[Tuple[str, str]], scale: float) -> None:
    if scale <= 0 or not lines:
        return
    ink = _color("ink")
    note = Image.new("RGBA", (NOTE_W + SHADOW[0], NOTE_H + SHADOW[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(note, "RGBA")
    d.rectangle([SHADOW[0], SHADOW[1], NOTE_W + SHADOW[0] - 1, NOTE_H + SHADOW[1] - 1], fill=ink)
    d.rectangle([0, 0, NOTE_W - 1, NOTE_H - 1], fill=_color("brand_yellow"), outline=ink, width=4)
    f = fredoka(NOTE_FONT, "display_medium")
    step = (NOTE_H - 2 * NOTE_PAD) / NOTE_LINES
    top = NOTE_PAD + (NOTE_LINES - len(lines)) * step / 2
    for k, (kind, text) in enumerate(lines[:NOTE_LINES]):
        cy = top + step * (k + 0.5)
        y = _text_y(f, cy)
        if kind == "alt":
            d.text((NOTE_PAD, y), NOTE_LEAD, font=f, fill=ink)
            d.text((NOTE_PAD + NOTE_LEAD_W, y), text, font=f, fill=_color("english_blue"))
        else:
            d.text((NOTE_PAD, y), text, font=f, fill=ink)
    if scale != 1.0:
        note = note.resize((max(1, round(note.size[0] * scale)), max(1, round(note.size[1] * scale))),
                           Image.LANCZOS)
    cx, cy = NOTE_X + NOTE_W / 2, NOTE_Y + NOTE_H / 2
    layer.alpha_composite(note, tuple(int(round(v)) for v in _p(cx - note.size[0] / 2, cy - note.size[1] / 2)))


def level_pencil_position(t: float, tl: LevelTimeline, items: List[Dict], answer: Optional[str],
                          centres: List[int], size: int, writes: bool = True) -> Tuple[float, float]:
    """Waits at the right end of the active row's answer line, jumps to its start as the
    answer begins, follows the mask, then goes back by the title for the verdict."""
    def glide(a, b, t0):
        p = ease_in_out((t - t0) / PENCIL_MOVE)
        return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)

    pos = LEVEL_PENCIL_PARK
    for i in range(tl.n):
        base = centres[i] + LINE2_DY + 26
        start = (LINE_X, base)
        if t < tl.row[i]:
            return pos
        wait = (PENCIL_WAIT_X, base)
        if not writes:                                 # true_false_level: it points, it does not write
            if t < tl.row_end(i):
                return glide(pos, wait, tl.row[i])
            pos = wait
            continue
        end = (LINE_X + fit_line(items[i][answer], size)[2], base)
        if t < tl.answer[i][0] - PENCIL_MOVE:
            return glide(pos, wait, tl.row[i])
        if t < tl.answer[i][0]:
            return glide(wait, start, tl.answer[i][0] - PENCIL_MOVE)
        p = tl.reveal(i, t)
        pos = (start[0] + (end[0] - start[0]) * p, base)
        if p < 1.0:
            return pos
        pos = end
    if t < tl.verdict[0]:
        return pos
    return glide(pos, LEVEL_PENCIL_PARK, tl.verdict[0])


def create_frame_level(t: float, data: Dict, duration: float, presentation=None) -> np.ndarray:
    """One frame of a level_test, say_it_level or true_false_level video."""
    mode = LEVEL_MODES[data["type"]]
    items: List[Dict] = data["items"]
    tl = data.get("_level_timeline")
    if tl is None:
        tl = LevelTimeline(data, duration)
        data["_level_timeline"] = tl
    n = len(items)
    centres = row_centres(n)
    prompt, answer = mode["prompt"], mode["answer"]
    blue, ink = _color("english_blue"), _color("ink")

    frame, _draw = create_base_frame(t)
    layer = _static_level_page(n, data["title"], data["theme"]).copy()
    draw = ImageDraw.Draw(layer, "RGBA")

    # 1. highlighter behind the active row, then the printed numbers and prompts over it
    yellow = _color("brand_yellow")
    for i in range(n):
        start, nxt = tl.row[i], tl.row_end(i)
        if t < start or t >= nxt + HIGHLIGHT_FADE:
            continue
        a = clamp01((t - start) / HIGHLIGHT_FADE)
        if t >= nxt:
            a *= 1.0 - clamp01((t - nxt) / HIGHLIGHT_FADE)
        if a > 0:
            cy = centres[i]
            draw.rounded_rectangle([*_p(LABEL_X1 + 6, cy - ROW_PITCH // 2 + 6),
                                    *_p(PAGE_W - 22, cy + ROW_PITCH // 2 - 10)],
                                   radius=18, fill=_on_paper(yellow, 0.7 * a))
    layer.alpha_composite(_static_level_text(tuple(it[prompt] for it in items), prompt == "english"))

    # 2. tier pills in the margin; the one a tier line announces pulses once
    for word, color, a, b in TIERS:
        top = centres[a] - ROW_PITCH // 2 + 10
        bottom = centres[b - 1] + ROW_PITCH // 2 - 16
        pill = _tier_pill(word, color, bottom - top)
        s = 1.0
        span = tl.tier.get(a)
        if span and span[0] <= t < span[1]:
            s = 1.0 + LABEL_PULSE * math.sin(math.pi * (t - span[0]) / (span[1] - span[0]))
        if s != 1.0:
            pill = pill.resize((max(1, round(pill.size[0] * s)), max(1, round(pill.size[1] * s))), Image.LANCZOS)
        cx, cy = (LABEL_X0 + LABEL_X1) / 2, (top + bottom) / 2
        layer.alpha_composite(pill, tuple(int(round(v)) for v in _p(cx - pill.size[0] / 2, cy - pill.size[1] / 2)))

    # 3. countdown dots, the answers written in, ticks (true_false_level: brought into focus)
    if answer is None:
        _draw_tf_answers(layer, t, tl, items, centres)
    answer_color = blue if answer == "english" else ink
    size = page_size(tuple(it[answer] for it in items)) if answer else 0
    for i, item in enumerate(items if answer else []):
        cy = centres[i] + LINE2_DY
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, LINE_X + 110, cy, (t - th0) / max(1e-6, th1 - th0))
        p = tl.reveal(i, t)
        if p <= 0:
            continue
        f, _size, w = fit_line(item[answer], size)
        word = _line_image(item[answer], size, answer_color)
        wy = _text_y(f, cy) - 2
        if p < 1.0:
            cut = int(round(word.size[0] * p))
            if cut > 0:
                layer.alpha_composite(word.crop((0, 0, cut, word.size[1])),
                                      tuple(int(v) for v in _p(LINE_X - 2, wy)))
            continue
        layer.alpha_composite(word, tuple(int(v) for v in _p(LINE_X - 2, wy)))
        tick_t = tl.answer[i][1]
        _draw_tick(layer, LINE_X + w + TICK_GAP, cy,
                   ease_out_cubic((t - tick_t) / TICK_POP) if t >= tick_t else 0.0)

    # 4. say_it_level: the tip and the other right answer, from the reveal to the next row
    for i, item in enumerate(items):
        lines = note_lines(item.get("tip"), item.get("alt"))
        if not lines:
            continue
        start, end = tl.answer[i][0], tl.row_end(i)
        if start <= t < end:
            _draw_note(layer, lines, ease_out_cubic((t - start) / NOTE_POP) * 0.15 + 0.85
                       if t < start + NOTE_POP else 1.0)

    # 5. the pencil
    pencil, (pcx, pcy) = pencil_image()
    px, py = level_pencil_position(t, tl, items, answer, centres, size, writes=answer is not None)
    lx, ly = _p(px, py)
    layer.alpha_composite(pencil, (int(round(lx - pcx)), int(round(ly - pcy))))

    # 6. the verdict note, over the lower rows while the verdict is spoken
    v0, v1 = tl.verdict
    if v0 <= t < v1 + NOTE_POP:
        note = _verdict_note()
        a = clamp01((t - v0) / NOTE_POP) * (1.0 - clamp01((t - v1) / NOTE_POP))
        s = 0.85 + 0.15 * ease_out_cubic((t - v0) / NOTE_POP)
        if s != 1.0:
            note = note.resize((max(1, round(note.size[0] * s)), max(1, round(note.size[1] * s))), Image.LANCZOS)
        if a < 1.0:
            note = note.copy()
            note.putalpha(note.split()[3].point(lambda v: int(v * a)))
        cx, cy = VERDICT_X + VERDICT_W / 2, VERDICT_Y + VERDICT_H / 2
        layer.alpha_composite(note, tuple(int(round(v)) for v in _p(cx - note.size[0] / 2, cy - note.size[1] / 2)))

    tilted = layer.rotate(TILT_DEG, resample=Image.BICUBIC)
    frame.alpha_composite(tilted, (PAGE_X - PAD, PAGE_Y - PAD))
    return finalize_frame(frame, ImageDraw.Draw(frame, "RGBA"), t, duration, scene_cuts=[v0])

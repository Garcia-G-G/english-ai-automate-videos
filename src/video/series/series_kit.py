"""What the four «Hecho con Claude» styles share (STEP 78 §2): canvas, safe areas, faces, text
that fits its box or says it does not, the level pill, the challenge card and the outro.

Shapes come from the notebook kit (video.notebook.kit: 4× supersampled, cached); text is
FreeType's, already anti-aliased. Every style draws through these, so the safe-area and overflow
checks hold for all four by construction.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..notebook import kit
from ..motion import clamp01, ease_out_back, ease_out_cubic

W, H = 1080, 1920
#: Platform UI: nothing important in the top 8 % or the bottom 22 % (STEP 78 §2).
SAFE_TOP = int(round(0.08 * H))              # 154
SAFE_BOTTOM = int(round(0.78 * H))           # 1498
SAFE_SIDE = 48
#: STEP 77 §4's button rail: nothing readable right of x 940 below y 950.
RAIL_X, RAIL_Y = 940, 950

FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"
FACES = {"inter": "Inter-Bold.ttf", "inter_black": "Inter-ExtraBold.ttf",
         "serif": "InstrumentSerif-Regular.ttf"}
#: Manrope (the brand's text face, OFL) is a variable font: face name -> its named weight.
MANROPE = {"manrope": b"Medium", "manrope_semibold": b"SemiBold", "manrope_bold": b"Bold"}

Box = Tuple[float, float, float, float]


class Overflow(ValueError):
    """A text does not fit its box at the smallest size the style allows."""


@lru_cache(maxsize=256)
def font(face: str, size: int) -> ImageFont.FreeTypeFont:
    """fredoka / fredoka_medium (the brand), inter / inter_black, serif."""
    if face == "fredoka":
        return kit.fredoka(size)
    if face == "fredoka_medium":
        return kit.fredoka(size, "display_medium")
    if face in MANROPE:
        f = ImageFont.truetype(str(FONTS / "Manrope[wght].ttf"), size)
        f.set_variation_by_name(MANROPE[face])
        return f
    return ImageFont.truetype(str(FONTS / FACES[face]), size)


# ── text with emoji: the faces have none, so an emoji cluster is drawn with Noto (kit.emoji) ──

def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x200D, 0xFE0F) or 0x2B00 <= o <= 0x2BFF


def runs(text: str) -> List[Tuple[str, bool]]:
    """(piece, is_emoji) in order; an emoji with its VS16/ZWJ joins stays one piece."""
    out: List[Tuple[str, bool]] = []
    for ch in text:
        e = _is_emoji(ch)
        if out and out[-1][1] == e and (not e or ord(ch) in (0x200D, 0xFE0F) or out[-1][0][-1] == "\u200d"):
            out[-1] = (out[-1][0] + ch, e)
        else:
            out.append((ch, e))
    return out


def length(text: str, f: ImageFont.FreeTypeFont) -> float:
    return sum(f.getlength(piece) if not e else f.size * 1.15 for piece, e in runs(text))


def draw_line(img: Image.Image, x: float, y: float, text: str, f: ImageFont.FreeTypeFont, fill) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    for piece, e in runs(text):
        if not e:
            d.text((x, y), piece, font=f, fill=fill)
            x += f.getlength(piece)
            continue
        size = int(round(f.size * 1.05))
        try:
            em = kit.emoji(piece.replace("\ufe0f", "") or piece, size)
        except ValueError:                                  # nothing to draw: leave its room
            em = None
        if em is not None:
            img.alpha_composite(em, (int(round(x + (f.size * 1.15 - em.width) / 2)),
                                     int(round(y + (top + bottom) / 2 - em.height / 2))))
        x += f.size * 1.15


def wrap(text: str, f: ImageFont.FreeTypeFont, width: float) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and length(trial, f) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


@lru_cache(maxsize=512)
def fit(text: str, face: str, width: int, max_size: int, min_size: int, max_lines: int = 1,
        step: int = 2) -> Tuple[int, Tuple[str, ...]]:
    """(size, lines): the largest size from max_size down to min_size at which `text` wraps into
    `max_lines` lines no wider than `width`. Raises Overflow — never draws past its box."""
    for size in range(max_size, min_size - 1, -step):
        f = font(face, size)
        lines = wrap(text, f, width)
        if len(lines) <= max_lines and all(length(x, f) <= width for x in lines):
            return size, tuple(lines)
    raise Overflow(f"{text!r} does not fit {width}px × {max_lines} lines at {min_size}px ({face})")


def line_height(size: int, face: str) -> int:
    return int(round(size * (1.08 if face.startswith("inter") else 1.18)))


def text_block(img: Image.Image, lines: Sequence[str], face: str, size: int, x: float, y: float,
               fill, align: str = "left", width: Optional[float] = None, alpha: float = 1.0) -> Box:
    """Draw lines from top-left (x, y); returns the block's ink box. align: left / center."""
    f = font(face, size)
    lh = line_height(size, face)
    if alpha <= 0:
        return block_box(lines, face, size, x, y, align, width)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)) if alpha < 1 else img
    for k, line in enumerate(lines):
        lw = length(line, f)
        lx = x + ((width or lw) - lw) / 2 if align == "center" else x
        draw_line(layer, lx, y + k * lh, line, f, fill)
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
        img.alpha_composite(layer)
    return block_box(lines, face, size, x, y, align, width)


def block_box(lines: Sequence[str], face: str, size: int, x: float, y: float, align: str = "left",
              width: Optional[float] = None) -> Box:
    f = font(face, size)
    lh = line_height(size, face)
    widths = [length(line, f) for line in lines]
    w = max(widths) if widths else 0
    x0 = x + ((width or w) - w) / 2 if align == "center" else x
    top = y + f.getbbox("Hg")[1]
    bottom = y + (len(lines) - 1) * lh + f.getbbox("Hg")[3]
    return (x0, top, x0 + w, bottom)


def in_safe_area(box: Box) -> bool:
    x0, y0, x1, y1 = box
    if y0 < SAFE_TOP or y1 > SAFE_BOTTOM or x0 < SAFE_SIDE * 0.5 or x1 > W - SAFE_SIDE * 0.5:
        return False
    return not (y1 > RAIL_Y and x1 > RAIL_X)


def inside(inner: Box, outer: Box, pad: float = 0) -> bool:
    return (inner[0] >= outer[0] + pad - 0.5 and inner[1] >= outer[1] + pad - 0.5
            and inner[2] <= outer[2] - pad + 0.5 and inner[3] <= outer[3] - pad + 0.5)


# ── shared pieces ────────────────────────────────────────────────────

PILL_Y = SAFE_TOP + 14


def level_pill(img: Image.Image, label: str, fill, ink, cx: float = W / 2, y: float = PILL_Y,
               face: str = "fredoka", size: int = 34) -> Box:
    """The level label in a rounded pill at the top, inside the safe area."""
    f = font(face, size)
    tw = f.getlength(label)
    w, h = tw + 44, size + 26
    x0 = cx - w / 2
    pill = kit.pill(int(h), int(w), fill)                    # kit.pill is vertical: draw it on its side
    pill = pill.rotate(90, expand=True)
    img.alpha_composite(pill, (int(round(x0)), int(round(y))))
    d = ImageDraw.Draw(img)
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    d.text((cx - tw / 2, y + h / 2 - (top + bottom) / 2 + 2), label, font=f, fill=ink)
    return (x0, y, x0 + w + 4, y + h + 4)


CHALLENGE_CTA = "Escríbelo en comentarios"


def challenge_layout(prompt: str, y: float, width: int = 800) -> Dict:
    """Sizes and boxes of the challenge card at top y (raises Overflow)."""
    size, lines = fit(prompt, "fredoka", width - 80, 56, 38, 3)
    lh = line_height(size, "fredoka")
    head = 34
    h = 40 + head + 18 + lh * len(lines) + 24 + 40 + 36
    x0 = (W - width) / 2
    return {"box": (x0, y, x0 + width, y + h), "size": size, "lines": lines, "x": x0, "y": y, "w": width, "h": h}


def challenge_card(img: Image.Image, prompt: str, y: float, p: float = 1.0, width: int = 800) -> Box:
    """«RETO» + the prompt + «Escríbelo en comentarios», on a sticky note that pops in with p."""
    lay = challenge_layout(prompt, y, width)
    if p <= 0:
        return lay["box"]
    s = 0.6 + 0.4 * ease_out_back(clamp01(p), 2.2)
    card = Image.new("RGBA", (int(lay["w"]) + 14, int(lay["h"]) + 14), (0, 0, 0, 0))
    card.alpha_composite(kit.note_card(int(lay["w"]), int(lay["h"]), kit.colour("brand_yellow"), 5, (10, 10)))
    d = ImageDraw.Draw(card)
    d.text((40, 36), "RETO", font=font("fredoka", 34), fill=kit.colour("error"))
    ink = kit.colour("ink")
    text_block(card, lay["lines"], "fredoka", lay["size"], 40, 36 + 34 + 18, ink)
    lh = line_height(lay["size"], "fredoka")
    d.text((40, 36 + 34 + 18 + lh * len(lay["lines"]) + 24), CHALLENGE_CTA, font=font("fredoka_medium", 36),
           fill=kit.colour("english_blue"))
    if s != 1.0:
        card = card.resize((max(1, round(card.width * s)), max(1, round(card.height * s))), Image.LANCZOS)
    cx, cy = W / 2, y + lay["h"] / 2
    img.alpha_composite(card, (int(round(cx - card.width / 2)), int(round(cy - card.height / 2))))
    return lay["box"]


# ── the outro: the brand card, Bubi waving, the challenge's answer after 2 s ──

OUTRO_ANSWER_AT = 2.0
OUTRO_ANSWER_W = 760                # centred: it ends left of the rail's x 940


def outro_frame(t: float, variant: Dict, answer: str) -> np.ndarray:
    """One outro frame (t from the outro's start): video.outro's card and Bubi, then, after
    OUTRO_ANSWER_AT, «¿Acertaste?» and the answer, small, under the card."""
    from .. import outro as O
    base = Image.fromarray(_outro_fn(variant["id"])(t)).convert("RGBA")
    if t >= OUTRO_ANSWER_AT:
        a = clamp01((t - OUTRO_ANSWER_AT) / 0.3)
        y = outro_answer_y()
        ink, blue = kit.colour("ink"), kit.colour("english_blue")
        size, lines = fit(answer, "fredoka", OUTRO_ANSWER_W, 44, 30, 2)
        text_block(base, ["¿Acertaste?"], "fredoka_medium", 38, 0, y, ink, "center", W, a)
        text_block(base, lines, "fredoka", size, 0, y + 54, blue, "center", W, a)
    return np.asarray(base.convert("RGB"))


def outro_answer_y() -> float:
    from .. import outro as O
    return (H - O.CARD_H) // 2 + O.CARD_DY + O.CARD_H + 40


def outro_answer_box(answer: str) -> Box:
    y = outro_answer_y()
    size, lines = fit(answer, "fredoka", OUTRO_ANSWER_W, 44, 30, 2)
    a = block_box(["¿Acertaste?"], "fredoka_medium", 38, 0, y, "center", W)
    b = block_box(lines, "fredoka", size, 0, y + 54, "center", W)
    return (min(a[0], b[0]), a[1], max(a[2], b[2]), b[3])


@lru_cache(maxsize=4)
def _outro_fn(variant_id: str):
    from .. import outro as O
    variant = next(v for v in O.load_variants()["variants"] if v["id"] == variant_id)
    return O._make_frame_fn(variant)


# ── marks drawn on: a ring and an arrow, stroke by stroke (the notebook kit's 4× painter) ──

def ring(layer: Image.Image, box: Box, p: float, colour, width: float = 9) -> None:
    """A hand-drawn loop round `box`, p of the way, overshooting a little (red ink)."""
    if p <= 0:
        return
    p = round(clamp01(p) * 96) / 96
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    sweep, a0 = 2 * math.pi * 1.1 * p, -math.pi * 0.8
    steps = max(2, int(120 * p))
    pts = []
    for j in range(steps + 1):
        a = a0 + sweep * j / steps
        wob = 1.0 + 0.04 * math.sin(3 * a + 0.4) + 0.05 * (a - a0) / (2 * math.pi)
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
    pts = tuple(pts)
    kit.paint(layer, kit._bbox(pts, width), lambda d, at, k: kit._lines(d, at, k, pts, colour, width),
              ("ring", p, tuple(colour), width))


def arrow_on(layer: Image.Image, pts: Sequence[Tuple[float, float]], p: float, colour, width: float = 8) -> None:
    """A curved arrow drawn on along `pts`, p of the way; its head appears at the end."""
    if p <= 0:
        return
    p = round(clamp01(p) * 48) / 48
    path = kit._partial(list(pts), p)
    head = ()
    if p >= 1.0:
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        ang = math.atan2(by - ay, bx - ax)
        head = tuple((bx - 34 * math.cos(ang + s), by - 34 * math.sin(ang + s)) for s in (0.5, -0.5))

    def painter(d, at, k):
        kit._lines(d, at, k, path, colour, width)
        for h in head:
            kit._lines(d, at, k, ((pts[-1][0], pts[-1][1]), h), colour, width)
    kit.paint(layer, kit._bbox(tuple(pts) + head, width + 2), painter, ("arrow_on", p, tuple(pts), tuple(colour)))


def ease(p: float) -> float:
    return ease_out_cubic(clamp01(p))

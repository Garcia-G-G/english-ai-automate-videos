"""The Tablero kit (STEP 82 §1): background, header, tiles, counter, Bubi, outro card.

Measures and colours come from _audit/design/tablero/tablero_mock.py; where this file and the
mock disagree the mock wins. Cards are painted at SS x and brought down once (anti-aliased,
like the notebook kit); text is drawn at 1x by FreeType.
"""
from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..notebook import kit as nb

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config.yaml"
PRON_PATH = ROOT / "assets" / "pron" / "es_figurada.json"
EXPRESSIONS = ROOT / "assets" / "branding" / "english-unlimited"
MANROPE = ROOT / "assets" / "fonts" / "Manrope[wght].ttf"

W, H = 1080, 1920
SS = 4
INK = (28, 24, 18, 255)
PAPER = (254, 253, 251, 255)
YEL = (242, 214, 107, 255)
BLUE = (27, 111, 168, 255)
CORAL = (255, 143, 122, 255)
WHITE = (255, 255, 255, 255)

# Grid (mock): 2 columns x 5 rows of 474x186 tiles.
TILE_W, TILE_H = 474, 186
GRID_X0, GRID_Y0, GRID_GAP, GRID_PITCH = 36, 430, 30, 212
TILE_LIMIT_Y = 1475          # no tile below this (the platforms' caption zone)
TILE_TOP_LIMIT = 150
TEXT_X = 168                 # the Spanish/English column inside a tile
TEXT_PAD_R = 24
ACTIVE_SCALE, ACTIVE_ROT = 1.07, -1.5
PRON_MAX = 14
FONT_MIN, FONT_MAX = 36, 56

#: Fallback when config.yaml has no tablero block (a test sandbox): the mock's coral family.
_DEFAULT_FAMILIES = {"casa": ["#FF7A59", "#D63E5C"]}

#: Topic words -> family. First match wins; anything else is «vida real».
FAMILY_WORDS = (
    ("casa", ("casa", "cocina", "muebles", "electrodom", "baño", "hogar", "mesa")),
    ("comida", ("comida", "bebida", "fruta", "carne", "lácteo", "verdura", "postre", "desayuno")),
    ("cuerpo", ("cuerpo", "cabeza", "médico", "mano")),
    ("animales", ("animal", "mascota", "ave", "insecto", "granja", "mar", "naturaleza")),
    ("ropa", ("ropa", "zapato", "color", "forma")),
    ("ciudad", ("ciudad", "tienda", "carro", "país", "oficina", "tecnolog", "trabajo", "escolar", "materia")),
    ("emociones", ("emoci", "sentimiento", "personalidad", "adjetivo", "opuesto", "familia")),
    ("clima", ("clima", "tiempo", "estaci", "navidad", "halloween")),
)


def families() -> Dict[str, Tuple[str, str]]:
    from yaml_cache import load_yaml
    try:
        raw = (load_yaml(CONFIG).get("tablero") or {}).get("families") or _DEFAULT_FAMILIES
    except OSError:
        raw = _DEFAULT_FAMILIES
    return {k: (v[0], v[1]) for k, v in raw.items()}


def family_for(theme: str) -> str:
    low = (theme or "").lower()
    for name, words in FAMILY_WORDS:
        if any(w in low for w in words):
            return name
    return "vida real"


def _rgb(hexv: str) -> Tuple[int, int, int]:
    return nb.hex_colour(hexv)[:3]


def luminance(rgb) -> float:
    c = [v / 255 for v in rgb[:3]]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast_with_white(hexv: str) -> float:
    return 1.05 / (luminance(_rgb(hexv)) + 0.05)


# ── fonts ────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def fredoka(px: int) -> ImageFont.FreeTypeFont:
    return nb.fredoka(int(px), "display")


@lru_cache(maxsize=16)
def manrope(px: int, wght: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(MANROPE), int(px))
    f.set_variation_by_axes([wght])
    return f


def fit_font(text: str, width: float, size: int = FONT_MAX, minimum: int = FONT_MIN) -> Tuple[int, float]:
    """The largest Fredoka size (even steps) at which `text` fits `width`, and its width.
    At the minimum it is returned even if too wide: callers (and the tests) check the fit."""
    while size > minimum and fredoka(size).getlength(text) > width:
        size -= 2
    return size, fredoka(size).getlength(text)


SPANISH_W = TILE_W - TEXT_PAD_R - TEXT_X - 34          # the index number sits top right
SPANISH_MIN = 30


def spanish_lines(text: str) -> Tuple[int, Tuple[str, ...]]:
    """The Spanish word as one line (52 down to 36 px) or, failing that, two lines of 34 px
    split at the most even space; a single long word shrinks to SPANISH_MIN."""
    size, w = fit_font(text, SPANISH_W, 52)
    if w <= SPANISH_W:
        return size, (text,)
    words = text.split()
    if len(words) > 1:
        cuts = [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
        best = min(cuts, key=lambda c: max(fredoka(34).getlength(c[0]), fredoka(34).getlength(c[1])))
        if max(fredoka(34).getlength(x) for x in best) <= SPANISH_W:
            return 34, best
    size, _ = fit_font(text, SPANISH_W, 36, SPANISH_MIN)
    return size, (text,)


# ── background ───────────────────────────────────────────────────────

@lru_cache(maxsize=12)
def _gradient(family: str) -> Image.Image:
    top, bot = (np.array(_rgb(h), float) for h in families()[family])
    t = np.linspace(0, 1, H)[:, None, None]
    col = top * (1 - t) + bot * t
    arr = np.broadcast_to(col, (H, W, 3)).astype(np.uint8)
    base = Image.fromarray(arr).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    rng = random.Random(3)
    for _ in range(26):                                   # soft circles, 5 %
        x, y, r = rng.randint(0, W), rng.randint(0, H), rng.randint(40, 140)
        o.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 13))
    base.alpha_composite(ov)
    return base


DOT_PITCH = 54


@lru_cache(maxsize=1)
def _dots() -> Image.Image:
    """The dot grid, one pitch larger each way so a drift offset is just a crop."""
    im = Image.new("RGBA", (W + DOT_PITCH, H + DOT_PITCH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for gx in range(0, W + DOT_PITCH, DOT_PITCH):
        for gy in range(0, H + DOT_PITCH, DOT_PITCH):
            d.ellipse((gx - 2, gy - 2, gx + 2, gy + 2), fill=(255, 255, 255, 26))   # 10 %
    return im


def background(family: str, t: float = 0.0) -> Image.Image:
    """The family gradient with the dot grid drifting slowly (idle motion: 6 px/s)."""
    off = int(t * 6) % DOT_PITCH
    frame = _gradient(family).copy()
    frame.alpha_composite(_dots().crop((off, off, off + W, off + H)))
    return frame


# ── cards ────────────────────────────────────────────────────────────

CARD_PAD = 40


@lru_cache(maxsize=64)
def card(w: int, h: int, fill: Tuple[int, int, int, int], shadow: int = 10, outline: int = 6,
         r: int = 34) -> Image.Image:
    """A paper card: ink outline, hard offset ink shadow, anti-aliased. CARD_PAD of margin."""
    k = SS
    big = Image.new("RGBA", ((w + 2 * CARD_PAD) * k, (h + 2 * CARD_PAD) * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    p = CARD_PAD * k
    if shadow:
        d.rounded_rectangle((p + shadow * k, p + shadow * k, p + (w + shadow) * k, p + (h + shadow) * k),
                            r * k, fill=INK)
    d.rounded_rectangle((p, p, p + w * k, p + h * k), r * k, fill=fill, outline=INK, width=outline * k)
    return big.resize((w + 2 * CARD_PAD, h + 2 * CARD_PAD), Image.LANCZOS)


def _rotated(im: Image.Image, deg: float) -> Image.Image:
    return im.rotate(deg, expand=True, resample=Image.BICUBIC)


@lru_cache(maxsize=64)
def header(theme_emoji: str, topic: str, title: str = "¿CÓMO SE DICE?") -> Image.Image:
    """«¿CÓMO SE DICE?» on its highlighter bar + the topic chip, as one full-width layer."""
    layer = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = fredoka(92)
    tw = d.textlength(title, font=f)
    x, y = (W - tw) / 2, 150
    bar = Image.new("RGBA", (int(tw + 60), 70), (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle((0, 0, tw + 60, 70), 22, fill=YEL)
    layer.alpha_composite(_rotated(bar, -1.5), (int(x - 30), int(y + 38)))
    d.text((x, y), title, font=f, fill=INK)
    text = topic.upper()
    size = 64
    while size > 36 and fredoka(size).getlength(text) > W - 120 - 156:       # a long topic shrinks, never clips
        size -= 2
    cf = fredoka(size)
    cw = int(min(W - 120, 120 + cf.getlength(text) + 36))
    chip = card(cw, 100, PAPER, shadow=8, outline=6, r=50).copy()
    em = nb.emoji(theme_emoji, 70)
    chip.alpha_composite(em, (CARD_PAD + 34, CARD_PAD + 50 - em.height // 2))
    ImageDraw.Draw(chip).text((CARD_PAD + 120, CARD_PAD + 50), text, font=cf, fill=INK, anchor="lm")
    chip = _rotated(chip, 2)
    layer.alpha_composite(chip, ((W - chip.width) // 2, 262))
    return layer


# ── tiles ────────────────────────────────────────────────────────────

def tile_origin(i: int) -> Tuple[int, int]:
    col, row = i % 2, i // 2
    return GRID_X0 + col * (TILE_W + GRID_GAP), GRID_Y0 + row * GRID_PITCH


def tile_bottom(i: int) -> int:
    return tile_origin(i)[1] + TILE_H


@lru_cache(maxsize=32)
def _blank_dashes(en: str, avail: float) -> Tuple[float, float]:
    step = min(40.0, avail / max(1, len(en)))
    return step, step * 0.75


@lru_cache(maxsize=1024)
def tile(index: int, emoji: str, spanish: str, english: str, pron: Optional[str], state: str,
         filled: int = 0, timer: float = 0.0) -> Image.Image:
    """One tile with CARD_PAD of margin. state: blank | active | done.
    `filled` letters of the English are written over the dashes (active); `timer` 0..1 is
    the share of the thinking pause already used (the coral bar shrinks)."""
    w, h = TILE_W, TILE_H
    fill = {"blank": PAPER, "active": YEL, "done": BLUE}[state]
    im = card(w, h, fill, shadow=10 if state != "active" else 14).copy()
    pad = CARD_PAD
    d = ImageDraw.Draw(im)
    disc = Image.new("RGBA", (124 * 2, 124 * 2), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse((0, 0, 247, 247), fill=(255, 255, 255, 235 if state == "done" else 255),
                                 outline=INK, width=10)
    im.alpha_composite(disc.resize((124, 124), Image.LANCZOS), (pad + 22, pad + 31))
    em = nb.emoji(emoji, 78)
    im.alpha_composite(em, (pad + 22 + 62 - em.width // 2, pad + 31 + 62 - em.height // 2))
    tx, right = pad + TEXT_X, pad + w - TEXT_PAD_R
    avail = right - tx
    ink = PAPER if state == "done" else INK
    sp_size, sp_lines = spanish_lines(spanish)
    for n, line in enumerate(sp_lines):
        d.text((tx, pad + (56 if len(sp_lines) == 1 else 40 + 34 * n)), line, font=fredoka(sp_size),
               fill=ink, anchor="lm")
    d.text((right, pad + 30), str(index + 1), font=fredoka(30), anchor="rm",
           fill=(255, 255, 255, 170) if state == "done" else (28, 24, 18, 120))
    if state == "done":
        ps = 28
        tag = f"«{pron}»" if pron else ""
        en_size = FONT_MAX
        while True:
            en_size, en_w = fit_font(english, avail, en_size)
            if not tag:
                break
            pw = manrope(ps).getlength(tag)
            if en_w + 12 + pw <= avail:
                break
            if en_size <= FONT_MIN and ps <= 22:
                tag = ""                            # no room even at the minimums: English only
                en_size, _ = fit_font(english, avail)
                break
            if en_size > FONT_MIN:
                en_size -= 2
            ps = max(22, ps - 1)
        d.text((tx, pad + 122), english, font=fredoka(en_size), fill=YEL, anchor="lm")
        if tag:
            d.text((tx + fredoka(en_size).getlength(english) + 12, pad + 126), tag, font=manrope(ps),
                   fill=(255, 255, 255, 217), anchor="lm")
    else:
        step, dash = _blank_dashes(english, right - 6 - tx)
        x, y = tx, pad + 138
        letter_i = 0
        for k, ch in enumerate(english):
            if ch == " ":
                x += step * 0.5
                continue
            if k == 0 or letter_i < filled:
                d.text((x, y - 12), ch.upper() if k == 0 else ch, font=fredoka(44), fill=BLUE, anchor="lm")
            d.rounded_rectangle((x, y + 14, x + dash, y + 20), 3,
                                fill=INK if state == "active" else (28, 24, 18, 150))
            x += step
            letter_i += 1
        if state == "active" and timer > 0:
            d.rounded_rectangle((pad + 40, pad + h - 16, pad + 40 + (w - 80) * (1 - timer), pad + h - 9), 4,
                                fill=CORAL)
    return im


def tile_english_extent(english: str, pron: Optional[str], state: str = "done") -> Tuple[float, float]:
    """(English width, whole line width) the done state draws at its final size: for the tests."""
    avail = TILE_W - TEXT_PAD_R - TEXT_X
    size, w = fit_font(english, avail)
    tag = manrope(22).getlength(f"«{pron}»") + 12 if pron else 0
    return w, w + tag


@lru_cache(maxsize=64)
def _glow(size: Tuple[int, int]) -> Image.Image:
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(g).rounded_rectangle((CARD_PAD, CARD_PAD, size[0] - CARD_PAD, size[1] - CARD_PAD),
                                        40, fill=(255, 240, 170, 120))
    return g.filter(ImageFilter.GaussianBlur(24))


def place_tile(frame: Image.Image, im: Image.Image, i: int, scale: float = 1.0, rot: float = 0.0,
               glow: bool = False, flip: float = 1.0) -> None:
    """Composite a tile at its grid slot. `scale`/`rot` animate the active state; `flip` is the
    scaleX of the done-flip (1 = whole, ~0 = edge-on)."""
    x, y = tile_origin(i)
    if scale != 1.0 or rot:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im = _rotated(im, rot)
    cx, cy = x + TILE_W / 2, y + TILE_H / 2
    if glow:                                            # sized before the flip squeezes the tile
        g = _glow(im.size)
        if flip < 1.0:
            g = g.resize((max(2, round(g.width * flip)), g.height), Image.LANCZOS)
        frame.alpha_composite(g, (round(cx - g.width / 2), round(cy - g.height / 2)))
    if flip < 1.0:
        im = im.resize((max(2, round(im.width * flip)), im.height), Image.LANCZOS)
    ox, oy = round(cx - im.width / 2), round(cy - im.height / 2)
    frame.alpha_composite(im, (ox, oy))


# ── phrase tiles (§6: phrases_level, one column) ─────────────────────

PHRASE_X, PHRASE_Y0, PHRASE_W, PHRASE_GAP, PHRASE_BOTTOM = 60, 424, 960, 10, 1470
PHRASE_COL1_X, PHRASE_COL2_X, PHRASE_COL_PAD = 100, 520, 30
PHRASE_COL1_W, PHRASE_COL2_W = 390, 410
PHRASE_SIZE_MAX, PHRASE_SIZE_MIN = 34, 26


def phrase_height(n: int) -> int:
    return min(132, (PHRASE_BOTTOM - PHRASE_Y0 - (n - 1) * PHRASE_GAP) // n)


def phrase_origin(i: int, n: int) -> Tuple[int, int]:
    return PHRASE_X, PHRASE_Y0 + i * (phrase_height(n) + PHRASE_GAP)


def phrase_lines(text: str, width: int) -> Tuple[int, Tuple[str, ...]]:
    """`text` on at most two lines at the largest size (34 down to 26) that fits `width`; a
    phrase that still does not fit is returned at the minimum on two lines for the tests to see."""
    words = text.split()
    for size in range(PHRASE_SIZE_MAX, PHRASE_SIZE_MIN - 1, -2):
        f = fredoka(size)
        if f.getlength(text) <= width:
            return size, (text,)
        cuts = [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
        best = min(cuts, key=lambda c: max(f.getlength(c[0]), f.getlength(c[1])), default=None)
        if best and max(f.getlength(x) for x in best) <= width:
            return size, best
    return PHRASE_SIZE_MIN, best if best else (text,)


@lru_cache(maxsize=512)
def phrase_tile(index: int, n: int, spanish: str, english: str, state: str, timer: float = 0.0) -> Image.Image:
    """One phrase tile (blank | active | done) with CARD_PAD of margin."""
    h = phrase_height(n)
    fill = {"blank": PAPER, "active": YEL, "done": BLUE}[state]
    im = card(PHRASE_W, h, fill, shadow=8 if state != "active" else 12, outline=5, r=28).copy()
    d, pad = ImageDraw.Draw(im), CARD_PAD
    cy = pad + h / 2
    badge = h - 36
    d.ellipse((pad + 20, cy - badge / 2, pad + 20 + badge, cy + badge / 2),
              fill=(255, 255, 255, 235) if state == "done" else (28, 24, 18, 255))
    d.text((pad + 20 + badge / 2, cy), str(index + 1), font=fredoka(30), anchor="mm",
           fill=INK if state == "done" else YEL)
    ink = (255, 255, 255, 217) if state == "done" else INK

    def block(text, x, width, colour):
        size, lines = phrase_lines(text, width)
        for k, line in enumerate(lines):
            y = cy + (k - (len(lines) - 1) / 2) * size * 1.12
            d.text((pad + x, y), line, font=fredoka(size), fill=colour, anchor="lm")

    block(spanish, PHRASE_COL1_X, PHRASE_COL1_W, ink)
    if state == "done":
        block(english, PHRASE_COL2_X, PHRASE_COL2_W, YEL)
    else:
        d.rounded_rectangle((pad + PHRASE_COL2_X, cy - 7, pad + PHRASE_COL2_X + 300, cy + 7), 7,
                            fill=(28, 24, 18, 90 if state == "blank" else 160))
        if state == "active" and timer > 0:
            d.rounded_rectangle((pad + 40, pad + h - 13, pad + 40 + (PHRASE_W - 80) * (1 - timer), pad + h - 7), 3,
                                fill=CORAL)
    return im


def place_phrase(frame: Image.Image, im: Image.Image, i: int, n: int, scale: float = 1.0, rot: float = 0.0,
                 glow: bool = False, flip: float = 1.0) -> None:
    x, y = phrase_origin(i, n)
    cx, cy = x + PHRASE_W / 2, y + phrase_height(n) / 2
    if scale != 1.0 or rot:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im = _rotated(im, rot)
    if flip < 1.0:
        im = im.resize((max(2, round(im.width * flip)), im.height), Image.LANCZOS)
    frame.alpha_composite(im, (round(cx - im.width / 2), round(cy - im.height / 2)))


# ── counter, Bubi, outro ─────────────────────────────────────

@lru_cache(maxsize=64)
def counter(n: int, total: int = 10, scale: float = 1.0) -> Image.Image:
    im = card(190, 86, INK, shadow=0, outline=0, r=43).copy()
    ImageDraw.Draw(im).text((im.width // 2, im.height // 2), f"{n}/{total}", font=fredoka(54), fill=YEL,
                            anchor="mm")
    if scale != 1.0:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    return im


EXPRESSION_FILES = {"simbolo": "simbolo_512.png", "wow": "expresiones/wow.png",
                    "bien_hecho": "expresiones/bien_hecho.png", "lo_lograste": "expresiones/lo_lograste.png"}


@lru_cache(maxsize=32)
def bubi(expr: str, size: int) -> Image.Image:
    b = Image.open(EXPRESSIONS / EXPRESSION_FILES[expr]).convert("RGBA")
    s = size / max(b.size)
    return b.resize((max(1, round(b.width * s)), max(1, round(b.height * s))), Image.LANCZOS)


def bubi_size(expr: str) -> int:
    return 330 if expr == "simbolo" else 280


BUBI_POS = {"simbolo": (740, 1470)}


def place_bubi(frame: Image.Image, expr: str, t: float = 0.0) -> None:
    """Bottom right; he breathes (a 2 % swell, 0.5 Hz) so frame 0 is never frozen."""
    breath = 1.0 + 0.02 * math.sin(t * math.pi)
    size = round(bubi_size(expr) * round(breath, 3))
    im = bubi(expr, size)
    x, y = BUBI_POS.get(expr, (770, 1470))
    frame.alpha_composite(im, (x, y))


@lru_cache(maxsize=16)
def speech(text: str, rot: float = -4.0) -> Image.Image:
    f = fredoka(46)
    tw = f.getlength(text)
    im = card(int(tw + 60), 96, PAPER, shadow=8, outline=6, r=30).copy()
    ImageDraw.Draw(im).text((CARD_PAD + 30, CARD_PAD + 48), text, font=f, fill=INK, anchor="lm")
    return _rotated(im, rot)


FOOTER = "learningroutes.com"


def draw_footer(frame: Image.Image) -> None:
    ImageDraw.Draw(frame).text((W // 2, 1860), FOOTER, font=fredoka(30), fill=(255, 255, 255, 200), anchor="mm")


OUTRO_DIM = 120                       # ink at alpha 120 / 255 = 47 %
OUTRO_Q = "¿Cuántas sabías?"
OUTRO_LINE = "Escríbelo en comentarios"
PILL_SEQUEL = "PARTE 2 MAÑANA · SUSCRÍBETE"
PILL_FOLLOW = "SÍGUENOS PARA MÁS"


@lru_cache(maxsize=4)
def outro_card(sequel: bool) -> Image.Image:
    im = card(820, 420, PAPER, shadow=14, outline=7, r=48).copy()
    d = ImageDraw.Draw(im)
    p, cx = CARD_PAD, CARD_PAD + 410
    d.text((cx, p + 90), OUTRO_Q, font=fredoka(64), fill=INK, anchor="mm")
    f = fredoka(42)
    tw = d.textlength(OUTRO_LINE, font=f)
    d.text((cx - 30, p + 200), OUTRO_LINE, font=f, fill=INK, anchor="mm")
    em = nb.emoji("👇", 48)
    im.alpha_composite(em, (int(cx - 30 + tw / 2 + 10), p + 176))
    d.rounded_rectangle((p + 120, p + 270, p + 700, p + 360), 45, fill=BLUE)
    d.text((cx, p + 316), PILL_SEQUEL if sequel else PILL_FOLLOW, font=fredoka(36), fill=PAPER, anchor="mm")
    return _rotated(im, -2)


def draw_outro(frame: Image.Image, amount: float, sequel: bool) -> None:
    """The dim (to 47 %) and the card, `amount` 0..1 in. Bubi is drawn by the caller on top."""
    if amount <= 0:
        return
    frame.alpha_composite(Image.new("RGBA", (W, H), (28, 24, 18, round(OUTRO_DIM * amount))))
    c = outro_card(sequel)
    s = 0.92 + 0.08 * amount
    if s != 1.0:
        c = c.resize((round(c.width * s), round(c.height * s)), Image.LANCZOS)
    frame.alpha_composite(c, ((W - c.width) // 2, 560))


# ── figured pronunciation (§3 reads it; §1 only displays what it is given) ──

def valid_pron(p: str) -> bool:
    import re
    return bool(p) and len(p) <= PRON_MAX and re.fullmatch(r"[a-záéíóúüñ-]+", p) is not None


@lru_cache(maxsize=1)
def pron_dictionary() -> Dict[str, dict]:
    try:
        return json.loads(PRON_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pron_for(item: dict) -> Optional[str]:
    """The item's own `pron`, else the dictionary's entry; None when neither is valid."""
    p = item.get("pron")
    if not p:
        entry = pron_dictionary().get(str(item.get("english", "")).lower())
        p = entry.get("pron") if isinstance(entry, dict) else entry
    return p if p and valid_pron(p) else None

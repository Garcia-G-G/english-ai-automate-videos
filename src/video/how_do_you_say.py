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
from typing import NamedTuple, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .constants import VIDEO_WIDTH, VIDEO_HEIGHT
from .motion import clamp01, ease_in_out, ease_out_back, ease_out_cubic, ease_out_expo
from .notebook import kit
from .utils import create_base_frame, finalize_frame

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

# Everything this module draws comes from the notebook kit (STEP 77 §1); these names stay
# because length_spec, outro and the tests read them from here.
brand, fredoka, _hex = kit.brand, kit.fredoka, kit.hex_colour
_color, _on_paper = kit.colour, kit.on_paper
PAPER = kit.PAPER
INK = kit.hex_colour("#1C1812")
emoji_image = kit.emoji


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
TITLE_Y = 94                    # 60 px below STEP 76: clear of TikTok's top tabs (STEP 77 §4)
THEME_SIZE = 42
THEME_Y = 206

ROWS_TOP = 282
ROWS_BOTTOM = PAGE_H - 70                      # the brand footer below
ROW_PITCH = 98                                 # ten rows fill ROWS_TOP..BOTTOM

EMOJI_SIZE = 76
EMOJI_X = 66

#: The two word columns. Their widths are what length_spec measures a word
#: against, at WORD_FONT_MAX shrinking to WORD_FONT_MIN.
SPANISH_X = 150
SPANISH_W = 296
ENGLISH_X = 454
ENGLISH_W = 298                                # its tick ends by CONTENT_R
WORD_FONT_MAX = 58
WORD_FONT_MIN = 42

TICK_GAP = 24             # ≥ 14 px of paper between a word's ink and the tick's (STEP 77 §3)
TICK_SIZE = 34
#: STEP 77 §4, safe areas: nothing the viewer reads lies right of page-local x CONTENT_R, which
#: the 1° tilt puts at frame x ≤ 938 at the page's foot (the button rail starts at 940).
CONTENT_R = 816

# ── Motion constants (seconds) ───────────────────────────────────────
HIGHLIGHT_FADE = 0.25
HIGHLIGHT_SWEEP = 0.25           # the marker swipes left to right (ease_out_expo)
EMOJI_POP = 0.30
EMOJI_POP_FROM = 0.6
EMOJI_OVERSHOOT = 4.0            # ease_out_back from 0.6 peaks at 1.15
PENCIL_MOVE = 0.35
TICK_POP = 0.25
PULSE_HALF = 0.20
PULSE_SCALE = 0.08

# ── Motion (STEP 77 §3) ──
RISE = 0.5                       # the page rises from RISE_FROM px below (ease_out_back)
RISE_FROM = 120
CASCADE_START, CASCADE_STAGGER, CASCADE_DUR, CASCADE_DY = 0.2, 0.05, 0.3, 24
HOOK_IN, HOOK_POP, HOOK_OUT = 0.45, 0.3, 0.2
HOOK_ROT = -4.0
HOOK_SIZE = 68                   # Fredoka 64–72
HOOK_W = 700
FEATHER = 12                     # px: the soft edge of a word being written, at the pencil tip
WOBBLE = 2.0                     # px, the pencil while it writes
LIFT = 22                        # px, the pencil between rows
PUSH_TO = 1.04                   # the slow push over the recap
HANDOFF = 0.3                    # the page slides away into the outro
CTA_LINES = ("¿Cuántas sabías?", "__/10")
CTA_SIZE = 58
CTA_POP = 0.35


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


def _draw_rings(layer: Image.Image, top: int, bottom: int) -> None:
    """Spiral binding (kit.rings), page-local top..bottom."""
    kit.rings(layer, *_p(RING_X, top), _p(0, bottom)[1], RINGS)


@lru_cache(maxsize=4)
def _static_page(items_key: Tuple[Tuple[str, str], ...], theme: str) -> Image.Image:
    """Paper, binding, title, theme, ruled lines. Nothing that changes."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    _draw_paper(layer)

    # ruled lines, one under each row, in the brand's sky blue
    sky = _on_paper(_color("sky"), 0.6)
    for cy in row_centres(len(items_key)):
        ly = cy + ROW_PITCH // 2 - 6
        kit.rule(layer, _p(60, 0)[0], _p(PAGE_W - 30, 0)[0], _p(0, ly)[1], 3, sky)

    _draw_title(layer, TITLE_TEXT, theme, fredoka(TITLE_SIZE), _color("english_blue"))
    _draw_rings(layer, 40, PAGE_H - 40)
    _draw_footer(layer)
    return layer


FOOTER_SIZE = 36
FOOTER_CY = PAGE_H - 38


def _draw_footer(layer: Image.Image) -> None:
    """The brand on the page (STEP 77 §4): Bubi mini + «learningroutes.com», centred at its foot,
    inside the safe area; it replaces the frame's watermark and progress bar."""
    foot = kit.footer(FOOTER_SIZE)
    cx = (64 + PAGE_W) / 2
    layer.alpha_composite(foot, tuple(int(round(v)) for v in _p(cx - foot.width / 2, FOOTER_CY - foot.height / 2)))


def _draw_paper(layer: Image.Image) -> None:
    """Hard sticker shadow, then the outlined page (kit.page)."""
    kit.page(layer, *_p(0, 0), PAGE_W, PAGE_H, PAGE_RADIUS, PAGE_OUTLINE, SHADOW)


def _draw_title(layer: Image.Image, title: str, theme: str,
                tf: ImageFont.FreeTypeFont, color) -> None:
    """Title centred right of the binding over a yellow marker stroke, theme under it.
    English is blue (brand rule); a Spanish title is ink."""
    draw = ImageDraw.Draw(layer, "RGBA")
    ink = _color("ink")
    tw = tf.getlength(title)
    cx = (64 + PAGE_W) / 2
    tx = cx - tw / 2
    # hand-drawn underline: a brand-yellow marker stroke that wobbles once
    uy = TITLE_Y + 92
    pts = [_p(tx - 8 + u * (tw + 16), uy + 5 * math.sin(u * math.pi * 1.5) - 3 * u)
           for u in (k / 40 for k in range(41))]
    kit.marker_stroke(layer, pts, 18, _color("brand_yellow"))
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


# ── Page memo (STEP 77 §2) ───────────────────────────────────────────
#
# Rotating the whole page layer was ~105 ms of every frame. A frame's page is now first
# DESCRIBED: every composite onto it is recorded instead of drawn (all drawing reaches the page
# through alpha_composite, the kit's included). The record — each image's content and where
# it lands — is the page's state. A state seen in the last few frames reuses its rotated page;
# a new one is drawn and rotated once. The pencil is not part of the page: it moves every
# frame, so it is drawn after the rotation, at its tip's rotated position (STEP 77 §2).

import hashlib
from collections import OrderedDict


class _PageRecorder:
    """Stands in for the page layer while a frame is described."""

    size = None

    def __init__(self, base: Image.Image):
        self.size = base.size
        self.ops = [(base, (0, 0))]

    def alpha_composite(self, im: Image.Image, dest=(0, 0), source=(0, 0)) -> None:
        if tuple(source) != (0, 0):
            im = im.crop((*source, *im.size))
        self.ops.append((im, (int(dest[0]), int(dest[1]))))


#: id(image) -> (image, digest) for the big, cached layers; holding the image keeps its id unique.
_DIGESTS: Dict[int, Tuple[Image.Image, bytes]] = {}


def _digest(im: Image.Image) -> bytes:
    if im.size[0] * im.size[1] < 400_000:
        return hashlib.blake2b(im.tobytes(), digest_size=12).digest() + bytes(str(im.size), "ascii")
    hit = _DIGESTS.get(id(im))
    if hit is None or hit[0] is not im:
        if len(_DIGESTS) > 64:
            _DIGESTS.clear()
        hit = _DIGESTS[id(im)] = (im, hashlib.blake2b(im.tobytes(), digest_size=12).digest())
    return hit[1]


_PAGES: "OrderedDict[tuple, Image.Image]" = OrderedDict()
_PAGES_MAX = 12
PAGE_STATS = {"drawn": 0, "reused": 0}


def _page(rec: _PageRecorder, scale: float = 1.0) -> Image.Image:
    """The rotated page for this frame's record: reused when the state was seen recently."""
    key = (scale,) + tuple((_digest(im), dest) for im, dest in rec.ops)
    page = _PAGES.get(key)
    if page is not None:
        _PAGES.move_to_end(key)
        PAGE_STATS["reused"] += 1
        return page
    layer = rec.ops[0][0].copy()
    for im, dest in rec.ops[1:]:
        layer.alpha_composite(im, dest)
    page = _PAGES[key] = _rotate(layer, scale)
    PAGE_STATS["drawn"] += 1
    if len(_PAGES) > _PAGES_MAX:
        _PAGES.popitem(last=False)
    return page


def _rotate(layer: Image.Image, scale: float = 1.0) -> Image.Image:
    """The page tilted by TILT_DEG about its centre: cv2's bicubic warp, 10× PIL's rotate
    (16 ms against 160) and within a mean 0.27 of it (the largest differences sit in pixels at
    alpha 1-2)."""
    import cv2
    m = cv2.getRotationMatrix2D((layer.width / 2 - 0.5, layer.height / 2 - 0.5), TILT_DEG, scale)
    out = cv2.warpAffine(np.asarray(layer), m, layer.size, flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(out)                          # 4 channels: RGBA


Motion = Tuple[float, float]
STILL: Motion = (0.0, 1.0)


def page_to_frame(x: float, y: float, motion: Motion = STILL) -> Tuple[float, float]:
    """A page-local point after the page's tilt and scale (about the layer's centre,
    counter-clockwise) and its vertical move (page_motion), in frame pixels."""
    dy, s = motion
    lx, ly = _p(x, y)
    cx, cy = LAYER_W / 2, LAYER_H / 2
    a = math.radians(TILT_DEG)
    rx = cx + s * ((lx - cx) * math.cos(a) + (ly - cy) * math.sin(a))
    ry = cy + s * (-(lx - cx) * math.sin(a) + (ly - cy) * math.cos(a))
    return rx + PAGE_X - PAD, ry + PAGE_Y - PAD + dy


def _composite_page(frame: Image.Image, rec: _PageRecorder, motion: Motion) -> None:
    """The page onto the frame, moved by `motion` (clipped: it rises from below and leaves
    through the top)."""
    dy, s = motion
    kit._composite_clipped(frame, _page(rec, s), PAGE_X - PAD, PAGE_Y - PAD + int(dy))


PENCIL_SHADOW = (6, 9)                   # offset of its soft shadow (STEP 77 §4)


@lru_cache(maxsize=32)
def _pencil_cropped(angle: int = None) -> Tuple[Image.Image, Tuple[int, int]]:
    """The pencil at `angle` with a soft ink shadow under it, cropped, and its tip in it."""
    from PIL import ImageFilter as _F
    img, (cx, cy) = kit.pencil(kit.PENCIL_ANGLE if angle is None else angle)
    shadow = Image.new("RGBA", img.size, _color("ink"))
    shadow.putalpha(img.getchannel("A").point(lambda v: v * 0.28).filter(_F.GaussianBlur(4)))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, PENCIL_SHADOW)
    out.alpha_composite(img)
    box = out.getbbox()
    return out.crop(box), (cx - box[0], cy - box[1])


def _place_pencil(frame: Image.Image, px: float, py: float, motion: Motion = STILL,
                  angle: float = None) -> None:
    """The pencil, unrotated (1° is invisible on it), its tip on the page point (px, py) after
    the tilt, placed with a sub-pixel affine shift so a slow move does not step."""
    sprite, (tx, ty) = _pencil_cropped(None if angle is None else int(round(angle / 6) * 6))
    fx, fy = page_to_frame(px, py, motion)
    x, y = fx - tx, fy - ty
    ix, iy = math.floor(x), math.floor(y)
    dx, dy = x - ix, y - iy
    if dx or dy:
        sprite = sprite.transform((sprite.width + 1, sprite.height + 1), Image.AFFINE,
                                  (1, 0, -dx, 0, 1, -dy), resample=Image.BILINEAR)
    kit._composite_clipped(frame, sprite, ix, iy)          # clipped to the frame, never to the page


# ── Motion (STEP 77 §3) ──────────────────────────────────────────────
#
# Every move here is a pure function of t, like the rest of the renderer.

def page_motion(t: float, enter: float, leave: float, push: Tuple[float, float]) -> Motion:
    """(dy, scale) of a page shown from `enter` to `leave`: it rises from RISE_FROM px below
    with an overshoot, pushes in 1.00 → PUSH_TO over `push` and holds, and slides up out of the
    frame in the HANDOFF seconds before `leave` (the next page, or the video's end and its
    outro). dy is whole pixels; the scale moves in 0.2 % steps (page memo)."""
    dy = RISE_FROM * (1.0 - ease_out_back((t - enter) / RISE)) if t < enter + RISE else 0.0
    if t > leave - HANDOFF:
        q = clamp01((t - (leave - HANDOFF)) / HANDOFF)
        dy -= (PAGE_Y + LAYER_H) * q ** 3
    s = 1.0
    if t >= push[0]:
        s = 1.0 + (PUSH_TO - 1.0) * ease_in_out((t - push[0]) / max(1.0, push[1] - push[0]))
        s = round(s * 500) / 500
    return float(round(dy)), s


def cascade(i: int, t: float) -> float:
    """0..1 of row i's entrance in the opening (50 ms apart)."""
    return clamp01((t - CASCADE_START - i * CASCADE_STAGGER) / CASCADE_DUR)


def _bands(centres: List[float]) -> List[Tuple[float, float]]:
    """(top, bottom) of rows at ROW_PITCH about their centres."""
    return [(cy - ROW_PITCH / 2, cy + ROW_PITCH / 2) for cy in centres]


def _rows_in(layer, img: Image.Image, rows, t: float) -> None:
    """A static layer of row text, whole — or, as its page comes in, row by row, each band
    (anything with .top/.bottom, or a (top, bottom) pair) fading and rising CASCADE_DY px."""
    bands = [(r.top, r.bottom) if hasattr(r, "top") else r for r in rows]
    n = len(bands)
    if cascade(n - 1, t) >= 1.0:
        layer.alpha_composite(img)
        return
    for i, (top, bottom) in enumerate(bands):
        e = ease_out_cubic(cascade(i, t))
        if e <= 0:
            continue
        y0, y1 = int(_p(0, top)[1]), int(_p(0, bottom)[1])
        band = _faded(img.crop((0, y0, img.width, y1)), round(e * 16) / 16)
        layer.alpha_composite(band, (0, y0 + int(round(CASCADE_DY * (1.0 - e)))))


def _highlight(layer, x0: float, cy: float, t: float, start: float, end: float) -> None:
    """The row's marker: swipes in left to right from `start`, fades out after `end`."""
    _highlight_band(layer, x0, cy - ROW_PITCH // 2 + 6, cy + ROW_PITCH // 2 - 10, t, start, end)


def _highlight_band(layer, x0: float, top: float, bottom: float, t: float, start: float, end: float) -> None:
    if t < start or t >= end + HIGHLIGHT_FADE:
        return
    a = 0.7 * (1.0 - clamp01((t - end) / HIGHLIGHT_FADE) if t >= end else 1.0)
    x1 = PAGE_W - 22
    w = round((x1 - x0) * ease_out_expo((t - start) / HIGHLIGHT_SWEEP) / 4) * 4
    if w < 40 or a <= 0:
        return
    kit.highlighter(layer, (*_p(x0, top), *_p(x0 + w, bottom)), a, _color("brand_yellow"))


def _written(word: Image.Image, p: float) -> Optional[Image.Image]:
    """The first p of a word being written, its edge a FEATHER px ramp centred on the cut
    (where the pencil tip is)."""
    if p >= 1.0:
        return word
    w, h = word.size
    cut = int(round(w * p))
    end = min(w, cut + FEATHER // 2)
    if end <= 0:
        return None
    arr = np.array(word.crop((0, 0, end, h)))
    r0 = max(0, cut - FEATHER // 2)
    ramp = np.clip((cut + FEATHER / 2 - (np.arange(r0, end) + 0.5)) / FEATHER, 0.0, 1.0)
    arr[:, r0:end, 3] = (arr[:, r0:end, 3] * ramp).astype(np.uint8)
    return Image.fromarray(arr)


def wobble(t: float) -> Tuple[float, float]:
    """The pencil's hand while it writes: two slow sines, within ±WOBBLE px."""
    return WOBBLE * math.sin(2 * math.pi * 6.3 * t), WOBBLE * math.sin(2 * math.pi * 8.9 * t + 0.7)


def _glide(a: Tuple[float, float], b: Tuple[float, float], t: float, t0: float) -> Tuple[float, float]:
    """The pencil from a to b over PENCIL_MOVE, lifted LIFT px at the middle of the move."""
    p = ease_in_out((t - t0) / PENCIL_MOVE)
    lift = LIFT * math.sin(math.pi * p) if a != b else 0.0
    return a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p - lift


def hook_text(data: Dict) -> str:
    """The opening sticky note: the script's `hook`, else one built from the theme."""
    if data.get("hook"):
        return data["hook"]
    n = len(data["items"])
    if data.get("type", "how_do_you_say") == "how_do_you_say":
        theme = (data.get("theme") or "").strip()
        de = "del " + theme[3:] if theme.lower().startswith("el ") else "de " + theme
        return f"¿Sabes decir estas {n} palabras {de}?"
    return f"¿Cuántas aciertas de {n}?"


def hook_end(data: Dict, first_row: float) -> float:
    """The hook leaves when the intro ends (or the first row starts), not before 1.5 s."""
    intro = (data.get("segment_times") or {}).get("intro")
    end = float(intro["end"]) if intro else first_row
    return max(end, HOOK_IN + HOOK_POP + 0.75)


def hook_state(t: float, end: float) -> Tuple[float, float]:
    """(scale, alpha) of the hook note: it slaps on at HOOK_IN (from 1.4× with an overshoot)
    and leaves over HOOK_OUT from `end`."""
    if t < HOOK_IN or t >= end + HOOK_OUT:
        return 0.0, 0.0
    if t < end:
        p = (t - HOOK_IN) / HOOK_POP
        return round((1.0 + 0.4 * (1.0 - ease_out_back(p))) * 100) / 100, round(clamp01(p * 3) * 16) / 16
    q = (t - end) / HOOK_OUT
    return round((1.0 - 0.2 * q) * 100) / 100, round((1.0 - q) * 16) / 16


def _wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and f.getlength(trial) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


def _sticky(lines: Tuple[str, ...], size: int, angle: float, width: int = 0) -> Image.Image:
    """A yellow sticky note (kit.note_card, hard shadow) with centred lines, tilted."""
    f = fredoka(size)
    pad = 30
    lh = int(size * 1.18)
    w = width or int(max(f.getlength(x) for x in lines)) + 2 * pad
    h = lh * len(lines) + 2 * pad
    note = kit.note_card(w, h, _color("brand_yellow"), 4, SHADOW).copy()
    d = ImageDraw.Draw(note)
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    for k, line in enumerate(lines):
        cy = pad + lh * (k + 0.5)
        d.text(((w - f.getlength(line)) / 2, cy - (top + bottom) / 2), line, font=f, fill=_color("ink"))
    return note.rotate(-angle, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=4)
def _hook_note(text: str) -> Image.Image:
    size = HOOK_SIZE
    while True:
        lines = _wrap(text, fredoka(size), HOOK_W - 60)
        if len(lines) <= 2 or size <= 56:
            break
        size -= 4
    return _sticky(tuple(lines), size, HOOK_ROT, HOOK_W)


@lru_cache(maxsize=4)
def _cta_card(width: int) -> Image.Image:
    """«¿Cuántas sabías? __/10» on a sticky note `width` wide, the Bubi sticker on its corner."""
    note = _sticky(CTA_LINES, CTA_SIZE, -3.0, width)
    bubi = kit.bubi_sticker(150)
    img = Image.new("RGBA", (bubi.width + note.width - CTA_OVERLAP, max(bubi.height, note.height)), (0, 0, 0, 0))
    img.alpha_composite(note, (bubi.width - CTA_OVERLAP, (img.height - note.height) // 2))
    img.alpha_composite(bubi, (0, (img.height - bubi.height) // 2 + 30))   # on the note's corner
    return img


@lru_cache(maxsize=64)
def _scaled_note(kind: str, text: str, s: float, width: int = 0) -> Image.Image:
    img = _hook_note(text) if kind == "hook" else _cta_card(width)
    if s == 1.0:
        return img
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def _place_note(layer, img: Image.Image, cx: float, cy: float, a: float = 1.0) -> None:
    layer.alpha_composite(_faded(img, a), tuple(int(round(v)) for v in _p(cx - img.width / 2, cy - img.height / 2)))


#: Over the rows' middle in the opening; over the title (the end needs no title) for the CTA,
#: left of where the pencil parks.
HOOK_AT = (PAGE_W / 2 + 20, 700)
CTA_W, CTA_OVERLAP = 620, 50
CTA_Y = TITLE_Y + 84
BUBI_STICKER_W = 186                     # kit.bubi_sticker(150)   # the note centred on the title


def _draw_hook(layer, t: float, data: Dict, first_row: float) -> None:
    s, a = hook_state(t, hook_end(data, first_row))
    if s > 0 and a > 0:
        _place_note(layer, _scaled_note("hook", hook_text(data), s), *HOOK_AT, a)


def cta_scale(t: float, start: float) -> float:
    """The CTA pops with an overshoot when the spoken outro starts, and stays."""
    if t < start:
        return 0.0
    return round((0.5 + 0.5 * ease_out_back((t - start) / CTA_POP)) * 100) / 100


def cta_width(title_w: float) -> int:
    """The CTA note covers the title it sits on (the end needs no title), within the page."""
    return int(min(PAGE_W - 120, max(CTA_W, title_w + 70)))


def _draw_cta(layer, t: float, start: float, title_w: float) -> None:
    """The CTA, its note centred on the title."""
    s = cta_scale(t, start)
    if s > 0:
        x = (64 + PAGE_W) / 2 - (BUBI_STICKER_W - CTA_OVERLAP) / 2 * s
        _place_note(layer, _scaled_note("cta", "", s, cta_width(title_w)), x, CTA_Y)


# ── Pencil ───────────────────────────────────────────────────────────

#: Degrees BELOW horizontal: tip upper-left, body trailing down-right.
#: Rows fill top to bottom, so the body lies over rows not yet written. With
#: the body up-right (the first render) it sat on the previous row's English
#: word whenever the tip rested -- "grandmother" vanished under it at item 8.
PENCIL_ANGLE = 38


PENCIL_ANGLE = kit.PENCIL_ANGLE


def pencil_image() -> Tuple[Image.Image, Tuple[int, int]]:
    """The pencil, tilted, and where its tip sits inside the image (kit.pencil)."""
    return kit.pencil()


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
PENCIL_PARK_RECAP = (PAGE_W - 80, THEME_Y + 10)   # in the margin, clear of the CTA on the title


def pencil_position(t: float, tl: Timeline, items: List[Dict],
                    centres: List[int]) -> Tuple[float, float]:
    """Page-local tip position at t. Pure function of t."""
    starts, ends = _pencil_targets(tl, items, centres)

    def glide(a, b, t0):
        return _glide(a, b, t, t0)

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
            wx, wy = wobble(t)
            return pos[0] + wx, pos[1] + wy
        pos = ends[i]
    if t < tl.recap[0]:
        return pos
    return glide(pos, PENCIL_PARK_RECAP, tl.recap[0])


# ── Frame ────────────────────────────────────────────────────────────

def _draw_tick(layer: Image.Image, x: float, cy: int, p: float) -> None:
    """A ✓ drawn along its stroke, p of the way (STEP 77 §3; it used to pop in by scale)."""
    kit.tick(layer, *_p(x, cy), 1.0, TICK_SIZE, progress=round(p * 24) / 24)


def _draw_countdown(layer: Image.Image, cy: int, p: float) -> None:
    """Three dots in the English column that empty over the think pause, so the silence
    reads as "your turn" and not as dead air. Mid-column: the pencil rests at its start."""
    kit.dots(layer, *_p(ENGLISH_X + 110, cy), p)


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
    layer = _PageRecorder(_static_page(key, data["theme"]))

    # 1. the marker swipes in behind the active row; in the recap it re-sweeps each row as
    #    the voice reaches its word
    pulses = _recap_word_times(data.get("recap", ""), items, tl.recap)
    for i in range(n):
        _highlight(layer, 56, centres[i], t, tl.es[i][0], tl.es[i + 1][0] if i + 1 < n else tl.recap[0])
    for i, tc in enumerate(pulses):
        if tc is not None:
            nxt = next((u for u in pulses[i + 1:] if u is not None), tl.recap[1] + 0.15)
            _highlight(layer, 56, centres[i], t, tc - 0.15, nxt - 0.15)

    # 2. emoji: in with its row in the opening, popping (ease_out_back) on its row's es_i
    for i, item in enumerate(items):
        scale = 1.0
        es0 = tl.es[i][0]
        if es0 <= t < es0 + EMOJI_POP:
            scale = EMOJI_POP_FROM + (1.0 - EMOJI_POP_FROM) * ease_out_back((t - es0) / EMOJI_POP,
                                                                              EMOJI_OVERSHOOT)
        e = ease_out_cubic(cascade(i, t))
        if e <= 0:
            continue
        size = max(1, round(EMOJI_SIZE * scale))
        img = _faded(kit.emoji_sticker(item["emoji"], size), round(e * 16) / 16)   # STEP 77 §5
        ex, ey = _p(EMOJI_X + (EMOJI_SIZE - img.size[0]) / 2,
                    centres[i] - img.size[1] / 2 + CASCADE_DY * (1.0 - e))
        layer.alpha_composite(img, (int(round(ex)), int(round(ey))))

    # 3. the Spanish column, static (row by row in the opening)
    _rows_in(layer, _static_words(key), _bands(centres), t)

    # 4. countdown dots, English reveal, ticks, recap pulses
    blue = _color("english_blue")
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
            part = _written(word, p)
            if part is not None:
                layer.alpha_composite(part, tuple(int(v) for v in _p(ENGLISH_X - 2, wy)))
            continue

        s = 1.0
        tc = pulses[i]
        if tc is not None and abs(t - tc) < PULSE_HALF:
            s = 1.0 + PULSE_SCALE * math.cos((t - tc) / PULSE_HALF * math.pi / 2) ** 2
            s = round(s * 200) / 200                     # 0.5 % steps: the page memo can reuse them
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

    # 5. the opening hook, and the CTA from the spoken outro on
    _draw_hook(layer, t, data, tl.es[0][0])
    _draw_cta(layer, t, tl.outro[0], fredoka(TITLE_SIZE).getlength(TITLE_TEXT))

    # 6. the page, tilted (memoised by state) and moved, then the pencil over it
    motion = page_motion(t, 0.0, duration, tl.recap)
    _composite_page(frame, layer, motion)
    _place_pencil(frame, *pencil_position(t, tl, items, centres), motion)

    return finalize_frame(frame, ImageDraw.Draw(frame, "RGBA"), t, duration,
                          scene_cuts=[tl.recap[0]], chrome=False)


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
    "true_false_level": {"prompt": "statement", "answer": None, "kind": "tf"},
    # STEP 62: the answer is written INTO the sentence's blank; the translation under it.
    "fill_level": {"prompt": "sentence", "answer": None, "kind": "fill"},
    # STEP 62 §2: both options under the sentence; the right one is circled, the other struck.
    "choose_level": {"prompt": "sentence", "answer": None, "kind": "choose"},
    # STEP 62 §3: say_it_level's page without tiers or verdict; until its reveal each
    # English line is the shared grey blurred bar.
    "phrases_level": {"prompt": "spanish", "answer": "english", "tiers": False, "placeholder": True},
}
#: phrases_level: the placeholder bar on the English line, one width for every row.
PHRASE_BAR_W = 300
#: Rows that open a tier, 0-based, and the tiers' bands and words.
TIER_STARTS = (3, 7)
TIERS = (("BÁSICO", "correct", 0, 3), ("INTERMEDIO", "brand_yellow", 3, 7),
         ("EXPERTO", "error", 7, 10))

NUM_CX = 130                     # row number, centred here
NUM_SIZE = 46
LABEL_X0, LABEL_X1 = 46, 92      # the tier pill, in the margin right of the rings
LABEL_SIZE = 32                  # ≥ 32 (STEP 77 §4)
#: One text column for both lines. Its right edge is CONTENT_R less the tick, so nothing the
#: viewer reads crosses the platforms' button rail (STEP 77 §4).
LINE_X = 172
LINE_W = CONTENT_R - (TICK_GAP + TICK_SIZE + 6) - LINE_X          # 580: line 2, which ends in a tick
LINE1_W = CONTENT_R - LINE_X                                     # 644: line 1 carries no tick
#: STEP 77 §4: one size per video, never under 42 px. A line that does not fit wraps; rows
#: take the height their lines need, and a page holds at most ROWS_PER_PAGE of them.
LINE_FONT_MAX = 46
LINE_FONT_MIN = 42
LINE_PITCH = 1.2                 # line height, in font sizes
ROW_PAD = 24                     # air inside a row, top and bottom together
ROW_EXTRA_MAX = 60               # at most this much more, when a page has room to spare
ROWS_PER_PAGE = 8
TIER_GAP = 30                    # between two tiers on one page: a choose circle hangs below its line
LEVEL_MAX_LINES = 3              # per field; length_spec reads it

#: The say_it_level note over the title: the tip and the other right answer.
NOTE_X, NOTE_Y, NOTE_W, NOTE_H = 96, 30, 740, 250       # ends above the first row (ROWS_TOP)
NOTE_PAD = 22
NOTE_FONT = 42
NOTE_LINES = 4                   # tip up to two lines + «También: …» up to two
NOTE_ALT_LINES = 2
NOTE_POP = 0.25
NOTE_LEAD = "También: "
NOTE_LEAD_W = 190                # NOTE_LEAD at NOTE_FONT plus a little air; length_spec reads it

#: The verdict note over the lower rows.
VERDICT_X, VERDICT_Y, VERDICT_W, VERDICT_H = 120, PAGE_H - 520, 640, 400
VERDICT_SIZE = 64
VERDICT_ROT = -3.0
LABEL_PULSE = 0.22
#: Where the pencil waits while the viewer thinks: STANDING in the right margin, tip by the
#: answer line, body hanging down the margin, so it covers no text and stays in the frame.
#: Steeper than the writing angle, so it narrows as it turns (STEP 77 §4).
PENCIL_WAIT_X = PAGE_W - 22
PENCIL_PARK_ANGLE = 74
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


#: fill_level: the blank is one width on the whole page, wide enough for the longest
#: answer, so its length gives no hint; the grey blurred bar in it is the same in every row.
FILL_BLANK = "____"
BLANK_PAD = 10                   # air either side of the answer inside the blank
BLANK_MIN = "_____"              # the narrowest blank, as wide as five underscores
BLANK_BAR_H = 26
BLANK_RULE = 4


def fill_parts(sentence: str) -> Tuple[str, str]:
    """(before, after) the blank. The before keeps its trailing space, the after its leading one."""
    before, after = sentence.split(FILL_BLANK)
    return before, after


def fit_line(text: str, size: int = LINE_FONT_MAX) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    return fit_word(text, LINE_W, size, LINE_FONT_MIN)


@lru_cache(maxsize=64)
def note_lines(tip: Optional[str], alt: Optional[str]) -> List[Tuple[str, str]]:
    """[(kind, text)] the note draws: the tip wrapped to the note, then the alternative.
    length_spec reads the same wrap, so a tip that needs a third line is caught there."""
    f = fredoka(NOTE_FONT, "display_medium")
    out = [("tip", line) for line in _wrap(tip, f, NOTE_W - 2 * NOTE_PAD)] if tip else []
    if alt:                       # «También: » once, the alternative wrapped beside it
        out += [("alt" if k == 0 else "alt+", line)
                for k, line in enumerate(_wrap(alt, f, NOTE_W - 2 * NOTE_PAD - NOTE_LEAD_W))]
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
        self.outro = span("outro")
        # phrases_level has no verdict: the last row runs to the outro
        self.verdict = span("verdict") if "verdict" in st else (self.outro[0], self.outro[0])

    def row_end(self, i: int) -> float:
        return self.row[i + 1] if i + 1 < self.n else self.verdict[0]

    def reveal(self, i: int, t: float) -> float:
        start, end = self.answer[i]
        if t < start:
            return 0.0
        return 1.0 if end <= start else clamp01((t - start) / (end - start))


# ── The level page's layout (STEP 77 §4) ─────────────────────────────
#
# Each row is two blocks of lines: line 1 (the prompt, the statement or the sentence with its
# blank) and line 2 (the answer, the translation or the options), each wrapped to LINE_W at
# the video's one size. Rows are as tall as their lines; they go onto pages of at most
# ROWS_PER_PAGE, split where a tier starts when one fits, and the page turns between them.

class LevelRow(NamedTuple):
    page: int
    top: float
    bottom: float
    l1: Tuple[Tuple[str, float], ...]          # (text, y centre); a sentence line may hold the blank
    l2: Tuple[Tuple[str, float], ...]

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


class LevelLayout(NamedTuple):
    size: int
    blank: int                                 # fill/choose: the blank's width; 0 otherwise
    pages: Tuple[Tuple[int, int], ...]         # [first, end) rows per page
    rows: Tuple[LevelRow, ...]

    def rows_on(self, page: int) -> range:
        return range(*self.pages[page])


def _line_w(line: str, f: ImageFont.FreeTypeFont, blank: int) -> float:
    return f.getlength(line.replace(FILL_BLANK, "")) + (blank if FILL_BLANK in line else 0)


def _wrap_line(text: str, f: ImageFont.FreeTypeFont, width: float, blank: int = 0) -> List[str]:
    """Words onto lines no wider than `width`; the blank counts as `blank` px."""
    lines, line = [], ""
    for word in text.split(" "):
        trial = f"{line} {word}" if line else word
        if line and _line_w(trial, f, blank) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


def _row_texts(vtype: str, item: Dict) -> Tuple[str, Tuple[str, ...], str]:
    """(line 1 text, line 2 texts, what the blank must hold) of one item."""
    mode = LEVEL_MODES[vtype]
    kind = mode.get("kind", "write")
    if kind == "fill":
        return item["sentence"], (item["translation"],), item["answer"]
    if kind == "choose":
        return item["sentence"], (choice_line(item),), max(item["options"], key=len)
    if kind == "tf":
        return item[mode["prompt"]], (tf_answer(item)[0],), ""
    return item[mode["prompt"]], (item[mode["answer"]],), ""


def level_layout(vtype: str, items: List[Dict]) -> LevelLayout:
    texts = tuple(_row_texts(vtype, it) for it in items)
    return _level_layout(LEVEL_MODES[vtype].get("tiers", True), LEVEL_MODES[vtype].get("kind", "write"), texts)


class LayoutError(ValueError):
    """The rows do not fit the pages at LINE_FONT_MIN: length_spec reports it."""


@lru_cache(maxsize=16)
def _level_layout(tiers: bool, kind: str, texts) -> LevelLayout:
    """The layout read best: fewest pages, split where a tier starts, fewest lines, then the
    largest size; more than two pages only when nothing else fits at LINE_FONT_MIN."""
    found = [lay for lay in (_layout_at(size, tiers, kind, texts, greedy=False)
                             for size in range(LINE_FONT_MAX, LINE_FONT_MIN - 1, -2)) if lay]
    if not found:
        lay = _layout_at(LINE_FONT_MIN, tiers, kind, texts, greedy=True)
        if lay is None:
            raise LayoutError("the rows do not fit at the smallest size")
        return lay

    def score(lay):
        split = len(lay.pages) == 1 or (tiers and lay.pages[1][0] in TIER_STARTS)
        lines = sum(len(r.l1) + len(r.l2) for r in lay.rows)
        return len(lay.pages), not split, lines, -lay.size
    return min(found, key=score)


def _layout_at(size: int, tiers: bool, kind: str, texts, greedy: bool) -> Optional[LevelLayout]:
    n = len(texts)
    band = ROWS_BOTTOM - ROWS_TOP
    f = fredoka(size)
    blank = 0
    if kind in ("fill", "choose"):
        blank = int(math.ceil(max([f.getlength(b) for _a, _l, b in texts] + [f.getlength(BLANK_MIN)]))) \
            + 2 * BLANK_PAD
    lines = [(_wrap_line(a, f, LINE1_W, blank), [x for t in l2 for x in _wrap_line(t, f, LINE_W)])
             for a, l2, _b in texts]
    if any(f.getlength(x) > LINE1_W for l1, _l2 in lines for x in l1 if " " not in x) or \
            any(f.getlength(x) > LINE_W for _l1, l2 in lines for x in l2 if " " not in x):
        return None                                        # one word wider than the column
    pitch = round(size * LINE_PITCH)
    heights = [ROW_PAD + pitch * (len(l1) + len(l2)) for l1, l2 in lines]

    def fits(a, b):
        gaps = sum(TIER_GAP for i in range(a + 1, b) if tiers and i in TIER_STARTS)
        return b - a <= ROWS_PER_PAGE and sum(heights[a:b]) + gaps <= band

    pages = None
    if fits(0, n):
        pages = [(0, n)]
    elif not greedy:
        order = (list(reversed(TIER_STARTS)) if tiers else []) + sorted(range(1, n), key=lambda k: abs(k - n / 2))
        for k in order:
            if 0 < k < n and fits(0, k) and fits(k, n):
                pages = [(0, k), (k, n)]
                break
    else:
        pages, a = [], 0
        while a < n:
            b = a + 1
            while b < n and fits(a, b + 1):
                b += 1
            if not fits(a, b):
                return None                                # a row taller than a page
            pages.append((a, b))
            a = b
    if pages is None:
        return None
    rows = [None] * n
    for p, (a, b) in enumerate(pages):
        gaps = [TIER_GAP if tiers and i in TIER_STARTS and i > a else 0 for i in range(a, b)]
        total = sum(heights[a:b]) + sum(gaps)
        extra = min(ROW_EXTRA_MAX, (band - total) / (b - a))
        y = ROWS_TOP + (band - total - extra * (b - a)) / 2
        for i in range(a, b):
            y += gaps[i - a]
            h = heights[i] + extra
            l1, l2 = lines[i]
            y0 = y + (h - pitch * (len(l1) + len(l2))) / 2
            ys = [y0 + pitch * (k + 0.5) for k in range(len(l1) + len(l2))]
            rows[i] = LevelRow(p, y, y + h, tuple(zip(l1, ys)), tuple(zip(l2, ys[len(l1):])))
            y += h
    return LevelLayout(size, blank, tuple(pages), tuple(rows))


def page_enters(tl: LevelTimeline, layout: LevelLayout) -> Tuple[float, ...]:
    """When each page is on: the first at 0; a later one when the tier line that opens it
    starts (+HANDOFF), else between the last answer and the next row. The page before it
    slides out over the HANDOFF before that."""
    out = [0.0]
    for a, _b in layout.pages[1:]:
        if a in tl.tier:
            out.append(tl.tier[a][0] + HANDOFF)
        else:
            out.append(max(tl.answer[a - 1][1] + TICK_POP, (tl.answer[a - 1][1] + tl.row[a]) / 2) + HANDOFF)
    return tuple(out)


def current_page(t: float, enters: Tuple[float, ...]) -> int:
    return max(p for p, e in enumerate(enters) if e <= t)


@lru_cache(maxsize=8)
def _static_level_page(layout: LevelLayout, page: int, title: str, theme: str,
                       tiers: bool = True) -> Image.Image:
    """Paper, binding, title, theme, footer and the ruled line under each row of the page;
    a line that closes a tier is thicker, in the next tier's colour."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    _draw_paper(layer)
    sky = _on_paper(_color("sky"), 0.6)
    closes = {t[2]: t[1] for t in TIERS[1:]} if tiers else {}   # row count -> colour of the tier it opens
    a, b = layout.pages[page]
    for i in range(a, b):
        ly = layout.rows[i].bottom - 4
        if i + 1 in closes and i + 1 < b:                       # sticker rule: ink under the colour
            ly += TIER_GAP / 2
            kit.rule(layer, _p(LABEL_X1 + 6, 0)[0], _p(PAGE_W - 30, 0)[0], _p(0, ly)[1], 11, _color("ink"))
            kit.rule(layer, _p(LABEL_X1 + 8, 0)[0], _p(PAGE_W - 32, 0)[0], _p(0, ly)[1], 6, _color(closes[i + 1]))
        else:
            kit.rule(layer, _p(LABEL_X1 + 6, 0)[0], _p(PAGE_W - 30, 0)[0], _p(0, ly)[1], 3, sky)
    # a Spanish title is ink; English is always blue (brand rule)
    _draw_title(layer, title, theme, fit_word(title, PAGE_W - 140, TITLE_SIZE, 56)[0], _color("ink"))
    _draw_rings(layer, 40, PAGE_H - 40)
    _draw_footer(layer)
    return layer


def _draw_sentence(draw: ImageDraw.ImageDraw, line: str, y_centre: float, f, blank: int, color) -> None:
    """A line of text; a sentence line keeps a `blank`-wide gap where its blank is."""
    y = _text_y(f, y_centre)
    if FILL_BLANK not in line:
        draw.text(_p(LINE_X, y), line, font=f, fill=color)
        return
    before, after = line.split(FILL_BLANK, 1)
    draw.text(_p(LINE_X, y), before, font=f, fill=color)
    draw.text(_p(LINE_X + f.getlength(before) + blank, y), after, font=f, fill=color)


@lru_cache(maxsize=8)
def _static_level_text(layout: LevelLayout, page: int, prompt_blue: bool) -> Image.Image:
    """The row numbers and every line 1 of the page: on it from the moment it shows."""
    layer = Image.new("RGBA", (LAYER_W, LAYER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    nf, f = fredoka(NUM_SIZE), fredoka(layout.size)
    color = _color("english_blue" if prompt_blue else "ink")
    for i in layout.rows_on(page):
        row = layout.rows[i]
        num = str(i + 1)
        draw.text(_p(NUM_CX - nf.getlength(num) / 2, _text_y(nf, row.l1[0][1])), num, font=nf,
                  fill=_color("secondary_text"))
        for line, y in row.l1:
            _draw_sentence(draw, line, y, f, layout.blank, color)
    return layer


def blank_at(layout: LevelLayout, i: int) -> Tuple[float, float]:
    """(x, y centre) where row i's blank starts."""
    f = fredoka(layout.size)
    for line, y in layout.rows[i].l1:
        if FILL_BLANK in line:
            return LINE_X + f.getlength(line.split(FILL_BLANK, 1)[0]), y
    raise ValueError(f"row {i + 1} has no blank")


@lru_cache(maxsize=32)
def _line_image(text: str, size: int, color: Tuple[int, int, int, int]) -> Image.Image:
    """A line at exactly `size` on its own strip, for the reveal mask."""
    f = fredoka(size)
    ascent, descent = f.getmetrics()
    img = Image.new("RGBA", (int(math.ceil(f.getlength(text))) + 8, ascent + descent + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2, 2), text, font=f, fill=color)
    return img


_plain_line = _line_image


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
    """An ✗ (kit.cross)."""
    kit.cross(layer, *_p(x, cy), scale, CROSS_SIZE)


def written_point(layout: LevelLayout, i: int, p: float) -> Tuple[int, float, float]:
    """(line, x) where row i's line 2 is being written at p of its reveal, and the width
    written on that line. The lines are written one after another, by width."""
    f = fredoka(layout.size)
    widths = [f.getlength(text) for text, _y in layout.rows[i].l2]
    left = sum(widths) * clamp01(p)
    for k, w in enumerate(widths):
        if left <= w or k == len(widths) - 1:
            return k, LINE_X + min(left, w), min(left, w)
        left -= w
    return len(widths) - 1, LINE_X + widths[-1], widths[-1]


def _draw_written(layer, layout: LevelLayout, i: int, p: float, color) -> None:
    """Row i's line 2, written in up to p; the line being written has the feathered edge."""
    f = fredoka(layout.size)
    k_now, _x, done = written_point(layout, i, p)
    for k, (text, y) in enumerate(layout.rows[i].l2):
        if k > k_now:
            break
        word = _line_image(text, layout.size, color)
        part = word if k < k_now or p >= 1.0 else _written(word, (done + 2) / word.width)
        if part is not None:
            layer.alpha_composite(part, tuple(int(v) for v in _p(LINE_X - 2, _text_y(f, y) - 2)))


def _line_end(layout: LevelLayout, i: int) -> Tuple[float, float]:
    """(x, y) right after row i's last line 2."""
    f = fredoka(layout.size)
    text, y = layout.rows[i].l2[-1]
    return LINE_X + f.getlength(text), y


def _draw_tf_answers(layer: Image.Image, t: float, tl: "LevelTimeline", items: List[Dict],
                     layout: LevelLayout, page: int) -> None:
    """The placeholder cross-fades to the real answer while the blur goes BLUR_MAX -> 0."""
    f = fredoka(layout.size)
    grey = _color("secondary_text")
    for i in layout.rows_on(page):
        row, item = layout.rows[i], items[i]
        color = _color(tf_answer(item)[1])
        p = tl.reveal(i, t)
        radius = int(round(BLUR_MAX * (1.0 - p) / BLUR_STEP)) * BLUR_STEP
        y0 = row.l2[0][1]
        if p < 1.0:
            layer.alpha_composite(_faded(_blurred_line(TF_PLACEHOLDER, layout.size, grey, radius), 1.0 - p),
                                  tuple(int(v) for v in _p(LINE_X - 2 - BLUR_PAD, _text_y(f, y0) - 2 - BLUR_PAD)))
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, LINE_X + 110, y0, (t - th0) / max(1e-6, th1 - th0))
        if p <= 0:
            continue
        for text, y in row.l2:
            at = tuple(int(v) for v in _p(LINE_X - 2 - BLUR_PAD, _text_y(f, y) - 2 - BLUR_PAD))
            layer.alpha_composite(_faded(_blurred_line(text, layout.size, color, radius), p), at)
        if p >= 1.0:
            mark_t = tl.answer[i][1]
            scale = ease_out_cubic((t - mark_t) / TICK_POP) if t >= mark_t else 0.0
            x, y = _line_end(layout, i)
            (_draw_tick if item["truth"] else _draw_cross)(layer, x + TICK_GAP, y, scale)


@lru_cache(maxsize=16)
def _blank_bar(width: int, radius: int) -> Image.Image:
    """The shared placeholder: a grey rounded bar, blurred, the blank's width."""
    img = Image.new("RGBA", (width + 2 * BLUR_PAD, BLANK_BAR_H + 2 * BLUR_PAD), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([BLUR_PAD + 4, BLUR_PAD, BLUR_PAD + width - 4, BLUR_PAD + BLANK_BAR_H],
                                          radius=BLANK_BAR_H // 2, fill=_color("secondary_text", 150))
    return img.filter(ImageFilter.GaussianBlur(radius)) if radius > 0 else img


def fill_spans(items: List[Dict], layout: LevelLayout) -> List[Tuple[float, float, float]]:
    """(x start, x end, pencil y) where each answer is written: centred in its blank."""
    f = fredoka(layout.size)
    out = []
    for i, it in enumerate(items):
        bx, y = blank_at(layout, i)
        w = f.getlength(it["answer"])
        x0 = bx + (layout.blank - w) / 2
        out.append((x0, x0 + w, y + 26))
    return out


def _blank_rule(layer, layout: LevelLayout, i: int, alpha: int = 255) -> None:
    bx, y = blank_at(layout, i)
    ry = y + layout.size * 0.42
    kit.rule(layer, _p(bx + 2, 0)[0], _p(bx + layout.blank - 2, 0)[0], _p(0, ry)[1], BLANK_RULE,
             _color("ink", alpha))


def _draw_fill_answers(layer: Image.Image, t: float, tl: "LevelTimeline", items: List[Dict],
                       layout: LevelLayout, page: int) -> None:
    """Before the reveal each blank holds the blurred grey bar over its rule. Over answer_i the
    answer is written into the blank in blue while bar and rule fade, and the translation
    comes up under the sentence in muted ink, with the tick after it."""
    f = fredoka(layout.size)
    blue, grey = _color("english_blue"), _color("secondary_text")
    spans = fill_spans(items, layout)
    for i in layout.rows_on(page):
        it, row = items[i], layout.rows[i]
        bx, y1 = blank_at(layout, i)
        p = tl.reveal(i, t)
        if p < 1.0:
            radius = int(round(BLUR_MAX * 0.5 * (1.0 - p) / BLUR_STEP)) * BLUR_STEP
            bar = _faded(_blank_bar(layout.blank, radius), 1.0 - p)
            layer.alpha_composite(bar, tuple(int(v) for v in _p(bx - BLUR_PAD, y1 - BLANK_BAR_H / 2 - BLUR_PAD)))
            _blank_rule(layer, layout, i, int(round(255 * (1.0 - p) * 16) / 16))
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, LINE_X + 110, row.l2[0][1], (t - th0) / max(1e-6, th1 - th0))
        if p <= 0:
            continue
        part = _written(_line_image(it["answer"], layout.size, blue), p)
        if part is not None:
            layer.alpha_composite(part, tuple(int(v) for v in _p(spans[i][0] - 2, _text_y(f, y1) - 2)))
        for text, y in row.l2:
            layer.alpha_composite(_faded(_line_image(text, layout.size, grey), p),
                                  tuple(int(v) for v in _p(LINE_X - 2, _text_y(f, y) - 2)))
        if p >= 1.0:
            tick_t = tl.answer[i][1]
            x, y = _line_end(layout, i)
            _draw_tick(layer, x + TICK_GAP, y, ease_out_cubic((t - tick_t) / TICK_POP) if t >= tick_t else 0.0)


#: choose_level: «make · do» under the sentence, muted, from frame 0.
CHOICE_SEP = "   ·   "           # wide, so a circle and a strike never touch
CIRCLE_PAD_X, CIRCLE_PAD_Y = 12, 6
DOTS_GAP = 34                    # the countdown starts this far after the options line


def blank_key(item: Dict) -> Tuple[str, str]:
    """(sentence, what the blank must hold): fill_level's answer, choose_level's longer option."""
    if "options" in item:
        return item["sentence"], max(item["options"], key=len)
    return item["sentence"], item["answer"]


def choice_line(item: Dict) -> str:
    return CHOICE_SEP.join(item["options"])


def choice_spans(items: List[Dict], layout: LevelLayout) -> List[List[Tuple[float, float]]]:
    """[(x start, x end) of option 0, of option 1] per row, on line 2 at the page's size."""
    f = fredoka(layout.size)
    out = []
    for it in items:
        a, b = it["options"]
        xb = LINE_X + f.getlength(a + CHOICE_SEP)
        out.append([(LINE_X, LINE_X + f.getlength(a)), (xb, xb + f.getlength(b))])
    return out


def _as_layer(target) -> Image.Image:
    """The image an ImageDraw paints on, or the image itself (the tests pass a draw)."""
    return target if hasattr(target, "alpha_composite") else target._image   # an image or the page recorder


def _hand_circle(target, box: Tuple[float, float, float, float], p: float) -> None:
    """A loop drawn by hand around box (page-local), p of the way (kit.circle)."""
    x0, y0, x1, y1 = box
    kit.circle(_as_layer(target), (*_p(x0, y0), *_p(x1, y1)), p)


def _strike(target, x0: float, x1: float, cy: float, p: float) -> None:
    """A red stroke through the wrong option, left to right (kit.strike)."""
    kit.strike(_as_layer(target), _p(x0, 0)[0], _p(x1, 0)[0], _p(0, cy)[1], p)


def circle_box(spans: List[Tuple[float, float]], right: int, cy: float, size: int) -> Tuple[float, ...]:
    x0, x1 = spans[right]
    return x0 - CIRCLE_PAD_X, cy - size / 2 - CIRCLE_PAD_Y, x1 + CIRCLE_PAD_X, cy + size / 2 + CIRCLE_PAD_Y


def _draw_choose_answers(layer: Image.Image, t: float, tl: "LevelTimeline", items: List[Dict],
                         layout: LevelLayout, page: int) -> None:
    """Both options stay readable: over answer_i the right one turns blue and is circled
    in green, the wrong one is struck in red; the tick follows the line. The countdown
    dots sit after the options, never over them."""
    f = fredoka(layout.size)
    grey, blue = _color("secondary_text"), _color("english_blue")
    all_spans = choice_spans(items, layout)
    for i in layout.rows_on(page):
        it, spans = items[i], all_spans[i]
        _blank_rule(layer, layout, i)              # the blank stays open: the options answer it
        cy = layout.rows[i].l2[0][1]
        y = _text_y(f, cy) - 2
        p = tl.reveal(i, t)
        right = it["answer"]
        dot = CHOICE_SEP.strip()
        layer.alpha_composite(_plain_line(dot, layout.size, grey), tuple(int(v) for v in _p(
            spans[0][1] + (f.getlength(CHOICE_SEP) - f.getlength(dot)) / 2 - 2, y)))
        for k, (x0, _x1) in enumerate(spans):
            at = tuple(int(v) for v in _p(x0 - 2, y))
            layer.alpha_composite(_plain_line(it["options"][k], layout.size, grey), at)
            if k == right and p > 0:
                layer.alpha_composite(_faded(_plain_line(it["options"][k], layout.size, blue), p), at)
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, spans[1][1] + DOTS_GAP, cy, (t - th0) / max(1e-6, th1 - th0))
        if p <= 0:
            continue
        _hand_circle(layer, circle_box(spans, right, cy, layout.size), p)
        _strike(layer, *spans[1 - right], cy, p)
        if p >= 1.0:
            tick_t = tl.answer[i][1]
            _draw_tick(layer, choose_tick_x(spans, right), cy,
                       ease_out_cubic((t - tick_t) / TICK_POP) if t >= tick_t else 0.0)


def choose_tick_x(spans: List[Tuple[float, float]], right: int) -> float:
    """After the options line, the hand-drawn circle (its loop runs up to 1.1× its radius, plus
    its ink) and the strike (6 px past the word, plus its ink), so the tick touches none of them
    (STEP 77 §3)."""
    x0, x1 = spans[right]
    cx, rx = (x0 + x1) / 2, (x1 - x0) / 2 + CIRCLE_PAD_X
    struck = spans[1 - right][1] + 6 + 7
    return max(spans[1][1], struck, cx + 1.1 * rx + 7) + TICK_GAP


def _draw_countdown_at(layer: Image.Image, x0: float, cy: float, p: float) -> None:
    """The three countdown dots at a given x (kit.dots)."""
    kit.dots(layer, *_p(x0, cy), p)


@lru_cache(maxsize=8)
def _tier_pill(word: str, color_name: str, height: int) -> Image.Image:
    """A vertical pill in the tier's colour with its word read bottom to top."""
    w = LABEL_X1 - LABEL_X0
    pill = kit.pill(w, height, _color(color_name)).copy()
    f = fredoka(LABEL_SIZE)
    text = Image.new("RGBA", (int(f.getlength(word)) + 4, LABEL_SIZE + 12), (0, 0, 0, 0))
    ink_on = color_name == "brand_yellow"           # yellow is never under paper-coloured text
    ImageDraw.Draw(text).text((2, 2), word, font=f, fill=_color("ink") if ink_on else PAPER)
    text = text.rotate(90, expand=True, resample=Image.BICUBIC)
    pill.alpha_composite(text, ((pill.size[0] - text.size[0]) // 2 + 1,
                                (pill.size[1] - text.size[1]) // 2))
    return pill


def _draw_arrow(img: Image.Image, x: float, y: float, length: float, color) -> None:
    """Fredoka has no «→» (kit.arrow)."""
    kit.arrow(img, x, y, length, color)


@lru_cache(maxsize=1)
def _verdict_note() -> Image.Image:
    """«3 → básico · 7 → intermedio · 10 → experto», one tier per line, on a sticky note."""
    ink = _color("ink")
    note = Image.new("RGBA", (VERDICT_W + SHADOW[0] + 4, VERDICT_H + SHADOW[1] + 4), (0, 0, 0, 0))
    note.alpha_composite(kit.note_card(VERDICT_W, VERDICT_H, _color("brand_yellow"), 5, SHADOW))
    d = ImageDraw.Draw(note, "RGBA")
    f = fredoka(VERDICT_SIZE)
    for k, (num, (word, color, _a, _b)) in enumerate(zip(("3", "7", "10"), TIERS)):
        cy = 80 + k * 120
        y = _text_y(f, cy)
        d.text((48, y), num, font=f, fill=ink)
        _draw_arrow(note, 150, cy, 70, ink)
        d.text((250, y), word.lower(), font=f, fill=_color(color) if color != "brand_yellow" else ink)
    return note.rotate(VERDICT_ROT, expand=True, resample=Image.BICUBIC)


@lru_cache(maxsize=16)
def _note_image(lines: Tuple[Tuple[str, str], ...]) -> Image.Image:
    """The say_it_level note (kit.note_card + its lines), drawn once per note."""
    ink = _color("ink")
    note = Image.new("RGBA", (NOTE_W + SHADOW[0], NOTE_H + SHADOW[1]), (0, 0, 0, 0))
    note.alpha_composite(kit.note_card(NOTE_W, NOTE_H, _color("brand_yellow"), 4, SHADOW).crop((0, 0, *note.size)))
    d = ImageDraw.Draw(note, "RGBA")
    f = fredoka(NOTE_FONT, "display_medium")
    step = (NOTE_H - 2 * NOTE_PAD) / NOTE_LINES
    top = NOTE_PAD + (NOTE_LINES - len(lines)) * step / 2
    for k, (kind, text) in enumerate(lines[:NOTE_LINES]):
        cy = top + step * (k + 0.5)
        y = _text_y(f, cy)
        if kind in ("alt", "alt+"):
            if kind == "alt":
                d.text((NOTE_PAD, y), NOTE_LEAD, font=f, fill=ink)
            d.text((NOTE_PAD + NOTE_LEAD_W, y), text, font=f, fill=_color("english_blue"))
        else:
            d.text((NOTE_PAD, y), text, font=f, fill=ink)
    return note


@lru_cache(maxsize=64)
def _note_scaled(lines: Tuple[Tuple[str, str], ...], scale: float) -> Image.Image:
    note = _note_image(lines)
    if scale == 1.0:
        return note
    return note.resize((max(1, round(note.size[0] * scale)), max(1, round(note.size[1] * scale))), Image.LANCZOS)


def _draw_note(layer: Image.Image, lines: List[Tuple[str, str]], scale: float) -> None:
    if scale <= 0 or not lines:
        return
    note = _note_scaled(tuple(lines), round(scale * 100) / 100)      # 1 % steps for the page memo
    cx, cy = NOTE_X + NOTE_W / 2, NOTE_Y + NOTE_H / 2
    layer.alpha_composite(note, tuple(int(round(v)) for v in _p(cx - note.size[0] / 2, cy - note.size[1] / 2)))


def level_text_boxes(vtype: str, items: List[Dict], layout: LevelLayout) -> List[List[Tuple[float, ...]]]:
    """[line boxes] per row, page-local (x0, y0, x1, y1), as each row reads once revealed:
    the last line 2 carries its tick, and in choose_level its circle and strike."""
    kind = LEVEL_MODES[vtype].get("kind", "write")
    f = fredoka(layout.size)
    bb = f.getbbox("Hgjy")

    def box(x1, cy):
        top = _text_y(f, cy)
        return (LINE_X, top + bb[1], x1, top + bb[3])

    spans = choice_spans(items, layout) if kind == "choose" else None
    out = []
    for i, row in enumerate(layout.rows):
        boxes = [box(LINE_X + _line_w(line, f, layout.blank), y) for line, y in row.l1]
        if kind == "choose":
            cy = row.l2[0][1]
            ry = (layout.size / 2 + CIRCLE_PAD_Y) * 1.1 + 5          # the hand circle's wobble and stroke
            boxes.append((LINE_X - CIRCLE_PAD_X - 6, cy - ry, choose_tick_x(spans[i], items[i]["answer"])
                          + TICK_SIZE + 7, cy + ry))
        else:
            mark = TICK_GAP + (max(TICK_SIZE, CROSS_SIZE) if kind == "tf" else TICK_SIZE) + 7
            for k, (text, y) in enumerate(row.l2):
                end = LINE_X + f.getlength(text) + (mark if k == len(row.l2) - 1 else 0)
                boxes.append(box(end, y))
        out.append(boxes)
    return out


#: The pencil image's box around its tip (pencil_image, PENCIL_ANGLE).
PENCIL_BOX = (-4, -4, 166, 135)          # kit.pencil, 200 px long (STEP 77 §3)


def _write_path(kind: str, items: List[Dict], layout: LevelLayout):
    """Per row, a function p -> (x, y) of the pencil tip while the row's answer is written:
    along line 2 (wrapped lines one after another), in the blank, or round the right option."""
    if kind == "fill":
        spans = fill_spans(items, layout)
        return [(lambda p, s=s: (s[0] + (s[1] - s[0]) * p, s[2])) for s in spans]
    if kind == "choose":
        paths = []
        for it, sp, row in zip(items, choice_spans(items, layout), layout.rows):
            x0, x1 = sp[it["answer"]]
            paths.append(lambda p, x0=x0, x1=x1, y=row.l2[0][1] + 26: (x0 + (x1 - x0) * p, y))
        return paths

    def along(i):
        def at(p):
            k, x, _done = written_point(layout, i, p)
            return x, layout.rows[i].l2[k][1] + 26
        return at
    return [along(i) for i in range(len(layout.rows))]


def level_pencil_position(t: float, tl: LevelTimeline, items: List[Dict], layout: LevelLayout,
                          kind: str = "write") -> Tuple[float, float]:
    """Stands in the right margin by the active row while the viewer thinks, comes to the
    answer as it begins and writes it; after the last answer it stands in the margin again,
    so the last frames show every answer (STEP 63: it sat on «Depende de ti»)."""
    writes = kind != "tf"
    paths = _write_path(kind, items, layout)

    def glide(a, b, t0):
        return _glide(a, b, t, t0)

    if writes and t >= tl.answer[-1][1]:
        end = paths[-1](1.0)
        return glide(end, (PENCIL_WAIT_X, layout.rows[-1].l2[-1][1] - 6), tl.answer[-1][1])

    pos = LEVEL_PENCIL_PARK
    for i in range(tl.n):
        if t < tl.row[i]:
            return pos
        wait = (PENCIL_WAIT_X, layout.rows[i].l2[0][1] - 6)
        if not writes:                                 # true_false_level: it points, it does not write
            if t < tl.row_end(i):
                return glide(pos, wait, tl.row[i])
            pos = wait
            continue
        start, end = paths[i](0.0), paths[i](1.0)
        if t < tl.answer[i][0] - PENCIL_MOVE:
            return glide(pos, wait, tl.row[i])
        if t < tl.answer[i][0]:
            return glide(wait, start, tl.answer[i][0] - PENCIL_MOVE)
        p = tl.reveal(i, t)
        if p < 1.0:
            x, y = paths[i](p)
            wx, wy = wobble(t)
            return x + wx, y + wy
        pos = end
    return pos


def level_pencil_angle(t: float, tl: LevelTimeline, kind: str = "write") -> float:
    """The pencil's angle: PENCIL_ANGLE to write, PENCIL_PARK_ANGLE (standing) while it waits
    in the margin, turned over the same glide that moves it."""
    def turn(a, b, t0):
        e = ease_in_out((t - t0) / PENCIL_MOVE)
        return a + (b - a) * e

    angle = PENCIL_ANGLE
    for i in range(tl.n):
        if t < tl.row[i]:
            return angle
        if kind == "tf":
            if t < tl.row_end(i):
                return turn(angle, PENCIL_PARK_ANGLE, tl.row[i])
            angle = PENCIL_PARK_ANGLE
            continue
        if t < tl.answer[i][0] - PENCIL_MOVE:
            return turn(angle, PENCIL_PARK_ANGLE, tl.row[i])
        if t < tl.answer[i][0]:
            return turn(PENCIL_PARK_ANGLE, PENCIL_ANGLE, tl.answer[i][0] - PENCIL_MOVE)
        if t < tl.answer[i][1]:
            return PENCIL_ANGLE
        angle = PENCIL_ANGLE
    return turn(angle, PENCIL_PARK_ANGLE, tl.answer[-1][1])          # standing again, to the end


def create_frame_level(t: float, data: Dict, duration: float, presentation=None) -> np.ndarray:
    """One frame of any level mode (LEVEL_MODES)."""
    vtype = data["type"]
    mode = LEVEL_MODES[vtype]
    items: List[Dict] = data["items"]
    tl = data.get("_level_timeline")
    if tl is None:
        tl = LevelTimeline(data, duration)
        data["_level_timeline"] = tl
        data["_level_layout"] = level_layout(vtype, items)
        data["_level_enters"] = page_enters(tl, data["_level_layout"])
    layout, enters = data["_level_layout"], data["_level_enters"]
    page = current_page(t, enters)
    first, end = layout.pages[page]
    rows = layout.rows
    prompt, answer = mode["prompt"], mode["answer"]
    blue, ink = _color("english_blue"), _color("ink")
    kind = mode.get("kind", "write")
    tiers = mode.get("tiers", True)

    frame, _draw = create_base_frame(t)
    layer = _PageRecorder(_static_level_page(layout, page, data["title"], data["theme"], tiers))
    t_page = t - enters[page]                          # the page's own clock: its rows cascade in

    # 1. the marker swipes in behind the active row, then the printed numbers and prompts over it
    for i in range(first, end):
        _highlight_band(layer, LABEL_X1 + 6, rows[i].top + 4, rows[i].bottom - 6, t, tl.row[i], tl.row_end(i))
    _rows_in(layer, _static_level_text(layout, page, prompt == "english" and kind == "write"),
             [rows[i] for i in range(first, end)], t_page)

    # 2. tier pills in the margin, for the tiers on this page; the one a tier line announces pulses
    for word, color, a, b in TIERS if tiers else ():
        a, b = max(a, first), min(b, end)
        if a >= b:
            continue
        top, bottom = rows[a].top + 8, rows[b - 1].bottom - 12
        pill = _tier_pill(word, color, int(bottom - top))
        s = 1.0
        span = tl.tier.get(a)
        if span and span[0] <= t < span[1]:
            s = 1.0 + LABEL_PULSE * math.sin(math.pi * (t - span[0]) / (span[1] - span[0]))
            s = round(s * 100) / 100
        if s != 1.0:
            pill = pill.resize((max(1, round(pill.size[0] * s)), max(1, round(pill.size[1] * s))), Image.LANCZOS)
        pill = _faded(pill, round(ease_out_cubic(cascade(a - first, t_page)) * 16) / 16)   # in with its first row
        if pill.getbbox() is None:
            continue
        cx, cy = (LABEL_X0 + LABEL_X1) / 2, (top + bottom) / 2
        layer.alpha_composite(pill, tuple(int(round(v)) for v in _p(cx - pill.size[0] / 2, cy - pill.size[1] / 2)))

    # 3. countdown dots, the answers written in, ticks (true_false_level: brought into focus)
    if kind == "tf":
        _draw_tf_answers(layer, t, tl, items, layout, page)
    elif kind == "fill":
        _draw_fill_answers(layer, t, tl, items, layout, page)
    elif kind == "choose":
        _draw_choose_answers(layer, t, tl, items, layout, page)
    answer_color = blue if answer == "english" else ink
    placeholder = mode.get("placeholder", False)
    f = fredoka(layout.size)
    for i in range(first, end) if answer else ():
        row = rows[i]
        y0 = row.l2[0][1]
        p = tl.reveal(i, t)
        if placeholder and p < 1.0:
            radius = int(round(BLUR_MAX * 0.5 * (1.0 - p) / BLUR_STEP)) * BLUR_STEP
            layer.alpha_composite(_faded(_blank_bar(PHRASE_BAR_W, radius), 1.0 - p), tuple(
                int(v) for v in _p(LINE_X - BLUR_PAD, y0 - BLANK_BAR_H / 2 - BLUR_PAD)))
        th0, th1 = tl.think[i]
        if th0 <= t < th1:
            _draw_countdown_at(layer, LINE_X + (PHRASE_BAR_W + DOTS_GAP if placeholder else 110), y0,
                               (t - th0) / max(1e-6, th1 - th0))
        if p <= 0:
            continue
        _draw_written(layer, layout, i, p, answer_color)
        if p >= 1.0:
            tick_t = tl.answer[i][1]
            x, y = _line_end(layout, i)
            _draw_tick(layer, x + TICK_GAP, y, ease_out_cubic((t - tick_t) / TICK_POP) if t >= tick_t else 0.0)

    # 4. say_it_level: the tip and the other right answer, from the reveal to the next row
    for i in range(first, end):
        lines = note_lines(items[i].get("tip"), items[i].get("alt"))
        if not lines:
            continue
        start, stop = tl.answer[i][0], tl.row_end(i)
        if start <= t < stop:
            _draw_note(layer, lines, ease_out_cubic((t - start) / NOTE_POP) * 0.15 + 0.85
                       if t < start + NOTE_POP else 1.0)

    # 5. the pencil: drawn after the page is tilted (see _place_pencil)
    pencil_at = level_pencil_position(t, tl, items, layout, kind)
    angle = level_pencil_angle(t, tl, kind)

    # 6. the verdict note, over the lower rows while the verdict is spoken
    v0, v1 = tl.verdict
    if tiers and v0 <= t < v1 + NOTE_POP:
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

    # 7. the opening hook, and the CTA from the spoken outro on
    _draw_hook(layer, t, data, tl.row[0])
    _draw_cta(layer, t, tl.outro[0], fit_word(data["title"], PAGE_W - 140, TITLE_SIZE, 56)[0].getlength(data["title"]))

    leave = enters[page + 1] if page + 1 < len(enters) else duration
    motion = page_motion(t, enters[page], leave, (tl.answer[-1][1], tl.outro[0]))
    _composite_page(frame, layer, motion)
    _place_pencil(frame, *pencil_at, motion, angle)
    return finalize_frame(frame, ImageDraw.Draw(frame, "RGBA"), t, duration, scene_cuts=[v0], chrome=False)


# ── Sound design (STEP 77 §7) ────────────────────────────────────────

def sfx_events(data: Dict, duration: float) -> Tuple[List[Tuple[str, float, float]], List[Tuple[float, float]]]:
    """(events, spoken spans) for a notebook Short, read off the same timeline the frames are:
    a swish as the page comes in, turns and leaves, a pop on every emoji, tick and note, and
    the pencil's scratch while it writes. Spoken spans: every segment but the think pauses."""
    st = data["segment_times"]
    spoken = sorted((float(v["start"]), float(v["end"])) for k, v in st.items() if not k.startswith("think"))
    events = [("swish", 0.0, 0.0), ("pop", HOOK_IN, 0.0)]
    if data["type"] == "how_do_you_say":
        tl = Timeline(data, duration)
        for i in range(tl.n):
            events.append(("pop", tl.es[i][0], 0.0))
            if tl.reveal_end[i] > tl.en[i][0]:
                events.append(("scratch", tl.en[i][0], tl.reveal_end[i] - tl.en[i][0]))
            events.append(("pop", tl.reveal_end[i], 0.0))
        cta = tl.outro[0]
    else:
        tl = LevelTimeline(data, duration)
        writes = LEVEL_MODES[data["type"]].get("kind", "write") != "tf"
        for i in range(tl.n):
            a, b = tl.answer[i]
            if writes and b > a:
                events.append(("scratch", a, b - a))
            events.append(("pop", b, 0.0))
        for enter in page_enters(tl, level_layout(data["type"], data["items"]))[1:]:
            events.append(("swish", enter - HANDOFF, 0.0))
        cta = tl.outro[0]
    events += [("pop", cta, 0.0), ("swish", max(0.0, duration - HANDOFF), 0.0)]
    return sorted(events, key=lambda e: e[1]), spoken

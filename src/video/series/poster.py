"""«Hecho con Claude» · poster (STEP 78 §5): an editorial poster. The wrong form, huge and black,
crossed out by a red bar; the right form in a red block; the examples under it.

The reference is _audit/series/reference/estilo_poster.jpg: white paper with a faint column grid,
a header rule, display type in Inter's black weight set to the width (long lines step down),
the red «SE DICE» block, a footer with «ERROR Nº …» and the page counter. Moved to the safe areas:
the header under the top 8 %, everything readable above the bottom 22 %. Timed on the beats:

    0 s             the hook as the poster's red kicker, `big_wrong` already set (the thumbnail)
    the wrong form  the red bar wipes across `big_wrong`
    the right form  the red block slides up with `big_right`
    each example    its line comes in when the voice says it
    the last beat   the challenge card, over the dimmed poster
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ..motion import clamp01, ease_out_cubic
from ..notebook import kit
from . import series_kit as K
from .mensajes import _place, phrase_time

PAPER = (255, 255, 255, 255)
GRID = (238, 238, 238, 255)
INK = (14, 14, 14, 255)
RED = (226, 52, 40, 255)
GREY = (128, 128, 128, 255)

X0, X1 = 60, 1020                      # the poster's column
HEADER_Y = 168
RULE_Y = 214
KICKER_Y = 236
BLOCK_W = 900                          # the red block: x 60..960, its text left of the rail (940)
BLOCK_TEXT_W = 820
EX_W = 860                             # examples: x 60..920
BOTTOM = K.SAFE_BOTTOM - 8


# ── display lines (STEP 78b §1) ──────────────────────────────────────

SEPARATORS = {"/", "→", "=", "≠", "—"}
#: A line holding only one word this short reads as a widow («IN», «OF»).
SHORT_WORD = 3


@lru_cache(maxsize=1024)
def display_lines(text: str, size: int, width: int, max_lines: int) -> Optional[Tuple[str, ...]]:
    """The display type's lines at `size`, or None when nothing valid fits `width`.

    Valid: every line fits; no line starts with a separator (/ → = ≠ —) or is one; no line is a
    lone short word. Best: fewest lines, then breaks right after separators, then the most even
    line lengths."""
    from itertools import combinations
    f = K.font("inter_black", size)
    words = text.split()
    n = len(words)
    best, best_key = None, None
    for k in range(1, min(max_lines, n) + 1):
        for cuts in combinations(range(1, n), k - 1):
            bounds = (0, *cuts, n)
            lines = [words[a:b] for a, b in zip(bounds, bounds[1:])]
            if any(line[0] in SEPARATORS for line in lines):
                continue
            if k > 1 and any(len(line) == 1 and len(line[0].strip(".,;:!?¡¿")) <= SHORT_WORD for line in lines):
                continue
            texts = [" ".join(line) for line in lines]
            widths = [K.length(x, f) for x in texts]
            if max(widths) > width:
                continue
            off_sep = sum(1 for c in cuts if words[c - 1] not in SEPARATORS)
            key = (k, off_sep if any(w in SEPARATORS for w in words) else 0, max(widths) - min(widths))
            if best_key is None or key < best_key:
                best, best_key = tuple(texts), key
        if best is not None:
            return best
    return None


# ── layout ───────────────────────────────────────────────────────────

def layout(script: Dict) -> Dict:
    """Budgeted from the bottom up: the examples and the red block against the safe area's
    bottom, then the display type takes the room left above them (long lines step down)."""
    po = script["poster"]
    kicker = K.fit(script["hook_text"], "inter", X1 - X0, 44, 30, 2)
    wrong_top = KICKER_Y + K.line_height(kicker[0], "inter") * len(kicker[1]) + 30
    right = next(((sz, ln) for sz in range(120, 50, -2)
                  for ln in [display_lines(po["big_right"], sz, BLOCK_TEXT_W, 2)] if ln), None)
    if right is None:
        raise K.Overflow(f"{script['id']}: big_right {po['big_right']!r} does not fit the block")
    block_h = 30 + 40 + 16 + K.line_height(right[0], "inter_black") * len(right[1]) + 34
    examples, ex_h = [], 0
    for e in po["examples"]:
        eng, _sep, es = e.partition(" — ")
        s_eng = K.fit(eng, "inter", EX_W, 34, 24, 2)
        s_es = K.fit(es, "inter", EX_W, 28, 22, 2) if es else None
        h = K.line_height(s_eng[0], "inter") * len(s_eng[1]) + (K.line_height(s_es[0], "inter") * len(s_es[1]) if s_es else 0)
        examples.append({"eng": s_eng, "es": s_es, "h": h})
        ex_h += h + 14
    block_top = min(980, BOTTOM - (block_h + 26 + ex_h - 14))
    y = block_top + block_h + 26
    for e in examples:
        e["y"] = y
        y += e["h"] + 14
    # the display type: as big as fits above the block; full width only above the rail's y 950
    limit = block_top - 26
    width = X1 - X0 if limit <= 950 else 880
    for size in range(190, 64, -6):
        lines = display_lines(po["big_wrong"], size, width, 4)
        if lines is None:
            continue
        if wrong_top + K.line_height(size, "inter_black") * len(lines) <= limit:
            break
    else:
        raise K.Overflow(f"{script['id']}: big_wrong {po['big_wrong']!r} does not fit above the block")
    # a long word caps the display size: close half the hole under it, so it does not gape
    gap = limit - (wrong_top + K.line_height(size, "inter_black") * len(lines))
    if gap > 90:
        lift = int((gap - 90) / 2)
        block_top -= lift
        for e in examples:
            e["y"] -= lift
    return {"kicker": kicker, "wrong": (size, lines), "wrong_top": wrong_top, "right": right, "block_top": block_top,
            "block_h": block_h, "examples": examples, "challenge": K.challenge_layout(script["challenge"]["prompt"], 560)}


def times(script: Dict, tl: Dict) -> Dict:
    beats = tl["beats"]
    po = script["poster"]
    first_explain = beats[min(1, len(beats) - 1)]["start"]
    wrong = phrase_time(tl, script["correction"]["wrong"]) or phrase_time(tl, po["big_wrong"])
    bar = max(0.8, min(wrong if wrong is not None else first_explain, first_explain))
    right = phrase_time(tl, script["correction"]["right"]) or phrase_time(tl, po["big_right"])
    block = max(bar + 0.8, right if right is not None else bar + 1.5)
    ex = []
    for k, e in enumerate(po["examples"]):
        at = phrase_time(tl, e.partition(" — ")[0])
        ex.append(max(block + 0.6 + 0.5 * k, at if at is not None else block + 1.2 + 1.2 * k))
    return {"bar": bar, "block": block, "examples": ex, "challenge": beats[-1]["start"]}


# ── drawing ──────────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _paper(level_label: str) -> Image.Image:
    img = Image.new("RGBA", (K.W, K.H), PAPER)
    d = ImageDraw.Draw(img)
    for x in range(X0, K.W, 160):
        d.line([(x, 0), (x, K.H)], fill=GRID, width=2)
    d.text((X0, HEADER_Y), "ENGLISH UNLIMITED", font=K.font("inter", 30), fill=INK)
    f = K.font("inter", 30)
    d.text((X1 - f.getlength(level_label.upper()), HEADER_Y), level_label.upper(), font=f, fill=RED)
    d.line([(X0, RULE_Y), (X1, RULE_Y)], fill=INK, width=4)
    return img


@lru_cache(maxsize=16)
def _wrong_type(lines: Tuple[str, ...], size: int) -> Image.Image:
    lh = K.line_height(size, "inter_black")
    img = Image.new("RGBA", (X1 - X0 + 20, lh * len(lines) + 20), (0, 0, 0, 0))
    K.text_block(img, lines, "inter_black", size, 0, 0, INK)
    return img


def _bar(img: Image.Image, lay: Dict, p: float) -> None:
    """The red bar, wiped in from the top left across the display type (p of the way)."""
    if p <= 0:
        return
    size, lines = lay["wrong"]
    top = lay["wrong_top"]
    bottom = top + K.line_height(size, "inter_black") * len(lines)
    a = (-20, top + (bottom - top) * 0.12)
    b = (K.W + 20, bottom - (bottom - top) * 0.05)
    end = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
    width = max(46, int(size * 0.42))
    kit.paint(img, kit._bbox((a, end), width), lambda d, at, k: d.line([at(*a), at(*end)], fill=RED, width=int(width * k)),
              ("poster_bar", round(p, 3), a, b, width))


@lru_cache(maxsize=16)
def _block(lines: Tuple[str, ...], size: int, h: int) -> Image.Image:
    img = Image.new("RGBA", (BLOCK_W, h), RED)
    d = ImageDraw.Draw(img)
    d.text((40, 30), "SE DICE", font=K.font("inter", 36), fill=PAPER)
    K.text_block(img, lines, "inter_black", size, 40, 30 + 40 + 16, PAPER)
    return img


@lru_cache(maxsize=1)
def _print_grain() -> Tuple[Image.Image, ...]:
    """Four tiles of ink grain over the paper, cycled 8 times a second: a printed poster is never
    perfectly still (STEP 78b §1, no still stretch over 4 s)."""
    tiles = []
    for k in range(4):
        a = np.random.default_rng(70 + k).integers(0, 14, (K.H, K.W), dtype=np.uint8)
        rgba = np.zeros((K.H, K.W, 4), np.uint8)
        rgba[..., :3] = 40
        rgba[..., 3] = a
        tiles.append(Image.fromarray(rgba))
    return tuple(tiles)


def frame(t: float, script: Dict, tl: Dict) -> Image.Image:
    lay, tm = layout(script), times(script, tl)
    img = _paper(script["level_label"]).copy()
    img.alpha_composite(_print_grain()[int(t * 8) % 4])
    ks, kl = lay["kicker"]
    K.text_block(img, kl, "inter", ks, X0, KICKER_Y, RED)
    ws, wl = lay["wrong"]
    img.alpha_composite(_wrong_type(wl, ws), (X0, int(lay["wrong_top"])))
    if t >= tm["bar"]:
        _bar(img, lay, ease_out_cubic(clamp01((t - tm["bar"]) / 0.35)))
    if t >= tm["block"]:
        p = ease_out_cubic(clamp01((t - tm["block"]) / 0.45))
        rs, rl = lay["right"]
        block = _block(rl, rs, int(lay["block_h"]))
        y = lay["block_top"] + (1 - p) * 420
        kit._composite_clipped(img, block, X0, int(round(y)))
    for e, at in zip(lay["examples"], tm["examples"]):
        if t < at:
            continue
        a = clamp01((t - at) / 0.3)
        y = e["y"] + (1 - ease_out_cubic(a)) * 24
        s_eng, l_eng = e["eng"]
        K.text_block(img, l_eng, "inter", s_eng, X0, y, INK, alpha=a)
        if e["es"]:
            s_es, l_es = e["es"]
            K.text_block(img, l_es, "inter", s_es, X0, y + K.line_height(s_eng, "inter") * len(l_eng), GREY, alpha=a)
    # footer, in the bottom band (decoration: the platforms' captions may cover it)
    page = 1 if t < tm["block"] else (2 if t < tm["challenge"] else 3)
    d = ImageDraw.Draw(img)
    d.line([(X0, 1660), (X1, 1660)], fill=INK, width=4)
    f = K.font("inter", 30)
    d.text((X0, 1680), f"ERROR Nº {script['poster']['error_no']}", font=f, fill=RED)
    counter = f"{page:02d} / 03"
    d.text((X1 - f.getlength(counter), 1680), counter, font=f, fill=INK)
    if t >= tm["challenge"]:
        p = clamp01((t - tm["challenge"]) / 0.4)
        img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(140 * p))))
        K.challenge_card(img, script["challenge"]["prompt"], lay["challenge"]["y"], p)
    return img


def sfx_events(script: Dict, tl: Dict) -> List[Tuple[str, float, float]]:
    tm = times(script, tl)
    ev = [("swish", 0.0, 0.0), ("scratch", tm["bar"], 0.35), ("swish", tm["block"], 0.0)]
    ev += [("pop", at, 0.0) for at in tm["examples"]] + [("pop", tm["challenge"], 0.0)]
    return sorted(ev, key=lambda e: e[1])


def text_boxes(script: Dict) -> List[Tuple[str, K.Box]]:
    lay = layout(script)
    ks, kl = lay["kicker"]
    out = [("hook", K.block_box(kl, "inter", ks, X0, KICKER_Y))]
    ws, wl = lay["wrong"]
    out.append(("big_wrong", K.block_box(wl, "inter_black", ws, X0, lay["wrong_top"])))
    rs, rl = lay["right"]
    out.append(("big_right", K.block_box(rl, "inter_black", rs, X0 + 40, lay["block_top"] + 86)))
    for k, e in enumerate(lay["examples"]):
        s_eng, l_eng = e["eng"]
        box = K.block_box(l_eng, "inter", s_eng, X0, e["y"])
        if e["es"]:
            s_es, l_es = e["es"]
            b2 = K.block_box(l_es, "inter", s_es, X0, e["y"] + K.line_height(s_eng, "inter") * len(l_eng))
            box = (box[0], box[1], max(box[2], b2[2]), b2[3])
        out.append((f"example {k + 1}", box))
    return out + [("challenge", lay["challenge"]["box"])]

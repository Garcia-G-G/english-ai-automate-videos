"""«Hecho con Claude» · comic (STEP 78 §6): a quick quiz, three options, a 3-second countdown.

The references are _audit/series/reference/fotograma_1..3.jpg: a yellow halftone ground with speed
lines, white speech cards with an ink outline and a hard shadow, option cards A/B/C, a countdown
ring, a red «¡NO!» stamp, and Bubi reacting (the brand guide's expressions, cut out by
tools/extract_bubi_expressions.py: «wow», «¡lo lograste!»). Timed on the beats:

    0 s            the hook in a speech card (frame 0 is the thumbnail), Bubi surprised
    the question   the card turns into `quiz.prompt`; each option pops in as the voice says it
    the countdown  3, 2, 1 in a ring, in the 3 s of room tone the timeline left for it
    the reveal     «¡NO!» stamped on the wrong options, the right one ringed; Bubi happy
    then           `quiz.after` as a sticky; the challenge card on the last beat
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ..motion import clamp01, ease_out_back, ease_out_cubic
from ..notebook import kit
from . import series_kit as K
from .mensajes import _place, phrase_time

YELLOW = (248, 204, 69)
INK = kit.colour("ink")
WHITE = (255, 255, 255, 255)
BLUE = kit.colour("english_blue")
RED = (222, 56, 46, 255)
GREEN = kit.colour("correct")
EXPRESSIONS = Path(__file__).resolve().parents[3] / "assets" / "branding" / "english-unlimited" / "expresiones"

BAR_Y = 168
CHIP_Y = 198
CARD_Y = 286                             # the hook card; the question and options cascade under it
CARD_W = 760
HOOK_W = 640
OPT_H = 104
OPT_GAP = 22
OPT_W = 600
OPT_X = 110
STICKY_W = 600
BUBI_W = 300
BUBI_C = (884, 1330)
LETTERS = "ABC"


# ── layout ───────────────────────────────────────────────────────────

def layout(script: Dict) -> Dict:
    """Top to bottom (STEP 78b §1: frame 0 shows the hook, the question and the three options):
    the hook card, the question card, the options, the countdown ring beside them, the sticky."""
    q = script["quiz"]
    hook = K.fit(script["hook_text"], "fredoka", HOOK_W - 70, 52, 34, 2)
    prompt = K.fit(q["prompt"], "fredoka", CARD_W - 80, 56, 36, 3)
    options = [K.fit(o, "fredoka", OPT_W - 140, 48, 28, 2) for o in q["options"]]
    card_h = lambda fit, pad=60: K.line_height(fit[0], "fredoka") * len(fit[1]) + pad
    hook_box = ((K.W - HOOK_W) / 2, CARD_Y, (K.W + HOOK_W) / 2, CARD_Y + card_h(hook, 50))
    prompt_box = ((K.W - CARD_W) / 2, hook_box[3] + 26, (K.W + CARD_W) / 2, hook_box[3] + 26 + card_h(prompt))
    opt_boxes, y = [], prompt_box[3] + 34
    for size, lines in options:
        h = max(OPT_H, K.line_height(size, "fredoka") * len(lines) + 36)
        opt_boxes.append((OPT_X, y, OPT_X + OPT_W, y + h))
        y += h + OPT_GAP
    after_y = y + 6
    after = K.fit(q["after"], "fredoka", STICKY_W - 60, 38, 24, max(1, int((K.SAFE_BOTTOM - 8 - after_y - 50) // 30)))
    after_h = K.line_height(after[0], "fredoka") * len(after[1]) + 50
    ring_c = (OPT_X + OPT_W + 150, round((opt_boxes[0][1] + opt_boxes[-1][3]) / 2))
    return {"hook": hook, "prompt": prompt, "options": options, "opt_boxes": opt_boxes, "after": after,
            "after_box": (70, after_y, 70 + STICKY_W, after_y + after_h), "ring_c": ring_c,
            "hook_box": hook_box, "prompt_box": prompt_box,
            "challenge": K.challenge_layout(script["challenge"]["prompt"], 560)}


def times(script: Dict, tl: Dict) -> Dict:
    beats = tl["beats"]
    q = script["quiz"]
    cd = tl.get("countdown")
    prompt = max(1.6, phrase_time(tl, q["prompt"]) or beats[0]["start"] + 0.6)
    opts = []
    for k, o in enumerate(q["options"]):
        at = phrase_time(tl, o)
        opts.append(max(prompt + 0.4 + 0.25 * k, at if at is not None else prompt + 0.8 + 0.6 * k))
    if cd:
        count0, reveal = cd
    else:                                            # no countdown left in the timeline: after the options
        count0 = opts[-1] + 0.8
        reveal = count0 + 3.0
    reveal = max(reveal, opts[-1] + 0.5)
    return {"prompt": prompt, "options": opts, "count0": count0, "reveal": reveal, "after": reveal + 1.2,
            "challenge": max(reveal + 2.0, beats[-1]["start"])}


# ── drawing ──────────────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _ground() -> Image.Image:
    """Yellow, speed lines from below centre, a halftone of dots stronger at the edges."""
    h, w = K.H, K.W
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w / 2, h * 0.62
    ang = np.arctan2(yy - cy, xx - cx)
    rays = (np.sin(ang * 36) > 0.55).astype(float) * 0.10
    base = np.array(YELLOW, float)[None, None, :] * (1 - rays[..., None]) + 255 * rays[..., None]
    d = np.hypot(xx - cx, yy - cy) / np.hypot(cx, cy)
    cell = 22
    gx, gy = (xx % cell) - cell / 2, (yy % cell) - cell / 2
    dots = (np.hypot(gx, gy) < (2.0 + 4.0 * d)).astype(float) * 0.10
    rgb = base * (1 - dots[..., None]) + np.array((214, 160, 30))[None, None, :] * dots[..., None]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=8)
def _expression(name: str, width: int) -> Image.Image:
    img = Image.open(EXPRESSIONS / f"{name}.png").convert("RGBA")
    return img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)


@lru_cache(maxsize=16)
def _speech(lines: Tuple[str, ...], size: int, width: int, colour_last: bool) -> Image.Image:
    h = K.line_height(size, "fredoka") * len(lines) + 70
    card = kit.note_card(width, h, WHITE, 6, (12, 12)).copy()
    for k, line in enumerate(lines):
        fill = BLUE if colour_last and k == len(lines) - 1 and len(lines) > 1 else INK
        K.text_block(card, [line], "fredoka", size, 0, 34 + k * K.line_height(size, "fredoka"), fill, "center", width)
    return card.rotate(2.5, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=16)
def _option(letter: str, lines: Tuple[str, ...], size: int, w: int, h: int) -> Image.Image:
    card = kit.note_card(w, h, WHITE, 5, (10, 10)).copy()
    d = ImageDraw.Draw(card)
    f = K.font("fredoka", 56)
    top, bottom = f.getbbox("Hx")[1], f.getbbox("Hx")[3]
    d.text((34, h / 2 - (top + bottom) / 2), letter, font=f, fill=BLUE)
    lh = K.line_height(size, "fredoka")
    K.text_block(card, lines, "fredoka", size, 110, h / 2 - lh * len(lines) / 2 + 2, INK)
    return card


def _stamp_cx(x1: float) -> float:
    """Beside the option, overlapping only its edge: never over the option's words."""
    return x1 + _stamp().width / 2 - 24


@lru_cache(maxsize=2)
def _stamp() -> Image.Image:
    f = K.font("fredoka", 72)
    w, h = int(f.getlength("¡NO!")) + 60, 120
    S = kit.SS
    big = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([4 * S, 4 * S, (w - 4) * S, (h - 4) * S], radius=18 * S, outline=RED, width=8 * S)
    img = big.resize((w, h), Image.LANCZOS)
    K.text_block(img, ["¡NO!"], "fredoka", 72, 0, 18, RED, "center", w)
    return img.rotate(12, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=8)
def _chip(text: str, fill: Tuple[int, ...], ink: Tuple[int, ...], size: int = 28) -> Image.Image:
    f = K.font("fredoka", size)
    w, h = int(f.getlength(text)) + 44, size + 30
    card = kit.note_card(w, h, fill, 3, (5, 5)).copy()
    K.text_block(card, [text], "fredoka", size, 0, 13, ink, "center", w)
    return card


def _bump(t: float, at: float, length: float = 0.35, amount: float = 0.12) -> float:
    """A pop from the visible state: up by `amount` and back, over `length` from `at`."""
    if not at <= t < at + length:
        return 0.0
    return round(amount * math.sin(math.pi * (t - at) / length), 3)


def _countdown(img: Image.Image, t: float, count0: float, reveal: float, ring_c) -> None:
    span = max(0.5, reveal - count0)
    n = 3 - int((t - count0) / (span / 3))
    p = ((t - count0) % (span / 3)) / (span / 3)
    r = 72
    disc = Image.new("RGBA", (2 * r * kit.SS, 2 * r * kit.SS), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([0, 0, 2 * r * kit.SS - 1, 2 * r * kit.SS - 1], fill=WHITE, outline=INK, width=6 * kit.SS)
    img.alpha_composite(disc.resize((2 * r, 2 * r), Image.LANCZOS), (ring_c[0] - r, ring_c[1] - r))
    K.ring(img, (ring_c[0] - r + 12, ring_c[1] - r + 12, ring_c[0] + r - 12, ring_c[1] + r - 12), 1.0 - p,
           (248, 190, 40, 255), 12)
    K.text_block(img, [str(max(1, n))], "fredoka", 76, ring_c[0] - r, ring_c[1] - 48, INK, "center", 2 * r)


def frame(t: float, script: Dict, tl: Dict) -> Image.Image:
    lay, tm = layout(script), times(script, tl)
    img = _ground().copy()
    d = ImageDraw.Draw(img)
    # progress, level, brand
    total = tl["duration"]
    d.rounded_rectangle([60, BAR_Y, K.W - 60, BAR_Y + 14], radius=7, fill=INK)
    d.rounded_rectangle([64, BAR_Y + 3, 64 + (K.W - 128) * clamp01(t / total), BAR_Y + 11], radius=4, fill=(255, 226, 120, 255))
    lvl = _chip(script["level_label"], INK[:3] + (255,), (255, 255, 255, 255))
    img.alpha_composite(lvl, (60, CHIP_Y))
    brand = _chip("English Unlimited", BLUE, (255, 255, 255, 255), 24)
    img.alpha_composite(brand, (K.W - 60 - brand.width, CHIP_Y + 4))

    # the hook card, then the question under it: both on screen from frame 0, the question
    # popping when the voice asks it
    size, lines = lay["hook"]
    _place(img, _speech(lines, size, HOOK_W, False), K.W / 2, (lay["hook_box"][1] + lay["hook_box"][3]) / 2, 1.0)
    size, lines = lay["prompt"]
    _place(img, _speech(lines, size, CARD_W, True), K.W / 2, (lay["prompt_box"][1] + lay["prompt_box"][3]) / 2,
           1.0 + _bump(t, tm["prompt"]))

    # the options; the countdown; the reveal
    q = script["quiz"]
    for k, (fit, box, at) in enumerate(zip(lay["options"], lay["opt_boxes"], tm["options"])):
        x0, y0, x1, y1 = box
        _place(img, _option(LETTERS[k], fit[1], fit[0], int(x1 - x0), int(y1 - y0)), (x0 + x1) / 2 + 5, (y0 + y1) / 2 + 5,
               1.0 + _bump(t, at))
        if t >= tm["reveal"]:
            if k == q["answer"]:
                K.ring(img, (x0 - 26, y0 - 22, x1 + 26, y1 + 22), (t - tm["reveal"]) / 0.5, GREEN, 10)
            else:
                ps = clamp01((t - tm["reveal"] - 0.1 * k) / 0.25)
                if ps > 0:
                    _place(img, _stamp(), _stamp_cx(x1), (y0 + y1) / 2, 1.0 + 0.6 * (1 - ease_out_back(ps, 1.8)), clamp01(ps * 3))
    if tm["count0"] <= t < tm["reveal"]:
        _countdown(img, t, tm["count0"], tm["reveal"], lay["ring_c"])

    if t >= tm["after"]:
        p = clamp01((t - tm["after"]) / 0.35)
        size, lines = lay["after"]
        box = lay["after_box"]
        note = kit.note_card(int(box[2] - box[0]), int(box[3] - box[1]), (242, 214, 107, 255), 4, (8, 8)).copy()
        K.text_block(note, lines, "fredoka", size, 30, 24, INK)
        _place(img, note.rotate(-2, resample=Image.BICUBIC, expand=True), (box[0] + box[2]) / 2, (box[1] + box[3]) / 2,
               0.7 + 0.3 * ease_out_back(p, 2.0), clamp01(p * 3))

    # Bubi: surprised, then happy at the reveal (a hop as he changes)
    name = "lo_lograste" if t >= tm["reveal"] else "wow"
    since = t - (tm["reveal"] if t >= tm["reveal"] else 0.0)
    hop = 40 * math.sin(math.pi * clamp01(since / 0.4)) if since < 0.4 else 0.0
    shake = 6 * math.sin(t * 9) if name == "wow" else 0.0
    breath = 1.0 + 0.015 * math.sin(t * 2 * math.pi / 2.4)            # a slow breath (STEP 78b §1)
    bubi = _expression(name, BUBI_W)
    bubi = bubi.resize((round(bubi.width * breath), round(bubi.height * breath)), Image.LANCZOS)
    img.alpha_composite(bubi, (int(BUBI_C[0] - bubi.width / 2 + shake), int(BUBI_C[1] - bubi.height / 2 - hop)))

    if t >= tm["challenge"]:
        p = clamp01((t - tm["challenge"]) / 0.4)
        img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(140 * p))))
        K.challenge_card(img, script["challenge"]["prompt"], lay["challenge"]["y"], p)
    return img


def sfx_events(script: Dict, tl: Dict) -> List[Tuple[str, float, float]]:
    tm = times(script, tl)
    ev = [("swish", 0.0, 0.0), ("pop", tm["prompt"], 0.0)] + [("pop", at, 0.0) for at in tm["options"]]
    span = tm["reveal"] - tm["count0"]
    ev += [("pop", tm["count0"] + span * k / 3, 0.0) for k in range(3)]
    ev += [("clap", tm["reveal"], 0.0), ("pop", tm["after"], 0.0), ("pop", tm["challenge"], 0.0)]
    return sorted(ev, key=lambda e: e[1])


def text_boxes(script: Dict) -> List[Tuple[str, K.Box]]:
    lay = layout(script)
    out = [("hook", lay["hook_box"]), ("prompt", lay["prompt_box"])]
    out += [(f"option {LETTERS[k]}", b) for k, b in enumerate(lay["opt_boxes"])]
    sw, sh = _stamp().size
    out += [(f"stamp {LETTERS[k]}", (_stamp_cx(b[2]) - sw / 2, (b[1] + b[3]) / 2 - sh / 2,
                                     _stamp_cx(b[2]) + sw / 2, (b[1] + b[3]) / 2 + sh / 2))
            for k, b in enumerate(lay["opt_boxes"]) if k != script["quiz"]["answer"]]
    return out + [("after", lay["after_box"]), ("challenge", lay["challenge"]["box"])]

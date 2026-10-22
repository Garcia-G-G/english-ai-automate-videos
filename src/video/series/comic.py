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
CARD_Y = 300
CARD_W = 760
OPT_Y = 610
OPT_H = 112
OPT_GAP = 26
OPT_W = 640
OPT_X = 110
RING_C = (900, 690)                      # the countdown ring, right of the options (above y 950)
STICKY_Y = 1030
STICKY_W = 600
BUBI_W = 330
BUBI_C = (858, 1270)
LETTERS = "ABC"


# ── layout ───────────────────────────────────────────────────────────

def layout(script: Dict) -> Dict:
    q = script["quiz"]
    hook = K.fit(script["hook_text"], "fredoka", CARD_W - 80, 74, 44, 3)
    prompt = K.fit(q["prompt"], "fredoka", CARD_W - 80, 64, 40, 3)
    options = [K.fit(o, "fredoka", OPT_W - 150, 52, 30, 2) for o in q["options"]]
    after = K.fit(q["after"], "fredoka", STICKY_W - 60, 40, 26, 6)
    after_h = K.line_height(after[0], "fredoka") * len(after[1]) + 50
    opt_boxes = []
    y = OPT_Y
    for size, lines in options:
        h = max(OPT_H, K.line_height(size, "fredoka") * len(lines) + 40)
        opt_boxes.append((OPT_X, y, OPT_X + OPT_W, y + h))
        y += h + OPT_GAP
    card_h = lambda fit: K.line_height(fit[0], "fredoka") * len(fit[1]) + 70
    return {"hook": hook, "prompt": prompt, "options": options, "opt_boxes": opt_boxes, "after": after,
            "after_box": (70, STICKY_Y, 70 + STICKY_W, STICKY_Y + after_h),
            "hook_box": ((K.W - CARD_W) / 2, CARD_Y, (K.W + CARD_W) / 2, CARD_Y + card_h(hook)),
            "prompt_box": ((K.W - CARD_W) / 2, CARD_Y, (K.W + CARD_W) / 2, CARD_Y + card_h(prompt)),
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


def _countdown(img: Image.Image, t: float, count0: float, reveal: float) -> None:
    span = max(0.5, reveal - count0)
    n = 3 - int((t - count0) / (span / 3))
    p = ((t - count0) % (span / 3)) / (span / 3)
    r = 72
    disc = Image.new("RGBA", (2 * r * kit.SS, 2 * r * kit.SS), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([0, 0, 2 * r * kit.SS - 1, 2 * r * kit.SS - 1], fill=WHITE, outline=INK, width=6 * kit.SS)
    img.alpha_composite(disc.resize((2 * r, 2 * r), Image.LANCZOS), (RING_C[0] - r, RING_C[1] - r))
    K.ring(img, (RING_C[0] - r + 12, RING_C[1] - r + 12, RING_C[0] + r - 12, RING_C[1] + r - 12), 1.0 - p,
           (248, 190, 40, 255), 12)
    K.text_block(img, [str(max(1, n))], "fredoka", 76, RING_C[0] - r, RING_C[1] - 48, INK, "center", 2 * r)


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

    # the speech card: the hook, then the question
    if t < tm["prompt"]:
        size, lines = lay["hook"]
        _place(img, _speech(lines, size, CARD_W, False), K.W / 2, (lay["hook_box"][1] + lay["hook_box"][3]) / 2, 1.0)
    else:
        p = clamp01((t - tm["prompt"]) / 0.3)
        size, lines = lay["prompt"]
        _place(img, _speech(lines, size, CARD_W, True), K.W / 2, (lay["prompt_box"][1] + lay["prompt_box"][3]) / 2,
               0.85 + 0.15 * ease_out_back(p, 2.2))

    # the options; the countdown; the reveal
    q = script["quiz"]
    for k, (fit, box, at) in enumerate(zip(lay["options"], lay["opt_boxes"], tm["options"])):
        if t < at:
            continue
        p = clamp01((t - at) / 0.3)
        x0, y0, x1, y1 = box
        _place(img, _option(LETTERS[k], fit[1], fit[0], int(x1 - x0), int(y1 - y0)), (x0 + x1) / 2 + 5, (y0 + y1) / 2 + 5,
               0.6 + 0.4 * ease_out_back(p, 2.4), clamp01(p * 3))
        if t >= tm["reveal"]:
            if k == q["answer"]:
                K.ring(img, (x0 - 26, y0 - 22, x1 + 26, y1 + 22), (t - tm["reveal"]) / 0.5, GREEN, 10)
            else:
                ps = clamp01((t - tm["reveal"] - 0.1 * k) / 0.25)
                if ps > 0:
                    _place(img, _stamp(), x1 - 40, (y0 + y1) / 2, 1.0 + 0.6 * (1 - ease_out_back(ps, 1.8)), clamp01(ps * 3))
    if tm["count0"] <= t < tm["reveal"]:
        _countdown(img, t, tm["count0"], tm["reveal"])

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
    bubi = _expression(name, BUBI_W)
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
    return out + [("after", lay["after_box"]), ("challenge", lay["challenge"]["box"])]

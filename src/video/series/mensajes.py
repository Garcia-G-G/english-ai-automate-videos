"""«Hecho con Claude» · mensajes (STEP 78 §3): a chat that goes wrong, then the correction.

The reference is _audit/series/reference/estilo_mensajes.jpg: a generic dark messenger (no app
name, no real logo; the input reads «Mensaje»), the contact in the header, «them» bubbles grey on
the left and «me» bubbles blue on the right. Timed on the voice's beats:

    0 s            the whole chat, the error included, under the hook card (frame 0 is the
                   thumbnail; STEP 79 §0)
    1.5 s → beat 1 each message pops as the voice reaches it
    the wrong form  a red ring drawn round the error message, then an arrow drawn on
    the right form  the «Se dice: …» card drops in, the rule sticky after it
    the last beat   the challenge card, over the dimmed chat
"""
from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from ..motion import clamp01, ease_out_back, ease_out_cubic
from ..notebook import kit
from . import series_kit as K

BG = (11, 10, 15, 255)
HEADER = (28, 28, 32, 255)
THEM = (40, 40, 46, 255)
ME = (10, 132, 255, 255)
WHITE = (255, 255, 255, 255)
GREY = (142, 142, 150, 255)
RED = (230, 60, 50, 255)
AVATAR = (238, 122, 92, 255)

HEADER_Y0, HEADER_Y1 = 110, 300
CHAT_TOP = 470                      # under the hook card (y 314..~454)
HOOK_Y = HEADER_Y1 + 14
HOOK_W = 900
CHAT_BOTTOM = 940                   # above the button rail's reach (y 950) and the cards
BUBBLE_MAX = 700
BUBBLE_FACE, BUBBLE_SIZE, BUBBLE_MIN = "manrope", 42, 32
PAD_X, PAD_Y = 30, 20
GAP, GAP_SAME = 26, 12
MARGIN = 50
HOOK_TO = 1.5                        # the hook banner, alone, until then
POP = 0.25
CARD_Y = 1080                        # «Se dice» card, top, at the latest
CARD_UNDER_CHAT = 110                # ...or this far under the chat's last bubble (room for the arrow)
CARD_W = 790                         # x 145..935: left of the rail (STEP 77 §4)
STICKY_GAP = 34


def _norm_tokens(text: str) -> List[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9']+", text)


def phrase_time(tl: Dict, target: str) -> Optional[float]:
    """When the voice says the [[English]] phrase closest to `target` (half its words, or more)."""
    want = set(_norm_tokens(target))
    best, when = 0.0, None
    for beat in tl["beats"]:
        for e in beat["english"]:
            got = set(_norm_tokens(e["text"]))
            if got and want:
                score = len(got & want) / len(got | want)
                if score > best:
                    best, when = score, e["start"]
    return when if best >= 0.5 else None


# ── layout (pure; the tests read it) ─────────────────────────────────

@lru_cache(maxsize=64)
def _bubble_layout(messages: Tuple[Tuple[str, ...], ...]) -> Tuple[int, List[Dict]]:
    """(size, [{who, lines, box}]) for the chat, at the largest bubble size that fits it."""
    for size in range(BUBBLE_SIZE, BUBBLE_MIN - 1, -2):
        f = K.font(BUBBLE_FACE, size)
        lh = int(size * 1.32)
        y, out, prev = CHAT_TOP, [], None
        for m in messages:
            who, text = m[0], m[1]
            lines = K.wrap(text, f, BUBBLE_MAX - 2 * PAD_X)
            w = max(K.length(x, f) for x in lines) + 2 * PAD_X
            h = lh * len(lines) + 2 * PAD_Y
            y += (GAP_SAME if prev == who else GAP) if out else 0
            x0 = MARGIN if who == "them" else K.W - MARGIN - w
            out.append({"who": who, "lines": tuple(lines), "box": (x0, y, x0 + w, y + h), "error": len(m) == 3,
                        "size": size, "lh": lh})
            y += h
            prev = who
        if y <= CHAT_BOTTOM:
            return size, out
    raise K.Overflow(f"the chat does not fit {CHAT_BOTTOM - CHAT_TOP}px at {BUBBLE_MIN}px")


def layout(script: Dict) -> Dict:
    msgs = tuple(tuple(m) for m in script["chat"]["messages"])
    size, bubbles = _bubble_layout(msgs)
    hook_size, hook_lines = K.fit(script["hook_text"], "fredoka", HOOK_W - 80, 44, 30, 2)
    right = script["correction"]["right"]
    card_size, card_lines = K.fit(f"Se dice: {right}", "fredoka", CARD_W - 80, 62, 40, 2)
    rule_size, rule_lines = K.fit(script["correction"]["rule"], "fredoka", 680, 42, 30, 2)
    card_h = K.line_height(card_size, "fredoka") * len(card_lines) + 70
    rule_h = K.line_height(rule_size, "fredoka") * len(rule_lines) + 50
    card_y = min(CARD_Y, bubbles[-1]["box"][3] + CARD_UNDER_CHAT)          # STEP 79 §0: no dead gap
    card_box = (K.W / 2 - CARD_W / 2, card_y, K.W / 2 + CARD_W / 2, card_y + card_h)
    rule_box = (K.W / 2 - 370, card_box[3] + STICKY_GAP, K.W / 2 + 370, card_box[3] + STICKY_GAP + rule_h)
    # The chat may scroll up (STEP 79 §0) until the error bubble's top meets the header.
    error_top = next((b["box"][1] for b in bubbles if b["error"]), bubbles[-1]["box"][1])
    max_lift = max(0, error_top - (HEADER_Y1 + 46))          # the ring round it stays whole
    return {"bubbles": bubbles, "size": size, "hook": (hook_size, hook_lines), "card": (card_size, card_lines, card_box),
            "rule": (rule_size, rule_lines, rule_box), "max_lift": max_lift,
            "challenge": K.challenge_layout(script["challenge"]["prompt"], 560)}


def _stack(rule_bottom: float) -> Tuple[float, int]:
    """(top, slots) of the example stack under a rule sticky ending at `rule_bottom`."""
    top = rule_bottom + 30
    return top, max(0, int((K.SAFE_BOTTOM - 8 - top + EX_GAP) // (EX_H + EX_GAP)))


def scroll_plan(script: Dict, tl: Dict) -> Dict:
    """How far the chat scrolls for the examples: enough for them all (up to MAX_SHOWN), never
    past the error bubble; and where the stack then sits, in the lower half."""
    lay = layout(script)
    n = min(len(examples(script, tl)), MAX_SHOWN)
    rule_bottom = lay["rule"][2][3]
    top, slots = _stack(rule_bottom)
    need = max(0, n - slots) * (EX_H + EX_GAP)
    lift = min(need, lay["max_lift"])
    top, slots = _stack(rule_bottom - lift)
    return {"lift": lift, "stack_top": top, "slots": max(1, slots)}


# ── STEP 78b §1: the examples the voice gives after the correction, one card each ──

EX_W, EX_H, EX_GAP = 600, 74, 10
#: When the examples start, the chat, «Se dice» and the rule scroll up together, as a messenger
#: does, and the stack takes the lower half under the rule (STEP 79 §0; 78b raised the cards over
#: the conversation instead).
FOCUS_MOVE = 0.5
MAX_SHOWN = 4
EX_SHIFT = 0.3                        # the stack moves up over this long when a card leaves


def _same(a: str, b: str) -> bool:
    x, y = set(_norm_tokens(a)), set(_norm_tokens(b))
    return bool(x and y) and len(x & y) / len(x | y) >= 0.75


def examples(script: Dict, tl: Dict) -> List[Tuple[str, float, bool]]:
    """(phrase, when it is said, right?) for every [[English]] phrase after the «Se dice» card,
    other than the right form itself, before the challenge. The wrong form said again keeps its
    card, with a cross: it is the error, not an example."""
    tm = times(script, tl)
    right, wrong = script["correction"]["right"], script["correction"]["wrong"]
    out = []
    for beat in tl["beats"]:
        for e in beat["english"]:
            if tm["card"] + 0.3 < e["start"] < tm["challenge"] and not _same(e["text"], right):
                out.append((e["text"], e["start"], not _same(e["text"], wrong)))
    return out


def focus_time(script: Dict, tl: Dict) -> Optional[float]:
    ex = examples(script, tl)
    return max(times(script, tl)["rule"] + 0.5, ex[0][1] - 0.4) if ex else None


def _example_card(text: str) -> Image.Image:
    return _example_card_cached(text)


@lru_cache(maxsize=32)
def _example_card_cached(text: str) -> Image.Image:
    size, lines = K.fit(text, "fredoka", EX_W - 130, 36, 26, 1)
    card = kit.note_card(EX_W, EX_H, WHITE, 4, (7, 7)).copy()
    K.text_block(card, lines, "fredoka", size, 34, EX_H / 2 - K.line_height(size, "fredoka") / 2 + 2, kit.colour("ink"))
    return card


def _draw_examples(img: Image.Image, t: float, lay: Dict, shown: List[Tuple[str, float, bool]]) -> None:
    """The stack under the rule: the newest at the bottom; past `slots`, the oldest fades out
    and the rest move up."""
    if not shown:
        return
    n, slots = len(shown), lay["slots"]
    e = ease_out_cubic(clamp01((t - shown[-1][1]) / EX_SHIFT))
    offset = max(0, n - slots) - (1 - e if n > slots else 0)
    for j, (text, at, ok) in enumerate(shown):
        slot = j - offset
        if slot <= -1:
            continue
        alpha = clamp01(slot + 1) * clamp01((t - at) / 0.25)
        p = clamp01((t - at) / 0.3)
        y = lay["stack_top"] + slot * (EX_H + EX_GAP)
        card = _example_card(text)
        _place(img, card, K.W / 2, y + EX_H / 2, 0.85 + 0.15 * ease_out_back(p, 2.0), alpha)
        if t >= at + 0.15 and ok:                              # the tick, drawn on its stroke
            kit.tick(img, K.W / 2 + EX_W / 2 - 92, y + EX_H / 2 + 4, 1.0, 40, progress=round(clamp01((t - at - 0.15) / 0.3) * 24) / 24)
        elif t >= at + 0.15:
            kit.cross(img, K.W / 2 + EX_W / 2 - 88, y + EX_H / 2, ease_out_cubic(clamp01((t - at - 0.15) / 0.25)), 34)


def times(script: Dict, tl: Dict) -> Dict:
    """When each part comes in, read off the beats."""
    beats = tl["beats"]
    n = len(script["chat"]["messages"])
    t0 = max(HOOK_TO, beats[0]["start"] + 0.3)
    t1 = max(t0 + 0.8 * n, beats[min(1, len(beats) - 1)]["end"])
    arrive = [t0 + k * (t1 - t0) / n for k in range(n)]
    # The error is ringed as soon as the voice starts explaining it (beat 2), or earlier if the
    # wrong form itself is heard first — never after the right one has been said.
    explain = beats[min(1, len(beats) - 1)]["start"]
    heard = phrase_time(tl, script["correction"]["wrong"])
    ring = max(arrive[-1] + 0.4, min(explain, heard) if heard is not None else explain)
    card = phrase_time(tl, script["correction"]["right"])
    card = max(ring + 1.0, card if card is not None else ring + 1.0)
    return {"arrive": arrive, "ring": ring, "arrow": ring + 0.5, "card": card, "rule": card + 0.8,
            "challenge": beats[-1]["start"]}


# ── drawing ──────────────────────────────────────────────────────────

def _initials(contact: str) -> str:
    name = contact.split("·")[0].strip()
    parts = name.split()
    if len(parts) > 1:
        return (parts[0][0] + parts[1][0]).upper()
    consonants = [c for c in name[1:] if c.isalpha() and c.lower() not in "aeiou"]
    return (name[0] + (consonants[0] if consonants else name[1:2])).upper()


@lru_cache(maxsize=16)
def _chrome(contact: str, level_label: str) -> Image.Image:
    """The messenger with no messages: status line, header, input bar, the level pill."""
    img = Image.new("RGBA", (K.W, K.H), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 36), "9:41", font=K.font("manrope_semibold", 44), fill=WHITE)
    d.rectangle([0, HEADER_Y0, K.W, HEADER_Y1], fill=HEADER)
    d.line([(88, 162), (66, 186), (88, 210)], fill=ME, width=6, joint="curve")
    cx, cy, r = K.W / 2, 186, 60
    disc = Image.new("RGBA", (2 * r * kit.SS, 2 * r * kit.SS), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([0, 0, 2 * r * kit.SS - 1, 2 * r * kit.SS - 1], fill=AVATAR)
    img.alpha_composite(disc.resize((2 * r, 2 * r), Image.LANCZOS), (int(cx - r), int(cy - r)))
    K.text_block(img, [_initials(contact)], "fredoka", 52, 0, cy - 34, WHITE, "center", K.W)
    K.text_block(img, [contact], "manrope_semibold", 36, 0, 252, WHITE, "center", K.W)
    d.rounded_rectangle([40, 1700, K.W - 40, 1790], radius=45, outline=(64, 64, 70, 255), width=3)
    d.text((100, 1726), "Mensaje", font=K.font("manrope", 38), fill=GREY)
    K.level_pill(img, level_label, kit.colour("brand_yellow"), kit.colour("ink"), cx=K.W - 190, y=K.SAFE_TOP + 4,
                 size=30)
    return img


@lru_cache(maxsize=64)
def _bubble(who: str, lines: Tuple[str, ...], size: int, lh: int, w: int, h: int) -> Image.Image:
    fill = ME if who == "me" else THEM
    big = Image.new("RGBA", ((w + 30) * kit.SS, (h + 4) * kit.SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    ox = 15 * kit.SS
    d.rounded_rectangle([ox, 0, ox + w * kit.SS, h * kit.SS], radius=44 * kit.SS, fill=fill)
    tail_x = ox + (w * kit.SS - 8 * kit.SS if who == "me" else 8 * kit.SS)
    sign = 1 if who == "me" else -1
    d.polygon([(tail_x, h * kit.SS - 40 * kit.SS), (tail_x + sign * 26 * kit.SS, h * kit.SS),
               (tail_x - sign * 30 * kit.SS, h * kit.SS - 6 * kit.SS)], fill=fill)
    img = big.resize((w + 30, h + 4), Image.LANCZOS)
    K.text_block(img, lines, BUBBLE_FACE, size, 15 + PAD_X, PAD_Y - 2, WHITE)
    return img


@lru_cache(maxsize=16)
def _hook_card(lines: Tuple[str, ...], size: int) -> Image.Image:
    """The hook, as a white card over the top of the chat (frame 0 is the thumbnail)."""
    f = K.font("fredoka", size)
    w = min(HOOK_W, int(max(K.length(x, f) for x in lines)) + 80)
    lh = K.line_height(size, "fredoka")
    h = lh * len(lines) + 36
    card = Image.new("RGBA", (w + 10, h + 10), (0, 0, 0, 0))
    card.alpha_composite(kit.note_card(w, h, WHITE, 4, (8, 8)))
    K.text_block(card, list(lines), "fredoka", size, 0, 18, kit.colour("ink"), "center", w)
    return card


def _place(img: Image.Image, sprite: Image.Image, cx: float, cy: float, scale: float, alpha: float = 1.0) -> None:
    if scale <= 0 or alpha <= 0:
        return
    if scale != 1.0:
        sprite = sprite.resize((max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))), Image.LANCZOS)
    if alpha < 1.0:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
    kit._composite_clipped(img, sprite, int(round(cx - sprite.width / 2)), int(round(cy - sprite.height / 2)))


@lru_cache(maxsize=16)
def _card(text_lines: Tuple[str, ...], size: int, right: str) -> Image.Image:
    """«Se dice: right»: white sticker, ink outline, hard shadow; «Se dice:» ink, the rest blue."""
    w, h = CARD_W, K.line_height(size, "fredoka") * len(text_lines) + 70
    card = kit.note_card(w, h, (255, 255, 255, 255), 5, (10, 10)).copy()
    f = K.font("fredoka", size)
    d = ImageDraw.Draw(card)
    lh = K.line_height(size, "fredoka")
    lead = "Se dice:"
    for k, line in enumerate(text_lines):
        x = (w - f.getlength(line)) / 2
        y = 30 + k * lh
        if k == 0 and line.startswith(lead):
            d.text((x, y), lead, font=f, fill=kit.colour("ink"))
            d.text((x + f.getlength(lead + " "), y), line[len(lead) + 1:], font=f, fill=kit.colour("english_blue"))
        else:
            d.text((x, y), line, font=f, fill=kit.colour("english_blue"))
    return card.rotate(1.5, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=16)
def _sticky(lines: Tuple[str, ...], size: int) -> Image.Image:
    w, h = 740, K.line_height(size, "fredoka") * len(lines) + 50
    note = kit.note_card(w, h, kit.colour("brand_yellow"), 4, (8, 8)).copy()
    K.text_block(note, lines, "fredoka", size, 0, 24, kit.colour("ink"), "center", w)
    return note.rotate(-1.0, resample=Image.BICUBIC, expand=True)


def frame(t: float, script: Dict, tl: Dict) -> Image.Image:
    lay, tm = layout(script), times(script, tl)
    tf = focus_time(script, tl)
    focus = ease_out_cubic(clamp01((t - tf) / FOCUS_MOVE)) if tf is not None and t >= tf else 0.0
    plan = scroll_plan(script, tl)
    scroll = round(plan["lift"] * focus)
    img = _chrome(script["chat"]["contact"], script["level_label"]).copy()
    # Everything that scrolls is drawn on its own layer, then shown below the header only.
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    K.text_block(layer, ["Hoy 21:14"], "manrope", 30, 0, CHAT_TOP - 50, GREY, "center", K.W)      # scrolls with the chat

    # the hook card over the top of the chat, from frame 0 until «Se dice» comes
    hook_size, hook_lines = lay["hook"]
    a = 1.0 - clamp01((t - tm["card"]) / 0.3)
    if a > 0:
        _place(layer, _hook_card(hook_lines, hook_size), K.W / 2, HOOK_Y + _hook_card(hook_lines, hook_size).height / 2, 1.0, a)

    # the messages: all on screen from frame 0; each pops as the voice reaches it
    for k, (b, at) in enumerate(zip(lay["bubbles"], tm["arrive"])):
        x0, y0, x1, y1 = b["box"]
        sprite = _bubble(b["who"], b["lines"], b["size"], b["lh"], int(x1 - x0), int(y1 - y0))
        bump = 0.08 * math.sin(math.pi * (t - at) / POP) if at <= t < at + POP else 0.0
        _place(layer, sprite, (x0 + x1) / 2, (y0 + y1) / 2 + 2, 1.0 + bump)
        if b["error"] and t >= tm["ring"]:
            K.ring(layer, (x0 - 22, y0 - 16, x1 + 22, y1 + 16), (t - tm["ring"]) / 0.5, RED)
            if t >= tm["arrow"] and focus < 0.5:
                start = (x0 + (x1 - x0) * 0.25, y1 + 24)
                end = (K.W / 2 - 120, lay["card"][2][1] - 30)
                mid = ((start[0] + end[0]) / 2 - 90, (start[1] + end[1]) / 2)
                pts = [_bez(start, mid, end, u / 16) for u in range(17)]
                K.arrow_on(layer, pts, (t - tm["arrow"]) / 0.4, RED)

    # «Se dice: …» drops in under the chat, the rule sticky after it
    size, lines, box = lay["card"]
    if t >= tm["card"]:
        p = clamp01((t - tm["card"]) / 0.45)
        drop = (1.0 - ease_out_back(p, 1.6)) * -140
        _place(layer, _card(lines, size, script["correction"]["right"]), K.W / 2, (box[1] + box[3]) / 2 + drop, 1.0,
               clamp01(p * 3))
    rsize, rlines, rbox = lay["rule"]
    if t >= tm["rule"]:
        p = clamp01((t - tm["rule"]) / 0.35)
        _place(layer, _sticky(rlines, rsize), K.W / 2, (rbox[1] + rbox[3]) / 2, 0.7 + 0.3 * ease_out_back(p, 2.0),
               clamp01(p * 3))

    img.alpha_composite(layer.crop((0, HEADER_Y1 + scroll, K.W, K.H + scroll)), (0, HEADER_Y1))
    stack = dict(lay, stack_top=plan["stack_top"] + plan["lift"] - scroll, slots=plan["slots"])

    # the examples the voice gives after the correction (STEP 78b §1)
    _draw_examples(img, t, stack, [e for e in examples(script, tl) if e[1] <= t])

    # the input's cursor blinks: the screen is never quite still
    if int(t * 2) % 2 == 0:
        ImageDraw.Draw(img).rectangle([84, 1722, 89, 1768], fill=ME)

    # the challenge, over the dimmed chat
    if t >= tm["challenge"]:
        p = clamp01((t - tm["challenge"]) / 0.4)
        shade = Image.new("RGBA", img.size, (0, 0, 0, int(150 * p)))
        img.alpha_composite(shade)
        K.challenge_card(img, script["challenge"]["prompt"], lay["challenge"]["y"], p)
    return img


def _bez(a, b, c, u):
    return ((1 - u) ** 2 * a[0] + 2 * (1 - u) * u * b[0] + u * u * c[0],
            (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * b[1] + u * u * c[1])


def sfx_events(script: Dict, tl: Dict) -> List[Tuple[str, float, float]]:
    tm = times(script, tl)
    ev = [("pop", at, 0.0) for at in tm["arrive"]]
    ev += [("scratch", tm["ring"], 0.5), ("scratch", tm["arrow"], 0.4), ("swish", tm["card"], 0.0),
           ("pop", tm["rule"], 0.0), ("pop", tm["challenge"], 0.0)]
    ev += [("pop", e[1], 0.0) for e in examples(script, tl)]
    return sorted(ev, key=lambda e: e[1])


def text_boxes(script: Dict) -> List[Tuple[str, K.Box]]:
    """Every readable box at its final place (the safe-area and overflow tests)."""
    lay = layout(script)
    hook_size, hook_lines = lay["hook"]
    card = _hook_card(hook_lines, hook_size)
    out = [("hook", (K.W / 2 - card.width / 2, HOOK_Y, K.W / 2 + card.width / 2, HOOK_Y + card.height))]
    out += [(f"message {k + 1}", b["box"]) for k, b in enumerate(lay["bubbles"])]
    out += [("se dice", lay["card"][2]), ("rule", lay["rule"][2]), ("challenge", lay["challenge"]["box"])]
    top, slots = _stack(lay["rule"][2][3] - lay["max_lift"])
    for k in range(slots):                                    # every slot the stack can use, fully scrolled
        y = top + k * (EX_H + EX_GAP)
        out.append((f"example slot {k + 1}", (K.W / 2 - EX_W / 2, y, K.W / 2 + EX_W / 2, y + EX_H)))
    return out

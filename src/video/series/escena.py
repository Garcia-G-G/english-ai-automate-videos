"""«Hecho con Claude» · escena (STEP 78 §4): a film take that goes wrong, «¡CORTEN!», take two.

The reference is _audit/series/reference/estilo_escena.jpg: letterbox bars, a dark film-grain
frame, the slate line and a red timecode in the top bar, a clapperboard, the first take as a
yellow subtitle struck through in red, «¡CORTEN!», «TOMA 2», the right line, the note under it.
Inter (OFL, assets/fonts/) for the film type. Timed on the voice's beats and words:

    0 s              the slate line (`hook_text`) and the clapper: frame 0 is the thumbnail
    «Toma uno»       the clapper snaps shut (a clap); take 1 comes up as a subtitle
    «¡Corten!»       a red marker strikes take 1; «¡CORTEN!» punches in
    «Toma dos»       «TOMA 2»; take 2 types in while the voice says it; the note below
    the last beat    the challenge card, over the dimmed frame
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ..motion import clamp01, ease_out_back, ease_out_cubic
from ..notebook import kit
from . import series_kit as K
from .beats import word_time
from .mensajes import _place, phrase_time

BLACK = (6, 6, 6, 255)
FILM = (62, 44, 34)
CREAM = (240, 234, 222, 255)
YELLOW = (255, 214, 64, 255)
RED = (214, 58, 44, 255)

BAR_TOP, BAR_BOTTOM = 252, 1610          # the letterbox bars end / begin here
SLATE_Y = 168
PILL_Y = 280
CLAP_CX, CLAP_CY = 770, 520              # the clapperboard's slate, centre
CLAP_W, CLAP_H = 380, 230
TAKE1_Y = 770
CORTEN_Y = 860
TOMA2_Y = 1040
TAKE2_Y = 1095
TEXT_W = 860
#: Below y 950 a centred line stays left of the rail (x 940): 780 px, x 150..930.
LOW_W = 780


#: Under take 1 at frame 0 and until the strike (STEP 78b §1).
SPOT_THE_ERROR = "¿Ves el error?"


def _scene_no(script: Dict) -> str:
    return f"ESCENA {int(script['id'][4:]):02d}"


# ── layout ───────────────────────────────────────────────────────────

def layout(script: Dict) -> Dict:
    sc = script["scene"]
    slate = K.fit(script["hook_text"], "inter", 700, 34, 24, 2)
    take1 = K.fit(sc["take1"], "inter_black", TEXT_W, 66, 40, 2)
    corten = K.fit("¡CORTEN!", "inter_black", 780, 150, 110, 1)          # x ≤ 930: off the rail
    take2 = K.fit(sc["take2"], "inter_black", LOW_W, 92, 46, 2)
    t2_bottom = TAKE2_Y + K.line_height(take2[0], "inter_black") * len(take2[1])
    note = K.fit(sc["note"], "inter", LOW_W, 38, 26, 4)
    note_y = t2_bottom + 30
    boxes = {
        "hook": K.block_box(slate[1], "inter", slate[0], 60, SLATE_Y),
        "take1": K.block_box(take1[1], "inter_black", take1[0], 0, TAKE1_Y - K.line_height(take1[0], "inter_black") *
                             (len(take1[1]) - 1), "center", K.W),
        "corten": K.block_box(corten[1], "inter_black", corten[0], 0, CORTEN_Y, "center", K.W),
        "toma2": K.block_box(["TOMA 2"], "inter", 40, 0, TOMA2_Y, "center", K.W),
        "take2": K.block_box(take2[1], "inter_black", take2[0], 0, TAKE2_Y, "center", K.W),
        "note": K.block_box(note[1], "inter", note[0], 0, note_y, "center", K.W),
        "clapper": (CLAP_CX - CLAP_W / 2 - 20, CLAP_CY - CLAP_H / 2 - 110, CLAP_CX + CLAP_W / 2 + 20, CLAP_CY + CLAP_H / 2 + 20),
    }
    t1 = boxes["take1"]
    w = K.font("inter", 30).getlength(SPOT_THE_ERROR) + 48
    boxes["spot"] = (K.W / 2 - w / 2, t1[3] + 22, K.W / 2 + w / 2, t1[3] + 22 + 60)
    return {"slate": slate, "take1": take1, "corten": corten, "take2": take2, "note": note, "note_y": note_y,
            "boxes": boxes, "challenge": K.challenge_layout(script["challenge"]["prompt"], 560)}


def _first_word_time(tl: Dict, phrase: str) -> Optional[float]:
    for beat in tl["beats"]:
        t = word_time(beat, phrase)
        if t is not None:
            return t
    return None


def times(script: Dict, tl: Dict) -> Dict:
    beats = tl["beats"]
    sc = script["scene"]
    toma1 = _first_word_time(tl, "Toma uno")
    toma1 = toma1 if toma1 is not None else beats[0]["start"] + 1.0
    take1 = phrase_time(tl, sc["take1"])
    take1 = max(toma1 + 0.3, take1 if take1 is not None else toma1 + 0.6)
    corten = _first_word_time(tl, "Corten")
    corten = max(take1 + 1.0, corten if corten is not None else beats[min(1, len(beats) - 1)]["start"])
    toma2 = _first_word_time(tl, "Toma dos")
    take2 = phrase_time(tl, sc["take2"])
    take2 = max(corten + 1.0, take2 if take2 is not None else corten + 1.6)
    toma2 = max(corten + 0.6, min(take2 - 0.3, toma2) if toma2 is not None else take2 - 0.5)
    t2_end = take2 + 1.2
    for beat in beats:
        for e in beat["english"]:
            if abs(e["start"] - take2) < 0.01:
                t2_end = max(e["end"], take2 + 0.6)
    return {"toma1": toma1, "take1": take1, "strike": corten - 0.3, "corten": corten, "toma2": toma2,
            "take2": take2, "take2_end": t2_end, "note": t2_end + 0.4, "challenge": beats[-1]["start"]}


# ── drawing ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _grain_tiles() -> Tuple[Image.Image, ...]:
    """Four grain tiles over the film frame, cycled 12 times a second, with a soft vignette."""
    h = BAR_BOTTOM - BAR_TOP
    yy, xx = np.mgrid[0:h, 0:K.W]
    d = np.hypot((xx - K.W / 2) / (K.W * 0.7), (yy - h / 2) / (h * 0.7))
    vignette = np.clip(1.0 - 0.45 * d ** 2, 0.45, 1.0)
    tiles = []
    for k in range(4):
        noise = np.random.default_rng(40 + k).normal(0, 9, (h, K.W))
        rgb = np.clip((np.array(FILM)[None, None, :] + noise[..., None]) * vignette[..., None], 0, 255).astype(np.uint8)
        tiles.append(Image.fromarray(rgb).convert("RGBA"))
    return tuple(tiles)


def _timecode(t: float) -> str:
    frames = int(t * 24)
    return f"00:00:{frames // 24:02d}:{frames % 24:02d}"


@lru_cache(maxsize=16)
def _clapper(scene_no: str, take: str, angle: float) -> Image.Image:
    """The slate and its striped stick, the stick open by `angle` degrees about its left hinge."""
    S = kit.SS
    head = 200                                          # room above the slate for the open stick
    W, H = CLAP_W + 120, CLAP_H + head + 40
    big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    x0, y0 = 60 * S, head * S
    d.rounded_rectangle([x0, y0, x0 + CLAP_W * S, y0 + CLAP_H * S], radius=16 * S, fill=(18, 18, 20, 255),
                        outline=CREAM, width=5 * S)
    sw, sh = CLAP_W * S, 56 * S
    stick = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stick)
    sd.rectangle([0, 0, sw - 1, sh - 1], fill=(20, 20, 22, 255))
    for k in range(8):
        a = k * 50 * S
        sd.polygon([(a, sh), (a + 26 * S, sh), (a + 52 * S, 0), (a + 26 * S, 0)], fill=CREAM)
    # rotate about the hinge (bottom-left of the stick), sitting just above the slate's top edge
    hinge = (x0, y0 - 8 * S)
    pad = Image.new("RGBA", (2 * sw, 2 * sw), (0, 0, 0, 0))
    pad.alpha_composite(stick, (sw, sw - sh))            # hinge at the pad's centre
    pad = pad.rotate(angle, resample=Image.BICUBIC, center=(sw, sw))
    kit._composite_clipped(big, pad, hinge[0] - sw, hinge[1] - sw)
    img = big.resize((W, H), Image.LANCZOS)
    f = K.font("inter", 40)
    dd = ImageDraw.Draw(img)
    for k, line in enumerate((scene_no, take, "EN → ES")):
        dd.text((60 + 34, head + 26 + k * 62), line, font=f, fill=CREAM)
    return img.rotate(-6, resample=Image.BICUBIC, expand=True)


def _clap_angle(t: float, toma1: float) -> float:
    """Open (28°) by 0.3 s, held, snapped shut over 0.12 s on «Toma uno», a small bounce after."""
    if t < toma1 - 0.12:
        return round(28 * ease_out_cubic(t / 0.3))
    if t < toma1:
        return round(28 * (1 - (t - (toma1 - 0.12)) / 0.12))
    return round(4 * max(0.0, math.sin((t - toma1) * 18)) * math.exp(-(t - toma1) * 8))


def frame(t: float, script: Dict, tl: Dict) -> Image.Image:
    lay, tm = layout(script), times(script, tl)
    img = Image.new("RGBA", (K.W, K.H), BLACK)
    img.alpha_composite(_grain_tiles()[int(t * 12) % 4], (0, BAR_TOP))
    d = ImageDraw.Draw(img)

    size, lines = lay["slate"]
    K.text_block(img, lines, "inter", size, 60, SLATE_Y, CREAM)
    d.text((1020 - K.font("inter", 30).getlength("00:00:00:00"), SLATE_Y + 2), _timecode(t),
           font=K.font("inter", 30), fill=RED)
    K.level_pill(img, script["level_label"], CREAM, kit.colour("ink"),
                 cx=60 + K.font("inter", 28).getlength(script["level_label"]) / 2 + 22, y=PILL_Y, face="inter", size=28)

    take = "TOMA 1" if t < tm["toma2"] else "TOMA 2"
    clap = _clapper(_scene_no(script), take, _clap_angle(t, tm["toma1"]))
    img.alpha_composite(clap, (int(CLAP_CX - clap.width / 2), int(CLAP_CY - clap.height / 2 - 80)))

    # take 1: on screen from frame 0, the thumbnail (STEP 78b §1), a pop when the voice reads it,
    # «¿Ves el error?» under it until the strike, then a red marker strike
    s1, l1 = lay["take1"]
    if l1:
        top = TAKE1_Y - K.line_height(s1, "inter_black") * (len(l1) - 1)
        bump = 0.0
        if tm["take1"] <= t < tm["take1"] + 0.35:
            bump = 0.08 * math.sin(math.pi * (t - tm["take1"]) / 0.35)
        if bump:
            sub = Image.new("RGBA", img.size, (0, 0, 0, 0))
            K.text_block(sub, l1, "inter_black", s1, 0, top, YELLOW, "center", K.W, 1.0, stroke=4, stroke_fill=(0, 0, 0, 255))
            bb = K.block_box(l1, "inter_black", s1, 0, top, "center", K.W)
            crop = sub.crop((0, int(bb[1]) - 12, K.W, int(bb[3]) + 12))
            _place(img, crop, K.W / 2, (bb[1] + bb[3]) / 2, 1.0 + bump)
        else:
            K.text_block(img, l1, "inter_black", s1, 0, top, YELLOW, "center", K.W, 1.0, stroke=4,
                         stroke_fill=(0, 0, 0, 255))
        if t < tm["strike"]:
            K.level_pill(img, SPOT_THE_ERROR, RED, CREAM, cx=K.W / 2, y=lay["boxes"]["take1"][3] + 22, face="inter", size=30)
        if t >= tm["strike"]:
            p = clamp01((t - tm["strike"]) / 0.3)
            for k, line in enumerate(l1):
                lw = K.length(line, K.font("inter_black", s1))
                y = top + k * K.line_height(s1, "inter_black") + s1 * 0.55
                pts = ((K.W / 2 - lw / 2 - 16, y + 4), (K.W / 2 + lw / 2 + 16, y - 6))
                path = kit._partial(list(pts), p)
                kit.paint(img, kit._bbox(path, 20), lambda dd, at, k_, pth=path: kit._lines(dd, at, k_, pth, RED, 16),
                          ("strike78", round(p, 3), pts))

    # ¡CORTEN!
    if t >= tm["corten"]:
        p = clamp01((t - tm["corten"]) / 0.35)
        cs, cl = lay["corten"]
        sprite = _corten(cs)
        _place(img, sprite, K.W / 2, CORTEN_Y + sprite.height / 2 - 10, 1.0 + 0.5 * (1 - ease_out_back(p, 1.8)),
               clamp01(p * 4))

    # TOMA 2, take 2 typed in, the note
    if t >= tm["toma2"]:
        K.text_block(img, ["TOMA 2"], "inter", 40, 0, TOMA2_Y, RED, "center", K.W, clamp01((t - tm["toma2"]) / 0.2))
    s2, l2 = lay["take2"]
    if t >= tm["take2"]:
        n = sum(len(x) for x in l2)
        shown = int(round(n * clamp01((t - tm["take2"]) / max(0.4, tm["take2_end"] - tm["take2"]))))
        out = []
        for line in l2:
            out.append(line[:max(0, shown)])
            shown -= len(line)
        _typed(img, l2, out, s2)
    if t >= tm["note"]:
        ns, nl = lay["note"]
        K.text_block(img, nl, "inter", ns, 0, lay["note_y"], CREAM, "center", K.W, clamp01((t - tm["note"]) / 0.3))

    d.text((K.W / 2 - K.font("inter", 30).getlength("learningroutes.com") / 2, 1750), "learningroutes.com",
           font=K.font("inter", 30), fill=(150, 146, 138, 255))

    if t >= tm["challenge"]:
        p = clamp01((t - tm["challenge"]) / 0.4)
        img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(160 * p))))
        K.challenge_card(img, script["challenge"]["prompt"], lay["challenge"]["y"], p)
    return img


def _typed(img: Image.Image, full: List[str], shown: List[str], size: int) -> None:
    """Typewriter: each line laid out where the full line will sit (centred), shown up to its cursor."""
    f = K.font("inter_black", size)
    lh = K.line_height(size, "inter_black")
    for k, (line, part) in enumerate(zip(full, shown)):
        x = (K.W - K.length(line, f)) / 2
        K.draw_line(img, x, TAKE2_Y + k * lh, part, f, YELLOW)


@lru_cache(maxsize=4)
def _corten(size: int) -> Image.Image:
    f = K.font("inter_black", size)
    w = int(K.length("¡CORTEN!", f)) + 20
    img = Image.new("RGBA", (w, int(size * 1.2)), (0, 0, 0, 0))
    K.draw_line(img, 10, 0, "¡CORTEN!", f, CREAM)
    return img


def sfx_events(script: Dict, tl: Dict) -> List[Tuple[str, float, float]]:
    tm = times(script, tl)
    ev = [("swish", 0.0, 0.0), ("clap", tm["toma1"], 0.0), ("pop", tm["take1"], 0.0),
          ("scratch", tm["strike"], 0.3), ("swish", tm["corten"], 0.0), ("pop", tm["toma2"], 0.0),
          ("scratch", tm["take2"], max(0.3, tm["take2_end"] - tm["take2"])), ("pop", tm["challenge"], 0.0)]
    return sorted(ev, key=lambda e: e[1])


def text_boxes(script: Dict) -> List[Tuple[str, K.Box]]:
    lay = layout(script)
    out = [(k, v) for k, v in lay["boxes"].items()]
    return out + [("challenge", lay["challenge"]["box"])]

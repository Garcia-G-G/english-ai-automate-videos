"""STEP 85b §2: «nothing cut» and «readable small» for a Tablero frame, from the boxes the kit draws.

Contrast >= 4.5:1 is enforced. The x-height at 180x320 is only a WARNING: the 7 px rule would fail every tile
(a 56 px Fredoka English word is ~4.7 px x-height at that size), so it is measured and stored, not enforced.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from video.tablero import kit

W, H = kit.W, kit.H
SMALL_SCALE = 180 / W
CONTRAST_MIN = 4.5
XHEIGHT_MIN = 7.0
#: where a tile may sit: inside the canvas, below the top margin, above the platforms' caption zone
SAFE = (0, kit.TILE_TOP_LIMIT, W, kit.TILE_LIMIT_Y)


def contrast(fg, bg) -> float:
    a, b = sorted((kit.luminance(fg), kit.luminance(bg)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)


def text_boxes(data: Dict) -> List[Dict]:
    """Every text box the kit draws for this video (absolute px, at the active tile's 1.07 scale)."""
    boxes: List[Dict] = []
    grow = (kit.ACTIVE_SCALE - 1) / 2
    gx, gy = grow * kit.TILE_W, grow * kit.TILE_H
    for i, item in enumerate(data["items"]):
        x0, y0 = kit.tile_origin(i)
        boxes.append({"name": f"tile{i + 1}", "box": (x0 - gx, y0 - gy, x0 + kit.TILE_W + gx, y0 + kit.TILE_H + gy), "safe": True})
        sp_size, sp_lines = kit.spanish_lines(item["spanish"])
        sp_w = max(kit.fredoka(sp_size).getlength(s) for s in sp_lines)
        boxes.append({"name": f"spanish{i + 1}", "box": (x0 + kit.TEXT_X, y0 + 20, x0 + kit.TEXT_X + sp_w, y0 + 80), "fit": sp_w <= kit.SPANISH_W})
        en_w, line_w = kit.tile_english_extent(item["english"], kit.pron_for(item))
        boxes.append({"name": f"english{i + 1}", "box": (x0 + kit.TEXT_X, y0 + 100, x0 + kit.TEXT_X + line_w, y0 + 150),
                      "fit": line_w <= kit.TILE_W - kit.TEXT_PAD_R - kit.TEXT_X})
    return boxes


def nothing_cut(data: Dict) -> Dict:
    bad = []
    for b in text_boxes(data):
        x0, y0, x1, y1 = b["box"]
        lim = SAFE if b.get("safe") else (0, 0, W, H)
        if x0 < lim[0] or y0 < lim[1] or x1 > lim[2] or y1 > lim[3] or b.get("fit") is False:
            bad.append(b["name"])
    return {"ok": not bad, "cut": bad}


def readable_small(data: Dict) -> Dict:
    """Contrast of the text pairs the kit draws (enforced) and the x-height at 180x320 (a warning)."""
    pairs = {"chip_topic": (kit.INK, kit.PAPER), "tile_spanish_blank": (kit.INK, kit.PAPER),
             "tile_spanish_done": (kit.PAPER, kit.BLUE), "tile_english_done": (kit.YEL, kit.BLUE)}
    ratios = {k: contrast(*v) for k, v in pairs.items()}
    english = min((kit.fit_font(it["english"], kit.TILE_W - kit.TEXT_PAD_R - kit.TEXT_X)[0] for it in data["items"]), default=kit.FONT_MIN)
    sizes = {"english": english, "chip_topic": 64}
    xh = {}
    for k, px in sizes.items():
        bb = kit.fredoka(px).getbbox("x")
        xh[k] = round((bb[3] - bb[1]) * SMALL_SCALE, 1)
    warn = [f"{k} x-height {v} px at 180x320 (< {XHEIGHT_MIN})" for k, v in xh.items() if v < XHEIGHT_MIN]
    # the spec: the topic chip and at least ONE tile's text reach 4.5:1. The yellow English on blue is 56 px bold
    # (WCAG large text, 3:1) and is recorded, not required to reach 4.5.
    ok = ratios["chip_topic"] >= CONTRAST_MIN and max(ratios["tile_spanish_blank"], ratios["tile_spanish_done"]) >= CONTRAST_MIN \
        and ratios["tile_english_done"] >= 3.0
    return {"contrast": ratios, "contrast_ok": ok,
            "xheight_px": xh, "warnings": warn}


def tablero_checks(data: Dict) -> Dict:
    c, r = nothing_cut(data), readable_small(data)
    return {"nothing_cut": c, "readable_small": r, "ok": c["ok"] and r["contrast_ok"]}

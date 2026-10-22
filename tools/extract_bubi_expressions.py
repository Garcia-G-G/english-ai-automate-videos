#!/usr/bin/env python3
"""Cut Bubi's expressions out of the brand guide (STEP 78 §6).

The brand v3 guide (assets/branding/english-unlimited/guia_de_marca.png) draws four expressions
«para cierres y reacciones en los vídeos»: hola, bien hecho, wow, lo lograste. Only «hola» exists
as its own file (simbolo_512.png). This cuts the four out on transparent ground: the guide's
paper is flood-filled away from the crop's edges (Bubi's ink outline closes his shape), and the
result is trimmed to his pixels.

    python3 tools/extract_bubi_expressions.py      → assets/branding/english-unlimited/expresiones/*.png
"""
from pathlib import Path

import numpy as np
from PIL import Image
import cv2

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "assets" / "branding" / "english-unlimited" / "guia_de_marca.png"
OUT = ROOT / "assets" / "branding" / "english-unlimited" / "expresiones"
#: name -> crop box in the guide (1800 × 2535)
#: «hola» is simbolo_512.png already, so it is not cut again.
BOXES = {"bien_hecho": (520, 1600, 880, 1900),
         "wow": (910, 1600, 1300, 1900), "lo_lograste": (1320, 1590, 1730, 1900)}
PAPER_TOLERANCE = 34          # colour distance from the paper still counted as paper (its grid lines)
MIN_PIECE = 200               # px: smaller opaque pieces are grid specks, not Bubi


def cut(box) -> Image.Image:
    rgb = np.asarray(Image.open(GUIDE).convert("RGB").crop(box)).astype(int)
    corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
    paper = np.median(corners, axis=0)
    near = np.abs(rgb - paper).sum(axis=2) <= PAPER_TOLERANCE
    _n, labels = cv2.connectedComponents(near.astype(np.uint8), connectivity=4)
    edge = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    background = np.isin(labels, [k for k in edge if k]) & near
    alpha = np.where(background, 0, 255).astype(np.uint8)
    # specks of the paper's grid left loose: drop any piece smaller than MIN_PIECE (his «!» marks stay)
    n, pieces, stats, _c = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), connectivity=8)
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < MIN_PIECE:
            alpha[pieces == k] = 0
    alpha = cv2.blur(alpha, (2, 2))                                        # a soft cut edge
    img = Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]))       # 4 channels: RGBA
    return img.crop(img.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, box in BOXES.items():
        img = cut(box)
        img.save(OUT / f"{name}.png")
        print(name, img.size)


if __name__ == "__main__":
    main()

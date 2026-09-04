#!/usr/bin/env python3
"""Strip the baked-in ground shadow from the chosen mascot sprite.

The generator drew a contact shadow as part of the character rather than
as background, so the alpha channel is honest about it: those smudge
pixels are opaque. Left in, the shadow travels with the sprite — it would
breathe, sway, tilt and bounce along with the character, and sit on top of
whatever background the video is using. character.py already draws its own
ground shadow ellipse (see the shadow buffer in render()), so the baked-in
one is redundant as well as wrong.

This edits alpha only. No pixels are repainted and nothing is regenerated.

Method
------
Below the row where the silhouette stops narrowing and abruptly widens,
the only thing that should survive is shoe. Shoe is dark and vertically
continuous with the shoe mass above; the shadow is the light tan smudge
plus scattered black stipple spreading outward past the shoe's width. So:
knock out everything light, then keep only the dark pixels still connected
upward to the confirmed shoe, and feather the cut so it does not read as a
scissor line.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SRC = Path(__file__).parent / "02_short_and_round.png"
DST = Path(__file__).parent / "02_short_and_round_noshadow.png"

# Row where the silhouette stops narrowing (shoes) and widens (shadow).
# Measured, not guessed: widths run 608→487px down to y=1140, then jump
# back out to 654px by y=1155.
Y_SPLIT = 1141

# Above this luminance a pixel in the shadow zone is smudge, not shoe.
SHADOW_LUM = 100.0

# The shadow's black component is scratchy stipple: short, thin horizontal
# strands. A shoe is a solid mass. Anything narrower than this in the
# shadow zone is stipple, and dropping it stops the flood from growing
# spidery roots down into the smudge.
MIN_RUN = 30

# How far above the split to hunt for unsupported wisps, and how far up to
# look for the support that proves a run belongs to the character.
WISP_BAND = 14
WISP_LOOKUP = 5


def _runs(row: np.ndarray):
    """Yield (start, end) of each horizontal run of True in ``row``."""
    padded = np.concatenate(([False], row, [False]))
    edges = np.diff(padded.astype(np.int8))
    return list(zip(np.where(edges == 1)[0], np.where(edges == -1)[0]))


def _wide_runs_only(row: np.ndarray, min_run: int) -> np.ndarray:
    """Zero out horizontal runs of True shorter than ``min_run``."""
    if not row.any():
        return row
    out = np.zeros_like(row)
    for s, e in _runs(row):
        if e - s >= min_run:
            out[s:e] = True
    return out


def strip(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGBA")
    a = np.array(img).astype(np.float32)
    alpha = a[:, :, 3].copy()
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]

    h = a.shape[0]
    opaque = alpha > 10

    # Seed: the last row of unambiguous shoe.
    keep = np.zeros((h, a.shape[1]), dtype=bool)
    keep[:Y_SPLIT] = opaque[:Y_SPLIT]

    # The smudge also throws a wisp up between the feet, just above the
    # split. It gives itself away by having nothing above it: real art at
    # this height (shoes, and the little bounce arcs beside them) is
    # continuous with the body. Drop runs with no support a few rows up.
    for y in range(Y_SPLIT - WISP_BAND, Y_SPLIT):
        for s, e in _runs(keep[y]):
            # Checked against `keep`, not `opaque`, and walked downward, so
            # a wisp cannot vouch for its own lower half once its top has
            # been removed — the deletion cascades down the blob.
            if not keep[y - WISP_LOOKUP, s:e].any():
                keep[y, s:e] = False

    seed = opaque[Y_SPLIT - 1] & (lum[Y_SPLIT - 1] < SHADOW_LUM)

    # Grow the shoe downward one row at a time. A pixel joins only if it is
    # opaque, dark, and 8-connected to a kept pixel on the row above, so the
    # shadow's outward wings never get a foothold.
    prev = seed
    for y in range(Y_SPLIT, h):
        cand = opaque[y] & (lum[y] < SHADOW_LUM)
        above = prev | np.roll(prev, 1) | np.roll(prev, -1)
        row = _wide_runs_only(cand & above, MIN_RUN)
        if not row.any():
            break
        keep[y] = row
        prev = row

    new_alpha = np.where(keep, alpha, 0.0)

    # Feather the cut: a 1px blur on the alpha only where we removed
    # something, so the shoe bottom does not end in a hard sawtooth.
    faded = Image.fromarray(new_alpha.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(0.8)
    )
    blurred = np.array(faded).astype(np.float32)
    # Never let the blur resurrect a removed pixel above the split line.
    new_alpha = np.minimum(np.maximum(new_alpha, blurred * (new_alpha > 0)), alpha)

    a[:, :, 3] = new_alpha
    out = Image.fromarray(a.astype(np.uint8))
    out.save(dst)

    before = int((alpha > 10).sum())
    after = int((new_alpha > 10).sum())
    rows = np.where(new_alpha.max(axis=1) > 10)[0]
    print(f"opaque px: {before} -> {after} ({100*(before-after)/before:.1f}% removed)")
    print(f"new bottom row: {rows.max()} (was {np.where(alpha.max(axis=1) > 10)[0].max()})")
    print(f"saved: {dst}")


if __name__ == "__main__":
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        sys.exit(1)
    strip(SRC, DST)

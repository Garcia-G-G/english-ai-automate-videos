#!/usr/bin/env python3
"""Render every background preset once, with identical text, onto labelled sheets.

The point is to make the aesthetic call by eye: the only thing that changes
between tiles is the background, so anything you notice is the background's
doing. Text, fonts, colours and the watermark come from the real renderer
(``src/video/utils.py``), so what you see is what a video would look like.

Alongside the sheets it writes two measurements per preset — the cost of one
frame, and the background luminance under the headline word — because "render
cost" and "text contrast" are the two reasons a preset might be unusable
rather than merely unwanted.

    python3 tools/background_contact_sheet.py
    python3 tools/background_contact_sheet.py --photo-index 2 --t 6.0

Outputs land in ``_audit/backgrounds/`` (regenerable, so git-ignored):
    sheet_00_ALL.png        every preset, one grid
    sheet_NN_<family>.png   one grid per background type
    frames/<preset>.png     full-resolution single frames
    metrics.md / .csv       per-frame cost and contrast table
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import secrets  # noqa: F401  — imported now so nothing imports it under the patch
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import numpy.random  # noqa: E402,F401  — same reason: no lazy import mid-patch
from PIL import Image, ImageDraw  # noqa: E402

from backgrounds import BACKGROUND_PRESETS, BackgroundGenerator  # noqa: E402
from video.brand import draw_watermark  # noqa: E402
from video.constants import (  # noqa: E402
    ENGLISH_WORD_COLOR,
    FONT_SIZE_ENGLISH,
    FONT_SIZE_SPANISH,
    FONT_SIZE_TRANS,
    OUTLINE_THICK,
    TEXT_AREA_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from video.utils import (  # noqa: E402
    draw_pill_badge,
    draw_text_centered,
    manrope,
)

logger = logging.getLogger("contact_sheet")

# The same words on every single tile. A long-ish English word so the headline
# fills the width the way a real vocabulary card does.
SAMPLE_LABEL = "VOCABULARIO"
SAMPLE_ENGLISH = "BREAKTHROUGH"
SAMPLE_SPANISH = "avance"
SAMPLE_SENTENCE = "Fue un gran avance para el equipo."

# Where the headline sits. Also the band we measure contrast in.
Y_LABEL = 300
Y_ENGLISH = 780
Y_SPANISH = 990
Y_SENTENCE = 1180

DEFAULT_T = 3.0
DEFAULT_DURATION = 30.0

# Families are drawn on their own sheet, in this order.
FAMILY_ORDER = [
    ("flat", ("solid_vignette", "animated_gradient")),
    ("particles", ("bokeh_particles", "particle_flow")),
    ("energetic", ("dynamic_glow_orbs", "light_rays", "aurora")),
    ("static_gradient", ("static_gradient",)),
    ("photo", ("photo_kenburns",)),
]


# ── deterministic photo choice ───────────────────────────────────

class _FixedChoice:
    """Stand-in for random.SystemRandom that picks a fixed slot, sorted by name.

    ``BackgroundGenerator._load_photo`` picks a random image per category and
    caches it. Random is right for production — every video gets a different
    photo — and wrong for a contact sheet you may want to regenerate and
    compare. This makes the pick reproducible without touching that code.

    Only ``choice`` is overridden; anything else delegates to a real one.
    """

    def __init__(self, index: int):
        self.index = index
        self._real = random.SystemRandom()

    def choice(self, seq):
        items = sorted(seq, key=lambda p: str(p))
        return items[self.index % len(items)]

    def __getattr__(self, name):
        return getattr(self._real, name)


class _DeterministicRandomModule:
    """Stands in for the ``random`` module, but only inside ``backgrounds``.

    Patching ``random.SystemRandom`` itself is not an option: that name is
    shared process-wide, ``secrets`` binds ``SystemRandom().getrandbits`` at
    import time, and numpy.random imports ``secrets`` lazily — so a stub
    installed there breaks unrelated code mid-run. Replacing the module
    reference held by ``backgrounds`` keeps the effect where it belongs.
    """

    def __init__(self, index: int):
        self.index = index

    def SystemRandom(self):
        return _FixedChoice(self.index)

    def __getattr__(self, name):
        return getattr(random, name)


# ── rendering ────────────────────────────────────────────────────

def render_background(gen: BackgroundGenerator, preset: str, t: float) -> np.ndarray:
    """One background frame, no text. Returns HxWx3 uint8 RGB."""
    return gen.render_from_preset(t, preset, duration=DEFAULT_DURATION)


def _fit_line(text: str, weight: str, max_size: int, max_width: int):
    """Largest font at which ``text`` fits on one line, like the real renderers."""
    for size in range(max_size, 23, -2):
        f = manrope(size, weight)
        if f.getbbox(text)[2] <= max_width:
            return f
    return manrope(24, weight)


def overlay_reference_text(bg: np.ndarray) -> Image.Image:
    """Paint the identical sample card over a background frame."""
    frame = Image.fromarray(bg).convert("RGBA")
    draw = ImageDraw.Draw(frame, "RGBA")

    draw_pill_badge(
        frame, draw, SAMPLE_LABEL,
        VIDEO_WIDTH // 2, Y_LABEL,
        font_size=44,
        bg_color=(0, 212, 255),
        text_color=(10, 10, 20),
    )

    draw_text_centered(
        draw, SAMPLE_ENGLISH, Y_ENGLISH,
        _fit_line(SAMPLE_ENGLISH, "ExtraBold", FONT_SIZE_ENGLISH, TEXT_AREA_WIDTH),
        ENGLISH_WORD_COLOR, outline=OUTLINE_THICK, max_width=TEXT_AREA_WIDTH,
    )
    draw_text_centered(
        draw, SAMPLE_SPANISH, Y_SPANISH,
        manrope(FONT_SIZE_SPANISH, "Bold"),
        (255, 255, 255), outline=OUTLINE_THICK, max_width=TEXT_AREA_WIDTH,
    )
    draw_text_centered(
        draw, SAMPLE_SENTENCE, Y_SENTENCE,
        manrope(FONT_SIZE_TRANS, "Medium"),
        (235, 235, 245), outline=4, max_width=TEXT_AREA_WIDTH,
    )

    draw_watermark(frame)
    return frame.convert("RGB")


# ── measurement ──────────────────────────────────────────────────

def _relative_luminance(rgb: np.ndarray) -> np.ndarray:
    """WCAG relative luminance for an array of sRGB values in 0..255."""
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def _contrast_ratio(l1: float, l2: float) -> float:
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def measure_contrast(bg: np.ndarray) -> Dict[str, float]:
    """Background luminance where the headline lands, and resulting contrast.

    Measured on the bare background, before any text is drawn — this is the
    surface the glyphs have to stand out from. Reported against the yellow
    headline colour and against white.

    Caveat worth remembering when reading these numbers: every string is drawn
    with a 6px black outline, which props up legibility even where the raw
    contrast here looks marginal.
    """
    x0 = (VIDEO_WIDTH - TEXT_AREA_WIDTH) // 2
    band = bg[Y_ENGLISH:Y_SPANISH, x0:x0 + TEXT_AREA_WIDTH]
    lum = _relative_luminance(band)

    l_mean = float(lum.mean())
    l_bright = float(np.percentile(lum, 95))  # worst case for light text
    l_yellow = float(_relative_luminance(np.array(ENGLISH_WORD_COLOR)))
    l_white = 1.0

    return {
        "bg_luminance_mean": round(l_mean, 4),
        "bg_luminance_p95": round(l_bright, 4),
        "contrast_yellow_mean": round(_contrast_ratio(l_yellow, l_mean), 2),
        "contrast_yellow_worst": round(_contrast_ratio(l_yellow, l_bright), 2),
        "contrast_white_mean": round(_contrast_ratio(l_white, l_mean), 2),
    }


# ── sheet assembly ───────────────────────────────────────────────

def build_sheet(tiles: List[Tuple[str, Image.Image, str]], cols: int,
                thumb_w: int, title: str) -> Image.Image:
    """Tile (name, image, sublabel) triples into a labelled grid."""
    thumb_h = int(thumb_w * VIDEO_HEIGHT / VIDEO_WIDTH)
    pad = 14
    label_h = 74  # name + two sublabel lines
    header_h = 74

    rows = (len(tiles) + cols - 1) // cols
    sheet_w = cols * thumb_w + (cols + 1) * pad
    sheet_h = header_h + rows * (thumb_h + label_h + pad) + pad

    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)

    draw.text((pad, 22), title, font=manrope(34, "Bold"), fill=(245, 245, 250))
    draw.text(
        (sheet_w - pad, 30), f"{len(tiles)} presets",
        font=manrope(24, "Medium"), fill=(150, 150, 165), anchor="ra",
    )

    name_font = manrope(23, "Bold")
    sub_font = manrope(19, "Medium")

    for i, (name, img, sub) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = pad + c * (thumb_w + pad)
        y = header_h + r * (thumb_h + label_h + pad)

        sheet.paste(img.resize((thumb_w, thumb_h), Image.LANCZOS), (x, y))
        draw.rectangle([x, y, x + thumb_w - 1, y + thumb_h - 1], outline=(60, 60, 70))

        draw.text((x, y + thumb_h + 7), name, font=name_font, fill=(255, 255, 255))
        for j, sub_line in enumerate(sub.split("\n")):
            colour = (110, 200, 130) if sub_line.endswith("ON") else (150, 150, 165)
            draw.text((x, y + thumb_h + 33 + j * 21), sub_line,
                      font=sub_font, fill=colour)

    return sheet


def write_metrics(rows: List[dict], out_dir: Path) -> None:
    fields = [
        "preset", "type", "enabled", "render_ms",
        "bg_luminance_mean", "bg_luminance_p95",
        "contrast_yellow_mean", "contrast_yellow_worst", "contrast_white_mean",
    ]
    with open(out_dir / "metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# Background preset measurements",
        "",
        f"One frame per preset at t={DEFAULT_T}s, {VIDEO_WIDTH}x{VIDEO_HEIGHT}.",
        "",
        "`render_ms` is one uncached frame. `contrast_*` is the WCAG ratio between",
        "the text colour and the bare background in the headline band — measured",
        "before text is drawn, and *before* the 6px black outline every string",
        "gets, which lifts legibility further. WCAG AA for large text is 3.0.",
        "",
        "| preset | type | on | ms/frame | bg lum (mean) | yellow (mean) | yellow (worst) | white (mean) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['preset']}` | {r['type']} | {'yes' if r['enabled'] else ''} "
            f"| {r['render_ms']:.0f} | {r['bg_luminance_mean']:.3f} "
            f"| {r['contrast_yellow_mean']:.2f} | {r['contrast_yellow_worst']:.2f} "
            f"| {r['contrast_white_mean']:.2f} |"
        )
    (out_dir / "metrics.md").write_text("\n".join(lines) + "\n")


# ── main ─────────────────────────────────────────────────────────

def enabled_presets() -> set:
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
    return set(cfg.get("video", {}).get("enabled_backgrounds", []) or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "_audit" / "backgrounds"),
                    help="output directory (default: _audit/backgrounds)")
    ap.add_argument("--cols", type=int, default=6, help="tiles per row")
    ap.add_argument("--thumb-width", type=int, default=260, help="tile width in px")
    ap.add_argument("--t", type=float, default=DEFAULT_T,
                    help=f"timestamp to sample, seconds (default {DEFAULT_T})")
    ap.add_argument("--photo-index", type=int, default=0,
                    help="which image per photo category, 0-based, sorted by name")
    ap.add_argument("--no-full-res", action="store_true",
                    help="skip writing full-resolution single frames")
    ap.add_argument("--only", default=None,
                    help="substring filter on preset name")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    out_dir = Path(args.out)
    frames_dir = out_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_full_res:
        frames_dir.mkdir(exist_ok=True)

    on = enabled_presets()
    names = [n for n in BACKGROUND_PRESETS
             if not args.only or args.only in n]

    # One generator for the whole run, so presets sharing a photo category
    # (photo_earth / photo_earth_dark) show the same image and the difference
    # you see is the preset's treatment, not a different photo.
    gen = BackgroundGenerator(VIDEO_WIDTH, VIDEO_HEIGHT)

    tiles: Dict[str, Tuple[str, Image.Image, str]] = {}
    rows: List[dict] = []

    print(f"Rendering {len(names)} presets at t={args.t}s ...")
    with patch("backgrounds.random", _DeterministicRandomModule(args.photo_index)):
        for i, name in enumerate(names, 1):
            preset_type = BACKGROUND_PRESETS[name].get("type", "?")

            t0 = time.perf_counter()
            bg = render_background(gen, name, args.t)
            render_ms = (time.perf_counter() - t0) * 1000

            metrics = measure_contrast(bg)
            composed = overlay_reference_text(bg)

            if not args.no_full_res:
                composed.save(frames_dir / f"{name}.png")

            sub = (f"{preset_type}\n{render_ms:.0f}ms  ·  "
                   f"{metrics['contrast_yellow_mean']:.1f}:1"
                   + ("  ·  ON" if name in on else ""))
            tiles[name] = (name, composed, sub)

            rows.append({"preset": name, "type": preset_type,
                         "enabled": name in on, "render_ms": render_ms,
                         **metrics})
            print(f"  [{i:2d}/{len(names)}] {name:24s} {render_ms:7.0f}ms")

    # Master sheet, then one per family.
    sheets = [("sheet_00_ALL", "All background presets — identical text on every tile",
               list(tiles.values()))]
    placed = set()
    for idx, (family, types) in enumerate(FAMILY_ORDER, 1):
        group = [tiles[n] for n in names
                 if BACKGROUND_PRESETS[n].get("type") in types and n in tiles]
        placed.update(n for n in names if BACKGROUND_PRESETS[n].get("type") in types)
        if group:
            sheets.append((f"sheet_{idx:02d}_{family}", f"{family} — {'/'.join(types)}", group))

    leftover = [tiles[n] for n in names if n not in placed]
    if leftover:
        sheets.append(("sheet_99_other", "other / unfamilied types", leftover))

    for stem, title, group in sheets:
        sheet = build_sheet(group, args.cols, args.thumb_width, title)
        path = out_dir / f"{stem}.png"
        sheet.save(path)
        print(f"  wrote {path.relative_to(ROOT)}  ({sheet.width}x{sheet.height})")

    write_metrics(rows, out_dir)
    print(f"  wrote {(out_dir / 'metrics.md').relative_to(ROOT)}")

    slowest = max(rows, key=lambda r: r["render_ms"])
    print(f"\nSlowest: {slowest['preset']} at {slowest['render_ms']:.0f}ms/frame "
          f"(~{slowest['render_ms'] * 30 * 60 / 1000 / 60:.1f} min of CPU for a 60s video)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

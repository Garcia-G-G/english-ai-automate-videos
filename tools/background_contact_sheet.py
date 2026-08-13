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
from text_contrast import (  # noqa: E402
    WCAG_NORMAL_TEXT,
    cycle_samples,
    measure_over_time,
)
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

# How many instants an animated preset is sampled at when measuring its
# contrast floor. The tile itself is still a single frame at --t; this only
# affects the numbers.
CYCLE_SAMPLES = 12

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

def measure_contrast(gen: BackgroundGenerator, preset: str) -> Dict[str, float]:
    """Worst contrast this preset reaches anywhere in its cycle.

    Delegates to ``src/text_contrast.py`` so the sheet, the palette
    generator's accept/reject gate and any quoted contrast floor are all
    the same measurement. Animated presets are sampled across a full colour
    cycle — one instant is not a floor.
    """
    spec = BACKGROUND_PRESETS[preset]
    m = measure_over_time(
        lambda t: gen.render_from_preset(t, preset, duration=DEFAULT_DURATION),
        cycle_samples(spec, n=CYCLE_SAMPLES),
    )
    return {
        "bg_luminance_mean": round(m["bg_luminance_mean"], 4),
        "bg_luminance_p95": round(m["bg_luminance_p95"], 4),
        "contrast_yellow_mean": round(m["contrast_mean"], 2),
        "contrast_yellow_worst": round(m["contrast_worst"], 2),
        "contrast_white_mean": round(m["contrast_white_mean"], 2),
        "samples": m["samples"],
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
        "preset", "type", "enabled", "render_ms", "samples",
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
    ap.add_argument("--sample", type=int, default=None,
                    help="evenly spaced subset of the selection, e.g. 24 of "
                         "the generated palettes")
    ap.add_argument("--enabled", action="store_true",
                    help="render exactly the enabled_backgrounds set from "
                         "config.yaml, and report its contrast floor")
    ap.add_argument("--floor", type=float, default=WCAG_NORMAL_TEXT,
                    help=f"contrast floor to check against (default "
                         f"{WCAG_NORMAL_TEXT}, WCAG AA for normal text)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    out_dir = Path(args.out)
    frames_dir = out_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_full_res:
        frames_dir.mkdir(exist_ok=True)

    on = enabled_presets()
    if args.enabled:
        missing = sorted(on - set(BACKGROUND_PRESETS))
        if missing:
            print(f"config names presets that do not exist: {', '.join(missing)}")
            return 1
        names = [n for n in BACKGROUND_PRESETS if n in on]
    else:
        names = [n for n in BACKGROUND_PRESETS
                 if not args.only or args.only in n]

    if args.sample and args.sample < len(names):
        # Evenly spaced rather than the first N, so the sheet reflects the
        # whole set instead of whatever the generator happened to accept
        # first — early palettes face an emptier distinctness gate.
        step = len(names) / args.sample
        names = [names[int(i * step)] for i in range(args.sample)]

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

            metrics = measure_contrast(gen, name)
            composed = overlay_reference_text(bg)

            if not args.no_full_res:
                composed.save(frames_dir / f"{name}.png")

            sub = (f"{preset_type}\n{render_ms:.0f}ms  ·  "
                   f"{metrics['contrast_yellow_worst']:.1f}:1 worst"
                   + ("  ·  ON" if name in on else ""))
            tiles[name] = (name, composed, sub)

            rows.append({"preset": name, "type": preset_type,
                         "enabled": name in on, "render_ms": render_ms,
                         **metrics})
            print(f"  [{i:2d}/{len(names)}] {name:24s} {render_ms:7.0f}ms")

    if args.enabled:
        sheets = [("sheet_enabled",
                   f"enabled_backgrounds — {len(names)} presets in random rotation",
                   list(tiles.values()))]
    elif args.only:
        sheets = [(f"sheet_{args.only.strip('_')}",
                   f"'{args.only}' — {len(names)} presets"
                   + (f", sampled evenly from {len(BACKGROUND_PRESETS)}" if args.sample else ""),
                   list(tiles.values()))]
    else:
        # Master sheet, then one per family.
        sheets = [("sheet_00_ALL", "All background presets — identical text on every tile",
                   list(tiles.values()))]
        placed = set()
        for idx, (family, types) in enumerate(FAMILY_ORDER, 1):
            group = [tiles[n] for n in names
                     if BACKGROUND_PRESETS[n].get("type") in types and n in tiles]
            placed.update(n for n in names if BACKGROUND_PRESETS[n].get("type") in types)
            if group:
                sheets.append((f"sheet_{idx:02d}_{family}",
                               f"{family} — {'/'.join(types)}", group))

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

    # static_gradient is rendered once and reused for every frame, so quoting
    # a per-frame cost for it and multiplying by 1800 would be nonsense.
    slowest = max(rows, key=lambda r: r["render_ms"])
    if slowest["type"] == "static_gradient":
        print(f"\nSlowest: {slowest['preset']} at {slowest['render_ms']:.0f}ms, "
              f"paid once per video (static_gradient renders a single frame)")
    else:
        print(f"\nSlowest: {slowest['preset']} at {slowest['render_ms']:.0f}ms/frame "
              f"(~{slowest['render_ms'] * 30 * 60 / 1000 / 60:.1f} min of CPU "
              f"for a 60s video, before the 5s pre-render cache)")

    # The floor is the worst preset in the set, because random selection means
    # the worst one is the one some video is going to get.
    worst = min(rows, key=lambda r: r["contrast_yellow_worst"])
    below = [r for r in rows if r["contrast_yellow_worst"] < args.floor]
    print(f"Contrast floor: {worst['contrast_yellow_worst']:.2f}:1 ({worst['preset']}), "
          f"against a {args.floor}:1 gate")
    if below:
        print(f"  {len(below)} below the gate: "
              + ", ".join(f"{r['preset']} {r['contrast_yellow_worst']:.2f}" for r in below))
        return 2 if args.enabled else 0
    print("  all presets clear the gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())

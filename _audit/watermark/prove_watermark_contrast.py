#!/usr/bin/env python3
"""Step W proof: the mark is measured, solved, and legible on real footage.

    python3 _audit/watermark/prove_watermark_contrast.py

Reproduces the step report's contrast table after the change, then extracts a
frame from the brightest and the darkest clip in output/artifacts/*/clips/
and states what the treatment cost each of them.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import clip_contrast as cc                                    # noqa: E402
import text_contrast as tc                                    # noqa: E402
from video import brand as B                                  # noqa: E402
from video.utils import manrope                               # noqa: E402
from config.layout import MARGIN_X, SAFE_AREA_BOTTOM          # noqa: E402

OUT = Path(__file__).resolve().parent
SIZE = (tc.VIDEO_WIDTH, tc.VIDEO_HEIGHT)


def glyph_layers():
    """The mark's ink and halo as separate alpha masks, matching brand.py."""
    font = manrope(B.WATERMARK_SIZE, B.WATERMARK_WEIGHT)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, _r, bottom = probe.textbbox((0, 0), B.WATERMARK_TEXT, font=font)
    x = MARGIN_X - left
    y = SAFE_AREA_BOTTOM - B.WATERMARK_BOTTOM_GAP - (bottom - top) - top
    glyph = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((x, y), B.WATERMARK_TEXT, font=font,
                               fill=(255, 255, 255, 255))
    shadow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + B.SHADOW_OFFSET[0], y + B.SHADOW_OFFSET[1]),
                                B.WATERMARK_TEXT, font=font,
                                fill=(0, 0, 0, B.SHADOW_ALPHA))
    shadow = shadow.filter(ImageFilter.GaussianBlur(B.SHADOW_BLUR))
    x0, y0, x1, y1 = B.watermark_bounds()
    sl = (slice(y0, y1), slice(x0, x1))
    ga, sa = np.asarray(glyph)[:, :, 3][sl], np.asarray(shadow)[:, :, 3][sl]
    return (ga > 200), ((ga < 8) & (sa > 8)), sl


INK, HALO, SL = glyph_layers()


def marked(background: np.ndarray) -> np.ndarray:
    """`background` with the real watermark overlay composited on it."""
    img = Image.fromarray(background).convert("RGBA")
    B.draw_watermark(img)
    return np.asarray(img.convert("RGB"))


def ratios(background: np.ndarray):
    """(white-against-background, glyph-ink-against-its-halo)."""
    bg_p95 = float(np.percentile(tc.relative_luminance(cc.mark_patch(background)), 95))
    lum = tc.relative_luminance(marked(background)[SL])
    return (tc.contrast_ratio(1.0, bg_p95),
            tc.contrast_ratio(float(np.median(lum[INK])), float(np.median(lum[HALO]))),
            bg_p95)


def treat(background: np.ndarray, strength: float) -> np.ndarray:
    """Apply the local mark scrim exactly as clip_background does."""
    if strength <= 0:
        return background
    out = background.astype(np.float32)
    rx0, ry0, rx1, ry1 = cc.mark_rect()
    out[ry0:ry1, rx0:rx1] *= cc.mark_profile(strength=strength)
    return np.clip(out, 0, 255).astype(np.uint8)


def flat(p95: float) -> np.ndarray:
    v = int(round(cc._grey_for(p95)))
    return np.full((tc.VIDEO_HEIGHT, tc.VIDEO_WIDTH, 3), v, dtype=np.uint8)


# ── 1. the table, reproduced after the change ────────────────────────────
print("THE CONTRAST TABLE, AFTER. Flat backgrounds, real overlay, mark scrim")
print("solved the way the renderer solves it: measure the frame's own mark zone,")
print("then solve_strength against white. No band credited — this is the")
print("educational case, where the readability band cannot reach the mark.")
print()
print("`derived` is strength_for's analytic answer for the NOMINAL p95, which")
print("is the column the step report quotes. It differs from `scrim` by up to")
print("one 0.005 scan step because the frame's measured p95 is not exactly the")
print("nominal one — _grey_for lands between two 8-bit values and the frame has")
print("to pick one. Solving against the nominal number instead of the measured")
print("one is what put two rows at 2.9995 on the first run of this proof.\n")
print(f"{'bg p95':>8} {'derived':>8} {'scrim':>7} "
      f"| {'white/bg':>9} {'glyph/halo':>11} | {'white/bg':>9} {'glyph/halo':>11}")
print(f"{'':>8} {'':>8} {'':>7} | {'BEFORE':>9} {'BEFORE':>11} "
      f"| {'AFTER':>9} {'AFTER':>11}  verdict")
rows = []
for p95 in (0.050, 0.200, 0.400, 0.600, 0.797, 0.950):
    base = flat(p95)
    derived = cc.strength_for(p95, cc.FLOOR, cc.MARK_COLOR)
    # The production path: measure this frame's mark zone, solve on what was
    # measured. treatment_for_dir does exactly this over every clip sample.
    measured = cc.measure_zone_patch(cc.mark_patch(base), cc.MARK_COLOR)
    s = cc.solve_strength([measured["p95_rgb"]], cc.FLOOR, cc.MARK_COLOR)
    b_white, b_halo, _ = ratios(base)
    a_white, a_halo, _ = ratios(treat(base, s))
    ok = a_white >= cc.FLOOR
    rows.append(ok)
    print(f"{p95:8.3f} {derived:8.3f} {s:7.3f} "
          f"| {b_white:9.2f} {b_halo:11.2f} "
          f"| {a_white:9.2f} {a_halo:11.2f}  {'ok' if ok else 'FAIL'}")
print(f"\nevery row at or above {cc.FLOOR}: {all(rows)}")

# ── 2. the brightest and darkest real clips ──────────────────────────────
clips = sorted(ROOT.glob("output/artifacts/*/clips/*.mp4"))
print(f"\n\nREAL FOOTAGE — {len(clips)} clips in output/artifacts/*/clips/")
measured = []
for path in clips:
    r = cc.worst_over_clip(path, "educational")
    if r:
        measured.append((r["mark_worst_contrast"], path))
measured.sort()
brightest, darkest = measured[0], measured[-1]
print(f"  brightest under the mark: {brightest[1].name}  {brightest[0]:.2f}:1")
print(f"  darkest   under the mark: {darkest[1].name}  {darkest[0]:.2f}:1")

for label, (_c, path) in (("brightest", brightest), ("darkest", darkest)):
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(path, tmp / path.name)
    from video.clip_background import ClipLibraryBackground
    bg = ClipLibraryBackground(str(tmp), *SIZE, duration=1.0,
                               video_type="educational")
    plan = bg.contrast_report
    treated = bg.get_frame(0.0)
    bg._mark = None
    untreated = bg.get_frame(0.0)
    bg.close()
    shutil.rmtree(tmp, ignore_errors=True)

    b_white, b_halo, b_p95 = ratios(untreated)
    a_white, a_halo, a_p95 = ratios(treated)

    changed = np.any(treated != untreated, axis=2)
    rx0, ry0, rx1, ry1 = cc.mark_rect()
    outside = changed.copy()
    outside[ry0:ry1, rx0:rx1] = False
    darkening = 1.0 - (treated[ry0:ry1, rx0:rx1].astype(np.float32).mean()
                       / max(1e-6, untreated[ry0:ry1, rx0:rx1].astype(np.float32).mean()))

    print(f"\n  {label.upper()}: {path.name}")
    print(f"    mark-zone p95 luminance   {b_p95:.3f} -> {a_p95:.3f}")
    print(f"    white against background  {b_white:.2f}:1 -> {a_white:.2f}:1 "
          f"(floor {cc.FLOOR})")
    print(f"    glyph against its halo    {b_halo:.2f}:1 -> {a_halo:.2f}:1")
    print(f"    solved mark scrim         {plan['mark_strength']:.3f}")
    print(f"    band credited over mark   {plan['mark_band_credit']:.3f}")
    print(f"    pixels changed outside the rectangle: {int(outside.sum())}")
    print(f"    VISUAL COST: rectangle mean darkened by {darkening * 100:.1f}%")

    out = OUT / f"{label}_{path.stem}.png"
    Image.fromarray(marked(treated)).save(out)
    Image.fromarray(marked(untreated)).save(
        OUT / f"{label}_{path.stem}_untreated.png")
    print(f"    frame: {out.relative_to(ROOT)}")

#!/usr/bin/env python3
"""Reversals per second, quantised and true, before and after.

    python3 _audit/kenburns/measure_reversals.py

docs/KENBURNS_DIAGNOSIS.md established two coupled faults: too much motion,
and three int() truncations that quantised the camera to whole source pixels.
It also established the trap — truncation error is constant per frame, so
slowing the pan makes stepping a LARGER share of the movement. photo_city_blur
had the calmest true path (0.17 rev/s) and the most erratic output (4.40).

So all four combinations are measured, not just the endpoints:

    old amplitude + truncated   what shipped
    old amplitude + sub-pixel   sampling fixed alone
    new amplitude + truncated   the trap: amplitude fixed alone
    new amplitude + sub-pixel   both, which is what landed

"true" counts reversals in the continuous pan curve — the camera genuinely
turning round. "quantised" counts them in the integer offsets a viewer
actually sees. The gap between the two is stepping, isolated from motion.
"""

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import kenburns_crop  # noqa: E402

FPS = 30
DURATION = 30.0
PHOTO_W, PHOTO_H = 1024, 1792
OUT_W, OUT_H = 1080, 1920


def old_curve(t, pan_speed, duration=DURATION):
    """The amplitudes as they shipped, frozen here so the comparison is real."""
    cycle = duration if duration > 0 else 30.0
    zoom_slow = (math.sin(t * math.pi * 2 / cycle) + 1) / 2
    zoom_med = (math.sin(t * 1.2 + 0.7) + 1) / 2 * 0.35
    zoom_fast = (math.sin(t * 2.5 + 1.5) + 1) / 2 * 0.15
    zoom_t = min(1.0, zoom_slow * 0.55 + zoom_med + zoom_fast)
    pan_x = (math.sin(t * 0.5 * pan_speed) * 0.45
             + math.sin(t * 0.22 * pan_speed + 1.2) * 0.35
             + math.sin(t * 0.9 * pan_speed + 3.0) * 0.15)
    pan_y = (math.sin(t * 0.4 * pan_speed + 0.7) * 0.45
             + math.cos(t * 0.18 * pan_speed + 2.1) * 0.30
             + math.cos(t * 0.75 * pan_speed + 4.5) * 0.15)
    return zoom_t, pan_x, pan_y


def new_curve(t, pan_speed, duration=DURATION):
    from backgrounds import KENBURNS_PAN_AMPLITUDE, KENBURNS_PAN_RATE
    cycle = duration if duration > 0 else 30.0
    zoom_t = (math.sin(t * math.pi * 2 / cycle - math.pi / 2) + 1) / 2
    rate = KENBURNS_PAN_RATE * pan_speed
    return (zoom_t,
            math.sin(t * rate) * KENBURNS_PAN_AMPLITUDE,
            math.cos(t * rate + 1.1) * KENBURNS_PAN_AMPLITUDE)


def offsets(curve, pan_speed, truncate):
    """Per-frame crop origin, in source pixels."""
    zoom_min, zoom_max = 1.05, 1.20
    xs, ys, zs = [], [], []
    for i in range(int(DURATION * FPS)):
        t = i / FPS
        zoom_t, pan_x, pan_y = curve(t, pan_speed)
        zoom = zoom_min + (zoom_max - zoom_min) * zoom_t
        if truncate:
            crop_w = int(OUT_W / zoom)
            crop_h = int(OUT_H / zoom)
            mox = (PHOTO_W - crop_w) // 2
            moy = (PHOTO_H - crop_h) // 2
            cx = PHOTO_W // 2 + int(pan_x * mox)
            cy = PHOTO_H // 2 + int(pan_y * moy)
            xs.append(float(cx)); ys.append(float(cy))
        else:
            base_w = min(float(PHOTO_W), PHOTO_H * OUT_W / OUT_H)
            base_h = base_w * OUT_H / OUT_W
            crop_w, crop_h = base_w / zoom, base_h / zoom
            mox = max(0.0, (PHOTO_W - crop_w) / 2)
            moy = max(0.0, (PHOTO_H - crop_h) / 2)
            xs.append(PHOTO_W / 2 + pan_x * mox)
            ys.append(PHOTO_H / 2 + pan_y * moy)
        zs.append(zoom)
    return np.array(xs), np.array(ys), np.array(zs)


def reversals_per_s(series, eps=1e-9):
    d = np.diff(series)
    d = d[np.abs(d) > eps]
    if len(d) < 2:
        return 0.0
    return int(np.sum(np.sign(d[1:]) != np.sign(d[:-1]))) / DURATION


def px_per_s(xs, ys):
    d = np.hypot(np.diff(xs), np.diff(ys))
    return float(d.mean() * FPS)


def stalled_pct(xs, ys):
    d = np.hypot(np.diff(xs), np.diff(ys))
    return 100.0 * float(np.mean(d < 1e-9))


def main():
    print(f"{DURATION:.0f}s at {FPS}fps, source {PHOTO_W}x{PHOTO_H}, "
          f"output {OUT_W}x{OUT_H}\n")
    header = (f"{'configuration':30s} {'pan px/s':>9s} {'stalled':>8s} "
              f"{'rev/s x':>8s} {'rev/s y':>8s} {'rev/s zoom':>11s}")
    print(header)
    print("-" * len(header))

    for pan_speed, label in ((1.20, "photo_earth   pan_speed 1.20"),
                             (0.60, "photo_city_blur pan_speed 0.60")):
        print(f"\n  {label}")
        for curve, cname in ((old_curve, "old amplitude"), (new_curve, "new amplitude")):
            for truncate, sname in ((True, "truncated"), (False, "sub-pixel")):
                xs, ys, zs = offsets(curve, pan_speed, truncate)
                print(f"    {cname + ' + ' + sname:26s} {px_per_s(xs, ys):9.1f} "
                      f"{stalled_pct(xs, ys):7.1f}% {reversals_per_s(xs):8.2f} "
                      f"{reversals_per_s(ys):8.2f} {reversals_per_s(zs):11.2f}")


if __name__ == "__main__":
    main()

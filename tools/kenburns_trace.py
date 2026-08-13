#!/usr/bin/env python3
"""Trace what the Ken Burns camera actually does, frame by frame.

The operator reports that photo backgrounds "move erratically". That could
be two very different faults and they want opposite fixes:

* **too much motion** — the camera path itself is wrong, moving too far or
  changing direction too often, in which case the numbers are smooth and
  the problem is the amplitudes.
* **frame-stepping** — the path is fine but it is being sampled onto whole
  pixels, so the image sits still and then jumps, in which case the
  amplitudes are innocent and the quantisation is the fault.

This measures both, so the answer is evidence rather than a hunch.

For every frame at 30fps it records the crop rectangle the renderer would
compute, then reports:

* how often the crop offset does not change at all (dwell), and how big the
  jump is when it finally does — the signature of stepping;
* the same displacements converted to screen pixels, since a one-pixel move
  in a cropped source is more than one pixel after the crop is blown up to
  1080x1920;
* how often the zoom curve saturates against its own ceiling, which freezes
  the zoom outright;
* how often the pan reverses direction, which is what "erratic" usually
  means.

The crop maths is replicated from ``BackgroundGenerator.photo_kenburns``,
then checked against real rendered frames so the trace is known to describe
the code that actually runs, not the code as read.

    python3 tools/kenburns_trace.py
    python3 tools/kenburns_trace.py --preset photo_city --duration 30
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from backgrounds import BACKGROUND_PRESETS, BackgroundGenerator  # noqa: E402

OUT_DIR = ROOT / "_audit" / "kenburns"


def crop_for(t: float, photo_w: int, photo_h: int, width: int, height: int,
             zoom_range, pan_speed: float, duration: float) -> Dict:
    """Replicate photo_kenburns' crop maths for time t.

    Mirrors src/backgrounds.py:1498-1538 exactly, including every int()
    truncation — those are the thing under investigation, so rounding
    differently here would hide the fault.
    """
    zoom_min, zoom_max = zoom_range
    cycle = duration if duration > 0 else 30.0

    zoom_slow = (math.sin(t * math.pi * 2 / cycle) + 1) / 2
    zoom_med = (math.sin(t * 1.2 + 0.7) + 1) / 2 * 0.35
    zoom_fast = (math.sin(t * 2.5 + 1.5) + 1) / 2 * 0.15
    zoom_raw = zoom_slow * 0.55 + zoom_med + zoom_fast
    zoom_t = min(1.0, zoom_raw)
    zoom = zoom_min + (zoom_max - zoom_min) * zoom_t

    pan_x = (math.sin(t * 0.5 * pan_speed) * 0.45
             + math.sin(t * 0.22 * pan_speed + 1.2) * 0.35
             + math.sin(t * 0.9 * pan_speed + 3.0) * 0.15)
    pan_y = (math.sin(t * 0.4 * pan_speed + 0.7) * 0.45
             + math.cos(t * 0.18 * pan_speed + 2.1) * 0.30
             + math.cos(t * 0.75 * pan_speed + 4.5) * 0.15)

    crop_w = int(width / zoom)
    crop_h = int(height / zoom)

    max_offset_x = (photo_w - crop_w) // 2
    max_offset_y = (photo_h - crop_h) // 2

    center_x = photo_w // 2 + int(pan_x * max_offset_x)
    center_y = photo_h // 2 + int(pan_y * max_offset_y)

    left = max(0, center_x - crop_w // 2)
    top = max(0, center_y - crop_h // 2)
    right = min(photo_w, left + crop_w)
    bottom = min(photo_h, top + crop_h)
    if right - left < crop_w:
        left = max(0, right - crop_w)
    if bottom - top < crop_h:
        top = max(0, bottom - crop_h)

    return {
        "t": t,
        "zoom_raw": zoom_raw,
        "zoom_t": zoom_t,
        "zoom_clipped": zoom_raw > 1.0,
        "zoom": zoom,
        "pan_x": pan_x,
        "pan_y": pan_y,
        "crop_w": crop_w,
        "crop_h": crop_h,
        "left": left,
        "top": top,
        # One source pixel becomes this many screen pixels after the crop is
        # scaled up to the full frame. It is why sub-pixel truncation in
        # source space is visible at all.
        "px_gain": width / crop_w,
    }


def trace(preset_name: str, duration: float, fps: int) -> List[Dict]:
    spec = BACKGROUND_PRESETS[preset_name]
    if spec.get("type") != "photo_kenburns":
        raise SystemExit(f"{preset_name} is not a photo_kenburns preset")

    gen = BackgroundGenerator(1080, 1920)
    photo = gen._load_photo(spec["category"])
    if photo is None:
        raise SystemExit(f"no photo available for category {spec['category']}")

    rows = []
    n = int(duration * fps)
    for i in range(n):
        rows.append(crop_for(
            i / fps, photo.width, photo.height, 1080, 1920,
            spec.get("zoom_range", (1.05, 1.20)),
            spec.get("pan_speed", 0.3),
            duration,
        ))
    return rows


def verify_against_render(preset_name: str, rows: List[Dict], fps: int,
                          n_frames: int = 60) -> Dict:
    """Confirm the replicated maths matches frames the renderer really makes.

    Renders consecutive frames and measures how much each differs from the
    one before. If the trace is right, frames whose crop offset did not
    change should differ far less than frames where it jumped.
    """
    gen = BackgroundGenerator(1080, 1920)
    prev = None
    diffs = []
    for i in range(n_frames):
        frame = gen.render_from_preset(i / fps, preset_name, duration=30.0)
        if prev is not None:
            diffs.append(float(np.abs(frame.astype(np.int16)
                                      - prev.astype(np.int16)).mean()))
        prev = frame

    moved, still = [], []
    for i, d in enumerate(diffs, start=1):
        stepped = (rows[i]["left"] != rows[i - 1]["left"]
                   or rows[i]["top"] != rows[i - 1]["top"])
        (moved if stepped else still).append(d)

    return {
        "frames": n_frames,
        "mean_diff_when_crop_moved": float(np.mean(moved)) if moved else None,
        "mean_diff_when_crop_still": float(np.mean(still)) if still else None,
        "n_moved": len(moved),
        "n_still": len(still),
    }


def analyse(rows: List[Dict], fps: int) -> Dict:
    left = np.array([r["left"] for r in rows], dtype=np.int64)
    top = np.array([r["top"] for r in rows], dtype=np.int64)
    gain = np.array([r["px_gain"] for r in rows])

    dl = np.diff(left)
    dt_ = np.diff(top)
    step = np.hypot(dl, dt_)
    screen_step = step * gain[1:]

    still = int(np.sum((dl == 0) & (dt_ == 0)))

    # Direction reversals: a sign change in per-frame displacement is the
    # camera changing its mind, which is what reads as erratic.
    #
    # Counted twice, and the difference is the whole question. On the
    # *continuous* pan curve a reversal is the camera path genuinely turning
    # around — a property of the amplitudes and frequencies. On the
    # *quantised* integer offsets, extra reversals appear that the path never
    # made: where true velocity is below one pixel per frame, truncation
    # makes the offset jitter back and forth. Continuous reversals mean too
    # much motion. Excess quantised ones mean stepping.
    def reversals(d):
        s = np.sign(d[d != 0])
        return int(np.sum(s[1:] != s[:-1])) if len(s) > 1 else 0

    pan_x = np.array([r["pan_x"] for r in rows])
    pan_y = np.array([r["pan_y"] for r in rows])
    cont_x, cont_y = reversals(np.diff(pan_x)), reversals(np.diff(pan_y))

    # Frames where the integer step disagrees with which way the continuous
    # path was actually heading — pure quantisation artefact.
    def disagreement(dq, dc):
        both = (dq != 0) & (np.abs(dc) > 1e-12)
        return int(np.sum(np.sign(dq[both]) != np.sign(dc[both])))

    jitter = disagreement(dl, np.diff(pan_x)) + disagreement(dt_, np.diff(pan_y))

    zoom = np.array([r["zoom"] for r in rows])
    clipped = int(sum(1 for r in rows if r["zoom_clipped"]))

    # What the zoom costs in visible motion: as the crop narrows, the content
    # at the frame edge sweeps inward. This is the speed of that sweep, in
    # screen pixels per second, which is comparable with the pan figures.
    crop_w = np.array([r["crop_w"] for r in rows], dtype=float)
    edge_speed = np.abs(np.diff(crop_w)) / 2 * gain[1:] * fps

    return {
        "frames": len(rows),
        "still_frames": still,
        "still_pct": 100.0 * still / max(1, len(dl)),
        "step_src_max": float(step.max()),
        "step_src_mean": float(step[step > 0].mean()) if np.any(step > 0) else 0.0,
        "step_screen_max": float(screen_step.max()),
        "step_screen_mean": float(screen_step[screen_step > 0].mean())
                            if np.any(screen_step > 0) else 0.0,
        "step_screen_p99": float(np.percentile(screen_step, 99)),
        "reversals_x": reversals(dl),
        "reversals_y": reversals(dt_),
        "reversals_per_sec": (reversals(dl) + reversals(dt_)) / (len(rows) / fps),
        "reversals_continuous_x": cont_x,
        "reversals_continuous_y": cont_y,
        "reversals_continuous_per_sec": (cont_x + cont_y) / (len(rows) / fps),
        "quantisation_jitter_frames": jitter,
        "quantisation_jitter_pct": 100.0 * jitter / max(1, len(dl)),
        "zoom_min": float(zoom.min()),
        "zoom_max": float(zoom.max()),
        "zoom_clipped_frames": clipped,
        "zoom_clipped_pct": 100.0 * clipped / len(rows),
        "zoom_reversals": reversals(np.diff(zoom)),
        "zoom_reversals_per_sec": reversals(np.diff(zoom)) / (len(rows) / fps),
        "zoom_edge_speed_mean": float(edge_speed.mean()),
        "zoom_edge_speed_max": float(edge_speed.max()),
        "pan_speed_px_per_sec": float(np.mean(screen_step) * fps),
        "crop_w_min": min(r["crop_w"] for r in rows),
        "crop_w_max": max(r["crop_w"] for r in rows),
    }


def sparkline(values, width: int = 72, height: int = 9) -> List[str]:
    """A crude plot, because there is no matplotlib here and a shape helps."""
    v = np.array(values, dtype=float)
    idx = np.linspace(0, len(v) - 1, width).astype(int)
    v = v[idx]
    lo, hi = v.min(), v.max()
    if hi - lo < 1e-9:
        hi = lo + 1
    rows = [[" "] * width for _ in range(height)]
    for x, val in enumerate(v):
        y = int(round((val - lo) / (hi - lo) * (height - 1)))
        rows[height - 1 - y][x] = "*"
    return ["".join(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", default="photo_earth")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--verify-frames", type=int, default=60,
                    help="how many real frames to render as a cross-check")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    rows = trace(args.preset, args.duration, args.fps)
    stats = analyse(rows, args.fps)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{args.preset}_trace.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"=== {args.preset} — {stats['frames']} frames "
          f"({args.duration}s at {args.fps}fps) ===\n")

    print("PAN, in source pixels then screen pixels")
    print(f"  frames where the crop did not move   {stats['still_frames']} "
          f"({stats['still_pct']:.1f}%)")
    print(f"  mean step when it did move           {stats['step_src_mean']:.2f} src px"
          f"  ->  {stats['step_screen_mean']:.2f} screen px")
    print(f"  largest single step                  {stats['step_src_max']:.0f} src px"
          f"  ->  {stats['step_screen_max']:.1f} screen px")
    print(f"  99th percentile step                 {stats['step_screen_p99']:.1f} screen px")
    print(f"  direction reversals, quantised       {stats['reversals_x']} in x, "
          f"{stats['reversals_y']} in y  ({stats['reversals_per_sec']:.2f}/s)")
    print(f"  direction reversals, true path       {stats['reversals_continuous_x']} in x, "
          f"{stats['reversals_continuous_y']} in y  "
          f"({stats['reversals_continuous_per_sec']:.2f}/s)")
    print(f"  steps going the wrong way            "
          f"{stats['quantisation_jitter_frames']} "
          f"({stats['quantisation_jitter_pct']:.1f}% — pure truncation artefact)")

    print("\nZOOM")
    print(f"  range reached                        {stats['zoom_min']:.3f} -> {stats['zoom_max']:.3f}")
    print(f"  crop width                           {stats['crop_w_max']} -> {stats['crop_w_min']} px")
    print(f"  frames saturated at the 1.0 ceiling  {stats['zoom_clipped_frames']} "
          f"({stats['zoom_clipped_pct']:.1f}%)")
    print(f"  zoom direction reversals             {stats['zoom_reversals']}  "
          f"({stats['zoom_reversals_per_sec']:.2f}/s)")
    print(f"  frame edge sweep from zoom alone     "
          f"{stats['zoom_edge_speed_mean']:.0f} px/s mean, "
          f"{stats['zoom_edge_speed_max']:.0f} px/s peak")
    print(f"  pan speed for comparison             "
          f"{stats['pan_speed_px_per_sec']:.0f} px/s mean")

    print("\nzoom over time")
    for line in sparkline([r["zoom"] for r in rows]):
        print("  " + line)

    print("\npan_x over time")
    for line in sparkline([r["pan_x"] for r in rows]):
        print("  " + line)

    if args.verify_frames:
        print(f"\nCROSS-CHECK against {args.verify_frames} real rendered frames")
        v = verify_against_render(args.preset, rows, args.fps, args.verify_frames)
        print(f"  mean pixel change, crop moved      "
              f"{v['mean_diff_when_crop_moved']}  ({v['n_moved']} frames)")
        print(f"  mean pixel change, crop still      "
              f"{v['mean_diff_when_crop_still']}  ({v['n_still']} frames)")

    print(f"\ntrace written to {(out / f'{args.preset}_trace.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

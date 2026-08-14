#!/usr/bin/env python3
"""Step 1 of 6a: measure where content actually sits. No code changes.

Content is isolated exactly rather than guessed at: every frame is rendered
through the real pipeline on a static_gradient background, and the same
background is regenerated independently and subtracted. What survives the
subtraction is drawn content, to the pixel.

The mascot is forced OFF for this run. It was installed days ago and its
footprint is already measured separately; leaving it on would paint content
into the very region the measurement is asking about.

    python3 _audit/layout/measure_layout.py
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.ERROR)

import video as videomod  # noqa: E402
import video.character as character  # noqa: E402
from config.layout import (  # noqa: E402
    SAFE_AREA_TOP, SAFE_AREA_BOTTOM, VIDEO_HEIGHT, VIDEO_WIDTH,
)

BG = "static_ocean"
SAMPLE_FPS = 3          # frames per second of source video to sample
DIFF_THRESHOLD = 16     # per-pixel RGB sum delta that counts as "drawn"

CASES = [
    ("educational",   "output/step3_verify/edu2_FRESH.json",   "output/step3_verify/edu2_FRESH.mp3"),
    ("quiz",          "output/step3_verify/q_FRESH.json",      "output/step3_verify/q_FRESH.mp3"),
    ("true_false",    "output/step3_verify/tf_FRESH.json",     "output/step3_verify/tf_FRESH.mp3"),
    ("fill_blank",    "output/r1_verify/trim_run1.json",       "output/r1_verify/trim_run1.mp3"),
    ("pronunciation", "output/smoke/pronunciation.json",       "output/smoke/pronunciation.mp3"),
    ("vocabulary",    "output/smoke/vocabulary.json",          "output/smoke/vocabulary.mp3"),
]

FRAME_FNS = {
    "educational": "create_frame_educational",
    "quiz": "create_frame_quiz",
    "true_false": "create_frame_true_false",
    "fill_blank": "create_frame_fill_blank",
    "pronunciation": "create_frame_pronunciation",
    "vocabulary": "create_frame_vocabulary",
}


def content_mask(frame_rgb: np.ndarray, t: float) -> np.ndarray:
    """Pixels that the renderer drew, as opposed to background."""
    from video.backgrounds import gradient
    bg = np.asarray(gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)).astype(np.int16)
    if bg.shape != frame_rgb.shape:
        bg = bg[:, :, :3]
    delta = np.abs(frame_rgb.astype(np.int16) - bg).sum(axis=2)
    return delta > DIFF_THRESHOLD


def measure(video_type: str, data_path: str, audio_path: str) -> dict:
    """Render through the real pipeline, capture frames, measure content."""
    captured = []

    target = FRAME_FNS[video_type]
    original = getattr(videomod, target)

    def spy(t, data, duration, *a, **kw):
        frame = original(t, data, duration, *a, **kw)
        captured.append((t, np.asarray(frame)))
        return frame

    setattr(videomod, target, spy)
    try:
        out = ROOT / "_audit" / "layout" / f"_probe_{video_type}.mp4"
        videomod.generate_video(
            audio_path=str(ROOT / audio_path),
            data_path=str(ROOT / data_path),
            output_path=str(out),
            video_type=video_type,
            fps=SAMPLE_FPS,
            background=BG,
        )
    finally:
        setattr(videomod, target, original)

    if not captured:
        return {"type": video_type, "error": "no frames captured"}

    band_h = SAFE_AREA_BOTTOM - SAFE_AREA_TOP
    row_hits = np.zeros(VIDEO_HEIGHT, dtype=np.int64)
    band_area_frac = []
    com_list = []
    outside_above = outside_below = 0
    total_content = 0

    for t, frame in captured:
        m = content_mask(frame[:, :, :3], t)
        if not m.any():
            continue
        rows = m.sum(axis=1)
        row_hits += rows
        total_content += int(m.sum())
        outside_above += int(m[:SAFE_AREA_TOP].sum())
        outside_below += int(m[SAFE_AREA_BOTTOM:].sum())

        band = m[SAFE_AREA_TOP:SAFE_AREA_BOTTOM]
        band_area_frac.append(band.sum() / band.size)
        if band.sum():
            ys = np.arange(SAFE_AREA_TOP, SAFE_AREA_BOTTOM)
            com_list.append(float((band.sum(axis=1) * ys).sum() / band.sum()))

    # Rows that carry content in ANY sampled frame — the band the layout
    # actually uses over the whole video, as opposed to at one instant.
    used_rows = np.where(row_hits > 0)[0]
    band_rows_used = np.where(row_hits[SAFE_AREA_TOP:SAFE_AREA_BOTTOM] > 0)[0]

    band_centre = (SAFE_AREA_TOP + SAFE_AREA_BOTTOM) / 2
    com = float(np.mean(com_list)) if com_list else float("nan")

    return {
        "type": video_type,
        "frames": len(captured),
        "duration": float(max(t for t, _ in captured)),
        "band_area_pct": 100 * float(np.mean(band_area_frac)) if band_area_frac else 0.0,
        "band_rows_used_pct": 100 * len(band_rows_used) / band_h,
        "com": com,
        "band_centre": band_centre,
        "com_offset": com - band_centre,
        "content_top": int(used_rows.min()) if len(used_rows) else -1,
        "content_bottom": int(used_rows.max()) if len(used_rows) else -1,
        "outside_above_pct": 100 * outside_above / total_content if total_content else 0.0,
        "outside_below_pct": 100 * outside_below / total_content if total_content else 0.0,
        "row_hits": row_hits,
    }


def main():
    # Force the mascot off — see module docstring.
    character._renderer = None
    character._renderer_resolved = True

    results = []
    for vt, dp, ap in CASES:
        if not (ROOT / dp).exists() or not (ROOT / ap).exists():
            print(f"SKIP {vt}: missing {dp} or {ap}")
            continue
        print(f"measuring {vt} ...", flush=True)
        try:
            results.append(measure(vt, dp, ap))
        except Exception as e:
            print(f"  FAILED {vt}: {type(e).__name__}: {e}")

    print()
    print(f"SAFE BAND {SAFE_AREA_TOP}..{SAFE_AREA_BOTTOM} "
          f"(height {SAFE_AREA_BOTTOM - SAFE_AREA_TOP}, centre "
          f"{(SAFE_AREA_TOP + SAFE_AREA_BOTTOM) // 2})")
    print()
    hdr = (f"{'type':14s} {'frames':>6s} {'band ink':>9s} {'rows used':>10s} "
           f"{'CoM':>7s} {'vs centre':>10s} {'content y':>14s} {'above':>7s} {'below':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        if "error" in r:
            print(f"{r['type']:14s} {r['error']}")
            continue
        print(f"{r['type']:14s} {r['frames']:6d} {r['band_area_pct']:8.1f}% "
              f"{r['band_rows_used_pct']:9.1f}% {r['com']:7.0f} "
              f"{r['com_offset']:+9.0f} {r['content_top']:6d}..{r['content_bottom']:<6d} "
              f"{r['outside_above_pct']:6.1f}% {r['outside_below_pct']:6.1f}%")

    out = ROOT / "_audit" / "layout" / "measurements.json"
    out.write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "row_hits"} for r in results],
        indent=2))

    np.save(ROOT / "_audit" / "layout" / "row_profiles.npy",
            {r["type"]: r["row_hits"] for r in results if "row_hits" in r},
            allow_pickle=True)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pin where every renderer puts its content, so layout moves show up here.

    python3 -m pytest tests/test_layout_pins.py
    python3 tests/test_layout_pins.py --update    # regenerate the golden

This exists because config/layout.py declares position constants that no
renderer reads, while the renderers use private constants holding different
values. Reconciling those two sets is supposed to move nothing. "Supposed to"
is not evidence, and the evidence for a layout change is otherwise a human
watching a video and noticing — which is how a 100px divergence survived in
the first place.

WHAT IS PINNED, AND WHY THIS SHAPE

Not a frame hash: those break on a font update or an antialiasing change and
tell you nothing about what moved. What is pinned is geometry — for each
sampled frame, the bounding box of drawn content and the list of horizontal
bands that carry it. A constant that shifts by 30px moves a band by 30px and
names itself in the diff.

Content is isolated by rendering on a static_gradient background and
subtracting that same background, so "content" means pixels a renderer drew
rather than pixels that happen to be bright.

The mascot is forced off. It is config-driven and off by default; leaving it
live would pin a decision that belongs to config rather than to layout.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

GOLDEN = Path(__file__).parent / "fixtures" / "layout_pins.json"

# Sampling rate for the pin. Low on purpose: this renders real videos, and
# one frame per second already catches any constant-sized shift.
PIN_FPS = 1
BG = "static_ocean"
DIFF_THRESHOLD = 16     # per-pixel RGB sum delta that counts as drawn
ROW_MIN_PIXELS = 20     # a row carries content above this many pixels
BAND_BUCKET = 8         # row bands quantised to this, to absorb antialiasing
TOLERANCE = 2           # px of slack on bbox edges

FIXTURES = [
    ("educational",   "output/step3_verify/edu2_FRESH.json", "output/step3_verify/edu2_FRESH.mp3"),
    ("quiz",          "output/step3_verify/q_FRESH.json",    "output/step3_verify/q_FRESH.mp3"),
    ("true_false",    "output/step3_verify/tf_FRESH.json",   "output/step3_verify/tf_FRESH.mp3"),
    ("fill_blank",    "output/r1_verify/trim_run1.json",     "output/r1_verify/trim_run1.mp3"),
    ("pronunciation", "output/smoke/pronunciation.json",     "output/smoke/pronunciation.mp3"),
    ("vocabulary",    "output/smoke/vocabulary.json",        "output/smoke/vocabulary.mp3"),
]

FRAME_FN = {
    "educational": "create_frame_educational",
    "quiz": "create_frame_quiz",
    "true_false": "create_frame_true_false",
    "fill_blank": "create_frame_fill_blank",
    "pronunciation": "create_frame_pronunciation",
    "vocabulary": "create_frame_vocabulary",
}


def _row_bands(mask: np.ndarray) -> list:
    """Contiguous row runs carrying content, quantised to BAND_BUCKET."""
    rows = mask.sum(axis=1) > ROW_MIN_PIXELS
    bands, start = [], None
    for i, v in enumerate(rows):
        if v and start is None:
            start = i
        elif not v and start is not None:
            bands.append([start // BAND_BUCKET * BAND_BUCKET,
                          -(-i // BAND_BUCKET) * BAND_BUCKET])
            start = None
    if start is not None:
        bands.append([start // BAND_BUCKET * BAND_BUCKET,
                      -(-len(rows) // BAND_BUCKET) * BAND_BUCKET])
    return bands


def measure_type(video_type: str, data_path: str, audio_path: str,
                 out_dir: Path) -> list:
    """Render through the real pipeline and describe each sampled frame."""
    import video as videomod
    import video.character as character
    from config.layout import VIDEO_HEIGHT, VIDEO_WIDTH
    from video.backgrounds import gradient

    character._renderer = None
    character._renderer_resolved = True   # force the mascot off

    captured = []
    name = FRAME_FN[video_type]
    original = getattr(videomod, name)

    def spy(t, data, duration, *a, **kw):
        frame = original(t, data, duration, *a, **kw)
        captured.append((round(float(t), 3), np.asarray(frame)))
        return frame

    setattr(videomod, name, spy)
    try:
        videomod.generate_video(
            audio_path=str(ROOT / audio_path),
            data_path=str(ROOT / data_path),
            output_path=str(out_dir / f"{video_type}.mp4"),
            video_type=video_type,
            fps=PIN_FPS,
            background=BG,
        )
    finally:
        setattr(videomod, name, original)

    out = []
    for t, frame in captured:
        bg = np.asarray(gradient(VIDEO_WIDTH, VIDEO_HEIGHT, t)).astype(np.int16)
        mask = np.abs(frame[:, :, :3].astype(np.int16)
                      - bg[:, :, :3]).sum(axis=2) > DIFF_THRESHOLD
        if not mask.any():
            out.append({"t": t, "bbox": None, "bands": []})
            continue
        ys, xs = np.where(mask)
        out.append({
            "t": t,
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "bands": _row_bands(mask),
        })
    return out


def build_all(out_dir: Path) -> dict:
    result = {}
    for vt, dp, ap in FIXTURES:
        if not (ROOT / dp).exists() or not (ROOT / ap).exists():
            continue
        result[vt] = measure_type(vt, dp, ap, out_dir)
    return result


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    return build_all(tmp_path_factory.mktemp("pins"))


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden not generated yet")
@pytest.mark.parametrize("video_type", [f[0] for f in FIXTURES])
def test_layout_unchanged(measured, video_type):
    golden = json.loads(GOLDEN.read_text())
    assert video_type in golden, f"{video_type} missing from golden"
    assert video_type in measured, f"{video_type} produced no frames"

    want, got = golden[video_type], measured[video_type]
    assert len(got) == len(want), (
        f"{video_type}: frame count changed {len(want)} -> {len(got)}")

    for w, g in zip(want, got):
        assert g["t"] == w["t"], f"{video_type}: timestamp drift"
        if w["bbox"] is None or g["bbox"] is None:
            assert w["bbox"] == g["bbox"], f"{video_type} t={w['t']}: content appeared/vanished"
            continue
        for i, edge in enumerate(("left", "top", "right", "bottom")):
            assert abs(g["bbox"][i] - w["bbox"][i]) <= TOLERANCE, (
                f"{video_type} t={w['t']}: content {edge} edge moved "
                f"{w['bbox'][i]} -> {g['bbox'][i]}")
        assert g["bands"] == w["bands"], (
            f"{video_type} t={w['t']}: content bands moved\n"
            f"  was: {w['bands']}\n  now: {g['bands']}")


if __name__ == "__main__":
    import tempfile
    if "--update" not in sys.argv:
        print("run with --update to regenerate the golden")
        sys.exit(1)
    with tempfile.TemporaryDirectory() as td:
        data = build_all(Path(td))
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(data, indent=1))
    total = sum(len(v) for v in data.values())
    print(f"wrote {GOLDEN} — {len(data)} types, {total} pinned frames")

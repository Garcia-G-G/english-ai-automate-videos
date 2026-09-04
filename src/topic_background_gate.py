#!/usr/bin/env python3
"""The contrast gate a generated background must pass before it is used.

    from topic_background_gate import accept
    verdict = accept("output/backgrounds/break_the_ice.png")

This is the whole safety story for per-video backgrounds. The previous photo
set shipped without one and six of eleven presets measured at or under 3.7:1
behind the headline, against a 3.0 floor for large text and the 4.5 this
project holds its palettes to. An image generator with no gate recreates that
the first time a model returns something bright in the middle.

WORST CASE, NOT AVERAGE. The image is measured through the same Ken Burns
camera the renderer will use, at samples across the cycle, and the WORST
sample decides. A background that is readable for 28 of 30 seconds is not
readable; the two seconds are where the viewer gives up.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import numpy as np

logger = logging.getLogger(__name__)

#: Same floor the generated palettes are held to, so one number governs both.
FLOOR = 4.5

#: Samples across the Ken Burns cycle. The camera moves, so contrast is a
#: function of time and a single frame does not decide it.
SAMPLES = 9
CYCLE = 30.0


def measure(image_path, width: int = 1080, height: int = 1920,
            duration: float = CYCLE) -> Dict:
    """Worst-case headline contrast for this image under the real camera."""
    import sys
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    from PIL import Image, ImageFilter
    from backgrounds import kenburns_crop
    from text_contrast import measure_frame

    photo = Image.open(image_path).convert("RGB")
    ratios, samples = [], []
    for i in range(SAMPLES):
        t = duration * i / SAMPLES
        from topic_background import RENDER_ZOOM_RANGE
        box = kenburns_crop(t, photo.width, photo.height, width, height,
                            zoom_range=RENDER_ZOOM_RANGE, duration=duration)
        frame = photo.resize((width, height), Image.LANCZOS, box=box)
        # The renderer blurs and darkens before any text lands on it; gating
        # the raw photo would measure something the viewer never sees. These
        # come from topic_background so the gate cannot drift from the
        # treatment that ships.
        from topic_background import RENDER_BLUR_RADIUS, RENDER_OVERLAY_OPACITY
        frame = frame.filter(ImageFilter.GaussianBlur(radius=RENDER_BLUR_RADIUS))
        arr = np.array(frame, dtype=np.float32) * (1.0 - RENDER_OVERLAY_OPACITY)
        m = measure_frame(arr.astype(np.uint8))
        # contrast_worst, not contrast_mean: the brightest patch under the
        # headline is what decides whether it can be read.
        ratios.append(m["contrast_worst"])
        samples.append({"t": round(t, 2), **{k: round(float(v), 3)
                                             for k, v in m.items()}})

    ratios = [r for r in ratios if r is not None]
    worst = float(min(ratios)) if ratios else 0.0
    return {"worst_ratio": worst, "floor": FLOOR,
            "passes": worst >= FLOOR, "samples": samples}


def accept(image_path, topic: str = None) -> Dict:
    """Gate one image. Logs a refusal at WARNING, with the topic."""
    try:
        result = measure(image_path)
    except Exception as exc:                                # noqa: BLE001
        # A gate that crashes must refuse, not wave the image through.
        logger.warning("background gate FAILED to measure %s (topic %r): %s "
                       "— refusing", image_path, topic, exc)
        return {"worst_ratio": 0.0, "floor": FLOOR, "passes": False,
                "error": str(exc), "samples": []}

    if result["passes"]:
        logger.info("background gate PASS %.2f:1 (floor %.1f) for %r",
                    result["worst_ratio"], FLOOR, topic)
    else:
        logger.warning(
            "background gate REJECTED %.2f:1 (floor %.1f) for topic %r — "
            "falling back to a palette. Image kept at %s",
            result["worst_ratio"], FLOOR, topic, image_path)
    return result

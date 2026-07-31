"""Learning Routes brand layer — persistent watermark.

This project exists to drive traffic to Learning Routes, and until now no
video has ever carried a CTA.

The watermark is composited in `utils.finalize_frame`, which every renderer
calls, so it lands on every frame of every video type by construction rather
than by seven separate call sites remembering to do it.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .utils import manrope
from config.layout import MARGIN_X, SAFE_AREA_BOTTOM

logger = logging.getLogger(__name__)

WATERMARK_TEXT = "learningroutes.com"

#: 36 px on a 1080x1920 canvas.
#:
#: Chosen for a PHONE, not a desktop preview. At 1080 wide the video occupies
#: roughly 2.7 inches on a typical handset, so 36 px renders at about the size
#: of the platform's own username label (~30-34 px equivalent) — legible at
#: arm's length without competing with the lesson copy, which runs 44-88 px.
#: Below ~30 px the domain becomes a smudge on a moving background; above
#: ~44 px it starts reading as content rather than attribution.
WATERMARK_SIZE = 36
WATERMARK_WEIGHT = "SemiBold"

#: CONTRAST TREATMENT: white text with a soft drop shadow. NO pill.
#:
#: The first version used an opaque black pill. It maximised measured
#: contrast and looked wrong: the only hard-edged, fully opaque element in a
#: frame otherwise built from soft translucent white cards, so it read as
#: pasted-on UI rather than part of the composition.
#:
#: WHY AAA IS DELIBERATELY NOT THE TARGET.
#: WCAG AAA (4.5:1) is an accessibility standard for text that must be read
#: without context — form labels, body copy, anything a reader depends on. A
#: watermark is attribution. It has to be READABLE WITHOUT COMPETING with the
#: lesson, and optimising it to an accessibility ceiling is what produced the
#: pill. The target here is ~2.5-3:1 at the stroke edge: legible at a glance,
#: subordinate by design.
#:
#: Measured against the REAL backdrop rather than a synthetic swatch — the
#: watermark region of a rendered quiz has mean luminance 0.137 with
#: highlights to 1.0, so the shadow has to survive bright patches inside an
#: otherwise dark frame. Stock footage in 4b will be brighter on average,
#: which is why the shadow is tuned for the bright case even though today's
#: backdrop rarely needs it.
SHADOW_ALPHA = 160
SHADOW_BLUR = 4
SHADOW_OFFSET = (0, 2)

TEXT_COLOR = (255, 255, 255, 242)

#: Clearance above the platform UI rail.
#:
#: SAFE_AREA_BOTTOM is 1632; below it sit the caption, username and action
#: buttons, which cover anything drawn there. Two elements in this repo
#: already make that mistake — TIMER_BAR_Y = 1750 and BAR_Y = 1850. The
#: watermark's pill BOTTOM sits at SAFE_AREA_BOTTOM - WATERMARK_BOTTOM_GAP, so
#: the whole element is inside the safe area, not merely its baseline.
#: Raised from 24 when the pill became a shadow: a Gaussian blur
#: extends the drawn bounds ~11 px past the glyphs, so a gap tuned to
#: the text alone left the SHADOW inside the rail even though the
#: letters cleared it.
WATERMARK_BOTTOM_GAP = 34

_overlay_cache: dict = {}


def _build_overlay(size: Tuple[int, int]) -> Image.Image:
    """Render the watermark once as an RGBA layer.

    Pre-rendered because this is composited on EVERY frame — a 40 s video at
    30 fps is 1200 frames, and re-rasterising the same text 1200 times is pure
    waste.
    """
    font = manrope(WATERMARK_SIZE, WATERMARK_WEIGHT)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_h = bottom - top

    x = MARGIN_X - left
    y = SAFE_AREA_BOTTOM - WATERMARK_BOTTOM_GAP - text_h - top

    # Shadow on its own layer so the blur cannot soften the glyphs themselves.
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(
        (x + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1]),
        WATERMARK_TEXT, font=font, fill=(0, 0, 0, SHADOW_ALPHA))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))

    layer = Image.alpha_composite(Image.new("RGBA", size, (0, 0, 0, 0)), shadow)
    ImageDraw.Draw(layer).text((x, y), WATERMARK_TEXT, font=font, fill=TEXT_COLOR)

    logger.debug("watermark text y=%d..%d (safe area bottom %d)",
                 y + top, y + top + text_h, SAFE_AREA_BOTTOM)
    return layer


def get_watermark_overlay(size: Tuple[int, int]) -> Optional[Image.Image]:
    """Cached RGBA overlay for this canvas size, or None if it cannot render."""
    if size not in _overlay_cache:
        try:
            _overlay_cache[size] = _build_overlay(size)
        except Exception:                          # noqa: BLE001
            # A missing brand font must not take the whole render down, but it
            # must be loud — a silently un-watermarked video defeats the point
            # of the step.
            logger.exception("watermark could not be rendered; video will "
                             "ship WITHOUT a CTA")
            _overlay_cache[size] = None
    return _overlay_cache[size]


def draw_watermark(frame: Image.Image) -> None:
    """Composite the watermark onto `frame` in place."""
    overlay = get_watermark_overlay(frame.size)
    if overlay is not None:
        frame.alpha_composite(overlay)


def watermark_bounds() -> Tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the drawn mark, for tests and layout checks."""
    from .constants import VIDEO_WIDTH, VIDEO_HEIGHT
    overlay = get_watermark_overlay((VIDEO_WIDTH, VIDEO_HEIGHT))
    if overlay is None:
        raise RuntimeError("watermark overlay unavailable")
    return overlay.getbbox()

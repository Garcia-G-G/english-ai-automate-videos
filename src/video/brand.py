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

from PIL import Image, ImageDraw

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

#: CONTRAST TREATMENT: a low-opacity dark pill behind white text.
#:
#: Picked over a plain shadow because the background is about to become stock
#: footage — aerial cities, beaches — with bright and dark regions inside the
#: SAME clip. A shadow only helps against light backgrounds and a light
#: outline only helps against dark ones; a scrim guarantees a known
#: backdrop behind the glyphs regardless of what the footage does under it.
#: /255. DERIVED against PURE WHITE, which is the genuine worst case for
#: white text — not merely a "bright" tone. Solving the WCAG contrast ratio
#: for the composited pill grey:
#:
#:     alpha   pill grey   contrast vs white text
#:       130         125     4.12
#:       136         119     4.48      still short
#:       140         115     4.74      <- chosen
#:       150         105     5.49
#:
#: 140 is the lowest value with real margin over WCAG AAA (4.5), so the scrim
#: stays as unobtrusive as it can while guaranteeing the domain is readable.
#:
#: An earlier pass swept a bright BEIGE and settled on 135, which measures
#: 4.8 there but only 4.42 on white — the test below caught it. The worst case
#: has to be the actual worst case.
#:
#: Without any pill, white text on white measures 1.0:1: literally invisible.
#: That is what makes the treatment necessary rather than decorative.
PILL_ALPHA = 140
PILL_RADIUS = 10
PILL_PAD_X = 16
PILL_PAD_Y = 9

TEXT_COLOR = (255, 255, 255, 236)
PILL_COLOR = (0, 0, 0)

#: Clearance above the platform UI rail.
#:
#: SAFE_AREA_BOTTOM is 1632; below it sit the caption, username and action
#: buttons, which cover anything drawn there. Two elements in this repo
#: already make that mistake — TIMER_BAR_Y = 1750 and BAR_Y = 1850. The
#: watermark's pill BOTTOM sits at SAFE_AREA_BOTTOM - WATERMARK_BOTTOM_GAP, so
#: the whole element is inside the safe area, not merely its baseline.
WATERMARK_BOTTOM_GAP = 24

_overlay_cache: dict = {}


def _build_overlay(size: Tuple[int, int]) -> Image.Image:
    """Render the watermark once as an RGBA layer.

    Pre-rendered because this is composited on EVERY frame — a 40 s video at
    30 fps is 1200 frames, and re-rasterising the same text 1200 times is pure
    waste.
    """
    font = manrope(WATERMARK_SIZE, WATERMARK_WEIGHT)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    left, top, right, bottom = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_w, text_h = right - left, bottom - top

    pill_w = text_w + PILL_PAD_X * 2
    pill_h = text_h + PILL_PAD_Y * 2
    pill_x0 = MARGIN_X
    pill_y1 = SAFE_AREA_BOTTOM - WATERMARK_BOTTOM_GAP
    pill_y0 = pill_y1 - pill_h

    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x0 + pill_w, pill_y1],
        radius=PILL_RADIUS, fill=(*PILL_COLOR, PILL_ALPHA),
    )
    # textbbox offsets are subtracted so the glyphs sit centred in the pill
    # rather than at a nominal origin that ignores ascender/descender.
    draw.text((pill_x0 + PILL_PAD_X - left, pill_y0 + PILL_PAD_Y - top),
              WATERMARK_TEXT, font=font, fill=TEXT_COLOR)

    logger.debug("watermark pill y=%d..%d (safe area bottom %d)",
                 pill_y0, pill_y1, SAFE_AREA_BOTTOM)
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
    """(x0, y0, x1, y1) of the pill, for tests and layout checks."""
    from .constants import VIDEO_WIDTH, VIDEO_HEIGHT
    overlay = get_watermark_overlay((VIDEO_WIDTH, VIDEO_HEIGHT))
    if overlay is None:
        raise RuntimeError("watermark overlay unavailable")
    return overlay.getbbox()

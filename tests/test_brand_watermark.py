#!/usr/bin/env python3
"""The persistent watermark: placement, legibility, and universality.

    python3 -m pytest tests/test_brand_watermark.py

This project exists to drive traffic to Learning Routes, and no video carried
a CTA before Step 4a. These tests defend the two ways the watermark can fail
silently: drawn where the platform UI covers it, or drawn where the background
swallows it.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.layout import SAFE_AREA_BOTTOM, VIDEO_HEIGHT, VIDEO_WIDTH  # noqa: E402
from video import brand as B  # noqa: E402
from video.utils import BrandFontMissing, manrope  # noqa: E402


def _luminance(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _framed(bg):
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), tuple(bg) + (255,))
    B.draw_watermark(img)
    return img


def _glyph_and_pill(img):
    x0, y0, x1, y1 = B.watermark_bounds()
    px = np.array(img.convert("RGB"))[y0:y1, x0:x1].reshape(-1, 3)
    lum = np.array([_luminance(p) for p in px])
    return tuple(px[lum.argmax()]), tuple(px[lum.argmin()])


# ── placement ────────────────────────────────────────────────────────

def test_watermark_sits_entirely_above_the_platform_ui_rail():
    """SAFE_AREA_BOTTOM is 1632; below it the caption, username and action
    buttons cover anything drawn there. TIMER_BAR_Y=1750 and BAR_Y=1850 in
    this repo already make that mistake — this must not become the third."""
    _x0, _y0, _x1, y1 = B.watermark_bounds()

    assert y1 <= SAFE_AREA_BOTTOM, (
        f"watermark bottom {y1} is below SAFE_AREA_BOTTOM {SAFE_AREA_BOTTOM} "
        "and would be covered by the platform UI")


def test_watermark_is_bottom_left_not_centred_or_right():
    x0, y0, x1, _y1 = B.watermark_bounds()

    assert x0 < VIDEO_WIDTH * 0.5, "not left-aligned"
    assert y0 > VIDEO_HEIGHT * 0.6, "not in the lower half"


def test_watermark_clears_the_rail_with_real_margin():
    """Touching 1632 exactly would leave no room for per-platform variation
    in where the rail actually starts."""
    _x0, _y0, _x1, y1 = B.watermark_bounds()

    assert SAFE_AREA_BOTTOM - y1 >= 16


# ── legibility ───────────────────────────────────────────────────────

@pytest.mark.parametrize("bg,label", [
    ((255, 255, 255), "flat white — the worst case for white text"),
    ((243, 240, 232), "bright beach/sky"),
    ((128, 128, 128), "mid grey"),
    ((14, 16, 22), "night city"),
    ((0, 0, 0), "black"),
])
def test_text_stays_legible_on_any_background(bg, label):
    """The background becomes stock footage next step — aerial cities and
    beaches with bright and dark regions inside the SAME clip."""
    glyph, pill = _glyph_and_pill(_framed(bg))

    assert _contrast(glyph, pill) >= 4.5, (
        f"{label}: contrast {_contrast(glyph, pill):.1f}:1 below WCAG AAA")


def test_the_scrim_is_what_makes_bright_backgrounds_work():
    """Without the pill, white text on white is 1.0:1 — invisible. This pins
    the reason the treatment exists, so nobody removes it as decoration."""
    white = (255, 255, 255)
    glyph, pill = _glyph_and_pill(_framed(white))

    assert _contrast(glyph, white) < 1.2, "sanity: glyphs are near-white"
    assert _contrast(glyph, pill) >= 4.5, "the pill must restore contrast"


def test_pill_is_translucent_not_an_opaque_bar():
    assert 0 < B.PILL_ALPHA < 200


# ── universality ─────────────────────────────────────────────────────

def test_every_renderer_gets_the_watermark_through_finalize_frame():
    """Applied at one choke point rather than seven call sites that each have
    to remember. If a renderer ever stops calling finalize_frame, that is the
    thing to catch."""
    import ast
    utils = ast.parse((ROOT / "src" / "video" / "utils.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(utils)
              if isinstance(n, ast.FunctionDef) and n.name == "finalize_frame")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    assert "draw_watermark" in called

    renderers = ["educational", "quiz", "true_false", "fill_blank",
                 "pronunciation", "vocabulary", "karaoke"]
    for name in renderers:
        src = (ROOT / "src" / "video" / f"{name}.py").read_text(encoding="utf-8")
        assert "finalize_frame" in src, f"{name}.py does not finalize its frames"


def test_watermark_overlay_is_built_once_and_cached():
    """Composited on every frame — a 40 s video is 1200 frames, and
    re-rasterising the same text 1200 times is pure waste."""
    B._overlay_cache.clear()
    first = B.get_watermark_overlay((VIDEO_WIDTH, VIDEO_HEIGHT))
    second = B.get_watermark_overlay((VIDEO_WIDTH, VIDEO_HEIGHT))

    assert first is second


# ── typography ───────────────────────────────────────────────────────

def test_manrope_never_renders_at_its_default_extralight_weight():
    """Manrope is a VARIABLE font whose default instance is ExtraLight — the
    thinnest weight it has. A naive truetype() call returns hairline text,
    which is exactly wrong for a watermark over photography."""
    assert manrope(36).getname()[1] != "ExtraLight"
    assert manrope(36, "SemiBold").getname() == ("Manrope", "SemiBold")


def test_a_missing_brand_face_raises_rather_than_substituting(monkeypatch):
    """A watermark that silently renders in Inter is a brand defect that
    looks like success."""
    monkeypatch.setattr(B, "_overlay_cache", {})
    from video import utils as U
    monkeypatch.setattr(U, "_MANROPE_VF", Path("/nonexistent/Manrope.ttf"))
    monkeypatch.setattr(U, "_brand_fonts", {})

    with pytest.raises(BrandFontMissing):
        U.manrope(36)


def test_watermark_text_is_the_domain():
    assert B.WATERMARK_TEXT == "learningroutes.com"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

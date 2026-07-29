"""v2 backgrounds — content-aware, precomputed where static.

ADULTS: animated mesh gradient (large radial brand-color blobs drifting
slowly over a deep ink base) + subtle film grain + vignette.

KIDS: warm cream base with soft geometric shapes (circles / rings / stars)
floating with slow parallax.

All motion is a pure function of ``t``. Expensive parts (vignette, grain
tiles, shape sprites, base gradient) are computed once in ``__init__``.
"""

import logging
import math
from typing import List

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .design import Tokens

logger = logging.getLogger(__name__)

try:
    import cv2
    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    _HAS_CV2 = False


def _upscale(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear upscale of a small float32 HxWx3 array to (h, w)."""
    if _HAS_CV2:
        return cv2.resize(arr, (w, h), interpolation=cv2.INTER_LINEAR)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return np.asarray(img.resize((w, h), Image.BILINEAR), dtype=np.float32)


class AdultsBackground:
    """Animated ink mesh-gradient with film grain and vignette."""

    _LOW_W, _LOW_H = 108, 192       # blobs rendered at 1/10 res, then upscaled
    _GRAIN_FRAMES = 6
    _GRAIN_STRENGTH = 5.0           # +- pixel values added (subtle)

    def __init__(self, width: int, height: int, tokens: Tokens, seed: int = 20):
        self.w, self.h = width, height
        self.tokens = tokens

        lw, lh = self._LOW_W, self._LOW_H
        ys, xs = np.mgrid[0:lh, 0:lw].astype(np.float32)
        self._xs = xs / lw
        self._ys = ys / lh

        # Blob definitions: (color, base center, orbit radius, speed, size, gain)
        c1, c2, c3 = tokens.bg_accents
        self._blobs = [
            {"color": np.array(c1, np.float32), "cx": 0.22, "cy": 0.20,
             "ox": 0.16, "oy": 0.10, "sp": 0.10, "ph": 0.0, "r": 0.62, "gain": 0.34},
            {"color": np.array(c2, np.float32), "cx": 0.85, "cy": 0.72,
             "ox": 0.12, "oy": 0.14, "sp": 0.07, "ph": 2.1, "r": 0.55, "gain": 0.20},
            {"color": np.array(c3, np.float32), "cx": 0.55, "cy": 1.02,
             "ox": 0.18, "oy": 0.08, "sp": 0.05, "ph": 4.0, "r": 0.70, "gain": 0.26},
        ]
        self._base = np.array(tokens.bg_base, np.float32)

        # Vignette (multiplicative, precomputed at full res)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        nx = (xx / width - 0.5) * 2.0
        ny = (yy / height - 0.5) * 2.0
        d = np.sqrt(nx * nx + ny * ny * 0.85)
        self._vignette = np.clip(1.0 - 0.34 * np.clip(d - 0.55, 0, None) ** 1.6,
                                 0.62, 1.0)[..., None]

        # Static grain tiles (deterministic; cycled by frame index)
        rng = np.random.default_rng(seed)
        self._grain = [
            rng.normal(0.0, self._GRAIN_STRENGTH, (height, width, 1)).astype(np.float32)
            for _ in range(self._GRAIN_FRAMES)
        ]

    def frame(self, t: float) -> np.ndarray:
        """Return the RGB uint8 background at time ``t``."""
        low = np.tile(self._base, (self._LOW_H, self._LOW_W, 1))
        aspect = self._LOW_H / self._LOW_W  # keep blobs round on screen
        for b in self._blobs:
            cx = b["cx"] + b["ox"] * math.sin(2 * math.pi * b["sp"] * t + b["ph"])
            cy = b["cy"] + b["oy"] * math.cos(2 * math.pi * b["sp"] * t + b["ph"] * 0.7)
            dx = self._xs - cx
            dy = (self._ys - cy) * aspect / 1.9
            w = np.exp(-(dx * dx + dy * dy) / (b["r"] * b["r"] * 0.5))
            low = low + b["color"] * (w[..., None] * b["gain"])

        img = _upscale(low, self.w, self.h)
        img *= self._vignette
        img += self._grain[int(t * 8) % self._GRAIN_FRAMES]
        return np.clip(img, 0, 255).astype(np.uint8)


def _make_star(size: int, color, alpha: int) -> Image.Image:
    """Soft 5-point star sprite."""
    s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    cx = cy = size / 2
    r_out, r_in = size * 0.48, size * 0.20
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=(*color, alpha))
    return s.filter(ImageFilter.GaussianBlur(1.2))


def _make_circle(size: int, color, alpha: int, ring: bool = False) -> Image.Image:
    """Soft filled circle or ring sprite."""
    s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    if ring:
        w = max(6, size // 9)
        d.ellipse([w, w, size - w, size - w], outline=(*color, alpha), width=w)
    else:
        d.ellipse([2, 2, size - 2, size - 2], fill=(*color, alpha))
    return s.filter(ImageFilter.GaussianBlur(1.2))


class KidsBackground:
    """Warm cream base with floating pastel shapes (slow parallax)."""

    def __init__(self, width: int, height: int, tokens: Tokens, seed: int = 11):
        self.w, self.h = width, height
        base = np.array(tokens.bg_base, np.float32)
        warm = base * 0.96 + np.array((255, 214, 170), np.float32) * 0.04
        ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        grad = base[None, None, :] * (1 - ramp) + warm[None, None, :] * ramp
        grad = np.repeat(grad, width, axis=1)
        self._base_img = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8))

        rng = np.random.default_rng(seed)
        kinds = ["circle", "ring", "star"]
        self._shapes: List[dict] = []
        for i in range(9):
            color = tokens.bg_accents[i % len(tokens.bg_accents)]
            kind = kinds[i % 3]
            size = int(rng.integers(70, 210))
            alpha = int(rng.integers(26, 54))
            if kind == "star":
                sprite = _make_star(size, color, alpha)
            else:
                sprite = _make_circle(size, color, alpha, ring=(kind == "ring"))
            depth = size / 210.0  # bigger = closer = drifts more
            self._shapes.append({
                "sprite": sprite,
                "x": float(rng.uniform(0.03, 0.9)),
                "y": float(rng.uniform(0.02, 0.92)),
                "ax": 18.0 + 26.0 * depth,
                "ay": 12.0 + 20.0 * depth,
                "sp": float(rng.uniform(0.05, 0.12)),
                "ph": float(rng.uniform(0, 2 * math.pi)),
            })

    def frame(self, t: float) -> Image.Image:
        """Return the RGB background image at time ``t``."""
        img = self._base_img.copy()
        for s in self._shapes:
            x = int(s["x"] * self.w + s["ax"] * math.sin(2 * math.pi * s["sp"] * t + s["ph"]))
            y = int(s["y"] * self.h + s["ay"] * math.cos(2 * math.pi * s["sp"] * t * 0.8 + s["ph"]))
            img.paste(s["sprite"], (x, y), s["sprite"])
        return img

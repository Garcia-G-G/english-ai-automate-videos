"""Design system for the v2 renderer — tokens per audience profile.

Two visual identities:
    * ADULTS — deep ink/navy premium-tech look, electric blue + amber accents.
    * KIDS   — warm cream, white cards, saturated friendly accents, big radii.

Everything visual (color, type scale, spacing, fonts, branding) lives here
so the renderer stays free of magic numbers.

Fonts: candidate lists are tried in order. Drop a premium font into
``assets/fonts/`` (see FONT recommendations in the repo report) and it is
picked up automatically — no code change needed.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import ImageFont

logger = logging.getLogger(__name__)

RGB = Tuple[int, int, int]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

# ── Canvas / safe zones (TikTok 1080x1920) ───────────────────────────
WIDTH = 1080
HEIGHT = 1920
SAFE_TOP = 200        # TikTok top UI
SAFE_BOTTOM = 320     # TikTok caption/actions
SAFE_SIDE = 72
CONTENT_W = WIDTH - 2 * SAFE_SIDE          # 936
CONTENT_BOTTOM = HEIGHT - SAFE_BOTTOM      # 1600

# ── Type scale (px) — strict, do not invent sizes in the renderer ────
TYPE_SCALE: Dict[str, dict] = {
    "display":  {"size": 128, "min": 76, "line": 1.10, "tracking": 0},
    "headline": {"size": 72,  "min": 52, "line": 1.18, "tracking": 0},
    "body":     {"size": 52,  "min": 40, "line": 1.35, "tracking": 0},
    "caption":  {"size": 36,  "min": 28, "line": 1.30, "tracking": 3},
    "micro":    {"size": 28,  "min": 24, "line": 1.30, "tracking": 4},
}

# ── Font candidates (first existing path wins) ───────────────────────
_SYSTEM_BOLD = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

# Preferred premium fonts — drop the files into assets/fonts/ to activate.
FONT_CANDIDATES: Dict[str, Dict[str, List[str]]] = {
    "adults": {
        "display": [
            str(FONTS_DIR / "Montserrat-ExtraBold.ttf"),
            str(FONTS_DIR / "Inter-ExtraBold.ttf"),
            *_SYSTEM_BOLD,
        ],
        "text": [
            str(FONTS_DIR / "Montserrat-Bold.ttf"),
            str(FONTS_DIR / "Inter-Bold.ttf"),
            *_SYSTEM_BOLD,
        ],
    },
    "kids": {
        "display": [
            str(FONTS_DIR / "Fredoka-SemiBold.ttf"),
            str(FONTS_DIR / "Fredoka-Bold.ttf"),
            str(FONTS_DIR / "BalooBhai2-Bold.ttf"),
            str(FONTS_DIR / "Inter-ExtraBold.ttf"),
            *_SYSTEM_BOLD,
        ],
        "text": [
            str(FONTS_DIR / "Fredoka-Medium.ttf"),
            str(FONTS_DIR / "Inter-Bold.ttf"),
            *_SYSTEM_BOLD,
        ],
    },
}


@dataclass(frozen=True)
class Tokens:
    """Resolved design tokens for one audience profile."""
    name: str

    # Background
    bg_base: RGB
    bg_accents: Tuple[RGB, ...]         # mesh blobs (adults) / shapes (kids)

    # Surfaces
    card_fill: RGB
    card_alpha: int
    card_radius: int
    card_border: Tuple[int, int, int, int]
    inner_panel_fill: Tuple[int, int, int, int]   # english highlight panel

    # Text
    text_primary: RGB
    text_secondary: RGB
    accent: RGB           # main brand accent
    accent_warm: RGB      # secondary accent
    word_active: RGB      # karaoke active word
    word_english: RGB     # english vocabulary words
    word_past: RGB
    word_upcoming: RGB

    # Chrome
    progress_track: Tuple[int, int, int, int]
    progress_fill: RGB
    brand_tag: str
    brand_handle: str
    cta_text: str

    # Clip window (kids only)
    has_clip_window: bool = False
    clip_dirs: Tuple[str, ...] = field(default_factory=tuple)


ADULTS = Tokens(
    name="adults",
    bg_base=(11, 15, 26),                       # #0B0F1A deep ink
    bg_accents=((79, 124, 255), (255, 184, 79), (98, 78, 224)),
    card_fill=(21, 28, 48),
    card_alpha=242,
    card_radius=48,
    card_border=(120, 148, 235, 56),
    inner_panel_fill=(79, 124, 255, 34),
    text_primary=(255, 255, 255),
    text_secondary=(158, 170, 200),
    accent=(79, 124, 255),                      # #4F7CFF electric
    accent_warm=(255, 184, 79),                 # #FFB84F amber
    word_active=(255, 184, 79),
    word_english=(130, 166, 255),
    word_past=(110, 121, 148),
    word_upcoming=(214, 221, 238),
    progress_track=(255, 255, 255, 36),
    progress_fill=(255, 184, 79),
    brand_tag="ENGLISH CON CAPI",
    brand_handle="@englishconcapi",
    cta_text="Sígueme para más",
)

KIDS = Tokens(
    name="kids",
    bg_base=(255, 246, 233),                    # #FFF6E9 warm cream
    bg_accents=((255, 107, 107), (78, 205, 196), (255, 209, 102)),
    card_fill=(255, 255, 255),
    card_alpha=255,
    card_radius=56,
    card_border=(255, 209, 102, 160),
    inner_panel_fill=(78, 205, 196, 40),
    text_primary=(45, 49, 66),                  # #2D3142 ink
    text_secondary=(122, 131, 155),
    accent=(255, 107, 107),                     # #FF6B6B coral
    accent_warm=(255, 176, 32),                 # amber (darkened FFD166 for contrast)
    word_active=(255, 87, 87),
    word_english=(20, 143, 134),                # darkened #4ECDC4 for AAA on white
    word_past=(173, 180, 199),
    word_upcoming=(96, 104, 128),
    progress_track=(45, 49, 66, 32),
    progress_fill=(255, 107, 107),
    brand_tag="MOMO & LILA",
    brand_handle="@momoylila",
    cta_text="¡Sígueme para más!",
    has_clip_window=True,
    clip_dirs=(
        str(PROJECT_ROOT / "assets" / "clips" / "kids" / "momo"),
        str(PROJECT_ROOT / "assets" / "clips" / "kids"),
    ),
)


def get_tokens(profile_name: str) -> Tokens:
    """Return design tokens for a profile name (defaults to adults)."""
    return KIDS if (profile_name or "").lower() == "kids" else ADULTS


# ── Font loading ─────────────────────────────────────────────────────

_font_cache: Dict[Tuple[str, str, int], ImageFont.FreeTypeFont] = {}
_resolved_paths: Dict[Tuple[str, str], str] = {}


def load_font(profile: str, role: str, size: int) -> ImageFont.FreeTypeFont:
    """Load (and cache) a font for ``role`` ('display'|'text') at ``size``."""
    key = (profile, role, size)
    if key in _font_cache:
        return _font_cache[key]

    path_key = (profile, role)
    if path_key not in _resolved_paths:
        candidates = FONT_CANDIDATES.get(profile, FONT_CANDIDATES["adults"])[role]
        resolved = next((p for p in candidates if Path(p).exists()), None)
        if resolved is None:
            logger.warning("v2 design: no font candidate found for %s/%s, "
                           "using PIL default", profile, role)
            resolved = ""
        else:
            logger.info("v2 design: %s/%s font -> %s", profile, role, resolved)
        _resolved_paths[path_key] = resolved

    path = _resolved_paths[path_key]
    try:
        f = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except OSError:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f

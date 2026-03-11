#!/usr/bin/env python3
"""
Background Generator for TikTok-style Videos
Supports multiple professional background styles including photo-based backgrounds.

Background Types:
- solid_vignette: Solid color with darker edges
- animated_gradient: Smooth color transitions over time
- bokeh_particles: Dark background with floating soft circles
- abstract_waves: Subtle animated wave patterns
- dynamic_glow_orbs: Floating glowing orbs
- particle_flow: Directional particles
- light_rays: Cinematic light beams
- aurora: Northern lights
- static_gradient: Multi-stop gradient (no animation)
- photo_kenburns: Real photograph with slow zoom/pan (Ken Burns effect)
"""

import logging
import math
import os
import numpy as np
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path
import random

logger = logging.getLogger(__name__)

# Video dimensions
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30

# Photo backgrounds directory
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"


# ============== COLOR UTILITIES ==============

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return '#{:02x}{:02x}{:02x}'.format(*rgb)


def interpolate_color(color1: Tuple, color2: Tuple, t: float) -> Tuple[int, int, int]:
    """Interpolate between two colors."""
    return tuple(int(c1 + (c2 - c1) * t) for c1, c2 in zip(color1, color2))


def ease_in_out_sine(t: float) -> float:
    """Smooth sine-based easing."""
    return -(math.cos(math.pi * t) - 1) / 2


# ============== BACKGROUND PRESETS ==============

BACKGROUND_PRESETS = {
    # === STATIC / MINIMAL ===
    "dark_professional": {
        "type": "solid_vignette",
        "color": "#0a0a12",
        "vignette_strength": 0.4
    },
    "minimal_dark": {
        "type": "solid_vignette",
        "color": "#000000",
        "vignette_strength": 0.3
    },

    # === ANIMATED GRADIENTS ===
    "purple_vibes": {
        "type": "animated_gradient",
        "colors": ["#1a1a2e", "#4a1a6b", "#2d1b4e", "#1a1a2e"],
        "cycle_duration": 8.0
    },
    "blue_calm": {
        "type": "animated_gradient",
        "colors": ["#0f1729", "#1a3a5c", "#0f2847", "#0f1729"],
        "cycle_duration": 10.0
    },
    "warm_sunset": {
        "type": "animated_gradient",
        "colors": ["#1a1a2e", "#4a1a3b", "#5c2a1a", "#1a1a2e"],
        "cycle_duration": 12.0
    },
    "deep_space": {
        "type": "animated_gradient",
        "colors": ["#0a0a14", "#141428", "#0f1f2f", "#0a0a14"],
        "cycle_duration": 15.0
    },
    "ocean_depth": {
        "type": "animated_gradient",
        "colors": ["#0a1628", "#0f2840", "#0a1e38", "#0a1628"],
        "cycle_duration": 10.0
    },

    # === BOKEH / PARTICLES ===
    "bokeh_lights": {
        "type": "bokeh_particles",
        "base_color": "#0a0a14",
        "particle_colors": ["#ffffff", "#00d4ff", "#ffd700", "#ff69b4"],
        "num_particles": 18,
        "min_size": 30,
        "max_size": 100
    },
    "bokeh_soft": {
        "type": "bokeh_particles",
        "base_color": "#0f0f1a",
        "particle_colors": ["#ffffff", "#e0e0ff", "#c0c0ff"],
        "num_particles": 12,
        "min_size": 40,
        "max_size": 120
    },
    "neon_glow": {
        "type": "bokeh_particles",
        "base_color": "#0a0a0f",
        "particle_colors": ["#00ffff", "#ff00ff", "#00ff00", "#ffff00"],
        "num_particles": 15,
        "min_size": 20,
        "max_size": 80
    },

    # === DYNAMIC / ENERGETIC ===
    "energetic_orbs": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0a0a14",
        "orb_colors": ["#00d4ff", "#ff6bb3", "#a855f7", "#22d3ee"],
        "orb_count": 10,
        "movement_speed": "medium"
    },
    "floating_dreams": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0f0f1a",
        "orb_colors": ["#ffffff", "#e0e0ff", "#c0d0ff", "#a0c0ff"],
        "orb_count": 8,
        "movement_speed": "slow"
    },
    "cyber_orbs": {
        "type": "dynamic_glow_orbs",
        "base_color": "#050510",
        "orb_colors": ["#00ffff", "#ff00ff", "#00ff88"],
        "orb_count": 12,
        "movement_speed": "fast"
    },

    # === PARTICLE FLOW ===
    "rising_stars": {
        "type": "particle_flow",
        "base_color": "#0a0a14",
        "particle_color": "#ffffff",
        "particle_count": 60,
        "direction": "up",
        "speed": 1.0
    },
    "snow_fall": {
        "type": "particle_flow",
        "base_color": "#0a0a18",
        "particle_color": "#e0e8ff",
        "particle_count": 50,
        "direction": "down",
        "speed": 0.6
    },
    "diagonal_flow": {
        "type": "particle_flow",
        "base_color": "#0a0a12",
        "particle_color": "#00d4ff",
        "particle_count": 45,
        "direction": "up-right",
        "speed": 0.8
    },

    # === CINEMATIC ===
    "cinematic_rays": {
        "type": "light_rays",
        "base_color": "#0a0a12",
        "ray_color": "#ffffff",
        "ray_count": 5,
        "ray_opacity": 0.12
    },
    "golden_hour": {
        "type": "light_rays",
        "base_color": "#0a0808",
        "ray_color": "#ffd700",
        "ray_count": 4,
        "ray_opacity": 0.10
    },

    # === AURORA / NORTHERN LIGHTS ===
    "aurora_borealis": {
        "type": "aurora",
        "base_color": "#050510",
        "aurora_colors": ["#00ff88", "#00ddff", "#aa55ff", "#ff55aa"]
    },
    "aurora_soft": {
        "type": "aurora",
        "base_color": "#080812",
        "aurora_colors": ["#4488ff", "#44ffaa", "#8844ff"]
    },

    # === RECOMMENDED FOR TIKTOK EDUCATIONAL ===
    "tiktok_energetic": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0a0a14",
        "orb_colors": ["#00d4ff", "#a855f7", "#ff6bb3", "#ffd700"],
        "orb_count": 10,
        "movement_speed": "medium"
    },

    # === VIBRANT TIKTOK BACKGROUNDS ===

    "neon_city": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0c0820",
        "orb_colors": ["#ff2d95", "#00f5ff", "#bf5af2", "#ff6b35"],
        "orb_count": 16,
        "movement_speed": "medium",
        "orb_size_min": 120,
        "orb_size_max": 280
    },
    "galaxy_swirl": {
        "type": "aurora",
        "base_color": "#06061a",
        "aurora_colors": ["#ff44cc", "#4466ff", "#00ffaa", "#ff9933"]
    },
    "electric_dreams": {
        "type": "bokeh_particles",
        "base_color": "#06061a",
        "particle_colors": ["#00ffff", "#ff00ff", "#ffff00", "#00ff88", "#ff4488"],
        "num_particles": 22,
        "min_size": 25,
        "max_size": 90
    },
    "sunset_glow": {
        "type": "animated_gradient",
        "colors": ["#1a0a2e", "#5c1a4a", "#8a3a2a", "#5c1a4a", "#1a0a2e"],
        "cycle_duration": 8.0
    },
    "ocean_waves": {
        "type": "aurora",
        "base_color": "#040818",
        "aurora_colors": ["#0088ff", "#00ccff", "#00ffcc", "#0066dd"]
    },
    "purple_rain": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0c0820",
        "orb_colors": ["#9b59b6", "#e74c8c", "#8e44ad", "#d63384", "#bf5af2"],
        "orb_count": 14,
        "movement_speed": "slow",
        "orb_size_min": 120,
        "orb_size_max": 260
    },
    "fire_ice": {
        "type": "dynamic_glow_orbs",
        "base_color": "#0a0a14",
        "orb_colors": ["#ff4500", "#ff8c00", "#00bfff", "#00ffff", "#ff69b4"],
        "orb_count": 12,
        "movement_speed": "medium",
        "orb_size_min": 120,
        "orb_size_max": 260
    },
    "candy_pop": {
        "type": "bokeh_particles",
        "base_color": "#0a0814",
        "particle_colors": ["#ff6bb3", "#ffd700", "#00d4ff", "#a855f7", "#ff4466", "#44ff88"],
        "num_particles": 20,
        "min_size": 30,
        "max_size": 100
    },
    "midnight_blue": {
        "type": "animated_gradient",
        "colors": ["#0a1628", "#1a3a6c", "#0f2a5c", "#1a2a4c", "#0a1628"],
        "cycle_duration": 10.0
    },
    "northern_vivid": {
        "type": "aurora",
        "base_color": "#040410",
        "aurora_colors": ["#00ff66", "#00ddff", "#cc44ff", "#ff44aa", "#ffaa00"]
    },

    # ================================================================
    # === SEMI-STATIC GRADIENTS (bonitos, divertidos, no distraen) ===
    # ================================================================
    # These render ONCE and stay the same every frame.
    # Beautiful multi-color gradients with vignette — no animation.

    # Sunset dream — warm pink-to-orange diagonal gradient
    "static_sunset": {
        "type": "static_gradient",
        "colors": ["#1a0533", "#5c1a6b", "#c2185b", "#ff6f00"],
        "direction": "diagonal",
        "vignette_strength": 0.35
    },

    # Ocean blue — deep navy to teal, calming and clean
    "static_ocean": {
        "type": "static_gradient",
        "colors": ["#0a0a20", "#0d3b66", "#1a8a8a", "#00bfa5"],
        "direction": "vertical",
        "vignette_strength": 0.30
    },

    # Purple dream — rich dark purple to lavender
    "static_purple": {
        "type": "static_gradient",
        "colors": ["#0a0015", "#2d1b69", "#7c3aed", "#c084fc"],
        "direction": "diagonal",
        "vignette_strength": 0.35
    },

    # Neon night — bright purple/cyan center fading to dark edges
    "static_neon": {
        "type": "static_gradient",
        "colors": ["#6b3fa0", "#3a1a6b", "#1a1a4e", "#0c0c2e"],
        "direction": "radial",
        "vignette_strength": 0.25
    },

    # Emerald — deep green gradient, fresh and modern
    "static_emerald": {
        "type": "static_gradient",
        "colors": ["#041210", "#0d3320", "#1a6b4a", "#34d399"],
        "direction": "vertical",
        "vignette_strength": 0.30
    },

    # Rose gold — warm pinkish glow, very TikTok
    "static_rosegold": {
        "type": "static_gradient",
        "colors": ["#2a0a20", "#6b1a45", "#d4548a", "#f4a9c0"],
        "direction": "diagonal",
        "vignette_strength": 0.28
    },

    # Midnight — purple glow center fading to deep blue edges
    "static_midnight": {
        "type": "static_gradient",
        "colors": ["#3a3a8c", "#1a2a5c", "#0f1a3a", "#050510"],
        "direction": "radial",
        "vignette_strength": 0.20
    },

    # Candy gradient — playful pink/purple/blue
    "static_candy": {
        "type": "static_gradient",
        "colors": ["#1a0a2e", "#6b1a8a", "#d63384", "#ff6bb3"],
        "direction": "diagonal",
        "vignette_strength": 0.30
    },

    # Fire — dark warm reds and oranges
    "static_fire": {
        "type": "static_gradient",
        "colors": ["#1a0a08", "#5c1a0a", "#b34700", "#ff6f00"],
        "direction": "vertical",
        "vignette_strength": 0.35
    },

    # Galaxy — bright purple center glow fading to dark space
    "static_galaxy": {
        "type": "static_gradient",
        "colors": ["#5a3a9c", "#2a1a5c", "#0f0a2e", "#030308"],
        "direction": "radial",
        "vignette_strength": 0.15
    },

    # Teal vibes — modern teal-to-dark-blue
    "static_teal": {
        "type": "static_gradient",
        "colors": ["#0a0a1a", "#0a2a3a", "#0d5c5c", "#14b8a6"],
        "direction": "diagonal",
        "vignette_strength": 0.30
    },

    # Cotton candy — soft pastel pink and blue on dark base
    "static_cotton": {
        "type": "static_gradient",
        "colors": ["#0f0a1a", "#2a1a4a", "#7c5ab8", "#a8d8ea"],
        "direction": "diagonal",
        "vignette_strength": 0.30
    },

    # ================================================================
    # === PHOTO-BASED BACKGROUNDS (Ken Burns effect on real images) ===
    # ================================================================
    # These use real photographs with slow zoom/pan animation.
    # Place images in assets/backgrounds/<category>/ to use.
    # Dark overlay ensures text readability.

    # Earth from space — like the reference quiz videos
    "photo_earth": {
        "type": "photo_kenburns",
        "category": "earth",
        "overlay_opacity": 0.12,
        "blur_radius": 0,
        "zoom_range": (1.08, 1.28),
        "pan_speed": 0.7,
        "color_tint": None,
    },
    # City at night — urban energy, neon lights
    "photo_city": {
        "type": "photo_kenburns",
        "category": "city",
        "overlay_opacity": 0.12,
        "blur_radius": 0,
        "zoom_range": (1.06, 1.24),
        "pan_speed": 0.6,
        "color_tint": None,
    },
    # Ocean/sunset — warm, calming vocabulary/educational backdrop
    "photo_ocean": {
        "type": "photo_kenburns",
        "category": "ocean",
        "overlay_opacity": 0.08,
        "blur_radius": 0,
        "zoom_range": (1.06, 1.22),
        "pan_speed": 0.5,
        "color_tint": None,
    },
    # Nature — forests, mountains, greenery
    "photo_nature": {
        "type": "photo_kenburns",
        "category": "nature",
        "overlay_opacity": 0.12,
        "blur_radius": 0,
        "zoom_range": (1.08, 1.26),
        "pan_speed": 0.65,
        "color_tint": None,
    },
    # Abstract textures — patterns, feathers, fabrics (like reference turtle video)
    "photo_abstract": {
        "type": "photo_kenburns",
        "category": "abstract",
        "overlay_opacity": 0.08,
        "blur_radius": 1,
        "zoom_range": (1.08, 1.30),
        "pan_speed": 0.8,
        "color_tint": None,
    },

    # City blurred heavy — for text-heavy layouts (quiz, pronunciation)
    "photo_city_blur": {
        "type": "photo_kenburns",
        "category": "city",
        "overlay_opacity": 0.25,
        "blur_radius": 4,
        "zoom_range": (1.04, 1.14),
        "pan_speed": 0.3,
        "color_tint": "#0a0020",
    },
    # Clouds from above — dramatic sky and atmosphere
    "photo_clouds": {
        "type": "photo_kenburns",
        "category": "clouds",
        "overlay_opacity": 0.08,
        "blur_radius": 0,
        "zoom_range": (1.06, 1.22),
        "pan_speed": 0.5,
        "color_tint": None,
    },
    # Earth dramatic — high contrast, deep dark overlay
    "photo_earth_dark": {
        "type": "photo_kenburns",
        "category": "earth",
        "overlay_opacity": 0.25,
        "blur_radius": 0,
        "zoom_range": (1.05, 1.18),
        "pan_speed": 0.5,
        "color_tint": "#000010",
    },
    # Ocean vibrant — less overlay, more color
    "photo_ocean_vibrant": {
        "type": "photo_kenburns",
        "category": "ocean",
        "overlay_opacity": 0.05,
        "blur_radius": 0,
        "zoom_range": (1.08, 1.24),
        "pan_speed": 0.6,
        "color_tint": None,
    },
    # Sunset — warm dramatic skies (like reference vocabulary videos)
    "photo_sunset": {
        "type": "photo_kenburns",
        "category": "sunset",
        "overlay_opacity": 0.08,
        "blur_radius": 0,
        "zoom_range": (1.06, 1.22),
        "pan_speed": 0.5,
        "color_tint": None,
    },
    # Galaxy — cosmic deep space backgrounds
    "photo_galaxy": {
        "type": "photo_kenburns",
        "category": "galaxy",
        "overlay_opacity": 0.08,
        "blur_radius": 0,
        "zoom_range": (1.08, 1.28),
        "pan_speed": 0.7,
        "color_tint": None,
    },
}


# ============== BACKGROUND GENERATOR CLASS ==============

class BackgroundGenerator:
    """
    Generates professional backgrounds for TikTok-style videos.

    Usage:
        bg = BackgroundGenerator(width=1080, height=1920)
        frame = bg.render_frame(t=0.5, bg_type="bokeh_particles", options={...})

    Performance:
        Use pre_render_loop() to generate a cached loop, then get_cached_frame()
        for fast playback. This is 10-50x faster than generating each frame.
    """

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT):
        self.width = width
        self.height = height
        self._particle_cache = None
        self._gradient_cache = None
        # Frame cache for fast playback
        self._frame_cache = {}
        self._cache_fps = DEFAULT_FPS
        self._cache_duration = 0
        self._cache_preset = None

    def pre_render_loop(self, preset_name: str, loop_duration: float = 5.0,
                        fps: int = DEFAULT_FPS, show_progress: bool = True) -> int:
        """
        Pre-render a background loop for fast playback.

        Args:
            preset_name: Background preset to render
            loop_duration: Duration of loop in seconds (will repeat)
            fps: Frames per second
            show_progress: Print progress

        Returns:
            Number of frames cached
        """
        self._cache_preset = preset_name
        self._cache_fps = fps
        self._cache_duration = loop_duration
        self._frame_cache = {}

        num_frames = int(loop_duration * fps)

        if show_progress:
            logger.info(f"Pre-rendering {num_frames} frames for {preset_name}...")

        for i in range(num_frames):
            t = i / fps
            frame = self.render_from_preset(t, preset_name, duration=loop_duration)
            self._frame_cache[i] = frame

            if show_progress and (i + 1) % 30 == 0:
                logger.debug(f"  {i + 1}/{num_frames} frames ({(i + 1) / num_frames * 100:.0f}%)")

        if show_progress:
            logger.info(f"Done! Cached {num_frames} frames")

        return num_frames

    def get_cached_frame(self, t: float) -> np.ndarray:
        """
        Get a frame from the pre-rendered cache (fast).

        The cache loops seamlessly.
        """
        if not self._frame_cache:
            raise RuntimeError("No cached frames. Call pre_render_loop() first.")

        # Loop the time within cache duration
        t_looped = t % self._cache_duration
        frame_idx = int(t_looped * self._cache_fps) % len(self._frame_cache)

        return self._frame_cache[frame_idx]

    def has_cache(self) -> bool:
        """Check if frames are cached."""
        return bool(self._frame_cache)

    def clear_cache(self):
        """Clear the frame cache to free memory."""
        self._frame_cache = {}
        self._cache_preset = None
        self._static_frame = None

    def render_static_once(self, preset_name: str) -> np.ndarray:
        """
        Render a static background once and cache it.
        Much faster than animated - same frame every time.
        """
        if not hasattr(self, '_static_frame') or self._static_frame is None:
            self._static_frame = self.render_from_preset(0, preset_name, duration=30.0)
            self._cache_preset = preset_name
        return self._static_frame

    def get_static_frame(self) -> np.ndarray:
        """Get the cached static frame (fast copy)."""
        if hasattr(self, '_static_frame') and self._static_frame is not None:
            return self._static_frame.copy()
        return None

    def get_preset(self, preset_name: str) -> Dict:
        """Get a background preset by name."""
        if preset_name not in BACKGROUND_PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {list(BACKGROUND_PRESETS.keys())}")
        return BACKGROUND_PRESETS[preset_name].copy()

    def render_frame(self, t: float, bg_type: str = "solid_vignette",
                     options: Dict = None, duration: float = 30.0) -> np.ndarray:
        """
        Render a single background frame at time t.

        Args:
            t: Current time in seconds
            bg_type: Background type
            options: Type-specific options
            duration: Total video duration (for looping animations)

        Returns:
            numpy array (H, W, 3) RGB
        """
        options = options or {}

        if bg_type == "static_gradient":
            return self.static_gradient(**options)
        elif bg_type == "solid_vignette":
            return self.solid_vignette(t, **options)
        elif bg_type == "animated_gradient":
            return self.animated_gradient(t, duration=duration, **options)
        elif bg_type == "bokeh_particles":
            return self.bokeh_particles(t, **options)
        elif bg_type == "abstract_waves":
            return self.abstract_waves(t, **options)
        elif bg_type == "dynamic_glow_orbs":
            return self.dynamic_glow_orbs(t, **options)
        elif bg_type == "particle_flow":
            return self.particle_flow(t, **options)
        elif bg_type == "light_rays":
            return self.light_rays(t, **options)
        elif bg_type == "aurora":
            return self.aurora(t, **options)
        elif bg_type == "photo_kenburns":
            return self.photo_kenburns(t, duration=duration, **options)
        else:
            # Default to solid vignette
            return self.solid_vignette(t, color="#0a0a12")

    def render_from_preset(self, t: float, preset_name: str, duration: float = 30.0) -> np.ndarray:
        """Render a frame using a preset."""
        preset = self.get_preset(preset_name)
        bg_type = preset.pop("type")
        return self.render_frame(t, bg_type=bg_type, options=preset, duration=duration)

    # ============== SOLID VIGNETTE ==============

    def solid_vignette(self, t: float, color: str = "#0a0a12",
                       vignette_strength: float = 0.4) -> np.ndarray:
        """
        Solid color background with darker edges (vignette effect).
        Professional, minimal look that ensures text readability.

        Args:
            t: Time (not used, static background)
            color: Base color (hex)
            vignette_strength: How dark the edges get (0-1)
        """
        rgb = hex_to_rgb(color)

        # Create base solid color
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)
        img[:, :] = rgb

        # Create vignette mask
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)

        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)

        # Distance from center (normalized)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist

        # Vignette falloff (smooth, not harsh)
        vignette = 1.0 - (dist ** 1.5) * vignette_strength
        vignette = np.clip(vignette, 0.3, 1.0)  # Don't go too dark

        # Apply vignette
        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== STATIC GRADIENT (semi-static, no animation) ==============

    def static_gradient(self, colors: List[str] = None,
                        direction: str = "vertical",
                        vignette_strength: float = 0.30) -> np.ndarray:
        """
        Beautiful multi-color gradient — rendered once, same every frame.
        Semi-static: no animation, no moving particles, just a pretty gradient.

        Supports vertical, diagonal, and radial directions.

        Args:
            colors: List of 2-4 hex colors (top→bottom or inner→outer)
            direction: "vertical", "diagonal", or "radial"
            vignette_strength: How dark the edges get (0-1)
        """
        if colors is None:
            colors = ["#0a0a20", "#1a1a4e", "#4a1a6b", "#00d4ff"]

        rgb_colors = [np.array(hex_to_rgb(c), dtype=np.float32) for c in colors]
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)

        y_coords = np.arange(self.height, dtype=np.float32).reshape(-1, 1)
        x_coords = np.arange(self.width, dtype=np.float32).reshape(1, -1)

        # Calculate the gradient ratio (0→1) based on direction
        if direction == "radial":
            # Radial: center=0, edges=1
            center_y, center_x = self.height / 2, self.width / 2
            max_dist = math.sqrt(center_x**2 + center_y**2)
            ratio = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        elif direction == "diagonal":
            # Diagonal: top-left=0, bottom-right=1
            ratio = (y_coords / self.height * 0.6 + x_coords / self.width * 0.4)
        else:
            # Vertical: top=0, bottom=1
            ratio = y_coords / self.height * np.ones((1, self.width))

        ratio = np.clip(ratio, 0.0, 1.0)

        # Multi-stop color interpolation
        n_stops = len(rgb_colors)
        if n_stops == 1:
            for c in range(3):
                img[:, :, c] = rgb_colors[0][c]
        else:
            # Scale ratio to number of segments
            scaled = ratio * (n_stops - 1)
            for seg in range(n_stops - 1):
                # Mask for this segment
                mask = (scaled >= seg) & (scaled < seg + 1) if seg < n_stops - 2 else (scaled >= seg)
                local_t = np.clip(scaled - seg, 0.0, 1.0)
                # Smooth easing per segment
                local_t_smooth = local_t * local_t * (3 - 2 * local_t)  # smoothstep

                for c_ch in range(3):
                    blended = rgb_colors[seg][c_ch] + (rgb_colors[seg + 1][c_ch] - rgb_colors[seg][c_ch]) * local_t_smooth
                    img[:, :, c_ch] = np.where(mask, blended, img[:, :, c_ch])

        # Add subtle noise/grain for visual richness (very subtle)
        noise = np.random.default_rng(42).normal(0, 3.0, (self.height, self.width))
        for c in range(3):
            img[:, :, c] += noise

        # Apply vignette
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 1.6) * vignette_strength
        vignette = np.clip(vignette, 0.3, 1.0)

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== ANIMATED GRADIENT ==============

    def animated_gradient(self, t: float, colors: List[str] = None,
                          cycle_duration: float = 8.0, duration: float = 30.0,
                          wave_intensity: float = 0.08) -> np.ndarray:
        """
        Smooth color gradient that transitions over time.

        Args:
            t: Current time in seconds
            colors: List of hex colors to cycle through
            cycle_duration: Seconds for one full color cycle
            duration: Total video duration
            wave_intensity: Subtle wave distortion amount
        """
        if colors is None:
            colors = ["#1a1a2e", "#2d1b4e", "#1a3a5c", "#1a1a2e"]

        # Convert colors to RGB
        rgb_colors = [hex_to_rgb(c) for c in colors]
        num_colors = len(rgb_colors)

        # Calculate current position in color cycle
        cycle_progress = (t % cycle_duration) / cycle_duration

        # Determine which two colors we're between
        total_segments = num_colors - 1
        segment = cycle_progress * total_segments
        idx1 = int(segment) % num_colors
        idx2 = (idx1 + 1) % num_colors
        local_t = segment - int(segment)

        # Smooth easing for color transition
        local_t = ease_in_out_sine(local_t)

        # Get the two colors for this moment
        color1 = np.array(rgb_colors[idx1], dtype=np.float32)
        color2 = np.array(rgb_colors[idx2], dtype=np.float32)

        # Create vertical gradient with wave distortion
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)

        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)

        # Add subtle wave animation (initialize with full shape for proper broadcasting)
        wave_y1 = wave_intensity * np.sin(y_coords * 0.008 + t * 0.5)
        wave_y2 = wave_intensity * 0.5 * np.sin(y_coords * 0.012 + t * 0.3 + 1.5)
        wave_x = wave_intensity * 0.3 * np.sin(x_coords * 0.005 + t * 0.4)

        # Combine waves (broadcasting happens here correctly)
        wave = wave_y1 + wave_y2 + wave_x

        # Gradient ratio (top to bottom) with wave distortion
        ratio = (y_coords / self.height) + wave
        ratio = np.clip(ratio, 0, 1)

        # Interpolate colors with time-based shift
        time_shift = local_t

        for c in range(3):
            # Base gradient
            top_color = color1[c] + (color2[c] - color1[c]) * time_shift
            bottom_color = color2[c] + (color1[c] - color2[c]) * time_shift * 0.3

            img[:, :, c] = top_color + (bottom_color - top_color) * ratio[:, :]

        # Add subtle vignette
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 2) * 0.25

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== BOKEH PARTICLES ==============

    def bokeh_particles(self, t: float, base_color: str = "#0a0a14",
                        particle_colors: List[str] = None,
                        num_particles: int = 18,
                        min_size: int = 30, max_size: int = 100) -> np.ndarray:
        """
        Dark background with floating soft bokeh circles.
        Very popular in TikTok educational content.

        Args:
            t: Current time in seconds
            base_color: Background color (hex)
            particle_colors: List of particle colors (hex)
            num_particles: Number of bokeh particles
            min_size: Minimum particle radius
            max_size: Maximum particle radius
        """
        if particle_colors is None:
            particle_colors = ["#ffffff", "#00d4ff", "#ffd700"]

        # Initialize particle positions (cached for consistency)
        if self._particle_cache is None or len(self._particle_cache) != num_particles:
            random.seed(42)  # Consistent particles across frames
            self._particle_cache = []
            for i in range(num_particles):
                self._particle_cache.append({
                    'x': random.random(),
                    'y': random.random(),
                    'size': random.randint(min_size, max_size),
                    'speed_x': (random.random() - 0.5) * 0.015,
                    'speed_y': (random.random() - 0.5) * 0.008 - 0.003,
                    'alpha': random.random() * 0.25 + 0.08,
                    'color_idx': random.randint(0, len(particle_colors) - 1),
                    'pulse_phase': random.random() * 2 * math.pi,
                    'pulse_speed': random.random() * 0.3 + 0.2,
                })

        # Create base background with gradient
        base_rgb = hex_to_rgb(base_color)
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)

        # Subtle vertical gradient on base
        for y in range(self.height):
            ratio = y / self.height
            for c in range(3):
                img[y, :, c] = base_rgb[c] * (0.8 + 0.2 * ratio)

        # Convert to PIL for drawing bokeh circles
        pil_img = Image.fromarray(img.astype(np.uint8), 'RGB').convert('RGBA')

        # Draw each particle
        for particle in self._particle_cache:
            # Animate position (wrapping)
            px = (particle['x'] + particle['speed_x'] * t * 30) % 1.0
            py = (particle['y'] + particle['speed_y'] * t * 30) % 1.0

            cx = int(px * self.width)
            cy = int(py * self.height)

            # Pulsing size and alpha
            pulse = 1.0 + 0.2 * math.sin(t * particle['pulse_speed'] * 2 + particle['pulse_phase'])
            size = int(particle['size'] * pulse)
            alpha = particle['alpha'] * (0.7 + 0.3 * math.sin(t * particle['pulse_speed'] + particle['pulse_phase']))

            # Get particle color
            color_hex = particle_colors[particle['color_idx']]
            color_rgb = hex_to_rgb(color_hex)

            # Create soft bokeh circle
            self._draw_bokeh_circle(pil_img, cx, cy, size, color_rgb, alpha)

        # Convert back to numpy
        result = np.array(pil_img.convert('RGB'))

        # Add subtle vignette
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 1.8) * 0.35

        for c in range(3):
            result[:, :, c] = (result[:, :, c] * vignette).astype(np.uint8)

        return result

    def _draw_bokeh_circle(self, img: Image.Image, cx: int, cy: int,
                           radius: int, color: Tuple, alpha: float):
        """Draw a soft bokeh circle with gaussian falloff."""
        # Create a small image for the circle
        size = radius * 2 + 10
        circle_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))

        # Draw circle with soft edges using numpy
        y, x = np.ogrid[:size, :size]
        center = size // 2
        dist = np.sqrt((x - center)**2 + (y - center)**2)

        # Gaussian falloff for soft bokeh effect
        mask = np.exp(-2.5 * (dist / max(radius, 1))**2)
        mask = (mask * 255 * alpha).astype(np.uint8)

        # Create RGBA array
        circle_data = np.zeros((size, size, 4), dtype=np.uint8)
        circle_data[:, :, 0] = color[0]
        circle_data[:, :, 1] = color[1]
        circle_data[:, :, 2] = color[2]
        circle_data[:, :, 3] = mask

        circle_img = Image.fromarray(circle_data, 'RGBA')

        # Paste onto main image
        paste_x = cx - size // 2
        paste_y = cy - size // 2

        # Handle edge cases
        if paste_x + size > 0 and paste_x < self.width and paste_y + size > 0 and paste_y < self.height:
            img.paste(circle_img, (paste_x, paste_y), circle_img)

    # ============== ABSTRACT WAVES ==============

    def abstract_waves(self, t: float, color: str = "#1a1a2e",
                       wave_color: str = "#2d2d4e",
                       num_waves: int = 4,
                       wave_opacity: float = 0.3) -> np.ndarray:
        """
        Subtle animated wave patterns on dark background.
        Adds depth without distraction.

        Args:
            t: Current time in seconds
            color: Base background color
            wave_color: Color of wave overlay
            num_waves: Number of wave layers
            wave_opacity: Opacity of waves
        """
        base_rgb = hex_to_rgb(color)
        wave_rgb = hex_to_rgb(wave_color)

        # Create base
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)
        img[:, :] = base_rgb

        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)

        # Add multiple wave layers
        wave_total = np.zeros((self.height, self.width), dtype=np.float32)

        for i in range(num_waves):
            freq_y = 0.003 + i * 0.002
            freq_x = 0.002 + i * 0.001
            speed = 0.3 + i * 0.15
            phase = i * math.pi / num_waves

            wave = np.sin(y_coords * freq_y * self.height + t * speed + phase)
            wave += 0.5 * np.sin(x_coords * freq_x * self.width + t * speed * 0.7 + phase)
            wave = (wave + 1.5) / 3.0  # Normalize to 0-1

            wave_total += wave * (1.0 / num_waves)

        # Apply wave overlay
        for c in range(3):
            wave_contribution = (wave_rgb[c] - base_rgb[c]) * wave_total * wave_opacity
            img[:, :, c] += wave_contribution

        # Add vignette
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 2) * 0.3

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== DYNAMIC GLOW ORBS ==============

    def dynamic_glow_orbs(self, t: float, base_color: str = "#0a0a14",
                          orb_colors: List[str] = None,
                          orb_count: int = 10,
                          movement_speed: str = "medium",
                          orb_size_min: int = 80,
                          orb_size_max: int = 220) -> np.ndarray:
        """
        Floating glowing orbs with MORE presence and movement than bokeh.
        More visible, more dynamic, more engaging.

        Args:
            t: Current time
            base_color: Background color
            orb_colors: Colors for orbs
            orb_count: Number of orbs (8-15 recommended)
            movement_speed: "slow", "medium", "fast"
            orb_size_min: Minimum orb radius (default 80)
            orb_size_max: Maximum orb radius (default 220)
        """
        if orb_colors is None:
            orb_colors = ["#00d4ff", "#ff6bb3", "#a855f7", "#22d3ee"]

        speed_mult = {"slow": 0.3, "medium": 0.6, "fast": 1.0}.get(movement_speed, 0.6)

        # Initialize orb data (cached)
        if not hasattr(self, '_glow_orbs') or not self._glow_orbs or len(self._glow_orbs) != orb_count:
            random.seed(123)
            self._glow_orbs = []
            for i in range(orb_count):
                self._glow_orbs.append({
                    'x': random.random(),
                    'y': random.random(),
                    'size': random.randint(orb_size_min, orb_size_max),
                    'speed_x': (random.random() - 0.5) * 0.025,
                    'speed_y': -random.random() * 0.015 - 0.008,  # Float upward
                    'alpha': random.random() * 0.35 + 0.15,  # MORE visible
                    'color_idx': i % len(orb_colors),
                    'pulse_phase': random.random() * math.pi * 2,
                    'pulse_speed': random.random() * 0.8 + 0.4,
                    'blur_radius': random.randint(40, 80),  # Soft glow
                })

        # Create base with gradient
        base_rgb = hex_to_rgb(base_color)
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)

        # Subtle vertical gradient
        for y in range(self.height):
            ratio = y / self.height
            brightness = 0.7 + 0.3 * ratio
            for c in range(3):
                img[y, :, c] = base_rgb[c] * brightness

        # Draw each orb with glow
        for orb in self._glow_orbs:
            # Animate position with wrapping and speed
            px = (orb['x'] + orb['speed_x'] * t * 40 * speed_mult) % 1.2 - 0.1
            py = (orb['y'] + orb['speed_y'] * t * 40 * speed_mult) % 1.2 - 0.1

            cx = int(px * self.width)
            cy = int(py * self.height)

            # Pulsing size and alpha - MORE dramatic
            pulse = 1.0 + 0.35 * math.sin(t * orb['pulse_speed'] * 2 + orb['pulse_phase'])
            size = int(orb['size'] * pulse)
            alpha = orb['alpha'] * (0.6 + 0.4 * math.sin(t * orb['pulse_speed'] + orb['pulse_phase']))

            # Get orb color with subtle shift
            color_hex = orb_colors[orb['color_idx']]
            color_rgb = hex_to_rgb(color_hex)

            # Color breathing
            hue_shift = math.sin(t * 0.5 + orb['pulse_phase']) * 0.15
            color_rgb = tuple(int(min(255, c * (1 + hue_shift))) for c in color_rgb)

            # Draw soft glow orb
            self._draw_glow_orb(img, cx, cy, size, orb['blur_radius'], color_rgb, alpha)

        # Vignette
        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 1.5) * 0.4

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    def _draw_glow_orb(self, img: np.ndarray, cx: int, cy: int,
                       size: int, blur: int, color: Tuple, alpha: float):
        """Draw a soft glowing orb with gaussian falloff."""
        total_size = size + blur * 2

        y_min = max(0, cy - total_size)
        y_max = min(self.height, cy + total_size)
        x_min = max(0, cx - total_size)
        x_max = min(self.width, cx + total_size)

        if y_max <= y_min or x_max <= x_min:
            return

        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)

        # Soft gaussian glow with larger falloff
        glow = np.exp(-1.8 * (dist / max(size, 1)) ** 2)
        glow = glow * alpha

        for c in range(3):
            img[y_min:y_max, x_min:x_max, c] += color[c] * glow

    # ============== PARTICLE FLOW ==============

    def particle_flow(self, t: float, base_color: str = "#0a0a14",
                      particle_color: str = "#ffffff",
                      particle_count: int = 50,
                      direction: str = "up",
                      speed: float = 1.0) -> np.ndarray:
        """
        Particles with directional movement - creates energy and flow.

        Args:
            t: Current time
            base_color: Background color
            particle_color: Particle color
            particle_count: Number of particles
            direction: "up", "down", "left", "right", "up-right", "up-left"
            speed: Movement speed multiplier
        """
        # Direction vectors
        directions = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
            "up-right": (0.7, -0.7),
            "up-left": (-0.7, -0.7),
        }
        dx, dy = directions.get(direction, (0, -1))

        # Initialize particles
        if not hasattr(self, '_flow_particles') or len(self._flow_particles) != particle_count:
            random.seed(456)
            self._flow_particles = []
            for i in range(particle_count):
                self._flow_particles.append({
                    'x': random.random(),
                    'y': random.random(),
                    'size': random.randint(2, 8),
                    'speed': random.random() * 0.5 + 0.5,
                    'alpha': random.random() * 0.4 + 0.2,
                    'twinkle_phase': random.random() * math.pi * 2,
                })

        # Create base
        base_rgb = hex_to_rgb(base_color)
        particle_rgb = hex_to_rgb(particle_color)
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)
        img[:, :] = base_rgb

        # Draw particles
        for p in self._flow_particles:
            # Move in direction with speed variation
            move_t = t * speed * p['speed'] * 0.08
            px = (p['x'] + dx * move_t) % 1.0
            py = (p['y'] + dy * move_t) % 1.0

            cx = int(px * self.width)
            cy = int(py * self.height)

            # Twinkle effect
            twinkle = 0.5 + 0.5 * math.sin(t * 3 + p['twinkle_phase'])
            alpha = p['alpha'] * twinkle

            # Draw particle with small glow
            size = p['size']
            y_min = max(0, cy - size * 3)
            y_max = min(self.height, cy + size * 3)
            x_min = max(0, cx - size * 3)
            x_max = min(self.width, cx + size * 3)

            if y_max > y_min and x_max > x_min:
                yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
                dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
                glow = np.exp(-2 * (dist / max(size, 1)) ** 2) * alpha

                for c in range(3):
                    img[y_min:y_max, x_min:x_max, c] += particle_rgb[c] * glow

        # Subtle vignette
        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 2) * 0.25

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== LIGHT RAYS ==============

    def light_rays(self, t: float, base_color: str = "#0a0a12",
                   ray_color: str = "#ffffff",
                   ray_count: int = 5,
                   ray_opacity: float = 0.12) -> np.ndarray:
        """
        Diagonal soft light beams for cinematic depth.

        Args:
            t: Current time
            base_color: Background color
            ray_color: Ray color
            ray_count: Number of rays
            ray_opacity: Ray opacity (0.08-0.2 recommended)
        """
        base_rgb = hex_to_rgb(base_color)
        ray_rgb = hex_to_rgb(ray_color)

        img = np.zeros((self.height, self.width, 3), dtype=np.float32)
        img[:, :] = base_rgb

        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)

        # Create rotating rays
        rotation_speed = 0.05
        base_angle = t * rotation_speed

        for i in range(ray_count):
            # Ray angle with rotation
            angle = base_angle + (i / ray_count) * math.pi + math.sin(t * 0.3 + i) * 0.1
            ray_width = 150 + 50 * math.sin(t * 0.5 + i * 0.7)

            # Calculate perpendicular distance to ray line
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            # Ray passes through center with offset
            offset = math.sin(t * 0.2 + i * 1.5) * 200
            cx = self.width / 2 + offset * cos_a
            cy = self.height / 2 + offset * sin_a

            # Distance from each pixel to the ray line
            dist = np.abs((x_coords - cx) * sin_a - (y_coords - cy) * cos_a)

            # Soft ray falloff
            ray_mask = np.exp(-2 * (dist / ray_width) ** 2)

            # Fade at edges
            edge_fade = 1.0 - np.abs(
                (x_coords - self.width/2) * cos_a + (y_coords - self.height/2) * sin_a
            ) / (max(self.width, self.height) * 0.7)
            edge_fade = np.clip(edge_fade, 0, 1)

            ray_intensity = ray_mask * edge_fade * ray_opacity

            for c in range(3):
                img[:, :, c] += ray_rgb[c] * ray_intensity

        # Vignette
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 1.8) * 0.35

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)

    # ============== AURORA / NORTHERN LIGHTS ==============

    def aurora(self, t: float, base_color: str = "#050510",
               aurora_colors: List[str] = None) -> np.ndarray:
        """
        Northern lights / aurora effect - flowing colored bands.
        Very engaging and dynamic.

        Args:
            t: Current time
            base_color: Dark background
            aurora_colors: Colors for aurora bands
        """
        if aurora_colors is None:
            aurora_colors = ["#00ff88", "#00ddff", "#aa55ff", "#ff55aa"]

        base_rgb = hex_to_rgb(base_color)
        img = np.zeros((self.height, self.width, 3), dtype=np.float32)
        img[:, :] = base_rgb

        y_coords = np.arange(self.height).reshape(-1, 1).astype(np.float32)
        x_coords = np.arange(self.width).reshape(1, -1).astype(np.float32)

        # Create flowing aurora bands
        for i, color_hex in enumerate(aurora_colors):
            color_rgb = hex_to_rgb(color_hex)

            # Wave parameters for this band
            freq1 = 0.003 + i * 0.001
            freq2 = 0.005 + i * 0.0015
            speed1 = 0.4 + i * 0.1
            speed2 = 0.3 + i * 0.15
            phase = i * math.pi / 2

            # Create flowing wave shape
            wave1 = np.sin(x_coords * freq1 + t * speed1 + phase) * 150
            wave2 = np.sin(x_coords * freq2 + t * speed2 + phase + 1) * 80
            wave3 = np.sin(y_coords * 0.002 + t * 0.2) * 50

            # Band center position (varies with x)
            band_y = self.height * (0.25 + i * 0.15) + wave1 + wave2 + wave3

            # Distance from band center
            dist = np.abs(y_coords - band_y)

            # Soft band with varying width
            band_width = 120 + 40 * np.sin(x_coords * 0.008 + t * 0.5 + i)
            band_intensity = np.exp(-2 * (dist / band_width) ** 2)

            # Shimmer effect
            shimmer = 0.7 + 0.3 * np.sin(x_coords * 0.02 + y_coords * 0.01 + t * 2 + i)
            band_intensity *= shimmer

            # Apply with low opacity for layering
            opacity = 0.25 - i * 0.03
            for c in range(3):
                img[:, :, c] += color_rgb[c] * band_intensity * opacity

        # Strong vignette for focus
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 1.5) * 0.5

        for c in range(3):
            img[:, :, c] *= vignette

        return np.clip(img, 0, 255).astype(np.uint8)


    # ============== PHOTO KEN BURNS ==============

    def _load_photo(self, category: str) -> Optional[Image.Image]:
        """Load a random photo from assets/backgrounds/<category>/."""
        if not hasattr(self, '_photo_cache'):
            self._photo_cache = {}

        # Return cached photo for this category
        if category in self._photo_cache:
            return self._photo_cache[category]

        cat_dir = ASSETS_DIR / category
        if not cat_dir.exists():
            logger.warning("Photo category dir not found: %s", cat_dir)
            return None

        # Find all image files
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        images = [f for f in cat_dir.iterdir()
                  if f.suffix.lower() in extensions and f.is_file()]

        if not images:
            logger.warning("No images in %s/", category)
            return None

        # Pick one using SystemRandom (not affected by global seed)
        chosen = random.SystemRandom().choice(images)
        logger.info("Loading photo background: %s", chosen.name)

        try:
            img = Image.open(chosen).convert('RGB')

            # Scale to cover the video frame (crop to fill)
            img_ratio = img.width / img.height
            target_ratio = self.width / self.height

            # We need extra margin for Ken Burns zoom (max 1.3x)
            margin = 1.35
            target_w = int(self.width * margin)
            target_h = int(self.height * margin)

            if img_ratio > target_ratio:
                # Image is wider: scale by height, crop width
                new_h = target_h
                new_w = int(new_h * img_ratio)
            else:
                # Image is taller: scale by width, crop height
                new_w = target_w
                new_h = int(new_w / img_ratio)

            img = img.resize((new_w, new_h), Image.LANCZOS)
            self._photo_cache[category] = img
            return img

        except Exception as e:
            logger.error("Failed to load photo %s: %s", chosen, e)
            return None

    def photo_kenburns(self, t: float, category: str = "earth",
                       overlay_opacity: float = 0.35,
                       blur_radius: int = 2,
                       zoom_range: tuple = (1.05, 1.20),
                       pan_speed: float = 0.3,
                       color_tint: str = None,
                       duration: float = 30.0) -> np.ndarray:
        """
        Real photograph background with Ken Burns effect (slow zoom + pan).
        Applies dark overlay and optional blur for text readability.

        Like the reference TikTok videos: Earth from space, city scenes,
        ocean sunsets, architecture, etc.

        Args:
            t: Current time in seconds
            category: Image subfolder in assets/backgrounds/
            overlay_opacity: Dark overlay strength (0=none, 1=black)
            blur_radius: Gaussian blur amount (0=sharp)
            zoom_range: (min_zoom, max_zoom) for Ken Burns
            pan_speed: How fast the camera pans (0=still, 1=fast)
            color_tint: Optional hex color tint overlay
            duration: Total video duration
        """
        photo = self._load_photo(category)

        if photo is None:
            # Fallback to a dark gradient if no photo available
            logger.info("No photo for '%s', using fallback gradient", category)
            return self.animated_gradient(t, colors=["#0a0a14", "#1a1a3a", "#0a1a2a", "#0a0a14"])

        # Ken Burns: calculate zoom and pan for current time
        zoom_min, zoom_max = zoom_range
        cycle = duration if duration > 0 else 30.0

        # Dynamic zoom — two layered oscillations for organic feel
        zoom_slow = (math.sin(t * math.pi * 2 / cycle) + 1) / 2
        zoom_fast = (math.sin(t * 0.8) + 1) / 2 * 0.3  # subtle fast pulse
        zoom_t = min(1.0, zoom_slow + zoom_fast)
        zoom = zoom_min + (zoom_max - zoom_min) * zoom_t

        # Dynamic pan — layered lissajous with drift for cinematic motion
        pan_x = (math.sin(t * 0.4 * pan_speed) * 0.4
                 + math.sin(t * 0.17 * pan_speed + 1.2) * 0.3)
        pan_y = (math.sin(t * 0.3 * pan_speed + 0.7) * 0.4
                 + math.cos(t * 0.13 * pan_speed + 2.1) * 0.25)

        # Calculate crop region
        crop_w = int(self.width / zoom)
        crop_h = int(self.height / zoom)

        # Center point with pan offset
        max_offset_x = (photo.width - crop_w) // 2
        max_offset_y = (photo.height - crop_h) // 2

        center_x = photo.width // 2 + int(pan_x * max_offset_x)
        center_y = photo.height // 2 + int(pan_y * max_offset_y)

        # Crop box
        left = max(0, center_x - crop_w // 2)
        top = max(0, center_y - crop_h // 2)
        right = min(photo.width, left + crop_w)
        bottom = min(photo.height, top + crop_h)

        # Ensure minimum size
        if right - left < crop_w:
            left = max(0, right - crop_w)
        if bottom - top < crop_h:
            top = max(0, bottom - crop_h)

        # Crop and resize to video dimensions
        cropped = photo.crop((left, top, right, bottom))
        frame = cropped.resize((self.width, self.height), Image.LANCZOS)

        # Apply blur if requested
        if blur_radius > 0:
            frame = frame.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Convert to numpy
        img = np.array(frame, dtype=np.float32)

        # Apply color tint if specified
        if color_tint:
            tint_rgb = hex_to_rgb(color_tint)
            tint_strength = 0.25
            for c in range(3):
                img[:, :, c] = img[:, :, c] * (1 - tint_strength) + tint_rgb[c] * tint_strength

        # Apply dark overlay for text readability (subtle — let the photo shine)
        if overlay_opacity > 0:
            img *= (1.0 - overlay_opacity)

        # Apply gentle vignette (just darken edges, keep center bright)
        y_coords = np.arange(self.height).reshape(-1, 1)
        x_coords = np.arange(self.width).reshape(1, -1)
        center_y, center_x = self.height / 2, self.width / 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2) / max_dist
        vignette = 1.0 - (dist ** 2.0) * 0.25
        vignette = np.clip(vignette, 0.55, 1.0)

        for c in range(3):
            img[:, :, c] *= vignette

        # === DYNAMIC OVERLAY EFFECTS (category-aware, make photos feel alive) ===

        # Category-specific effect profiles (boosted for more dynamism)
        _EFFECT_PROFILES = {
            'earth':    {'breath': (0.06, 0.04, 0.08), 'particle_color': (200, 220, 255), 'particle_count': 30, 'particle_size': (2, 6), 'leak_color': (180, 200, 255), 'leak_strength': 0.07},
            'city':     {'breath': (0.08, 0.05, 0.09), 'particle_color': (255, 200, 255), 'particle_count': 22, 'particle_size': (2, 5), 'leak_color': (255, 180, 220), 'leak_strength': 0.08},
            'ocean':    {'breath': (0.04, 0.07, 0.08), 'particle_color': (180, 230, 255), 'particle_count': 28, 'particle_size': (2, 6), 'leak_color': (140, 200, 255), 'leak_strength': 0.08},
            'nature':   {'breath': (0.05, 0.08, 0.04), 'particle_color': (220, 255, 200), 'particle_count': 24, 'particle_size': (2, 7), 'leak_color': (255, 240, 180), 'leak_strength': 0.07},
            'abstract': {'breath': (0.08, 0.06, 0.09), 'particle_color': (255, 220, 255), 'particle_count': 20, 'particle_size': (3, 8), 'leak_color': (255, 200, 255), 'leak_strength': 0.08},
            'clouds':   {'breath': (0.05, 0.05, 0.06), 'particle_color': (255, 240, 230), 'particle_count': 16, 'particle_size': (3, 9), 'leak_color': (255, 220, 200), 'leak_strength': 0.09},
            'sunset':   {'breath': (0.09, 0.05, 0.03), 'particle_color': (255, 200, 120), 'particle_count': 26, 'particle_size': (2, 6), 'leak_color': (255, 180, 100), 'leak_strength': 0.10},
            'galaxy':   {'breath': (0.06, 0.05, 0.09), 'particle_color': (200, 180, 255), 'particle_count': 35, 'particle_size': (1, 4), 'leak_color': (180, 160, 255), 'leak_strength': 0.06},
        }
        profile = _EFFECT_PROFILES.get(category, _EFFECT_PROFILES['earth'])

        # 1. Color breathing — category-tuned hue shift (layered for organic feel)
        br, bg_b, bb = profile['breath']
        breath_r = 1.0 + br * math.sin(t * 0.8) + br * 0.3 * math.sin(t * 1.7 + 0.5)
        breath_g = 1.0 + bg_b * math.sin(t * 0.6 + 1.0) + bg_b * 0.3 * math.sin(t * 1.4 + 1.8)
        breath_b = 1.0 + bb * math.sin(t * 0.9 + 2.0) + bb * 0.3 * math.sin(t * 2.0 + 0.3)
        img[:, :, 0] *= breath_r
        img[:, :, 1] *= breath_g
        img[:, :, 2] *= breath_b

        # 2. Floating particles — category-specific style
        cache_key = f'_particles_{category}'
        if not hasattr(self, cache_key):
            rng = random.Random(hash(category) + 12345)
            particles = []
            p_count = profile['particle_count']
            p_min, p_max = profile['particle_size']
            for _ in range(p_count):
                particles.append({
                    'x': rng.random(),
                    'y': rng.random(),
                    'size': rng.randint(p_min, p_max),
                    'speed_y': -(rng.random() * 0.015 + 0.005),
                    'drift_x': (rng.random() - 0.5) * 0.008,
                    'brightness': rng.random() * 0.4 + 0.6,
                    'phase': rng.random() * math.pi * 2,
                    'twinkle_speed': rng.random() * 2.5 + 1.0,
                })
            setattr(self, cache_key, particles)

        h, w = self.height, self.width
        p_color = profile['particle_color']
        for p in getattr(self, cache_key):
            px = ((p['x'] + p['drift_x'] * t * 30 + math.sin(t * 0.7 + p['phase']) * 0.04) % 1.0)
            py = ((p['y'] + p['speed_y'] * t * 30 + math.sin(t * 0.5 + p['phase'] * 0.7) * 0.015) % 1.0)
            cx, cy = int(px * w), int(py * h)
            twinkle = 0.5 + 0.5 * math.sin(t * p['twinkle_speed'] + p['phase'])
            alpha = p['brightness'] * twinkle * 0.7
            size = p['size']

            y_min, y_max = max(0, cy - size), min(h, cy + size + 1)
            x_min, x_max = max(0, cx - size), min(w, cx + size + 1)
            if y_max > y_min and x_max > x_min:
                yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
                dist_p = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
                particle_mask = dist_p <= size
                glow = np.exp(-2.0 * (dist_p / max(size, 1)) ** 2) * particle_mask * alpha
                img[y_min:y_max, x_min:x_max, 0] += p_color[0] * glow
                img[y_min:y_max, x_min:x_max, 1] += p_color[1] * glow
                img[y_min:y_max, x_min:x_max, 2] += p_color[2] * glow

        # 3. Moving light leak — category-colored glow
        leak_r, leak_g, leak_b = profile['leak_color']
        leak_str = profile['leak_strength']
        lx = w * (0.6 + 0.3 * math.sin(t * 0.25) + 0.1 * math.sin(t * 0.6))
        ly = h * (0.25 + 0.2 * math.sin(t * 0.3 + 0.8) + 0.05 * math.cos(t * 0.7))
        lr = max(w, h) * 0.5
        y_full = np.arange(h).reshape(-1, 1)
        x_full = np.arange(w).reshape(1, -1)
        dist_leak = np.sqrt((x_full - lx) ** 2 + (y_full - ly) ** 2)
        leak_area = dist_leak < lr
        leak_intensity = leak_str * ((1 - dist_leak / lr) ** 2) * leak_area
        leak_pulse = 0.7 + 0.3 * math.sin(t * 0.25)
        img[:, :, 0] += leak_r * leak_intensity * leak_pulse
        img[:, :, 1] += leak_g * leak_intensity * leak_pulse
        img[:, :, 2] += leak_b * leak_intensity * leak_pulse

        return np.clip(img, 0, 255).astype(np.uint8)


# ============== PHOTO DOWNLOAD HELPER ==============

def get_available_photo_categories() -> Dict[str, int]:
    """Return available photo categories and image count per category."""
    categories = {}
    if ASSETS_DIR.exists():
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        for cat_dir in ASSETS_DIR.iterdir():
            if cat_dir.is_dir():
                count = sum(1 for f in cat_dir.iterdir()
                           if f.suffix.lower() in extensions and f.is_file())
                categories[cat_dir.name] = count
    return categories


def download_sample_backgrounds():
    """
    Download sample royalty-free backgrounds for each category.
    Uses Pexels API (free tier, 200 req/month).

    Set PEXELS_API_KEY in .env to enable, or manually place images in:
        assets/backgrounds/earth/
        assets/backgrounds/city/
        assets/backgrounds/ocean/
        assets/backgrounds/nature/
        assets/backgrounds/abstract/
    """
    import requests
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        print("=" * 60)
        print("PHOTO BACKGROUND SETUP")
        print("=" * 60)
        print()
        print("Option 1: Add PEXELS_API_KEY to .env (free at pexels.com/api)")
        print("          Then run: python3 src/backgrounds.py --download")
        print()
        print("Option 2: Manually place images in these folders:")
        for cat in ["earth", "city", "ocean", "nature", "abstract"]:
            cat_path = ASSETS_DIR / cat
            cat_path.mkdir(parents=True, exist_ok=True)
            print(f"  assets/backgrounds/{cat}/")
        print()
        print("Recommended image specs:")
        print("  - Resolution: 1080x1920 or larger (vertical preferred)")
        print("  - Format: JPG or PNG")
        print("  - 3-5 images per category for variety")
        print()
        print("Search terms for free stock photos (Pexels, Unsplash, Pixabay):")
        print("  earth: 'earth from space', 'planet night', 'earth satellite'")
        print("  city:  'city night aerial', 'neon street', 'times square'")
        print("  ocean: 'ocean sunset', 'tropical beach', 'sea waves aerial'")
        print("  nature:'mountain landscape', 'forest aerial', 'northern lights photo'")
        print("  abstract:'blue feather texture', 'neon abstract', 'colorful smoke'")
        print("=" * 60)
        return

    headers = {"Authorization": api_key}
    search_queries = {
        "earth": "earth from space night",
        "city": "city night aerial neon",
        "ocean": "ocean sunset tropical",
        "nature": "mountain forest landscape",
        "abstract": "abstract colorful texture",
    }

    for category, query in search_queries.items():
        cat_dir = ASSETS_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        existing = list(cat_dir.glob("*.jpg")) + list(cat_dir.glob("*.png"))
        if len(existing) >= 3:
            print(f"  {category}: already has {len(existing)} images, skipping")
            continue

        print(f"  Downloading {category} backgrounds...")
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params={"query": query, "per_page": 5, "orientation": "portrait"},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            for i, photo in enumerate(data.get("photos", [])[:5]):
                # Get portrait-sized image
                url = photo["src"].get("large2x", photo["src"]["large"])
                img_resp = requests.get(url, timeout=30)
                img_resp.raise_for_status()

                filename = cat_dir / f"{category}_{i+1}.jpg"
                with open(filename, 'wb') as f:
                    f.write(img_resp.content)
                size_mb = len(img_resp.content) / (1024 * 1024)
                print(f"    Downloaded: {filename.name} ({size_mb:.1f} MB)")

        except Exception as e:
            print(f"    Error downloading {category}: {e}")

    print("\nDone! Photo backgrounds are ready to use.")
    print("Use presets: photo_earth, photo_city, photo_ocean, photo_nature, photo_abstract")


# ============== UTILITY FUNCTIONS ==============

def list_presets() -> List[str]:
    """Return list of available preset names."""
    return list(BACKGROUND_PRESETS.keys())


def get_preset_info(preset_name: str) -> Dict:
    """Get info about a specific preset."""
    if preset_name not in BACKGROUND_PRESETS:
        return None
    preset = BACKGROUND_PRESETS[preset_name].copy()
    preset['name'] = preset_name
    return preset


def get_recommended_preset() -> str:
    """
    Return the recommended default preset based on TikTok best practices.
    Dynamic backgrounds with visible movement work best for engagement.
    """
    return "aurora_borealis"  # Northern lights - beautiful flowing colors, viral TikTok style


# ============== CLI FOR TESTING ==============

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Background Generator")
    parser.add_argument("--preset", default="bokeh_soft", help="Preset name")
    parser.add_argument("--list", action="store_true", help="List all presets")
    parser.add_argument("--download", action="store_true", help="Download sample photo backgrounds")
    parser.add_argument("--photos", action="store_true", help="Show photo background status")
    parser.add_argument("--time", type=float, default=0.0, help="Time for frame")
    parser.add_argument("-o", "--output", default="test_bg.png", help="Output file")

    args = parser.parse_args()

    if args.download:
        download_sample_backgrounds()
    elif args.photos:
        categories = get_available_photo_categories()
        print("Photo Background Status:")
        print("=" * 40)
        if categories:
            for cat, count in sorted(categories.items()):
                status = f"{count} images" if count > 0 else "EMPTY - add images!"
                print(f"  {cat}: {status}")
        else:
            print("  No categories found. Run --download or add images manually.")
        print(f"\nDirectory: {ASSETS_DIR}")
    elif args.list:
        print("Available presets:")
        for name in list_presets():
            info = get_preset_info(name)
            print(f"  {name}: {info['type']}")
        print(f"\nRecommended default: {get_recommended_preset()}")
        print(f"\nPhoto presets: photo_earth, photo_city, photo_ocean, photo_nature, photo_abstract")
    else:
        print(f"Generating frame with preset: {args.preset}")
        bg = BackgroundGenerator()
        frame = bg.render_from_preset(args.time, args.preset)

        img = Image.fromarray(frame, 'RGB')
        img.save(args.output)
        print(f"Saved to: {args.output}")

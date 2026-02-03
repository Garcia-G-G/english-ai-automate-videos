#!/usr/bin/env python3
"""
Background Generator for TikTok-style Videos
Supports multiple professional background styles.

Background Types:
- solid_vignette: Solid color with darker edges
- animated_gradient: Smooth color transitions over time
- bokeh_particles: Dark background with floating soft circles
- abstract_waves: Subtle animated wave patterns
- video_loop: Loop a background video
- ken_burns: Slow zoom/pan on static image
"""

import logging
import math
import numpy as np
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageFilter
import random

logger = logging.getLogger(__name__)

# Video dimensions
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30


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

    # === DYNAMIC / ENERGETIC (NEW) ===
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

    # === PARTICLE FLOW (NEW) ===
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

    # === CINEMATIC (NEW) ===
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

    # === AURORA / NORTHERN LIGHTS (NEW) ===
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
    }
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

        if bg_type == "solid_vignette":
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
                          movement_speed: str = "medium") -> np.ndarray:
        """
        Floating glowing orbs with MORE presence and movement than bokeh.
        More visible, more dynamic, more engaging.

        Args:
            t: Current time
            base_color: Background color
            orb_colors: Colors for orbs
            orb_count: Number of orbs (8-15 recommended)
            movement_speed: "slow", "medium", "fast"
        """
        if orb_colors is None:
            orb_colors = ["#00d4ff", "#ff6bb3", "#a855f7", "#22d3ee"]

        speed_mult = {"slow": 0.3, "medium": 0.6, "fast": 1.0}.get(movement_speed, 0.6)

        # Initialize orb data (cached)
        if not hasattr(self, '_glow_orbs') or len(self._glow_orbs) != orb_count:
            random.seed(123)
            self._glow_orbs = []
            for i in range(orb_count):
                self._glow_orbs.append({
                    'x': random.random(),
                    'y': random.random(),
                    'size': random.randint(80, 220),  # LARGER than bokeh
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
    from PIL import Image

    parser = argparse.ArgumentParser(description="Background Generator Test")
    parser.add_argument("--preset", default="bokeh_soft", help="Preset name")
    parser.add_argument("--list", action="store_true", help="List all presets")
    parser.add_argument("--time", type=float, default=0.0, help="Time for frame")
    parser.add_argument("-o", "--output", default="test_bg.png", help="Output file")

    args = parser.parse_args()

    if args.list:
        print("Available presets:")
        for name in list_presets():
            info = get_preset_info(name)
            print(f"  {name}: {info['type']}")
        print(f"\nRecommended default: {get_recommended_preset()}")
    else:
        print(f"Generating frame with preset: {args.preset}")
        bg = BackgroundGenerator()
        frame = bg.render_from_preset(args.time, args.preset)

        img = Image.fromarray(frame, 'RGB')
        img.save(args.output)
        print(f"Saved to: {args.output}")

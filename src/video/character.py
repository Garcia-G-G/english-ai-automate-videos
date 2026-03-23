"""Character renderer with rich animation system.

Renders an animated mascot character onto video frames with:
- Lip-sync mouth movement via word-level Whisper timestamps
- Natural breathing cycle (always active)
- Eye blink animation (periodic + random)
- Idle body sway (gentle pendulum when silent)
- Talking bounce with squash/stretch (Disney-style)
- Head bob synced to speech rhythm
- Excitement reactions (sparkle burst on key moments)
- Smooth state machine transitions between idle/talking/reacting
"""

import logging
import math
import os
import random
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

# Config file path — resolve via __file__ so it works regardless of cwd
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config.yaml",
)

# Project root for asset resolution
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Single sprite mode: use one consistent image and animate programmatically
# DALL-E 3 can't maintain character consistency across generations,
# so switching sprites looks jarring.  Instead we use one image and
# add rich programmatic animations.
MOUTH_STATES = ["closed"]

# Class-level sprite cache: {(character_name, size): {mouth_state: PIL.Image}}
_sprite_cache: Dict[Tuple[str, int], Dict[str, Image.Image]] = {}


def _load_config() -> dict:
    """Load character configuration from config.yaml."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


# ── Deterministic pseudo-random for blink timing ──────────────────
# We pre-generate blink times so they're consistent across frames
_BLINK_SEED = 42
_blink_times: List[float] = []


def _generate_blink_times(duration: float = 300.0) -> List[float]:
    """Generate natural blink times: every 2-6 seconds with slight variation."""
    global _blink_times
    if _blink_times:
        return _blink_times

    rng = random.Random(_BLINK_SEED)
    t = rng.uniform(1.0, 3.0)  # First blink after 1-3s
    times = []
    while t < duration:
        times.append(t)
        # Natural blink interval: 2-5 seconds with occasional quick double-blinks
        if rng.random() < 0.15:  # 15% chance of double-blink
            t += rng.uniform(0.25, 0.4)
            times.append(t)
        t += rng.uniform(2.0, 5.0)

    _blink_times = times
    return times


class CharacterRenderer:
    """Renders an animated character with rich, Disney-inspired animations.

    Uses a single sprite with layered programmatic effects:
    1. Breathing (always) — gentle vertical sine oscillation
    2. Idle sway (when silent) — slow pendulum body rotation
    3. Eye blinks (periodic) — squash eyelid overlay
    4. Talking bounce (when speaking) — scale pulse + vertical bounce
    5. Squash/stretch (when speaking) — volume-preserving deformation
    6. Head bob (when speaking) — rhythmic tilt synced to words
    7. Tail wag (when speaking) — implied via slight horizontal oscillation
    8. Excitement burst — scale pop + sparkle particles on key moments
    """

    # ── Animation Parameters ──────────────────────────────────────
    # Values tuned for visibility on phone screens (TikTok vertical)
    # Oscillation frequency for speech animation
    OSCILLATION_HZ = 3.0
    # Anticipation: mouth animation starts before word audio
    ANTICIPATION_SEC = 0.05

    # Breathing (always active — keeps character alive even in silence)
    BREATHING_HZ = 0.35         # cycles/sec — slow, natural
    BREATHING_AMPLITUDE = 6     # pixels vertical (visible on phone)

    # Idle sway (when not speaking — gentle "alive" movement)
    IDLE_SWAY_HZ = 0.2          # very slow pendulum
    IDLE_SWAY_ANGLE = 3.5       # ±3.5 degrees rotation (visible tilt)
    IDLE_SWAY_X = 5             # ±5 pixels horizontal drift

    # Eye blink (subtle squash of eye region)
    BLINK_DURATION = 0.15       # seconds for full close+open
    BLINK_SQUASH = 0.35         # how much the "eyelid" closes

    # Talking animations (energetic, bouncy — Duolingo-style)
    TALK_SCALE_MAX = 0.12       # up to 12% bigger when speaking
    TALK_BOUNCE_Y = 16          # pixels upward bounce at peak
    TALK_TILT_ANGLE = 5.0       # ±5° tilt when speaking
    TALK_TILT_HZ = 1.8          # tilt oscillation speed
    TALK_SQUASH_AMOUNT = 0.06   # 6% squash/stretch (visible deformation)

    # Head bob (vertical micro-bounce synced to syllables)
    HEAD_BOB_HZ = 4.0           # faster than tilt for syllable feel
    HEAD_BOB_AMPLITUDE = 5      # pixels (visible on phone)

    # Excitement reaction (answer reveal — big, joyful)
    EXCITEMENT_DURATION = 1.0   # how long excitement lasts (longer for impact)
    EXCITEMENT_SCALE = 1.25     # pop to 125% size (dramatic)
    EXCITEMENT_BOUNCE = 30      # pixels upward jump (big!)

    # Entrance animation (first appearance)
    ENTRANCE_DURATION = 0.6     # seconds for bounce-in
    ENTRANCE_DELAY = 0.2        # delay before character appears

    def __init__(
        self,
        character_name: str = "fox",
        position_x: int = 50,
        position_y: int = 1450,
        size: int = 350,
        opacity: float = 0.95,
    ):
        self.character_name = character_name
        self.position_x = position_x
        self.position_y = position_y
        self.size = size
        self.opacity = opacity

        # Animation state
        self._excitement_start: Optional[float] = None
        self._last_speaking_end: float = 0.0

        # Load sprites (uses class-level cache)
        self.sprites = self._load_sprites()
        self.available = len(self.sprites) > 0

        # Pre-generate blink schedule
        _generate_blink_times()

        if self.available:
            logger.info(
                "Character '%s' loaded: %d sprites, size=%dpx, animations=rich",
                character_name,
                len(self.sprites),
                size,
            )
        else:
            logger.warning(
                "Character '%s' has no sprites — rendering disabled",
                character_name,
            )

    def _load_sprites(self) -> Dict[str, Image.Image]:
        """Load and resize character sprites, using class-level cache."""
        cache_key = (self.character_name, self.size)
        if cache_key in _sprite_cache:
            return _sprite_cache[cache_key]

        sprites_dir = os.path.join(
            PROJECT_ROOT, "assets", "characters", self.character_name
        )

        if not os.path.isdir(sprites_dir):
            logger.debug("Sprites directory not found: %s", sprites_dir)
            _sprite_cache[cache_key] = {}
            return {}

        # Expected filenames for each mouth state
        mouth_files = {
            "closed": "mouth_closed.png",
            "slightly_open": "mouth_slightly_open.png",
            "open": "mouth_open.png",
            "wide": "mouth_wide.png",
        }

        loaded: Dict[str, Image.Image] = {}

        for state, filename in mouth_files.items():
            path = os.path.join(sprites_dir, filename)
            if not os.path.isfile(path):
                logger.debug("Missing sprite: %s", path)
                continue

            try:
                img = Image.open(path).convert("RGBA")

                # Remove white/light background — make it transparent
                img = self._remove_background(img)

                # Resize preserving aspect ratio, fitting within size x size
                orig_w, orig_h = img.size
                scale = self.size / max(orig_w, orig_h)
                new_w = int(orig_w * scale)
                new_h = int(orig_h * scale)
                img = img.resize((new_w, new_h), Image.LANCZOS)

                loaded[state] = img
            except Exception as e:
                logger.warning("Failed to load sprite %s: %s", path, e)

        _sprite_cache[cache_key] = loaded
        return loaded

    @staticmethod
    def _remove_background(img: Image.Image, threshold: int = 220) -> Image.Image:
        """Remove background by sampling corner pixels to detect bg color.

        Uses multi-pass approach:
        1. Color-distance from detected bg color (corner sampling)
        2. High-luminance removal (catches gradients from DALL-E)
        3. Edge erosion to kill halo fringing
        4. Bottom shadow cleanup
        """

        data = np.array(img, dtype=np.float32)
        h, w = data.shape[:2]
        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]

        # Sample corner regions (15x15 for more robust bg detection)
        corner_size = 15
        corners = [
            data[:corner_size, :corner_size, :3],
            data[:corner_size, -corner_size:, :3],
            data[-corner_size:, :corner_size, :3],
            data[-corner_size:, -corner_size:, :3],
        ]
        bg_color = np.mean(np.concatenate([c.reshape(-1, 3) for c in corners], axis=0), axis=0)

        dist = np.sqrt(
            (r - bg_color[0]) ** 2 +
            (g - bg_color[1]) ** 2 +
            (b - bg_color[2]) ** 2
        )

        # Tighter thresholds for cleaner edges
        close_threshold = 35.0   # definitely background
        far_threshold = 55.0     # tighter feather zone

        mask = np.ones_like(dist)
        mask[dist < close_threshold] = 0.0
        feather_zone = (dist >= close_threshold) & (dist < far_threshold)
        mask[feather_zone] = (dist[feather_zone] - close_threshold) / (far_threshold - close_threshold)

        # Luminance + saturation analysis
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        max_rgb = np.maximum(np.maximum(r, g), b)
        min_rgb = np.minimum(np.minimum(r, g), b)
        saturation = np.zeros_like(luminance)
        nonzero = max_rgb > 0
        saturation[nonzero] = (max_rgb[nonzero] - min_rgb[nonzero]) / max_rgb[nonzero]

        # Only remove bright pixels that are ALSO desaturated (background)
        # Bright saturated pixels are likely character features (white fur, highlights)
        bright_mask = np.ones_like(luminance)

        # Very bright AND desaturated = definitely background
        desat_bg = (luminance > 200) & (saturation < 0.12)
        bright_mask[desat_bg] = 0.0

        # Moderately bright and somewhat desaturated with feather
        desat_feather = (luminance > 190) & (saturation < 0.18) & ~desat_bg
        bright_mask[desat_feather] = np.clip(
            (saturation[desat_feather] - 0.08) / 0.10, 0.0, 1.0
        )

        # Pure white (>240 lum, <0.05 sat) is always background
        pure_white = (luminance > 240) & (saturation < 0.05)
        bright_mask[pure_white] = 0.0

        final_mask = np.minimum(mask, bright_mask)

        # Bottom shadow cleanup: aggressively remove light pixels in bottom 8%
        bottom_rows = int(h * 0.08)
        if bottom_rows > 0:
            bottom_lum = luminance[-bottom_rows:, :]
            # In bottom zone, remove anything that looks like a ground shadow
            shadow_mask = np.ones_like(bottom_lum)
            shadow_mask[bottom_lum > 180] = 0.0
            shadow_feather = (bottom_lum > 160) & (bottom_lum <= 180)
            shadow_mask[shadow_feather] = (180 - bottom_lum[shadow_feather]) / 20.0
            final_mask[-bottom_rows:, :] = np.minimum(final_mask[-bottom_rows:, :], shadow_mask)

        # Apply mask
        data[:, :, 3] = a * final_mask

        # Erode alpha edges to kill remaining halo (1px erosion)
        alpha_channel = data[:, :, 3]
        # Simple erosion: each pixel takes the min of its 3x3 neighborhood
        padded = np.pad(alpha_channel, 1, mode='constant', constant_values=0)
        eroded = padded[1:-1, 1:-1].copy()
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dy == 0 and dx == 0:
                    continue
                eroded = np.minimum(eroded, padded[1+dy:h+1+dy, 1+dx:w+1+dx])
        # Blend: keep original where fully opaque, use eroded at edges
        edge_zone = (alpha_channel > 0) & (alpha_channel < 250)
        data[:, :, 3][edge_zone] = eroded[edge_zone]

        return Image.fromarray(data.astype(np.uint8))

    # ── Speaking detection ────────────────────────────────────────

    def _is_speaking(self, t: float, word_timestamps: List[Dict]) -> float:
        """Return 0.0–1.0 speaking intensity at time t.

        Uses a sine wave during active words for rhythmic pulse.
        """
        if not word_timestamps:
            return 0.0

        for word in word_timestamps:
            w_start = word.get("start", 0) - self.ANTICIPATION_SEC
            w_end = word.get("end", 0)
            if w_start <= t <= w_end:
                elapsed = t - w_start
                pulse = abs(math.sin(2 * math.pi * self.OSCILLATION_HZ * elapsed))
                return pulse
        return 0.0

    def _is_in_speech_block(self, t: float, word_timestamps: List[Dict]) -> bool:
        """Check if we're broadly within an active speech section (not just one word)."""
        if not word_timestamps:
            return False
        # Consider "in speech" if within 0.3s of any word
        for word in word_timestamps:
            w_start = word.get("start", 0) - 0.3
            w_end = word.get("end", 0) + 0.3
            if w_start <= t <= w_end:
                return True
        return False

    # ── Eye blink ─────────────────────────────────────────────────

    def _get_blink_state(self, t: float) -> float:
        """Return 0.0 (eyes open) to 1.0 (eyes fully closed) for blink animation."""
        blink_times = _generate_blink_times()

        for bt in blink_times:
            if bt <= t <= bt + self.BLINK_DURATION:
                elapsed = t - bt
                progress = elapsed / self.BLINK_DURATION
                # Quick close (first 40%), slower open (last 60%)
                if progress < 0.4:
                    return progress / 0.4  # 0→1 close
                else:
                    return 1.0 - (progress - 0.4) / 0.6  # 1→0 open
            elif bt > t + 0.5:
                break  # No point checking future blinks

        return 0.0

    def _apply_blink(self, sprite: Image.Image, blink_amount: float) -> Image.Image:
        """Apply eye blink by vertically squashing the eye region.

        Instead of drawing fake eyelids (which looks bad), we squash the
        eye region vertically toward its center. This creates a natural
        "squinting" effect that works with any character design.
        """
        if blink_amount < 0.05:
            return sprite

        w, h = sprite.size

        # Eye region: upper 20-45% of character height
        eye_top = int(h * 0.20)
        eye_bottom = int(h * 0.45)
        eye_height = eye_bottom - eye_top
        eye_center = eye_top + eye_height // 2

        # Squash factor: 1.0 = normal, 0.0 = fully closed
        squash = 1.0 - (blink_amount * 0.7)  # don't fully close, max 70% squash

        if squash >= 0.95:
            return sprite

        result = sprite.copy()

        # Extract eye region
        eye_strip = sprite.crop((0, eye_top, w, eye_bottom))

        # Squash it vertically
        new_eye_h = max(2, int(eye_height * squash))
        squashed = eye_strip.resize((w, new_eye_h), Image.LANCZOS)

        # Calculate where to paste (centered on eye region)
        paste_y = eye_center - new_eye_h // 2

        # Fill original eye region with the pixels just above (forehead/fur)
        # This creates the "eyelid" naturally from surrounding pixels
        fur_strip = sprite.crop((0, max(0, eye_top - 3), w, max(1, eye_top)))
        for y in range(eye_top, eye_bottom):
            result.paste(fur_strip, (0, y))

        # Paste squashed eye region back
        result.paste(squashed, (0, paste_y), squashed)

        return result

    # ── Excitement/reaction ───────────────────────────────────────

    def trigger_excitement(self, t: float):
        """Trigger an excitement reaction at time t."""
        self._excitement_start = t

    def _get_excitement_state(self, t: float) -> float:
        """Return 0.0–1.0 excitement intensity."""
        if self._excitement_start is None:
            return 0.0
        elapsed = t - self._excitement_start
        if elapsed < 0 or elapsed > self.EXCITEMENT_DURATION:
            return 0.0
        # Quick burst then decay
        progress = elapsed / self.EXCITEMENT_DURATION
        if progress < 0.15:
            return progress / 0.15  # fast ramp up
        else:
            return 1.0 - ((progress - 0.15) / 0.85) ** 0.5  # smooth decay

    def _draw_sparkle_particles(
        self, frame: Image.Image, cx: int, cy: int, t: float
    ):
        """Draw sparkle/star particles around the character during excitement."""
        excitement = self._get_excitement_state(t)
        if excitement < 0.05:
            return

        draw = ImageDraw.Draw(frame)
        elapsed = t - (self._excitement_start or t)
        num_particles = 8

        for i in range(num_particles):
            angle = (i / num_particles) * 2 * math.pi + elapsed * 2.0
            distance = int(60 + 80 * excitement * (0.5 + 0.5 * math.sin(elapsed * 5 + i)))

            px = cx + int(math.cos(angle) * distance)
            py = cy + int(math.sin(angle) * distance)

            alpha = int(255 * excitement * (0.5 + 0.5 * math.sin(elapsed * 8 + i * 1.5)))
            alpha = max(0, min(255, alpha))

            if alpha < 10:
                continue

            # Alternating star shapes and circles
            if i % 2 == 0:
                # 4-point star
                size = int(8 * excitement)
                if size > 1:
                    draw.polygon([
                        (px, py - size), (px + size // 3, py - size // 3),
                        (px + size, py), (px + size // 3, py + size // 3),
                        (px, py + size), (px - size // 3, py + size // 3),
                        (px - size, py), (px - size // 3, py - size // 3),
                    ], fill=(255, 255, 200, alpha))
            else:
                # Small glowing circle
                r = int(5 * excitement)
                if r > 0:
                    draw.ellipse(
                        [px - r, py - r, px + r, py + r],
                        fill=(255, 230, 100, alpha),
                    )

    # ── Main render ───────────────────────────────────────────────

    def render(
        self,
        frame: Image.Image,
        t: float,
        word_timestamps: Optional[List[Dict]] = None,
    ) -> Image.Image:
        """Render the character onto frame with full animation stack.

        Animation layers (applied in order):
        1. Get base sprite
        2. Apply eye blink overlay
        3. Calculate speaking intensity
        4. Apply breathing (always)
        5. Apply idle sway OR talking animations
        6. Apply squash/stretch when talking
        7. Apply excitement reaction if triggered
        8. Composite onto frame with opacity
        9. Draw sparkle particles on top

        Args:
            frame: RGBA PIL Image to render onto.
            t: Current time in seconds.
            word_timestamps: Word-level timestamps for lip sync.

        Returns:
            The frame (same object, modified in place).
        """
        if not self.available:
            return frame

        # ── 0. Entrance animation — bounce in from below ──
        if t < self.ENTRANCE_DELAY:
            return frame  # not visible yet

        entrance_progress = 1.0
        entrance_scale = 1.0
        entrance_y_offset = 0
        if t < self.ENTRANCE_DELAY + self.ENTRANCE_DURATION:
            elapsed = t - self.ENTRANCE_DELAY
            progress = elapsed / self.ENTRANCE_DURATION
            # Elastic ease-out for bouncy entrance
            if progress < 1.0:
                p = 0.3
                entrance_progress = pow(2, -10 * progress) * math.sin(
                    (progress - p / 4) * (2 * math.pi) / p
                ) + 1.0
                entrance_progress = max(0.0, min(1.2, entrance_progress))
            # Slide up from below + scale pop
            entrance_y_offset = int(200 * (1.0 - entrance_progress))
            entrance_scale = 0.3 + 0.7 * min(1.0, entrance_progress)

        # Get base sprite
        sprite = self.sprites.get("closed")
        if sprite is None:
            if self.sprites:
                sprite = next(iter(self.sprites.values()))
            else:
                return frame

        # ── 1. Eye blink ──
        blink = self._get_blink_state(t)
        if blink > 0.05:
            sprite = self._apply_blink(sprite, blink)

        # ── 2. Speaking intensity ──
        speaking = self._is_speaking(t, word_timestamps or [])
        in_speech = self._is_in_speech_block(t, word_timestamps or [])

        # Track speech end for smooth idle transition
        if in_speech:
            self._last_speaking_end = t

        # Smooth transition from talking to idle (0.5s blend)
        idle_blend = min(1.0, max(0.0, (t - self._last_speaking_end) / 0.5))

        # ── 3. Breathing (always active) ──
        breathing_offset = int(
            self.BREATHING_AMPLITUDE
            * math.sin(2 * math.pi * self.BREATHING_HZ * t)
        )

        # ── 4. Idle sway (fades in when not speaking) ──
        idle_angle = 0.0
        idle_x = 0
        if idle_blend > 0.1:
            idle_angle = (
                self.IDLE_SWAY_ANGLE
                * math.sin(2 * math.pi * self.IDLE_SWAY_HZ * t)
                * idle_blend
            )
            idle_x = int(
                self.IDLE_SWAY_X
                * math.sin(2 * math.pi * self.IDLE_SWAY_HZ * t + 0.5)
                * idle_blend
            )

        # ── 5. Talking animations (fade out when silent) ──
        talk_blend = 1.0 - idle_blend  # inverse of idle
        talk_scale = 1.0
        talk_bounce_y = 0
        talk_tilt = 0.0
        head_bob_y = 0
        squash_x = 1.0
        squash_y = 1.0

        if speaking > 0.01 or talk_blend > 0.05:
            effective_speaking = speaking * max(talk_blend, 0.3 if speaking > 0 else 0)

            # Scale pulse
            talk_scale = 1.0 + self.TALK_SCALE_MAX * effective_speaking

            # Vertical bounce
            talk_bounce_y = int(-self.TALK_BOUNCE_Y * effective_speaking)

            # Head tilt (slower sinusoid for personality)
            talk_tilt = (
                self.TALK_TILT_ANGLE
                * math.sin(2 * math.pi * self.TALK_TILT_HZ * t)
                * effective_speaking
            )

            # Head bob (faster, smaller — syllable rhythm)
            head_bob_y = int(
                self.HEAD_BOB_AMPLITUDE
                * abs(math.sin(2 * math.pi * self.HEAD_BOB_HZ * t))
                * effective_speaking
            )

            # Squash/stretch — volume-preserving deformation
            squash_phase = math.sin(2 * math.pi * self.OSCILLATION_HZ * t)
            squash_amount = self.TALK_SQUASH_AMOUNT * effective_speaking
            squash_y = 1.0 - squash_amount * abs(squash_phase)
            squash_x = 1.0 / max(0.85, squash_y)  # preserve volume

        # ── 6. Excitement reaction ──
        excitement = self._get_excitement_state(t)
        excite_scale = 1.0
        excite_bounce_y = 0

        if excitement > 0.01:
            # Quick pop then settle
            if excitement > 0.5:
                excite_scale = 1.0 + (self.EXCITEMENT_SCALE - 1.0) * excitement
            else:
                excite_scale = 1.0 + (self.EXCITEMENT_SCALE - 1.0) * excitement * 0.5
            excite_bounce_y = int(-self.EXCITEMENT_BOUNCE * excitement)

        # ── Combine all transforms (including entrance) ──
        total_scale_x = talk_scale * squash_x * excite_scale * entrance_scale
        total_scale_y = talk_scale * squash_y * excite_scale * entrance_scale
        total_angle = idle_angle + talk_tilt
        total_y_offset = (
            breathing_offset + talk_bounce_y + head_bob_y
            + excite_bounce_y + entrance_y_offset
        )
        total_x_offset = idle_x

        # ── Apply transforms to sprite ──
        orig_w, orig_h = sprite.size
        new_w = max(1, int(orig_w * total_scale_x))
        new_h = max(1, int(orig_h * total_scale_y))

        working = sprite
        needs_transform = (
            abs(total_scale_x - 1.0) > 0.005
            or abs(total_scale_y - 1.0) > 0.005
            or abs(total_angle) > 0.3
        )

        if needs_transform:
            working = sprite.resize((new_w, new_h), Image.LANCZOS)
            if abs(total_angle) > 0.3:
                working = working.rotate(
                    total_angle,
                    resample=Image.BICUBIC,
                    expand=False,
                    center=(new_w // 2, new_h // 2),
                )

        # ── Calculate paste position (anchor at bottom-center) ──
        scale_offset_x = (new_w - orig_w) // 2
        scale_offset_y = (new_h - orig_h)

        paste_x = self.position_x - scale_offset_x + total_x_offset
        paste_y = self.position_y - scale_offset_y + total_y_offset

        # ── Apply opacity ──
        if self.opacity < 1.0:
            sprite_copy = working.copy()
            r, g, b, a = sprite_copy.split()
            a = a.point(lambda x: int(x * self.opacity))
            sprite_copy = Image.merge("RGBA", (r, g, b, a))
        else:
            sprite_copy = working

        # ── Bounds check ──
        frame_w, frame_h = frame.size
        sprite_w, sprite_h = sprite_copy.size
        if paste_x + sprite_w <= 0 or paste_x >= frame_w:
            return frame
        if paste_y + sprite_h <= 0 or paste_y >= frame_h:
            return frame

        # ── Draw ground shadow (small ellipse, rendered locally) ──
        shadow_cx = paste_x + sprite_w // 2
        shadow_cy = paste_y + sprite_h - 3
        shadow_rx = int(sprite_w * 0.32)
        shadow_ry = max(3, int(sprite_h * 0.03))
        shadow_alpha = int(50 * self.opacity * min(1.0, entrance_progress))

        if shadow_alpha > 5:
            # Render shadow into a small local buffer for efficiency
            sw = shadow_rx * 2 + 4
            sh = shadow_ry * 2 + 4
            shadow_buf = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow_buf)
            sd.ellipse([2, 2, sw - 2, sh - 2], fill=(0, 0, 0, shadow_alpha))
            sx = shadow_cx - shadow_rx - 2
            sy = shadow_cy - shadow_ry - 2
            # Clamp to frame bounds
            if 0 <= sx < frame.size[0] and 0 <= sy < frame.size[1]:
                frame.paste(shadow_buf, (sx, sy), shadow_buf)

        # ── White outline glow (makes character pop against any bg) ──
        if entrance_progress > 0.5:
            glow_alpha_base = int(35 * self.opacity * min(1.0, entrance_progress))
            # Create glow by drawing the sprite's alpha dilated
            alpha_ch = sprite_copy.split()[3]
            # Expand alpha outward by 2px using max filter
            glow_mask = alpha_ch.filter(ImageFilter.MaxFilter(5))
            # Subtract original to get just the outline
            glow_arr = np.array(glow_mask, dtype=np.int16) - np.array(alpha_ch, dtype=np.int16)
            glow_arr = np.clip(glow_arr, 0, 255).astype(np.uint8)
            # Scale alpha
            glow_arr = (glow_arr.astype(np.float32) * glow_alpha_base / 255).astype(np.uint8)
            # Create white glow image
            glow_img = Image.new('RGBA', sprite_copy.size, (255, 255, 255, 0))
            glow_img.putalpha(Image.fromarray(glow_arr))
            frame.paste(glow_img, (paste_x, paste_y), glow_img)

        # ── Composite character ──
        frame.paste(sprite_copy, (paste_x, paste_y), sprite_copy)

        # ── Draw sparkle particles on top (excitement) ──
        if excitement > 0.01:
            char_cx = paste_x + sprite_w // 2
            char_cy = paste_y + sprite_h // 3  # particles around upper body
            self._draw_sparkle_particles(frame, char_cx, char_cy, t)

        return frame


# ── Module-level singleton ───────────────────────────────────────

_renderer: Optional[CharacterRenderer] = None


def get_character_renderer() -> Optional[CharacterRenderer]:
    """Get or create the character renderer singleton.

    Returns None if the character system is disabled in config or if
    sprite assets are missing.
    """
    global _renderer

    if _renderer is not None:
        return _renderer if _renderer.available else None

    config = _load_config()
    char_config = config.get("character", {})

    if not char_config.get("enabled", False):
        logger.debug("Character renderer disabled in config")
        return None

    _renderer = CharacterRenderer(
        character_name=char_config.get("name", "fox"),
        position_x=char_config.get("position_x", 50),
        position_y=char_config.get("position_y", 1450),
        size=char_config.get("size", 350),
        opacity=char_config.get("opacity", 0.95),
    )

    if not _renderer.available:
        logger.info("Character renderer created but no sprites found — disabled")
        return None

    return _renderer

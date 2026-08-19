#!/usr/bin/env python3
"""One background image per video, generated from that video's own topic.

    from topic_background import generate_for_topic
    result = generate_for_topic("break the ice", "idioms", "fill_blank")

Replaces picking from a catalogue. The catalogue is now the FALLBACK: if the
generated image fails the contrast gate, the video takes a palette instead and
the failure is logged with the topic, so a bad image costs a plain background
rather than an unreadable video.

WHY THE PROMPT IS SHAPED THE WAY IT IS

docs/BACKGROUND_CATEGORIES_PROPOSED.md measured the previous photo set and
found six of eleven presets at or under 3.7:1 behind the headline, against a
3.0 floor for large text. The cause was compositional, not technical: a sunset
or a cloudscape puts its brightest region across the middle of the frame,
which is exactly where the card sits. So every prompt here pins the exposure —
bright top and bottom thirds, deep shadow across the middle band — as an
instruction rather than a hope, and then the gate checks it anyway.

The gate is the safety story. An image generator with no gate recreates
March 2026.
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
BACKGROUND_DIR = ROOT / "output" / "backgrounds"

#: gpt-image-2 is the cheapest of the family at this size and does not need
#: transparency, which is the one thing it cannot do.
IMAGE_MODEL = "gpt-image-2"
IMAGE_SIZE = "1024x1536"
IMAGE_QUALITY = "medium"

#: The exposure instruction, identical on every prompt. This is the part that
#: keeps text readable, so it is not paraphrased per topic.
EXPOSURE = (
    "The centre of the frame is in deep shadow across a wide horizontal band, "
    "with brightness only in the top third and the bottom third. "
    "Cinematic photography, portrait orientation, shallow depth of field, "
    "softly out of focus, rich dark tones. "
    "No text, no letters, no signage, no watermark, no legible faces, no people "
    "in the centre of the frame."
)

#: Scene stems per content category. The topic supplies the subject; these
#: supply a setting that can plausibly hold one without becoming an
#: illustration of the phrase, which is what produces literal-minded images.
CATEGORY_SCENES = {
    "business": "a dark modern office after hours, a desk and a laptop lit by one lamp",
    "travel": "a dimly lit airport terminal at night, seats and a window onto the apron",
    "social": "a low-lit bar table with glasses and a jacket over the chair",
    "daily_life": "a kitchen counter at night lit by one warm bulb",
    "idioms": "a worn wooden table with objects arranged on it in low light",
    "phrasal_verbs": "a cluttered desk in a dark room, one lamp raking across it",
    "false_friends": "two objects side by side on a shadowed surface, one lit",
    "common_mistakes": "an open notebook and a pen on a dark desk, single light source",
    "kids_animals": "a quiet room at dusk with soft toys on a shelf",
    "food": "a dark table set with plates and linen, narrow window light",
    "technology": "a dark room with a screen glow falling across a desk",
}
DEFAULT_SCENE = "a quiet interior at night, one warm light source, most of the frame in shadow"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "background").lower()).strip("_") or "background"


def build_prompt(topic: str, category: str = None) -> str:
    """The prompt for one video's background."""
    scene = CATEGORY_SCENES.get((category or "").lower(), DEFAULT_SCENE)
    return (
        f"{scene.capitalize()}, evoking the idea of \"{topic}\" without "
        f"illustrating it literally and without spelling anything out. "
        f"{EXPOSURE}"
    )


def generate_for_topic(topic: str, category: str = None,
                       video_type: str = None,
                       out_dir: Path = None) -> Optional[Dict]:
    """Generate one background. Returns a dict, or None if generation failed.

    Does NOT gate the result — see topic_background_gate.accept(), which the
    pipeline calls next. Kept separate so the gate can be tested without
    spending, and so a gate change does not touch the generation path.
    """
    from image_gen import generate_image, get_client, price_per_image

    client = get_client()
    if client is None:
        logger.warning("no OpenAI client — cannot generate a background for %r", topic)
        return None

    out_dir = Path(out_dir) if out_dir else BACKGROUND_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_slug(topic)}.png"

    prompt = build_prompt(topic, category)
    logger.info("background: generating for %r (%s)", topic, category)

    result = generate_image(
        client, prompt, path,
        size=IMAGE_SIZE, quality=IMAGE_QUALITY, model=IMAGE_MODEL,
        label=f"background_{_slug(topic)}",
    )
    if result is None:
        logger.warning("background generation FAILED for %r", topic)
        return None

    return {
        "path": str(result),
        "topic": topic,
        "category": category,
        "video_type": video_type,
        "prompt": prompt,
        "model": IMAGE_MODEL,
        "cost_usd": price_per_image(IMAGE_QUALITY, IMAGE_SIZE, IMAGE_MODEL),
    }


def fallback_preset(enabled: list = None) -> Optional[str]:
    """A palette from the culled rotation, for when the image is refused.

    Reads the rotation from config rather than holding its own list, so the
    cull lands in one place and this follows it.
    """
    try:
        from backgrounds import BACKGROUND_PRESETS, resolve_enabled
        from video.backgrounds import _load_video_config  # noqa: F401
    except Exception:                                       # noqa: BLE001
        from backgrounds import BACKGROUND_PRESETS, resolve_enabled

    names = enabled
    if names is None:
        try:
            import yaml
            cfg = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
            names = (cfg.get("video") or {}).get("enabled_backgrounds") or []
        except Exception:                                   # noqa: BLE001
            names = []
    pool = [n for n in resolve_enabled(names) if n in BACKGROUND_PRESETS]
    if not pool:
        return None
    return random.SystemRandom().choice(pool)

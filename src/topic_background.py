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

import hashlib
import logging
import random
import re
from pathlib import Path
from typing import Dict, Optional

import sys as _sys
_SRC = str(Path(__file__).resolve().parent)
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)
from config.layout import VIDEO_HEIGHT           # noqa: E402
from text_contrast import HEADLINE_BOTTOM, HEADLINE_TOP  # noqa: E402

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
BACKGROUND_DIR = ROOT / "output" / "backgrounds"

#: gpt-image-2 is the cheapest of the family at this size and does not need
#: transparency, which is the one thing it cannot do.
IMAGE_MODEL = "gpt-image-2"
IMAGE_SIZE = "1024x1536"
IMAGE_QUALITY = "medium"

#: RENDER TREATMENT for a generated background, shared with the gate so the
#: gate measures what actually ships.
#:
#: photo_kenburns defaults to overlay_opacity 0.35 and blur 2, tuned for the
#: bright DALL-E photo set it was built for — knocking those down was the only
#: way to get text over them. These images arrive with the dark band already
#: composed in, so another 35% of darkening turned them black: the first batch
#: rendered six videos whose backgrounds were invisible, and the contrast gate
#: waved every one through at ~14.7:1 because black is extremely readable.
#:
#: The exposure is pinned in the prompt now, so the renderer does not need to
#: pin it again.
RENDER_OVERLAY_OPACITY = 0.10
RENDER_BLUR_RADIUS = 1

#: NO ZOOM for a generated background, and this is the important one.
#:
#: The prompt puts the picture in the top and bottom thirds and shadow across
#: the middle. Ken Burns zoom crops INWARD from the centre, so any zoom above
#: 1.0 throws away exactly the parts that carry the image and keeps the part
#: that is deliberately empty. The first batch rendered six videos that were
#: black from top to bottom for this reason, while the contrast gate passed
#: every one at ~14.7:1 — black reads beautifully.
#:
#: At 1.0 the crop is the largest 9:16 rectangle inside the 2:3 source: full
#: height, about 160px of spare width. kenburns_crop then pans within that
#: spare width and cannot pan vertically at all, because there is no vertical
#: slack to pan into. Horizontal drift over an intact composition, which is
#: what this image was composed for.
RENDER_ZOOM_RANGE = (1.0, 1.0)

#: The readability band, composited in code by apply_readability_scrim.
#:
#: SCRIM_FEATHER is deliberately larger than the band's own half-height: the
#: failure mode here is a visible seam, and a seam is worse than the dark
#: images this replaces. Falloff is a raised cosine, so the derivative is zero
#: at both ends and there is no edge for the eye to catch.
SCRIM_FEATHER = 300
SCRIM_STRENGTH = 0.62

#: The composition instruction, identical on every prompt.
#:
#: It used to ask for "deep shadow across the middle band" and "rich dark
#: tones", and every scene stem asked for night or low light on top of that.
#: The reason was the contrast gate — and the gate REWARDS darkness, because
#: a darker background raises the ratio without limit. v_vs_b_sounds scored
#: 14.882:1 against a 4.5 floor by being barely there. Nothing measured
#: vividness, so there was never any pressure the other way, and eleven of
#: fourteen images came out as the same dark room.
#:
#: Readability is now built in code — see apply_readability_scrim — so the
#: generator is asked for a picture and not for a shadow. What it is still
#: asked for is an UNCLUTTERED middle band, which is a composition
#: instruction: keep the busy detail out of the centre, at any brightness.
COMPOSITION = (
    "Vivid, colourful and well lit, rich saturated colour. "
    "The middle band across the centre of the frame is calm and uncluttered — "
    "keep detail, subjects and busy texture in the upper and lower thirds and "
    "leave the centre simple and open. "
    "Portrait orientation, photographic, shallow depth of field, "
    "softly out of focus. "
    "No text, no letters, no signage, no watermark, no legible faces, no people "
    "in the centre of the frame."
)

#: Scenes per category, built against content/topics/*.json rather than from
#: memory. The previous dict had 11 keys for 20 real categories, so 11 fell
#: through to a single DEFAULT stem — which is why eleven of fourteen images
#: were the same room. It also carried two orphan keys, "daily_life" and
#: "food", that no category ever used; the real ones are
#: everyday_expressions and food_restaurant.
#:
#: Several per category, because one scene per category means two videos in
#: the same category share a frame, and `social` alone appears six times in
#: the job history.
CATEGORY_SCENES = {
    "business": [
        "a bright modern office with glass walls and a city view",
        "a sunlit meeting room with a whiteboard and coloured markers",
        "a clean desk with an open laptop, a plant and a coffee cup",
        "a busy co-working space with warm wood and yellow chairs",
    ],
    "work_office": [
        "a tidy desk with stacked notebooks and a mug of pens",
        "an office corridor with tall windows and green plants",
        "a desk by a window with sunlight across the keyboard",
        "a bright break room with mugs on an open shelf",
    ],
    "travel": [
        "an airport window with a plane on the apron under a blue sky",
        "a sunlit train platform with a suitcase and a departure board",
        "a harbour with white boats and turquoise water",
        "a market street with awnings and hanging lanterns",
    ],
    "social": [
        "a rooftop terrace with string lights and potted plants",
        "a cafe table with two cups and a slice of cake",
        "a park bench under blossoming trees",
        "a colourful bar counter with fruit and glassware",
    ],
    "everyday_expressions": [
        "a kitchen counter with fruit in a bowl and a sunlit window",
        "a hallway with a coat rack and a striped rug",
        "a laundry line with bright clothes against the sky",
        "a bookshelf with plants and framed pictures",
    ],
    "idioms": [
        "a wooden table with scattered playing cards and a teapot",
        "a workshop bench with tools laid out in rows",
        "a windowsill with jars, a clock and a small cactus",
        "a picnic blanket with a basket on green grass",
    ],
    "phrasal_verbs": [
        "a desk covered in open notebooks, pens and sticky notes",
        "a staircase with a bright window on the landing",
        "a kitchen shelf with jars, tins and a kettle",
        "a bicycle leaning on a painted wall",
    ],
    "false_friends": [
        "two identical mugs side by side on a bright table",
        "a pair of doors painted in contrasting colours",
        "two plants in matching pots on a windowsill",
        "a split-tone wall with two colours meeting",
    ],
    "confusing_words": [
        "two labelled jars on a clean shelf",
        "a fork in a garden path between hedges",
        "two coloured pencils crossed on white paper",
        "a mirror reflecting a bright room",
    ],
    "common_mistakes": [
        "an open notebook with a pen and an eraser on a bright desk",
        "a whiteboard with coloured marker strokes",
        "a chalkboard with a clean surface and coloured chalk",
        "crumpled paper beside a fresh notepad on a sunlit table",
    ],
    "grammar": [
        "wooden letter blocks arranged on a light table",
        "an open book with a ribbon marker in the sunlight",
        "a card index box with coloured dividers",
        "a typewriter on a bright desk with a plant behind it",
    ],
    "pronunciation": [
        "a vintage microphone on a stand against a colourful wall",
        "a radio studio desk with a bright pop filter",
        "headphones on a yellow table beside a notebook",
        "a speaker cabinet with a plant and warm daylight",
    ],
    "spanish_specific": [
        "a tiled courtyard with terracotta pots and geraniums",
        "a sunlit balcony with striped awnings",
        "a painted door in a whitewashed wall with bougainvillea",
        "a market stall with bright ceramics",
    ],
    "cultural": [
        "a festival street with paper flags across the sky",
        "a museum hall with tall windows and pale stone",
        "a table set for a celebration with colourful dishes",
        "a plaza with a fountain and painted facades",
    ],
    "food_restaurant": [
        "a bright kitchen counter with fresh vegetables",
        "a restaurant table by a window with a bowl of salad",
        "a bakery display of pastries under warm daylight",
        "a market stall with citrus fruit stacked in crates",
    ],
    "technology": [
        "a clean desk with a laptop, a phone and a plant in daylight",
        "a bright workshop bench with cables coiled neatly",
        "a wall of small screens in a light room",
        "a desk with a keyboard, a notebook and a mug by a window",
    ],
    "slang": [
        "a graffiti wall in bright colours",
        "a skate park ramp under a blue sky",
        "a row of painted shopfronts on a sunny street",
        "a street corner with neon signage unlit in daylight",
    ],
    "kids_animals": [
        "soft toy animals on a bright shelf",
        "a sunny meadow with butterflies",
        "a colourful farmyard fence with painted animals",
        "a child's bedroom with animal wallpaper in daylight",
    ],
    "kids_colors": [
        "coloured pencils fanned out on white paper",
        "paint pots in a rainbow row on a bright table",
        "coloured balloons against a clear sky",
        "a stack of bright building blocks",
    ],
    "kids_numbers": [
        "wooden number blocks on a light rug",
        "a bright abacus on a clean table",
        "chalk numbers on a sunlit pavement",
        "a colourful counting chart on a nursery wall",
    ],
}

#: Light and time of day. No night, no low light — the readability band is
#: composited afterwards and no longer has to be begged for here.
LIGHT = [
    "bright late-morning daylight",
    "warm golden-hour sunlight with long highlights",
    "clean soft daylight from a large window",
    "crisp midday light with vivid colour",
]

#: Palette. An independent axis so two videos sharing a scene still differ.
PALETTE = [
    "a warm palette of amber, coral and cream",
    "a cool palette of teal, sky blue and mint",
    "a bold palette of saturated primary colours",
    "a fresh palette of green, yellow and white",
]

#: Framing. Cheap to vary and it changes the picture more than its length
#: suggests.
FRAMING = [
    "a wide establishing view",
    "a close three-quarter view",
    "an overhead flat-lay view",
    "a low angle looking slightly up",
]


def prompt_space() -> dict:
    """How many distinct prompts this table can produce."""
    per_axis = len(LIGHT) * len(PALETTE) * len(FRAMING)
    per_category = {c: len(v) * per_axis for c, v in CATEGORY_SCENES.items()}
    return {
        "categories": len(CATEGORY_SCENES),
        "light": len(LIGHT), "palette": len(PALETTE), "framing": len(FRAMING),
        "per_category_min": min(per_category.values()),
        "total": sum(per_category.values()),
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "background").lower()).strip("_") or "background"


def _axis_pick(seq, seed_text: str, salt: str):
    """Deterministic choice from `seq` for this topic. Same topic, same image."""
    h = hashlib.sha256(f"{salt}:{seed_text}".encode("utf-8")).digest()
    return seq[int.from_bytes(h[:4], "big") % len(seq)]


def choose_axes(topic: str, category: str = None) -> dict:
    """The (scene, light, palette, framing) this topic gets.

    Deterministic on the topic slug so a re-run reproduces the image rather
    than paying for a different one.
    """
    cat = (category or "").lower()
    scenes = CATEGORY_SCENES.get(cat)
    if not scenes:
        # A category with no scenes is a bug in the table, not a case to
        # absorb quietly — the old DEFAULT_SCENE swallowed eleven of them.
        if cat:
            logger.warning("background: category %r is not in CATEGORY_SCENES "
                           "— add it; falling back to a generic table", cat)
        scenes = [sc for v in CATEGORY_SCENES.values() for sc in v]
    slug = _slug(topic)
    return {
        "category": cat or "unknown",
        "scene": _axis_pick(scenes, slug, "scene"),
        "light": _axis_pick(LIGHT, slug, "light"),
        "palette": _axis_pick(PALETTE, slug, "palette"),
        "framing": _axis_pick(FRAMING, slug, "framing"),
    }


def build_prompt(topic: str, category: str = None, axes: dict = None) -> str:
    """The prompt for one video's background, composed from four axes."""
    axes = axes or choose_axes(topic, category)
    return (
        f"{axes['framing'].capitalize()} of {axes['scene']}, "
        f"{axes['light']}, {axes['palette']}, "
        f"evoking the idea of \"{topic}\" without illustrating it literally "
        f"and without spelling anything out. {COMPOSITION}"
    )


def apply_readability_scrim(image_path, out_path=None):
    """Composite the readability band onto the image, in code.

    THE POINT OF THIS. Contrast used to be requested in the prompt and then
    checked by the gate, which meant the design was being driven by a
    measurement that rewards darkness without limit — so the generator was
    asked for darker and darker pictures and the operator got black frames.

    The band is composed here instead, over the rows the gate measures, so
    contrast is guaranteed by construction and the gate goes back to being a
    safety net rather than the thing steering the art.

    Soft and generous at both edges. A hard seam would look worse than the
    dark images did, so the falloff is a raised cosine over a distance
    comparable to the band itself, not a linear ramp over a few pixels.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # The rows the headline occupies, in this image's coordinates.
    top = HEADLINE_TOP / VIDEO_HEIGHT * h
    bottom = HEADLINE_BOTTOM / VIDEO_HEIGHT * h
    feather = SCRIM_FEATHER / VIDEO_HEIGHT * h

    y = np.arange(h, dtype=np.float32)
    band = np.zeros(h, dtype=np.float32)
    band[(y >= top) & (y <= bottom)] = 1.0

    upper = (y < top) & (y > top - feather)
    band[upper] = 0.5 * (1 + np.cos(np.pi * (top - y[upper]) / feather))
    lower = (y > bottom) & (y < bottom + feather)
    band[lower] = 0.5 * (1 + np.cos(np.pi * (y[lower] - bottom) / feather))

    arr = np.asarray(img, dtype=np.float32)
    darken = 1.0 - SCRIM_STRENGTH * band[:, None, None]
    out = np.clip(arr * darken, 0, 255).astype(np.uint8)

    dest = Path(out_path or image_path)
    Image.fromarray(out).save(dest)
    return dest


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

    # Composite the readability band before anything else sees the file, so
    # the gate measures — and the renderer draws — the same pixels.
    try:
        apply_readability_scrim(result)
    except Exception:                                       # noqa: BLE001
        logger.exception("background: could not apply the readability scrim "
                         "to %s — the gate will judge it unscrimmed", result)

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

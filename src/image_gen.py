#!/usr/bin/env python3
"""Shared OpenAI image generation, on the gpt-image family.

Replaces the dall-e-3 calls that were scattered across
generate_backgrounds.py, generate_character.py and generate_app_icon.py.
OpenAI removed dall-e-2 and dall-e-3 from the API on 2026-05-12.

Why gpt-image-1.5 and not gpt-image-2
-------------------------------------
gpt-image-2 is cheaper and newer, but it does not support transparent
backgrounds: a request carrying ``background="transparent"`` is rejected
outright. Character sprites have to composite over video, so transparency
is not negotiable for them, and having one model for every asset beats
having the sprite path silently diverge. gpt-image-1.5 accepts
``background="transparent"`` and undercuts gpt-image-1 at every tier.

What changed from dall-e-3, for anyone reading an old call site
---------------------------------------------------------------
  - quality is low/medium/high, not standard/hd
  - portrait is 1024x1536 (2:3), not 1024x1792 (1:1.75), so slightly more
    of each image survives the crop to 9:16
  - the response carries base64 in ``b64_json``; there is no ``url`` to
    download from, and no ``revised_prompt`` on this endpoint
  - transparency needs an output format that has an alpha channel, so png
    (the default) or webp
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# The model every generate call names.
IMAGE_MODEL = "gpt-image-1.5"

# Named sizes. gpt-image accepts any multiple of 16 up to a 3840px edge,
# but these three are the ones the per-image price table is quoted for,
# so straying off them makes cost estimates guesswork.
SIZE_SQUARE = "1024x1024"
SIZE_PORTRAIT = "1024x1536"
SIZE_LANDSCAPE = "1536x1024"

# Per-image USD, from the image-generation guide's cost table (checked
# 2026-08-14). Keyed (model, size, quality). Kept here rather than in
# cost_tracker so the price and the call that incurs it live together.
PER_IMAGE_USD = {
    ("gpt-image-2", SIZE_SQUARE): {"low": 0.006, "medium": 0.053, "high": 0.211},
    ("gpt-image-2", SIZE_PORTRAIT): {"low": 0.005, "medium": 0.041, "high": 0.165},
    ("gpt-image-2", SIZE_LANDSCAPE): {"low": 0.005, "medium": 0.041, "high": 0.165},
    ("gpt-image-1.5", SIZE_SQUARE): {"low": 0.009, "medium": 0.034, "high": 0.133},
    ("gpt-image-1.5", SIZE_PORTRAIT): {"low": 0.013, "medium": 0.050, "high": 0.200},
    ("gpt-image-1.5", SIZE_LANDSCAPE): {"low": 0.013, "medium": 0.050, "high": 0.200},
    ("gpt-image-1", SIZE_SQUARE): {"low": 0.011, "medium": 0.042, "high": 0.167},
    ("gpt-image-1", SIZE_PORTRAIT): {"low": 0.016, "medium": 0.063, "high": 0.250},
    ("gpt-image-1", SIZE_LANDSCAPE): {"low": 0.016, "medium": 0.063, "high": 0.250},
    ("gpt-image-1-mini", SIZE_SQUARE): {"low": 0.005, "medium": 0.011, "high": 0.036},
    ("gpt-image-1-mini", SIZE_PORTRAIT): {"low": 0.006, "medium": 0.015, "high": 0.052},
    ("gpt-image-1-mini", SIZE_LANDSCAPE): {"low": 0.006, "medium": 0.015, "high": 0.052},
}

# Models that accept background="transparent". gpt-image-2 is absent on
# purpose — see the module docstring.
TRANSPARENCY_MODELS = frozenset({"gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"})

# Output formats that carry an alpha channel.
ALPHA_FORMATS = frozenset({"png", "webp"})


def price_per_image(quality: str, size: str = SIZE_PORTRAIT,
                    model: str = IMAGE_MODEL) -> float:
    """USD for one image at this model/size/quality, or 0.0 if unpriced.

    Unpriced returns zero rather than guessing: a wrong number in a cost
    report is worse than a visible gap.
    """
    return PER_IMAGE_USD.get((model, size), {}).get(quality, 0.0)


def estimate(count: int, quality: str, size: str = SIZE_PORTRAIT,
             model: str = IMAGE_MODEL) -> float:
    """USD for ``count`` images before spending any of it."""
    return count * price_per_image(quality, size, model)


def get_client():
    """An OpenAI client, or None if the key is missing."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set in .env")
        return None
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def generate_image(client, prompt: str, filepath: Path, *,
                   size: str = SIZE_PORTRAIT,
                   quality: str = "medium",
                   transparent: bool = False,
                   output_format: str = "png",
                   model: str = IMAGE_MODEL,
                   label: str = "image") -> Path | None:
    """Generate one image and write it to ``filepath``.

    Returns the path on success, None on failure. Failures are logged and
    swallowed so a batch of prompts does not die on one bad apple.
    """
    if transparent:
        if model not in TRANSPARENCY_MODELS:
            logger.error("  %s cannot do transparent backgrounds; use one of %s",
                         model, ", ".join(sorted(TRANSPARENCY_MODELS)))
            return None
        if output_format not in ALPHA_FORMATS:
            logger.error("  transparent needs an alpha format (%s), got %s",
                         "/".join(sorted(ALPHA_FORMATS)), output_format)
            return None

    kwargs = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
        "output_format": output_format,
    }
    if transparent:
        kwargs["background"] = "transparent"

    try:
        response = client.images.generate(**kwargs)
    except Exception as e:
        logger.error("  Failed to generate %s: %s", filepath.name, e)
        return None

    # gpt-image returns base64, never a URL. There is nothing to download.
    payload = response.data[0].b64_json
    if not payload:
        logger.error("  %s: response carried no image data", filepath.name)
        return None

    image_bytes = base64.b64decode(payload)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(image_bytes)

    try:
        from cost_tracker import get_tracker
        get_tracker().log_image(count=1, size=size, quality=quality,
                                model=model, label=label)
    except Exception:
        pass

    logger.info("  Saved: %s (%.1f MB, ~$%.3f)", filepath.name,
                len(image_bytes) / (1024 * 1024),
                price_per_image(quality, size, model))
    return filepath

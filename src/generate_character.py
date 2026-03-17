#!/usr/bin/env python3
"""
Character Sprite Generator using OpenAI DALL-E 3.

Generates a turtle mascot character with different mouth positions for
lip-sync animation in English learning videos. Each image is a full
character with only the mouth expression varying.

Images are saved to assets/characters/turtle/ and used by the video
compositor for character overlay animations.

Usage:
    python3 src/generate_character.py            # Generate all mouth states
    python3 src/generate_character.py --list     # Show what exists
    python3 src/generate_character.py --preview  # Generate 1 preview (closed)

Cost estimate (DALL-E 3, 1024x1024, standard quality):
    $0.040 per image
    5 mouth states = $0.20 total
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Setup
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

ASSETS_DIR = ROOT / "assets" / "characters" / "turtle"

# ============================================================
# CHARACTER DESIGN — consistent base prompt with mouth variants
# ============================================================
# Key principles:
# - Front-facing, full body, centered
# - Simple clean cartoon style with flat shading
# - White background for easy compositing
# - Same character across ALL variants — only the mouth changes
# - 1024x1024 square format for sprite use

CHARACTER_BASE = (
    "A cute friendly cartoon turtle mascot character, front-facing full body view, "
    "standing upright on two legs in a confident pose with hands on hips. "
    "The turtle has a bright green body, a rounded lighter green shell on its back, "
    "big expressive friendly eyes with small black pupils, small rounded arms and legs. "
    "Simple clean cartoon style with flat shading, thick outlines, no textures. "
    "Solid white background, centered composition, no text, no other objects, "
    "no shadows on background. The character is designed as a children's educational mascot."
)

MOUTH_STATES = {
    "mouth_closed": (
        f"{CHARACTER_BASE} "
        "The turtle's mouth is closed in a gentle smile, lips together forming a small "
        "friendly curved line."
    ),
    "mouth_slightly_open": (
        f"{CHARACTER_BASE} "
        "The turtle's mouth is slightly open, showing a small gap between the lips as if "
        "starting to speak, a relaxed half-open mouth shape."
    ),
    "mouth_open": (
        f"{CHARACTER_BASE} "
        "The turtle's mouth is open in a medium-sized oval shape as if saying 'ah', "
        "showing a dark interior, an actively speaking expression."
    ),
    "mouth_wide": (
        f"{CHARACTER_BASE} "
        "The turtle's mouth is wide open in a big excited expression as if saying a loud "
        "'aah', showing the inside of the mouth, an enthusiastic wide-open mouth."
    ),
    "mouth_o": (
        f"{CHARACTER_BASE} "
        "The turtle's mouth is shaped into a small round 'O' shape, lips pursed forward "
        "in a circle as if saying 'ooh', a rounded pucker expression."
    ),
}


def generate_character_images(states: list[str] = None):
    """Generate character images for the specified mouth states using DALL-E 3."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set in .env")
        return []

    client = OpenAI(api_key=api_key)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    if states is None:
        states = list(MOUTH_STATES.keys())

    generated = []
    size = "1024x1024"
    quality = "standard"

    for i, state in enumerate(states):
        if state not in MOUTH_STATES:
            logger.error("Unknown mouth state: %s. Available: %s",
                         state, list(MOUTH_STATES.keys()))
            continue

        filename = f"{state}.png"
        filepath = ASSETS_DIR / filename

        # Skip if already exists
        if filepath.exists():
            logger.info("  [%d/%d] Already exists: %s", i + 1, len(states), filename)
            generated.append(filepath)
            continue

        prompt = MOUTH_STATES[state]
        logger.info("  [%d/%d] Generating: %s", i + 1, len(states), filename)
        logger.info("  Mouth state: %s", state)

        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )

            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt

            # Track DALL-E cost
            try:
                from cost_tracker import get_tracker
                get_tracker().log_dalle(count=1, size=size, quality=quality,
                                        label=f"character_turtle_{state}")
            except Exception:
                pass

            logger.info("  DALL-E revised prompt: %s...", revised_prompt[:100])

            # Download the image
            import requests
            img_response = requests.get(image_url, timeout=60)
            img_response.raise_for_status()

            with open(filepath, 'wb') as f:
                f.write(img_response.content)

            size_mb = len(img_response.content) / (1024 * 1024)
            logger.info("  Saved: %s (%.1f MB)", filename, size_mb)
            generated.append(filepath)

        except Exception as e:
            logger.error("  Failed to generate %s: %s", filename, e)

    return generated


def list_characters():
    """Show current character images status."""
    print("=" * 60)
    print("CHARACTER SPRITES STATUS — Turtle")
    print("=" * 60)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    images = [f for f in ASSETS_DIR.iterdir()
              if f.suffix.lower() in extensions and f.is_file()] if ASSETS_DIR.exists() else []

    total_size = sum(f.stat().st_size for f in images)

    all_states = list(MOUTH_STATES.keys())
    for state in all_states:
        filepath = ASSETS_DIR / f"{state}.png"
        if filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  [OK] {state:25s}: {size_mb:.1f} MB")
        else:
            print(f"  [!!] {state:25s}: MISSING")

    print("-" * 60)
    print(f"  Total: {len(images)} images, {total_size / (1024 * 1024):.1f} MB")
    print(f"  Location: {ASSETS_DIR}")
    print()

    missing = [s for s in all_states if not (ASSETS_DIR / f"{s}.png").exists()]
    if missing:
        print(f"  Missing: {len(missing)} states")
        print(f"  Run: python3 src/generate_character.py")
        print(f"  Cost: ~$0.04 per image (DALL-E 3, 1024x1024, standard)")
    else:
        print("  All mouth states present!")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate turtle mascot character sprites using DALL-E 3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 src/generate_character.py              # Generate all 5 mouth states
  python3 src/generate_character.py --list       # Show status
  python3 src/generate_character.py --preview    # Generate 1 preview (closed)

Mouth states: closed, slightly_open, open, wide, o_shape

Cost: ~$0.04 per image (DALL-E 3, 1024x1024, standard)
Total: ~$0.20 for all 5 states
        """
    )

    parser.add_argument("--list", "-l", action="store_true",
                        help="List current character images")
    parser.add_argument("--preview", action="store_true",
                        help="Generate just 1 image (mouth_closed) for preview")

    args = parser.parse_args()

    if args.list:
        list_characters()
        return

    if args.preview:
        logger.info("Generating 1 preview image (mouth_closed)...")
        results = generate_character_images(["mouth_closed"])
        if results:
            logger.info("Preview saved: %s", results[0])
        return

    # Generate all mouth states
    all_states = list(MOUTH_STATES.keys())

    # Check how many need generating
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    to_generate = [s for s in all_states if not (ASSETS_DIR / f"{s}.png").exists()]

    if not to_generate:
        logger.info("All character sprites already exist! Use --list to see them.")
        return

    estimated_cost = len(to_generate) * 0.04
    logger.info("=" * 50)
    logger.info("DALL-E 3 Character Sprite Generation")
    logger.info("=" * 50)
    logger.info("Character: Turtle Mascot")
    logger.info("Mouth states to generate: %d / %d", len(to_generate), len(all_states))
    logger.info("States: %s", ", ".join(to_generate))
    logger.info("Estimated cost: $%.2f", estimated_cost)
    logger.info("=" * 50)

    results = generate_character_images(to_generate)
    logger.info("")
    logger.info("Done! Generated %d character sprites.", len(results))
    logger.info("Run 'python3 src/generate_character.py --list' to see results.")


if __name__ == "__main__":
    main()

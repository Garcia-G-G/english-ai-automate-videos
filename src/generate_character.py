#!/usr/bin/env python3
"""
Character Sprite Generator using OpenAI gpt-image.

Generates an owl mascot character with different mouth/beak positions for
lip-sync animation in English learning videos. Each image is a full
character with only the beak expression varying.

Images are saved to assets/characters/owl/ and used by the video
compositor for character overlay animations.

Usage:
    python3 src/generate_character.py            # Generate all mouth states
    python3 src/generate_character.py --list     # Show what exists
    python3 src/generate_character.py --preview  # Generate 1 preview (closed)
    python3 src/generate_character.py --name owl # Specify character name

Migrated off dall-e-3, which OpenAI removed from the API on 2026-05-12.
The call goes through image_gen.py; see that module for the model choice.

Sprites are generated with a transparent background rather than the white
one the old prompts asked for, so the compositor no longer has to key the
white out. The prompt text still says "white background" for characters
written before the migration — background="transparent" overrides it, and
character.py's luminance keying still copes either way.

Cost (gpt-image-1.5, 1024x1024):
    low $0.009   medium $0.034   high $0.133  per image
    5 mouth states at medium = $0.17
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from image_gen import IMAGE_MODEL, SIZE_SQUARE, estimate, generate_image, get_client

# Setup
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_CHARACTER = "fox"
DEFAULT_QUALITY = "medium"
ASSETS_DIR = ROOT / "assets" / "characters" / DEFAULT_CHARACTER

# ============================================================
# CHARACTER DESIGNS — consistent base prompt with mouth variants
# ============================================================
# Key principles:
# - Front-facing, full body, centered
# - Simple clean cartoon style with flat shading
# - White background for easy compositing
# - Same character across ALL variants — only the mouth/beak changes
# - 1024x1024 square format for sprite use

# ── OWL CHARACTER (legacy) ──
OWL_BASE = (
    "A cute friendly cartoon owl mascot character, front-facing full body view, "
    "standing upright on two legs in a confident teacher pose with one wing raised as if waving. "
    "IMPORTANT: Only ONE owl character in the image. "
    "The owl has a round chubby body with bright teal-blue feathers, a cream/white belly patch, "
    "very large round expressive eyes with big black pupils and a sparkle highlight, "
    "thick dark eyebrows for expressiveness, small rounded wings like arms, "
    "a prominent yellow-orange beak in the center of the face, "
    "tiny orange feet, and a small tuft of darker feathers on top of the head like hair. "
    "The owl wears a tiny graduation cap tilted to the side. "
    "Simple clean cartoon style with flat shading, thick black outlines, bright saturated colors. "
    "Solid white background, centered composition, no text, no other objects, "
    "no shadows on background. ONLY ONE character. "
    "The character is designed as a viral educational mascot for language learning videos."
)

OWL_MOUTH_STATES = {
    "mouth_closed": (
        f"{OWL_BASE} "
        "The owl's beak is closed in a gentle smile, the yellow-orange beak forming a small "
        "friendly V-shape, looking content and happy."
    ),
    "mouth_slightly_open": (
        f"{OWL_BASE} "
        "The owl's beak is slightly open, showing a small gap as if starting to speak, "
        "the yellow-orange beak parted just a little with a hint of dark interior."
    ),
    "mouth_open": (
        f"{OWL_BASE} "
        "The owl's beak is open in a medium oval shape as if saying a word, "
        "the yellow-orange beak clearly open showing a dark pink interior, actively speaking."
    ),
    "mouth_wide": (
        f"{OWL_BASE} "
        "The owl's beak is wide open in a big excited expression as if saying 'aah!', "
        "the yellow-orange beak fully open showing the inside, an enthusiastic teaching expression."
    ),
    "mouth_o": (
        f"{OWL_BASE} "
        "The owl's beak is shaped into a small round 'O' shape, the yellow-orange beak "
        "pursed forward in a circle as if saying 'ooh', a surprised curious expression."
    ),
}

# ── FOX CHARACTER (primary — charismatic educational mascot) ──
FOX_BASE = (
    "A single cute friendly cartoon fox mascot character standing alone in the center of the image. "
    "Front-facing full body view, standing upright on two legs in a confident charismatic pose "
    "with one paw raised giving a thumbs-up. "
    "CRITICAL: There is exactly ONE fox in this image. Do NOT draw multiple characters, "
    "do NOT draw a character sheet, do NOT draw reference poses. Just ONE single fox character. "
    "The fox has a sleek but slightly chubby body with bright warm orange-red fur, "
    "a fluffy cream-white chest and belly, a big bushy tail with a white tip, "
    "very large round expressive bright green eyes with big black pupils and a sparkle highlight, "
    "thick expressive dark eyebrows, small rounded paws like hands, "
    "a small cute black nose, pointed triangular ears with cream-white inner fur, "
    "and darker orange-brown fur markings on the ears and paws. "
    "The fox wears a small bright blue bow tie. "
    "Simple clean cartoon style with flat shading, thick black outlines, bright saturated colors. "
    "Pure solid white background, centered composition, no text, no other objects, "
    "no shadows on background, no ground, no props. Just the ONE fox character. "
    "Full body visible including feet and tail. "
    "The character is designed as a viral educational mascot for language learning videos."
)

FOX_MOUTH_STATES = {
    "mouth_closed": (
        f"{FOX_BASE} "
        "The fox's mouth is closed in a confident friendly smile, with a small curved line "
        "showing a gentle grin, looking smart and approachable."
    ),
    "mouth_slightly_open": (
        f"{FOX_BASE} "
        "The fox's mouth is slightly open in a small friendly grin, showing just a hint of "
        "tongue and teeth, as if about to say something clever."
    ),
    "mouth_open": (
        f"{FOX_BASE} "
        "The fox's mouth is open in a medium oval shape as if actively teaching a word, "
        "showing a pink tongue and small white teeth, an enthusiastic speaking expression."
    ),
    "mouth_wide": (
        f"{FOX_BASE} "
        "The fox's mouth is wide open in an excited happy expression as if saying 'amazing!', "
        "showing tongue and teeth, an enthusiastic and encouraging teaching expression."
    ),
    "mouth_o": (
        f"{FOX_BASE} "
        "The fox's mouth is shaped into a small round 'O' shape, lips pursed forward "
        "as if saying 'ooh', a surprised and curious expression with raised eyebrows. "
        "This is a single illustration of one fox, NOT a character sheet or reference page."
    ),
}

# ── TURTLE CHARACTER (legacy) ──
TURTLE_BASE = (
    "A cute friendly cartoon turtle mascot character, front-facing full body view, "
    "standing upright on two legs in a confident pose with hands on hips. "
    "The turtle has a bright green body, a rounded lighter green shell on its back, "
    "big expressive friendly eyes with small black pupils, small rounded arms and legs. "
    "Simple clean cartoon style with flat shading, thick outlines, no textures. "
    "Solid white background, centered composition, no text, no other objects, "
    "no shadows on background. The character is designed as a children's educational mascot."
)

TURTLE_MOUTH_STATES = {
    "mouth_closed": (
        f"{TURTLE_BASE} "
        "The turtle's mouth is closed in a gentle smile, lips together forming a small "
        "friendly curved line."
    ),
    "mouth_slightly_open": (
        f"{TURTLE_BASE} "
        "The turtle's mouth is slightly open, showing a small gap between the lips as if "
        "starting to speak, a relaxed half-open mouth shape."
    ),
    "mouth_open": (
        f"{TURTLE_BASE} "
        "The turtle's mouth is open in a medium-sized oval shape as if saying 'ah', "
        "showing a dark interior, an actively speaking expression."
    ),
    "mouth_wide": (
        f"{TURTLE_BASE} "
        "The turtle's mouth is wide open in a big excited expression as if saying a loud "
        "'aah', showing the inside of the mouth, an enthusiastic wide-open mouth."
    ),
    "mouth_o": (
        f"{TURTLE_BASE} "
        "The turtle's mouth is shaped into a small round 'O' shape, lips pursed forward "
        "in a circle as if saying 'ooh', a rounded pucker expression."
    ),
}

# Registry of all characters
CHARACTER_REGISTRY = {
    "fox": FOX_MOUTH_STATES,
    "owl": OWL_MOUTH_STATES,
    "turtle": TURTLE_MOUTH_STATES,
}

# Active character (set by CLI or default)
MOUTH_STATES = FOX_MOUTH_STATES


def generate_character_images(states: list[str] = None, character: str = None,
                              quality: str = DEFAULT_QUALITY):
    """Generate character images for the specified mouth states."""
    client = get_client()
    if client is None:
        return []

    char_name = character or DEFAULT_CHARACTER
    mouth_states = CHARACTER_REGISTRY.get(char_name, OWL_MOUTH_STATES)
    assets_dir = ROOT / "assets" / "characters" / char_name

    assets_dir.mkdir(parents=True, exist_ok=True)

    if states is None:
        states = list(mouth_states.keys())

    generated = []
    size = SIZE_SQUARE

    for i, state in enumerate(states):
        if state not in mouth_states:
            logger.error("Unknown mouth state: %s. Available: %s",
                         state, list(mouth_states.keys()))
            continue

        filename = f"{state}.png"
        filepath = assets_dir / filename

        # Skip if already exists
        if filepath.exists():
            logger.info("  [%d/%d] Already exists: %s", i + 1, len(states), filename)
            generated.append(filepath)
            continue

        prompt = mouth_states[state]
        logger.info("  [%d/%d] Generating: %s", i + 1, len(states), filename)
        logger.info("  Mouth state: %s", state)

        result = generate_image(client, prompt, filepath,
                                size=size, quality=quality,
                                transparent=True,
                                label=f"character_{char_name}_{state}")
        if result:
            generated.append(result)

    return generated


def list_characters(character: str = None):
    """Show current character images status."""
    char_name = character or DEFAULT_CHARACTER
    mouth_states = CHARACTER_REGISTRY.get(char_name, OWL_MOUTH_STATES)
    assets_dir = ROOT / "assets" / "characters" / char_name

    print("=" * 60)
    print(f"CHARACTER SPRITES STATUS — {char_name.title()}")
    print("=" * 60)

    assets_dir.mkdir(parents=True, exist_ok=True)

    extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    images = [f for f in assets_dir.iterdir()
              if f.suffix.lower() in extensions and f.is_file()] if assets_dir.exists() else []

    total_size = sum(f.stat().st_size for f in images)

    all_states = list(mouth_states.keys())
    for state in all_states:
        filepath = assets_dir / f"{state}.png"
        if filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  [OK] {state:25s}: {size_mb:.1f} MB")
        else:
            print(f"  [!!] {state:25s}: MISSING")

    print("-" * 60)
    print(f"  Total: {len(images)} images, {total_size / (1024 * 1024):.1f} MB")
    print(f"  Location: {assets_dir}")
    print()

    # Show all available characters
    print(f"  Available characters: {', '.join(CHARACTER_REGISTRY.keys())}")

    missing = [s for s in all_states if not (assets_dir / f"{s}.png").exists()]
    if missing:
        print(f"  Missing: {len(missing)} states")
        print(f"  Run: python3 src/generate_character.py --name {char_name}")
        print(f"  Cost: ~${estimate(1, DEFAULT_QUALITY, SIZE_SQUARE):.3f} per image "
              f"({IMAGE_MODEL}, {SIZE_SQUARE}, {DEFAULT_QUALITY})")
    else:
        print("  All mouth states present!")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate character mascot sprites using OpenAI gpt-image",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python3 src/generate_character.py                    # Generate owl (default)
  python3 src/generate_character.py --name turtle      # Generate turtle
  python3 src/generate_character.py --list             # Show status
  python3 src/generate_character.py --preview          # Generate 1 preview

Available characters: {', '.join(CHARACTER_REGISTRY.keys())}

Mouth states: closed, slightly_open, open, wide, o_shape

Cost: ~$0.034 per image (gpt-image-1.5, 1024x1024, medium)
Total: ~$0.17 for all 5 states. --quality changes the tier.
        """
    )

    parser.add_argument("--list", "-l", action="store_true",
                        help="List current character images")
    parser.add_argument("--preview", action="store_true",
                        help="Generate just 1 image (mouth_closed) for preview")
    parser.add_argument("--name", "-n", default=DEFAULT_CHARACTER,
                        choices=list(CHARACTER_REGISTRY.keys()),
                        help=f"Character to generate (default: {DEFAULT_CHARACTER})")
    parser.add_argument("--quality", "-q", default=DEFAULT_QUALITY,
                        choices=["low", "medium", "high"],
                        help=f"Image quality tier (default: {DEFAULT_QUALITY}). "
                             "Drives the price per image.")

    args = parser.parse_args()
    char_name = args.name

    if args.list:
        list_characters(char_name)
        return

    if args.preview:
        logger.info("Generating 1 preview image (mouth_closed) for %s...", char_name)
        results = generate_character_images(["mouth_closed"], character=char_name,
                                            quality=args.quality)
        if results:
            logger.info("Preview saved: %s", results[0])
        return

    # Generate all mouth states
    mouth_states = CHARACTER_REGISTRY.get(char_name, OWL_MOUTH_STATES)
    all_states = list(mouth_states.keys())

    # Check how many need generating
    assets_dir = ROOT / "assets" / "characters" / char_name
    assets_dir.mkdir(parents=True, exist_ok=True)
    to_generate = [s for s in all_states if not (assets_dir / f"{s}.png").exists()]

    if not to_generate:
        logger.info("All character sprites already exist! Use --list to see them.")
        return

    estimated_cost = estimate(len(to_generate), args.quality, SIZE_SQUARE)
    logger.info("=" * 50)
    logger.info("Character Sprite Generation (%s, %s)", IMAGE_MODEL, args.quality)
    logger.info("=" * 50)
    logger.info("Character: %s Mascot", char_name.title())
    logger.info("Mouth states to generate: %d / %d", len(to_generate), len(all_states))
    logger.info("States: %s", ", ".join(to_generate))
    logger.info("Estimated cost: $%.2f", estimated_cost)
    logger.info("=" * 50)

    results = generate_character_images(to_generate, character=char_name,
                                        quality=args.quality)
    logger.info("")
    logger.info("Done! Generated %d character sprites.", len(results))
    logger.info("Run 'python3 src/generate_character.py --list --name %s' to see results.", char_name)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
AI Background Generator using OpenAI DALL-E 3.

Generates realistic, high-quality background images for TikTok-style
English learning videos. Images are saved to assets/backgrounds/<category>/
and used by the photo_kenburns background system with Ken Burns animation.

Usage:
    python3 src/generate_backgrounds.py                    # Generate all categories
    python3 src/generate_backgrounds.py --category earth   # Single category
    python3 src/generate_backgrounds.py --count 5          # 5 per category
    python3 src/generate_backgrounds.py --list              # Show what exists
    python3 src/generate_backgrounds.py --preview earth     # Generate 1 preview

Cost estimate (DALL-E 3, 1024x1792 portrait):
    $0.080 per image
    Default: 3 images x 6 categories = 18 images = ~$1.44
    Full: 5 images x 6 categories = 30 images = ~$2.40
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Setup
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

ASSETS_DIR = ROOT / "assets" / "backgrounds"

# ============================================================
# DALL-E 3 PROMPTS — carefully tuned for video backgrounds
# ============================================================
# Key principles:
# - Portrait orientation (1024x1792) for TikTok 9:16
# - Rich detail but not too busy (text will overlay)
# - Dark enough for white/yellow text readability
# - Cinematic, dramatic lighting
# - No text, no people, no logos

BACKGROUND_PROMPTS = {
    "earth": [
        (
            "Planet Earth seen from space at night, showing city lights glowing across "
            "continents, deep black space background, the blue atmosphere glowing at the "
            "edges, highly detailed satellite view, cinematic photography, 8K resolution, "
            "dramatic lighting, no text, no labels"
        ),
        (
            "Stunning view of Earth from low orbit, half illuminated by the sun showing "
            "blue oceans and white cloud formations, the curve of the planet visible, "
            "stars in the background, NASA-style photography, ultra realistic, no text"
        ),
        (
            "Close-up of Earth from space showing a massive hurricane over the ocean, "
            "swirling white clouds against deep blue water, the thin blue line of the "
            "atmosphere visible, cinematic space photography, dark background, no text"
        ),
        (
            "Earth and Moon together from deep space, the Earth showing Africa and Europe "
            "at night with golden city lights, the Moon in the background, stars scattered "
            "across deep black space, ultra realistic space photography, no text"
        ),
        (
            "Dramatic view of Earth's atmosphere at sunset from space, the terminator line "
            "between day and night, golden and blue light along the horizon, city lights "
            "emerging on the dark side, cinematic and ethereal, no text"
        ),
    ],
    "city": [
        (
            "Aerial night view of a modern city with neon lights, skyscrapers reflecting "
            "in wet streets below, purple and blue city lights, cyberpunk atmosphere, "
            "portrait orientation, cinematic photography, dramatic, moody, no text"
        ),
        (
            "Times Square New York City at night, vibrant neon signs and billboards "
            "creating colorful light, busy intersection seen from above, slight motion "
            "blur, rain-wet reflective streets, cinematic urban photography, no text, "
            "no readable signs"
        ),
        (
            "Tokyo city skyline at night with Tokyo Tower glowing orange, sea of lights "
            "stretching to the horizon, purple-blue twilight sky, aerial photography, "
            "ultra detailed, cinematic mood, no text"
        ),
        (
            "Narrow neon-lit alley in an Asian city at night, pink and cyan neon signs "
            "reflecting on wet cobblestones, steam rising, moody cinematic atmosphere, "
            "shallow depth of field, portrait orientation, no people, no text"
        ),
        (
            "Modern city at golden hour viewed from a rooftop, glass skyscrapers "
            "reflecting warm orange sunset light, dramatic shadows, urban landscape "
            "stretching to the horizon, cinematic wide photography, no text"
        ),
    ],
    "ocean": [
        (
            "Dramatic ocean sunset with vibrant orange, pink, and purple clouds reflected "
            "in calm tropical water, the sun half-set on the horizon, silhouette of waves, "
            "cinematic landscape photography, portrait orientation, no text"
        ),
        (
            "Aerial view of a tropical turquoise ocean with gentle waves creating "
            "patterns, a coral reef visible beneath crystal clear water, deep blue "
            "transitioning to light turquoise, drone photography, no text"
        ),
        (
            "Massive ocean wave curling with spray and foam, deep blue-green water, "
            "dramatic lighting from behind the wave, powerful and dynamic, surf "
            "photography style, portrait orientation, no text"
        ),
        (
            "Calm ocean at twilight, dark blue water stretching to the horizon, "
            "a spectacular sky filled with stars and the Milky Way above, the faintest "
            "glow of sunset on the horizon, long exposure photography, serene, no text"
        ),
        (
            "Tropical beach from above showing turquoise waves gently breaking on white "
            "sand, palm tree shadows, the contrast between deep ocean blue and shallow "
            "water turquoise, paradise aerial photography, no text"
        ),
    ],
    "nature": [
        (
            "Majestic mountain landscape at sunrise, snow-capped peaks with golden light, "
            "a lake in the valley reflecting the mountains, pine forests on the slopes, "
            "dramatic clouds, epic landscape photography, portrait orientation, no text"
        ),
        (
            "Dense tropical rainforest canopy seen from above, layers of green in every "
            "shade, morning mist rising between the trees, rays of golden sunlight "
            "piercing through, drone aerial photography, lush and vibrant, no text"
        ),
        (
            "Northern lights aurora borealis over a snowy mountain landscape, vivid green "
            "and purple lights dancing across the dark sky, stars visible, a frozen lake "
            "reflecting the colors, long exposure photography, breathtaking, no text"
        ),
        (
            "Autumn forest from above, trees in brilliant red orange and gold colors, "
            "a winding river cutting through the forest, morning fog in the valleys, "
            "aerial drone photography, rich warm colors, no text"
        ),
        (
            "Volcanic landscape at twilight, a volcano with glowing lava visible in the "
            "crater, dramatic red and orange sky, rugged black volcanic rock in the "
            "foreground, powerful and dramatic nature photography, no text"
        ),
    ],
    "abstract": [
        (
            "Close-up macro photography of iridescent blue and teal feathers, showing "
            "intricate barb patterns, soft bokeh background, rich saturated colors, "
            "abstract organic texture, portrait orientation, studio lighting, no text"
        ),
        (
            "Abstract swirling colorful smoke on black background, vibrant cyan magenta "
            "and gold colors intertwining, fluid dynamics captured in high speed, "
            "dramatic studio photography, deep black negative space, no text"
        ),
        (
            "Macro photography of oil and water creating abstract iridescent patterns, "
            "bubbles with rainbow reflections on dark background, psychedelic colors, "
            "purple blue and gold, scientific art photography, no text"
        ),
        (
            "Abstract close-up of cracked ice with blue and white patterns, geometric "
            "fracture lines creating natural mosaic, cold blue light shining through, "
            "nature abstract texture photography, dark moody, no text"
        ),
        (
            "Macro photography of crystals with prismatic light refractions, rainbow "
            "colors scattered through transparent mineral formations on dark background, "
            "geological beauty, studio lighting, abstract, no text"
        ),
    ],
    "clouds": [
        (
            "Dramatic aerial view above the clouds at sunset, golden and pink light "
            "illuminating the cloud tops, an opening in the clouds revealing the ground "
            "far below, airplane window perspective, cinematic photography, no text"
        ),
        (
            "Towering cumulonimbus thunderstorm cloud at sunset, dramatic orange and "
            "purple light, lightning bolt illuminating the interior, seen from a distance, "
            "powerful atmospheric photography, portrait orientation, no text"
        ),
        (
            "Soft pastel clouds at dawn, cotton candy pink purple and blue colors, "
            "peaceful dreamy atmosphere, the clouds filling the entire frame, ethereal "
            "and calming, fine art sky photography, portrait orientation, no text"
        ),
        (
            "Dark dramatic storm clouds over an open landscape, volumetric light rays "
            "breaking through gaps in the clouds, god rays illuminating patches below, "
            "epic cinematic weather photography, powerful mood, no text"
        ),
        (
            "Sea of clouds filling a mountain valley at sunrise, mountain peaks rising "
            "above like islands, golden warm light, mist and fog creating layers, "
            "aerial landscape photography, serene and majestic, no text"
        ),
    ],
    "sunset": [
        (
            "Breathtaking tropical sunset over calm ocean, vivid orange red and purple "
            "sky with dramatic cloud formations, the sun touching the horizon creating a "
            "golden path on the water, cinematic landscape photography, portrait, no text"
        ),
        (
            "Desert sunset with silhouette of sand dunes, dramatic red and gold sky with "
            "layered clouds, rich warm colors transitioning from deep orange to purple, "
            "cinematic nature photography, portrait orientation, no text"
        ),
        (
            "Mountain sunset with dramatic alpenglow, snow-capped peaks catching the last "
            "golden light, deep purple valleys below, gradient sky from warm gold to cool "
            "blue, epic landscape photography, portrait orientation, no text"
        ),
        (
            "Sunset through forest trees, golden hour light filtering through branches, "
            "dramatic sunbeams and lens flare, warm amber tones, silhouetted tree canopy, "
            "cinematic nature photography, portrait orientation, no text"
        ),
        (
            "Dramatic sunset sky with mammatus clouds, vibrant orange pink and purple "
            "colors, rare and spectacular cloud formations backlit by the setting sun, "
            "atmospheric photography, portrait orientation, no text"
        ),
    ],
    "galaxy": [
        (
            "Deep space nebula in vivid purple blue and pink colors, swirling gas clouds "
            "with bright stars scattered throughout, Hubble telescope style, cosmic and "
            "ethereal, dark background with rich color accents, portrait, no text"
        ),
        (
            "Milky Way galaxy core seen from a dark mountain location, millions of stars "
            "in dense band across the sky, purple and gold nebula glow, dark silhouette "
            "of mountain horizon, astrophotography, portrait orientation, no text"
        ),
        (
            "Colorful spiral galaxy viewed from above, arms of blue stars and pink nebulae "
            "swirling around a bright golden core, deep black space with distant galaxies, "
            "Hubble-style space photography, portrait orientation, no text"
        ),
        (
            "Stunning planetary nebula with concentric rings of glowing gas in teal blue "
            "and magenta, a bright white dwarf star at the center, dark space background, "
            "astronomical photography, portrait orientation, no text"
        ),
        (
            "Star-forming region in deep space, pillars of colorful gas and dust in gold "
            "brown and green, backlit by hot young blue stars, like the Pillars of Creation, "
            "Hubble telescope style, portrait orientation, no text"
        ),
    ],
}


def generate_images(category: str, count: int = 3, size: str = "1024x1792"):
    """Generate background images for a category using DALL-E 3."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set in .env")
        return []

    client = OpenAI(api_key=api_key)

    if category not in BACKGROUND_PROMPTS:
        logger.error("Unknown category: %s. Available: %s",
                     category, list(BACKGROUND_PROMPTS.keys()))
        return []

    cat_dir = ASSETS_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    prompts = BACKGROUND_PROMPTS[category][:count]
    generated = []

    for i, prompt in enumerate(prompts):
        filename = f"{category}_{i+1:02d}.png"
        filepath = cat_dir / filename

        # Skip if already exists
        if filepath.exists():
            logger.info("  [%d/%d] Already exists: %s", i+1, count, filename)
            generated.append(filepath)
            continue

        logger.info("  [%d/%d] Generating: %s", i+1, count, filename)
        logger.info("  Prompt: %s...", prompt[:80])

        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="hd",
                n=1,
            )

            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt

            # Track DALL-E cost
            try:
                from cost_tracker import get_tracker
                get_tracker().log_dalle(count=1, size=size, quality="hd",
                                        label=f"bg_{category}")
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


def list_backgrounds():
    """Show current background images status."""
    print("=" * 60)
    print("BACKGROUND IMAGES STATUS")
    print("=" * 60)

    total_images = 0
    total_size = 0

    categories = list(BACKGROUND_PROMPTS.keys())
    for cat in categories:
        cat_dir = ASSETS_DIR / cat
        cat_dir.mkdir(parents=True, exist_ok=True)

        extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        images = [f for f in cat_dir.iterdir()
                  if f.suffix.lower() in extensions and f.is_file()]

        cat_size = sum(f.stat().st_size for f in images)
        total_images += len(images)
        total_size += cat_size

        status = f"{len(images)} images ({cat_size / (1024*1024):.1f} MB)" if images else "EMPTY"
        icon = "OK" if images else "!!"
        print(f"  [{icon}] {cat:12s}: {status}")

        for img in sorted(images):
            print(f"       - {img.name} ({img.stat().st_size / (1024*1024):.1f} MB)")

    print("-" * 60)
    print(f"  Total: {total_images} images, {total_size / (1024*1024):.1f} MB")
    print(f"  Location: {ASSETS_DIR}")
    print()
    print("  Available presets: photo_earth, photo_city, photo_ocean,")
    print("                     photo_nature, photo_abstract, photo_clouds,")
    print("                     photo_sunset, photo_galaxy")
    print()

    if total_images == 0:
        print("  Run: python3 src/generate_backgrounds.py")
        print("  Cost: ~$1.44 for 3 images/category (DALL-E 3)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate AI background images using DALL-E 3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 src/generate_backgrounds.py                     # Generate 3 per category
  python3 src/generate_backgrounds.py --category earth    # Only earth backgrounds
  python3 src/generate_backgrounds.py --count 5           # 5 per category
  python3 src/generate_backgrounds.py --list              # Show status
  python3 src/generate_backgrounds.py --preview ocean     # Quick 1-image test

Categories: earth, city, ocean, nature, abstract, clouds

Cost: ~$0.08 per image (DALL-E 3, 1024x1792 HD)
        """
    )

    parser.add_argument("--category", "-c", type=str, default=None,
                        choices=list(BACKGROUND_PROMPTS.keys()),
                        help="Generate only this category")
    parser.add_argument("--count", "-n", type=int, default=3,
                        help="Images per category (default: 3, max: 5)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List current background images")
    parser.add_argument("--preview", type=str, default=None,
                        choices=list(BACKGROUND_PROMPTS.keys()),
                        help="Generate just 1 image for preview")

    args = parser.parse_args()

    if args.list:
        list_backgrounds()
        return

    if args.preview:
        logger.info("Generating 1 preview image for '%s'...", args.preview)
        results = generate_images(args.preview, count=1)
        if results:
            logger.info("Preview saved: %s", results[0])
        return

    count = min(args.count, 5)

    if args.category:
        categories = [args.category]
    else:
        categories = list(BACKGROUND_PROMPTS.keys())

    total_new = 0
    total_cost = 0.0

    # Check how many actually need generating
    for cat in categories:
        cat_dir = ASSETS_DIR / cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            filepath = cat_dir / f"{cat}_{i+1:02d}.png"
            if not filepath.exists():
                total_new += 1

    if total_new == 0:
        logger.info("All backgrounds already exist! Use --list to see them.")
        return

    estimated_cost = total_new * 0.08
    logger.info("=" * 50)
    logger.info("DALL-E 3 Background Generation")
    logger.info("=" * 50)
    logger.info("Categories: %s", ", ".join(categories))
    logger.info("Images per category: %d", count)
    logger.info("New images to generate: %d", total_new)
    logger.info("Estimated cost: $%.2f", estimated_cost)
    logger.info("=" * 50)

    for cat in categories:
        logger.info("")
        logger.info("[%s] Generating backgrounds...", cat.upper())
        results = generate_images(cat, count=count)
        logger.info("[%s] Generated %d images", cat.upper(), len(results))

    logger.info("")
    logger.info("Done! Run 'python3 src/generate_backgrounds.py --list' to see results.")
    logger.info("Use these presets in your videos:")
    for cat in categories:
        logger.info("  photo_%s", cat)


if __name__ == "__main__":
    main()

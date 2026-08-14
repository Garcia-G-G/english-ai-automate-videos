#!/usr/bin/env python3
"""Generate a professional app icon for TikTok Developer Portal.

Migrated off dall-e-3 (removed from the OpenAI API 2026-05-12) to
gpt-image-1.5 via image_gen.py.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

from image_gen import IMAGE_MODEL, SIZE_SQUARE, estimate, generate_image, get_client

load_dotenv()

QUALITY = "high"  # An app icon is a one-off; buy the good one.

client = get_client()
if client is None:
    sys.exit(1)

PROMPT = """Design a clean, modern app icon for an English language learning app called "English Unlimited".

Requirements:
- Simple, bold design that reads well at small sizes (app icon)
- A stylized letter "E" or open book combined with a speech bubble
- Color scheme: deep blue (#1a237e) to bright blue (#0d47a1) gradient background
- White or gold accent elements
- NO text, NO words, NO letters spelled out
- NO owls, NO animals, NO cartoon characters
- Minimalist, professional style like Duolingo's simplicity but unique
- Square composition suitable for an app icon
- Clean geometric shapes, modern flat design
"""

output_dir = Path("assets/branding")
output_dir.mkdir(parents=True, exist_ok=True)

print(f"Generating app icon with {IMAGE_MODEL} "
      f"(~${estimate(1, QUALITY, SIZE_SQUARE):.3f})...")

output_path = output_dir / "app_icon.png"
result = generate_image(client, PROMPT, output_path,
                        size=SIZE_SQUARE, quality=QUALITY,
                        label="app_icon")
if result is None:
    sys.exit(1)
print(f"Saved to {output_path}")

# Also copy to docs for website
docs_path = Path("docs/icon.png")
docs_path.parent.mkdir(parents=True, exist_ok=True)
docs_path.write_bytes(output_path.read_bytes())
print(f"Also saved to {docs_path}")

print("\nDone! Use assets/branding/app_icon.png as your TikTok app icon.")

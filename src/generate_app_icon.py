#!/usr/bin/env python3
"""Generate a professional app icon for TikTok Developer Portal using DALL-E 3."""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

print("Generating app icon with DALL-E 3...")
response = client.images.generate(
    model="dall-e-3",
    prompt=PROMPT,
    size="1024x1024",
    quality="hd",
    n=1,
)

image_url = response.data[0].url
revised_prompt = response.data[0].revised_prompt
print(f"Revised prompt: {revised_prompt}")

# Download
img_data = requests.get(image_url).content
output_path = output_dir / "app_icon.png"
output_path.write_bytes(img_data)
print(f"Saved to {output_path}")

# Also copy to docs for website
docs_path = Path("docs/icon.png")
docs_path.write_bytes(img_data)
print(f"Also saved to {docs_path}")

print("\nDone! Use assets/branding/app_icon.png as your TikTok app icon.")

#!/usr/bin/env python3
"""Logo concepts for the rebrand, rendered with OpenAI gpt-image (the only
image vendor we pay for). One image per concept; pick a winner, then refine it.

    python3 tools/logo_concepts.py              # all concepts
    python3 tools/logo_concepts.py --only 1 4   # just these
    python3 tools/logo_concepts.py --dry-run    # print prompts + cost, no calls

Writes output/qa/design_proposals/logos_v2/<n>_<slug>.png and a contact sheet
with each one also shown as a small circle (how YouTube crops the avatar).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "output" / "qa" / "design_proposals" / "logos_v2"
MODEL, SIZE, QUALITY = "gpt-image-2", "1024x1024", "high"

AVATAR = ("It is the profile picture of a YouTube channel that teaches English to Spanish "
          "speakers, so it will be shown as a small circle: keep one bold, centered subject "
          "with a clear silhouette and everything important inside the central 70% of the "
          "square. Plain seamless background, no border, no watermark, no other words.")
NAME = ("Under the subject, the channel name 'English Unlimited' in two lines, spelled exactly "
        "like that, in rounded bold 3D letters: 'English' in cobalt blue (#1B6FA8), 'Unlimited' "
        "in near-black ink (#1C1812).")

CONCEPTS = [
    ("ajolote", "An original, lovable 3D mascot: a pink Mexican axolotl (ajolote) with "
     "feathery gill fronds, big glossy dark eyes with sparkles, a happy open smile, wearing small "
     "cobalt-blue headphones, holding up a white speech bubble that contains a blue infinity sign. "
     "animated-feature-film quality 3D character render, soft subsurface skin, warm studio light, sunny yellow "
     "(#F2D66B) background. " + NAME),
    ("eu_inflado", "A monogram made of two inflated, puffy 3D balloon letters 'E' and 'U' "
     "squeezed together and slightly overlapping, glossy vinyl with soft highlights: the E in "
     "cobalt blue (#1B6FA8), the U in sunny yellow (#F2D66B), the U reads like a smile. Soft "
     "studio lighting, gentle contact shadow, warm cream (#F3EEE4) background. " + NAME),
    ("burbuja_personaje", "An original designer-toy character: a chubby, glossy white speech "
     "bubble with tiny arms and legs, huge friendly eyes, rosy cheeks, waving hello with one hand; "
     "a blue infinity sign is printed on its belly. Vinyl collectible toy look, soft shadows, "
     "premium 3D render, cobalt blue (#1B6FA8) background. Under it the name 'English Unlimited' "
     "in two lines, spelled exactly like that, white rounded bold 3D letters with 'English' "
     "highlighted in sunny yellow (#F2D66B)."),
    ("infinito_cristal", "A premium 3D infinity loop made of frosted iridescent glass that "
     "twists into the outline of a speech bubble, blue-to-yellow refraction, subtle caustics and "
     "a soft glow, floating over a deep navy (#101826) background. Under it 'English Unlimited' in "
     "two lines, spelled exactly like that, clean modern rounded white letters, 'English' tinted "
     "light blue. High-end, calm, modern."),
    ("mundo_isla", "A tiny isometric 3D world on a round island shaped like a speech bubble: a "
     "red double-decker bus, a yellow taxi, a miniature Big Ben and Statue of Liberty, little "
     "trees and a road shaped like an infinity loop, soft clay render with tilt-shift depth of "
     "field, light sky-blue (#9AD1F0) background. In front of the island a small 3D sign reads "
     "'English Unlimited', spelled exactly like that, blue and dark letters."),
    ("colibri", "An original cute 3D mascot: a round, cheerful hummingbird (colibrí) with "
     "iridescent emerald and cobalt feathers, big shiny eyes, hovering with blurred wings, its long "
     "beak gently touching a white speech bubble with a blue infinity sign. Stylized animated-film "
     "3D render, warm rim light, sunny yellow (#F2D66B) background. " + NAME),
    ("plastilina_letras", "The words 'English' and 'Unlimited', spelled exactly like that and "
     "stacked in two lines, sculpted from soft modeling clay with visible fingerprints and "
     "handmade imperfections: 'English' in cobalt blue clay, 'Unlimited' in coral-red clay; a small "
     "yellow clay speech bubble with a blue clay infinity sign sits on top. Stop-motion claymation "
     "look, soft daylight, warm cream (#F3EEE4) background. This is the whole image, no other words."),
    ("sticker_3d", "A thick die-cut 3D sticker: a yellow (#F2D66B) speech bubble with a glossy "
     "cobalt-blue infinity sign, puffy beveled surface, a wide white sticker border and a slightly "
     "peeled corner casting a soft shadow, tilted a few degrees on a light blue (#9AD1F0) "
     "background. " + NAME),
]


def contact_sheet(paths: list[Path]) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    font = ROOT / "assets" / "fonts" / "Fredoka-Bold.ttf"
    f = ImageFont.truetype(str(font), 34)
    cell, small = 520, 98
    cols = 4
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell + 20) + 20, rows * (cell + 170) + 20), "#F3EEE4")
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        x, y = 20 + (i % cols) * (cell + 20), 20 + (i // cols) * (cell + 170)
        im = Image.open(p).convert("RGB").resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, (x, y))
        c = Image.open(p).convert("RGB").resize((small, small), Image.LANCZOS)
        m = Image.new("L", (small * 4, small * 4), 0)
        ImageDraw.Draw(m).ellipse((0, 0, small * 4 - 1, small * 4 - 1), fill=255)
        sheet.paste(c, (x, y + cell + 12), m.resize((small, small), Image.LANCZOS))
        d.text((x + small + 16, y + cell + 40), p.stem, font=f, fill="#1C1812")
    out = OUT / "propuestas_v2.png"
    sheet.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", type=int, help="1-based concept numbers")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    from image_gen import estimate, generate_image, get_client
    picks = [(i, c) for i, c in enumerate(CONCEPTS, 1) if not a.only or i in a.only]
    print(f"{len(picks)} images, {MODEL} {SIZE} {QUALITY}: ~${estimate(len(picks), QUALITY, SIZE, MODEL):.2f}")
    if a.dry_run:
        for i, (slug, prompt) in picks:
            print(f"\n[{i}] {slug}\n{prompt} {AVATAR}")
        return 0
    client = get_client()
    if client is None:
        return 1
    for i, (slug, prompt) in picks:
        print(f"[{i}/{len(CONCEPTS)}] {slug} …", flush=True)
        generate_image(client, f"{prompt} {AVATAR}", OUT / f"{i}_{slug}.png", size=SIZE,
                       quality=QUALITY, model=MODEL, label="logo_concept")
    done = sorted(OUT.glob("[0-9]_*.png"))
    if done:
        print("contact sheet:", contact_sheet(done).relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

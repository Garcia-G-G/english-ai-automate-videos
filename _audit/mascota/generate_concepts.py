#!/usr/bin/env python3
"""Five mascot concepts, one image each — a design-selection round.

These are five DISTINCT characters, not five poses of one. They differ in
build and attitude before they differ in what sits on the neck, which is
the whole point of the exercise: a spindly showman and a squat bouncer
read as different characters from across the room, whereas five identical
bodies wearing different heads read as one character with a hat rack.

This does NOT generate the four animation states. Four separate calls
produce four different characters — consistency does not survive across
generations. Once one concept is picked, the next step is a SINGLE
character-sheet image carrying every pose in one frame, cut into sprites
afterwards.

Run:  python3 _audit/mascota/generate_concepts.py
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from image_gen import IMAGE_MODEL, SIZE_PORTRAIT, estimate, generate_image, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = ROOT / "_audit" / "mascota"
QUALITY = "high"

# Identical wording on all five, verbatim. Any drift here stops the five
# from being comparable, which is the only thing this round is for.
SHARED_STYLE = (
    "1930s American cartoon in the rubber hose tradition. Hand-inked look: "
    "heavy black brush outlines that swell and taper, never uniform width. "
    "Pie-cut eyes with a wedge missing from each. Four-finger white gloves. "
    "Noodle arms and legs with no elbows or knees. Oversized rounded black "
    "shoes. Muted period palette: cream, dusty red, mustard, deep teal, "
    "black. Cross-hatch and stipple shading, slightly grubby aged linework. "
    "Cheerful and a little mischievous. Full body, centred, facing the "
    "viewer. Transparent background. No text, no letters, no watermark, no "
    "signature."
)

# Build and attitude first, head second — deliberately, so the model reads
# the silhouette as the defining trait rather than the object on the neck.
CONCEPTS = {
    "01_tall_showman": (
        "This character is a TALL SHOWMAN: very tall and spindly, with long thin "
        "limbs, a narrow chest, and an elongated lanky silhouette. His head is a "
        "vintage cathedral radio — the arched wooden cabinet kind — with the "
        "speaker grille forming a wide singing mouth and two round tuning dials "
        "for eyes. Both arms are thrown wide mid-announcement, he is leaning back "
        "theatrically, mid-flourish, presenting to an audience."
    ),
    "02_short_and_round": (
        "This character is SHORT AND ROUND: squat and wide, with a pear-shaped "
        "body, a heavy low centre of gravity, and short stubby limbs. His head is "
        "an open book, the two facing pages forming the face, with a red ribbon "
        "bookmark flopping over the top edge like a cowlick. He is bouncing up on "
        "the balls of his feet, eager and leaning in towards the viewer."
    ),
    "03_wiry_and_sharp": (
        "This character is WIRY AND SHARP: thin and angular, hunched forward, all "
        "sharp elbows and coiled tension in a narrow bony silhouette. His head is "
        "a vintage ribbon microphone suspended in its rectangular mount yoke. One "
        "gloved hand is cupped behind where an ear would be, listening hard. "
        "Intense, alert, coiled like a spring."
    ),
    "04_big_and_slouchy": (
        "This character is BIG AND SLOUCHY: heavy and broad-shouldered, with a "
        "bulky slack posture, slumped spine and a wide lumbering silhouette. His "
        "head is a large lightbulb with a visible glowing filament inside, and "
        "heavy-lidded pie eyes half closed. Both hands are shoved in his pockets. "
        "Deadpan, unimpressed, thoroughly unbothered."
    ),
    "05_small_and_scrappy": (
        "This character is SMALL AND SCRAPPY: tiny and short, chest puffed out, "
        "with a compact pugnacious silhouette. He has NO object for a head — he is "
        "a little fellow with an ordinary cartoon face, wearing a flat newsboy cap, "
        "grinning an enormous confident grin. Hands planted on his hips, one foot "
        "forward, cocky and full of himself."
    ),
}


def main():
    client = get_client()
    if client is None:
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    todo = [n for n in CONCEPTS if not (OUT_DIR / f"{n}.png").exists()]
    if not todo:
        logger.info("All five concepts already exist in %s", OUT_DIR)
        return 0

    logger.info("=" * 58)
    logger.info("Mascot concepts — %s, %s, %s", IMAGE_MODEL, SIZE_PORTRAIT, QUALITY)
    logger.info("To generate: %d of %d", len(todo), len(CONCEPTS))
    logger.info("Estimated cost: $%.2f", estimate(len(todo), QUALITY, SIZE_PORTRAIT))
    logger.info("=" * 58)

    spent = 0.0
    made = []
    for i, name in enumerate(todo, 1):
        logger.info("[%d/%d] %s", i, len(todo), name)
        prompt = f"{SHARED_STYLE} {CONCEPTS[name]}"
        result = generate_image(
            client, prompt, OUT_DIR / f"{name}.png",
            size=SIZE_PORTRAIT, quality=QUALITY,
            transparent=True, output_format="png",
            label=f"mascot_concept_{name}",
        )
        if result:
            made.append(result)
            spent += estimate(1, QUALITY, SIZE_PORTRAIT)

    logger.info("")
    logger.info("Generated %d/%d concepts. Actual spend: $%.2f",
                len(made), len(todo), spent)
    logger.info("Saved to: %s", OUT_DIR)
    return 0 if len(made) == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())

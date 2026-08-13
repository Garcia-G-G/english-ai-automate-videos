"""Gradient palettes generated from a seed, not hand-listed.

A fixed pool of backgrounds has a ceiling, and the arithmetic is unkind:
random selection with no memory repeats after roughly sqrt(pi*N/2) videos,
so buying variety by the asset costs a fortune for a linear-looking gain.
A `static_gradient` preset, though, is four colours, a direction and a
vignette strength — a point in a parameter space. Sampling that space has
no ceiling and costs nothing.

The catch is that most of the space is unusable. Anything bright behind the
headline band fails the text, and neighbouring samples look identical.
Generation is therefore a filter, not a formula, and the two gates are:

**Contrast.** Every candidate is rendered at full size and measured
through ``text_contrast``, exactly the measurement the enabled presets are
held to. Below the floor it is rejected outright. This is not a preference
that can be tuned away — a palette that fails here would put unreadable
text in front of a learner.

**Distinctness.** Each candidate is reduced to a small grid of CIELAB
samples and compared against every palette already accepted. Too close to
any of them and it is rejected, which is what stops the output being forty
subtly different blues. The threshold is calibrated against the hand-made
presets rather than picked from the air — see ``DEFAULT_MIN_DISTANCE``.

Generation is expensive because the contrast gate renders every candidate,
so the accepted set is baked to ``assets/palettes.json`` and loaded at
import. Same seed, same palettes, forever; a video that rendered on
``gen_017`` renders identically next week.

Regenerate with:

    python3 -m palettes --count 60 --out assets/palettes.json
"""

from __future__ import annotations

import argparse
import colorsys
import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from text_contrast import WCAG_NORMAL_TEXT, measure_frame

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PALETTES_PATH = ROOT / "assets" / "palettes.json"

# The seed the baked set was generated from. Changing it reshuffles every
# palette, so it lives here as a constant rather than a default argument
# somebody can pass past without noticing.
DEFAULT_SEED = 20260813

# Grid the rendered frame is reduced to before comparing palettes. Coarse on
# purpose: this should answer "do these look like the same background", not
# "do these differ anywhere".
FEATURE_COLS, FEATURE_ROWS = 6, 10

# Minimum mean CIELAB distance between any two accepted palettes.
#
# Calibrated against the hand-made set rather than picked from the air. The
# nine static gradients now in rotation span distances of 9.8 to 88.5, with
# a median of 47.1. The closest pair is static_midnight / static_galaxy at
# 9.8 — two dark radial purples, and honestly the pair you would drop first
# if asked to cut one.
#
# The gate sits at 12.0, deliberately above that 9.8: no two generated
# palettes may be as alike as the most alike pair a human already shipped.
# Below about 10 the tiles start reading as the same background twice.
DEFAULT_MIN_DISTANCE = 12.0

DIRECTIONS = ("vertical", "diagonal", "radial")


# ── feature extraction ───────────────────────────────────────────

def palette_feature(frame: np.ndarray) -> np.ndarray:
    """Reduce a rendered frame to a small grid of CIELAB samples."""
    import cv2

    small = cv2.resize(frame, (FEATURE_COLS, FEATURE_ROWS),
                       interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float64)
    # OpenCV packs 8-bit Lab as L in 0..255 and a/b offset by 128.
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1] -= 128.0
    lab[..., 2] -= 128.0
    return lab.reshape(-1, 3)


def feature_distance(f1: np.ndarray, f2: np.ndarray) -> float:
    """Mean CIE76 colour difference across the grid.

    CIE76 rather than CIEDE2000: the question here is whether two whole
    backgrounds read as different, where the errors CIEDE2000 corrects are
    far smaller than the distances being judged.
    """
    return float(np.sqrt(((f1 - f2) ** 2).sum(axis=1)).mean())


# ── sampling ─────────────────────────────────────────────────────

def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(r * 255))),
        max(0, min(255, round(g * 255))),
        max(0, min(255, round(b * 255))),
    )


def sample_palette(rng: random.Random) -> Dict:
    """One candidate: four colours, a direction, a vignette strength.

    Shaped rather than uniform. The stops climb a monotonic lightness ramp
    from near-black to a capped ceiling, because a gradient that is bright
    at both ends has nowhere dark for the headline to sit — sampling colours
    independently would spend most attempts on candidates the contrast gate
    throws away.
    """
    direction = rng.choices(DIRECTIONS, weights=(0.4, 0.4, 0.2))[0]

    # Radial puts its first stop at the centre of the frame, which is very
    # near the headline band, so its bright end has to stay darker.
    l_max = rng.uniform(0.18, 0.30) if direction == "radial" else rng.uniform(0.28, 0.58)
    l_min = rng.uniform(0.02, 0.07)

    ramp = [l_min + (l_max - l_min) * (i / 3) ** rng.uniform(0.9, 1.8)
            for i in range(4)]

    base_hue = rng.random()
    scheme = rng.choices(("analogous", "accent", "split"),
                         weights=(0.45, 0.35, 0.20))[0]
    if scheme == "analogous":
        drift = rng.uniform(0.04, 0.14) * rng.choice((-1, 1))
        hues = [(base_hue + drift * i) % 1.0 for i in range(4)]
    elif scheme == "accent":
        # Three related stops and one that jumps, for a gradient that turns
        # a corner rather than fading along one hue.
        jump = rng.uniform(0.30, 0.50) * rng.choice((-1, 1))
        drift = rng.uniform(0.02, 0.08) * rng.choice((-1, 1))
        hues = [(base_hue + drift * i) % 1.0 for i in range(3)]
        hues.append((base_hue + jump) % 1.0)
    else:
        step = rng.uniform(0.12, 0.22) * rng.choice((-1, 1))
        hues = [(base_hue + step * i) % 1.0 for i in range(4)]

    sat_low = rng.uniform(0.30, 0.60)
    sat_high = rng.uniform(0.60, 0.98)
    sats = [sat_low + (sat_high - sat_low) * (i / 3) for i in range(4)]

    colors = [_hex(*colorsys.hls_to_rgb(h, l, s))
              for h, l, s in zip(hues, ramp, sats)]

    # Radial reads inner→outer, so the bright end belongs at the centre.
    if direction != "radial":
        if rng.random() < 0.5:
            colors.reverse()
    else:
        colors.reverse()

    return {
        "type": "static_gradient",
        "colors": colors,
        "direction": direction,
        "vignette_strength": round(rng.uniform(0.15, 0.40), 3),
    }


# ── generation ───────────────────────────────────────────────────

def generate(count: int = 60,
             seed: int = DEFAULT_SEED,
             floor: float = WCAG_NORMAL_TEXT,
             min_distance: float = DEFAULT_MIN_DISTANCE,
             max_attempts: int = 4000,
             progress: bool = False) -> Tuple[List[Dict], Dict[str, int]]:
    """Sample until ``count`` palettes pass both gates.

    Returns the accepted palettes, in acceptance order, and a tally of why
    candidates were turned away. Greedy and order-dependent by design: the
    distinctness test compares against what has already been accepted, so
    the same seed must replay the same sequence to reproduce the same set.
    """
    from backgrounds import BackgroundGenerator

    gen = BackgroundGenerator(1080, 1920)
    rng = random.Random(seed)

    accepted: List[Dict] = []
    features: List[np.ndarray] = []
    stats = {"attempts": 0, "rejected_contrast": 0, "rejected_similar": 0}

    while len(accepted) < count and stats["attempts"] < max_attempts:
        stats["attempts"] += 1
        spec = sample_palette(rng)

        frame = gen.static_gradient(
            colors=spec["colors"],
            direction=spec["direction"],
            vignette_strength=spec["vignette_strength"],
        )

        metrics = measure_frame(frame)
        if metrics["contrast_worst"] < floor:
            stats["rejected_contrast"] += 1
            continue

        feat = palette_feature(frame)
        if features:
            nearest = min(feature_distance(feat, f) for f in features)
            if nearest < min_distance:
                stats["rejected_similar"] += 1
                continue
        else:
            nearest = float("inf")

        spec = dict(spec)
        spec["contrast_worst"] = round(metrics["contrast_worst"], 2)
        spec["contrast_mean"] = round(metrics["contrast_mean"], 2)
        spec["nearest_neighbour"] = (round(nearest, 1)
                                     if nearest != float("inf") else None)
        accepted.append(spec)
        features.append(feat)

        if progress and len(accepted) % 10 == 0:
            print(f"  {len(accepted)}/{count} accepted "
                  f"({stats['attempts']} tried)")

    return accepted, stats


def pairwise_distances(specs: Sequence[Dict]) -> np.ndarray:
    """Full distance matrix for a set of palettes — for reporting."""
    from backgrounds import BackgroundGenerator

    gen = BackgroundGenerator(1080, 1920)
    feats = [palette_feature(gen.static_gradient(
        colors=s["colors"], direction=s["direction"],
        vignette_strength=s["vignette_strength"])) for s in specs]

    n = len(feats)
    d = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            d[i, j] = d[j, i] = feature_distance(feats[i], feats[j])
    return d


# ── baking and loading ───────────────────────────────────────────

def palette_name(index: int) -> str:
    return f"gen_{index + 1:03d}"


def save(accepted: Sequence[Dict], stats: Dict, path: Path,
         seed: int, floor: float, min_distance: float) -> None:
    payload = {
        "_comment": "Generated by src/palettes.py — do not hand-edit. "
                    "Regenerate: python3 -m palettes",
        "seed": seed,
        "contrast_floor": floor,
        "min_distance": min_distance,
        "stats": stats,
        "palettes": {palette_name(i): s for i, s in enumerate(accepted)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def load_palettes(path: Path = PALETTES_PATH) -> Dict[str, Dict]:
    """The baked palettes as preset specs, ready for BACKGROUND_PRESETS.

    Returns an empty dict if the file is missing rather than raising — a
    checkout without it should still render, just without generated
    backgrounds.
    """
    if not path.exists():
        logger.warning("No generated palettes at %s — run python3 -m palettes", path)
        return {}

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Could not read generated palettes from %s: %s", path, e)
        return {}

    presets = {}
    for name, spec in payload.get("palettes", {}).items():
        presets[name] = {
            "type": spec["type"],
            "colors": spec["colors"],
            "direction": spec["direction"],
            "vignette_strength": spec["vignette_strength"],
        }
    return presets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--floor", type=float, default=WCAG_NORMAL_TEXT)
    ap.add_argument("--min-distance", type=float, default=DEFAULT_MIN_DISTANCE)
    ap.add_argument("--out", default=str(PALETTES_PATH))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print(f"Generating {args.count} palettes (seed {args.seed}, "
          f"floor {args.floor}:1, min distance {args.min_distance}) ...")
    accepted, stats = generate(args.count, args.seed, args.floor,
                               args.min_distance, progress=True)

    if len(accepted) < args.count:
        print(f"WARNING: only {len(accepted)} of {args.count} accepted "
              f"within {stats['attempts']} attempts")

    save(accepted, stats, Path(args.out), args.seed, args.floor, args.min_distance)

    worst = min(s["contrast_worst"] for s in accepted)
    nearest = [s["nearest_neighbour"] for s in accepted if s["nearest_neighbour"]]
    print(f"\naccepted            {len(accepted)}")
    print(f"attempts            {stats['attempts']}")
    print(f"rejected, contrast  {stats['rejected_contrast']}")
    print(f"rejected, similar   {stats['rejected_similar']}")
    print(f"contrast floor      {worst}:1")
    print(f"closest pair        {min(nearest):.1f} (gate {args.min_distance})")
    print(f"written to          {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

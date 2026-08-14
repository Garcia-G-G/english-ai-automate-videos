#!/usr/bin/env python3
"""The hue gate has to agree with the eye that set it.

    python3 -m pytest tests/test_palette_gates.py

Contrast and distinctness both pass palettes that look cheap: complementary
ramps that go brown where the ends meet, and anything landing in olive. The
third gate encodes what the hand-made set does and the rejected palettes do
not — so the test that matters is whether it reproduces the judgement it was
derived from.

Two reference sets, both from the operator:

    the nine hand-made gradients in rotation      — must all pass
    seven generated palettes called out as good   — must all pass
    nine generated palettes called out as bad     — must all be rejected

If a threshold is ever retuned, this is what says whether it still means
what it meant.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import BACKGROUND_PRESETS, BackgroundGenerator  # noqa: E402
from palettes import (  # noqa: E402
    MAX_HUE_ARC, MIN_CHROMA_MEDIAN, hue_arc, hue_discipline, stop_hues,
)

# In rotation, and the reference for what good looks like here.
HAND_MADE = ["static_sunset", "static_ocean", "static_purple", "static_neon",
             "static_emerald", "static_midnight", "static_fire",
             "static_galaxy", "static_teal"]

# Called out as working: adjacent hues, high saturation.
APPROVED = ["gen_008", "gen_011", "gen_013", "gen_028", "gen_031",
            "gen_038", "gen_058"]

# Called out as cheap. gen_051 is the red-to-green one that goes brown in the
# middle; gen_018/026/036/046 land in olive; gen_003/021/041/053 are muddy or
# washed out.
REJECTED = ["gen_051", "gen_018", "gen_026", "gen_036", "gen_046",
            "gen_003", "gen_021", "gen_041", "gen_053"]


@pytest.fixture(scope="module")
def generator():
    return BackgroundGenerator(1080, 1920)


def _judge(generator, name):
    spec = BACKGROUND_PRESETS[name]
    frame = generator.static_gradient(
        colors=spec["colors"], direction=spec["direction"],
        vignette_strength=spec["vignette_strength"])
    return hue_discipline(spec, frame)


@pytest.mark.parametrize("name", HAND_MADE)
def test_the_hand_made_set_passes_its_own_gate(generator, name):
    """A gate derived from these that then rejects one of them is wrong."""
    verdict = _judge(generator, name)
    assert verdict["ok"], f"{name} is in rotation but fails: {verdict['reasons']}"


@pytest.mark.parametrize("name", APPROVED)
def test_the_approved_palettes_pass(generator, name):
    verdict = _judge(generator, name)
    assert verdict["ok"], f"{name} was called good but fails: {verdict['reasons']}"


@pytest.mark.parametrize("name", REJECTED)
def test_the_cheap_palettes_are_rejected(generator, name):
    verdict = _judge(generator, name)
    assert not verdict["ok"], (
        f"{name} was called cheap but passes — arc {verdict['hue_arc']:.0f}, "
        f"mud {verdict['mud_fraction'] * 100:.0f}%, "
        f"chroma {verdict['chroma_median']:.1f}")


def test_the_olive_band_is_what_separates_them(generator):
    """The mud band does most of the work, and the reference sets sit at zero.

    Recorded because it is the claim the threshold rests on: if hand-made or
    approved palettes ever put pixels in the olive band, the band is drawn in
    the wrong place.
    """
    for name in HAND_MADE + APPROVED:
        assert _judge(generator, name)["mud_fraction"] == 0.0, (
            f"{name} has lit pixels in the olive band; the band is misplaced")


def test_a_complementary_ramp_is_rejected_on_arc_alone():
    """gen_051, the red-to-green one that goes brown where they meet.

    Its own colours rather than invented ones, so the test cannot drift away
    from the case it stands for.
    """
    red_to_green = ["#0f0a05", "#481d0e", "#86130d", "#12fcb4"]
    assert hue_arc(stop_hues(red_to_green)) > MAX_HUE_ARC


def test_an_analogous_ramp_passes_on_arc():
    """static_purple's colours: four adjacent hues, and in rotation."""
    assert hue_arc(stop_hues(["#0a0015", "#2d1b69", "#7c3aed", "#c084fc"])) <= MAX_HUE_ARC


def test_the_chroma_floor_is_the_hand_made_minimum(generator):
    """The floor is read off static_teal, so static_teal must clear it.

    It clears it by almost nothing, which is the point: the floor cannot be
    raised without throwing out a preset already in rotation. This test fails
    if someone raises it anyway.
    """
    lowest = min(_judge(generator, n)["chroma_median"] for n in HAND_MADE)
    assert lowest >= MIN_CHROMA_MEDIAN, (
        f"the hand-made minimum is {lowest:.3f}, below the floor "
        f"{MIN_CHROMA_MEDIAN} — the floor is no longer derived from it")
    assert lowest - MIN_CHROMA_MEDIAN < 1.0, (
        "the floor has drifted below the hand-made minimum and stopped biting")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

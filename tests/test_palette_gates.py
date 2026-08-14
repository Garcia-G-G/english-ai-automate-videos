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

# In rotation, and the reference for what good looks like here. Referenced by
# name because these are hand-written and stable.
HAND_MADE = ["static_sunset", "static_ocean", "static_purple", "static_neon",
             "static_emerald", "static_midnight", "static_fire",
             "static_galaxy", "static_teal"]

# The judged palettes, frozen as literal colours rather than looked up by name.
#
# gen_NNN names are positional in assets/palettes.json, so regenerating
# reassigns every one of them — the first version of this file referenced the
# names and started testing sixteen unrelated palettes the moment the third
# gate changed the output. These are the exact specs that were looked at,
# recovered from the palettes.json of commit adec16e. Names kept only so the
# failure messages match the conversation they came from.
#
# Adding a gate should not change these. If a threshold moves and one of these
# flips, the threshold stopped meaning what it was derived to mean.

# Called out as working: adjacent hues, high saturation.
APPROVED = [
    ("gen_008", ['#070815', '#130b2c', '#330f4d', '#761280'], "vertical", 0.17),
    ("gen_011", ['#760ecd', '#152a71', '#123637', '#050a06'], "diagonal", 0.259),
    ("gen_013", ['#0d0504', '#2e0d23', '#3c175b', '#24429f'], "diagonal", 0.287),
    ("gen_028", ['#8742db', '#2328a0', '#0f273c', '#061514'], "diagonal", 0.163),
    ("gen_031", ['#040c9e', '#550c6e', '#430d25', '#180d07'], "vertical", 0.25),
    ("gen_038", ['#2380bc', '#291e7e', '#301037', '#0f060a'], "diagonal", 0.264),
    ("gen_058", ['#170613', '#390f58', '#0f20ac', '#11c9fa'], "vertical", 0.392),
]

# Called out as cheap. gen_051 is the red-to-green one that goes brown in the
# middle; gen_018/026/036/046 land in olive; gen_003/021/041/053 are muddy or
# washed out.
REJECTED = [
    ("gen_051", ['#0f0a05', '#481d0e', '#86130d', '#12fcb4'], "diagonal", 0.292),
    ("gen_018", ['#0c170c', '#293b16', '#7f7d1f', '#c76b1a'], "vertical", 0.346),
    ("gen_026", ['#100d07', '#1f210b', '#365e17', '#18951c'], "diagonal", 0.195),
    ("gen_036", ['#249847', '#165d1a', '#0f2609', '#0a1104'], "diagonal", 0.23),
    ("gen_046", ['#1d785a', '#164e1b', '#1a270d', '#131207'], "vertical", 0.391),
    ("gen_003", ['#12180a', '#353311', '#74451c', '#b5201e'], "vertical", 0.392),
    ("gen_021", ['#680528', '#0b4326', '#0b2111', '#060c07'], "radial", 0.327),
    ("gen_041", ['#501b6d', '#13203a', '#0f241d', '#060904'], "radial", 0.167),
    ("gen_053", ['#040e0c', '#0b2c2f', '#113a52', '#194697'], "vertical", 0.368),
]


@pytest.fixture(scope="module")
def generator():
    return BackgroundGenerator(1080, 1920)


def _judge_spec(generator, colors, direction, vignette):
    spec = {"colors": colors, "direction": direction,
            "vignette_strength": vignette}
    frame = generator.static_gradient(
        colors=colors, direction=direction, vignette_strength=vignette)
    return hue_discipline(spec, frame)


def _judge(generator, name):
    spec = BACKGROUND_PRESETS[name]
    return _judge_spec(generator, spec["colors"], spec["direction"],
                       spec["vignette_strength"])


@pytest.mark.parametrize("name", HAND_MADE)
def test_the_hand_made_set_passes_its_own_gate(generator, name):
    """A gate derived from these that then rejects one of them is wrong."""
    verdict = _judge(generator, name)
    assert verdict["ok"], f"{name} is in rotation but fails: {verdict['reasons']}"


@pytest.mark.parametrize("name,colors,direction,vignette", APPROVED)
def test_the_approved_palettes_pass(generator, name, colors, direction, vignette):
    verdict = _judge_spec(generator, colors, direction, vignette)
    assert verdict["ok"], f"{name} was called good but fails: {verdict['reasons']}"


@pytest.mark.parametrize("name,colors,direction,vignette", REJECTED)
def test_the_cheap_palettes_are_rejected(generator, name, colors, direction, vignette):
    verdict = _judge_spec(generator, colors, direction, vignette)
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
    for name in HAND_MADE:
        assert _judge(generator, name)["mud_fraction"] == 0.0, (
            f"{name} has lit pixels in the olive band; the band is misplaced")
    for name, colors, direction, vignette in APPROVED:
        assert _judge_spec(generator, colors, direction,
                           vignette)["mud_fraction"] == 0.0, (
            f"{name} has lit pixels in the olive band; the band is misplaced")


def test_every_shipped_palette_passes_the_gate_it_was_generated_under(generator):
    """Whatever is in assets/palettes.json now must satisfy all three gates.

    The set is regenerated by hand, so this is the check that the file on
    disk was produced by the gates currently in the code and not by an
    earlier, laxer version of them.
    """
    from palettes import load_palettes

    for name, spec in load_palettes().items():
        verdict = _judge_spec(generator, spec["colors"], spec["direction"],
                              spec["vignette_strength"])
        assert verdict["ok"], (
            f"{name} is shipped but fails the current gate: {verdict['reasons']}"
            " — regenerate with `python3 -m palettes`")


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

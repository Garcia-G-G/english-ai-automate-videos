#!/usr/bin/env python3
"""A generated background must clear the contrast floor or not be used.

    python3 -m pytest tests/test_topic_background_gate.py

The previous photo set shipped with no gate and six of its eleven presets
measured at or under 3.7:1 behind the headline, against a 3.0 floor for large
text and the 4.5 this project holds its palettes to. Per-video generated
images put an unsupervised image generator on the main path, so the gate is
the whole safety story and it is tested rather than assumed.
"""

import re
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import topic_background_gate as gate  # noqa: E402
from topic_background import build_prompt  # noqa: E402


def _write(tmp_path, arr, name="bg.png"):
    p = tmp_path / name
    Image.fromarray(arr.astype(np.uint8)).save(p)
    return p


def test_a_dark_middle_band_passes(tmp_path):
    """The shape every prompt asks for: bright edges, dark centre."""
    a = np.zeros((1536, 1024, 3), dtype=np.uint8)
    a[:512] = 150
    a[-512:] = 150
    img = _write(tmp_path, a)
    r = gate.measure(img)
    assert r["passes"], f"a dark middle band should pass, got {r['worst_ratio']:.2f}"


def test_a_bright_middle_band_is_refused(tmp_path):
    """The failure the old photo set had: brightest region behind the text."""
    a = np.full((1536, 1024, 3), 20, dtype=np.uint8)
    a[400:1100] = 235
    img = _write(tmp_path, a)
    r = gate.measure(img)
    assert not r["passes"], f"a bright middle band must fail, got {r['worst_ratio']:.2f}"


def test_a_uniformly_bright_image_is_refused(tmp_path):
    img = _write(tmp_path, np.full((1536, 1024, 3), 240, dtype=np.uint8))
    assert not gate.measure(img)["passes"]


def test_worst_case_not_average(tmp_path):
    """One bright patch under the headline is enough to refuse the image.

    Averaged over the frame this image is dark; the camera passes the patch
    under the card partway through the cycle, and those seconds are where a
    viewer gives up.
    """
    a = np.full((1536, 1024, 3), 12, dtype=np.uint8)
    a[600:900, 200:800] = 250
    img = _write(tmp_path, a)
    r = gate.measure(img)
    assert not r["passes"]
    assert len(r["samples"]) == gate.SAMPLES, "must sample across the cycle"


def test_a_broken_image_is_refused_not_waved_through(tmp_path):
    """A gate that cannot measure must refuse."""
    bad = tmp_path / "truncated.png"
    bad.write_bytes(b"not a png")
    r = gate.accept(bad, topic="whatever")
    assert r["passes"] is False
    assert "error" in r


def test_the_floor_matches_the_palette_floor():
    """One number governs both, so a generated image is held to what the
    generated palettes were held to."""
    from text_contrast import WCAG_NORMAL_TEXT
    assert gate.FLOOR == WCAG_NORMAL_TEXT == 4.5


#: Words the prompt must never contain again. Asking for these is what
#: produced eleven identical dark rooms: the contrast gate rewards darkness
#: without limit, so "satisfy the gate" and "make it dark" became the same
#: instruction. Readability is composited in code now.
#: Matched on word boundaries — "sunlit" contains "unlit" and is its
#: opposite, so a substring test would reject exactly the stems we want.
FORBIDDEN = ("dark", "darker", "night", "dimly", "low-lit", "low lit",
             "shadow", "shadowed", "dusk", "unlit", "gloom", "gloomy")


def _forbidden_hits(text: str):
    low = text.lower()
    return [w for w in FORBIDDEN if re.search(rf"\b{re.escape(w)}\b", low)]


def test_the_prompt_asks_for_a_picture_not_a_shadow():
    p = build_prompt("break the ice", "idioms")
    low = p.lower()
    assert not _forbidden_hits(p), f"prompt still asks for {_forbidden_hits(p)}: {p}"
    assert "vivid" in low and "colourful" in low
    assert "uncluttered" in low, "the middle band is a COMPOSITION instruction"
    assert "no text" in low and "no legible faces" in low, "constraints kept"
    assert "break the ice" in p, "the topic has to reach the prompt"


def test_no_scene_stem_asks_for_darkness():
    """The stems, not just the shared tail."""
    from topic_background import CATEGORY_SCENES, LIGHT
    for cat, scenes in CATEGORY_SCENES.items():
        for scene in scenes:
            assert not _forbidden_hits(scene), f"{cat}: {scene!r} {_forbidden_hits(scene)}"
    for light in LIGHT:
        assert not _forbidden_hits(light), f"LIGHT {light!r} {_forbidden_hits(light)}"


def test_every_real_category_has_scenes():
    """The table is built against the directory, not from memory.

    The previous dict had 11 keys for 20 categories and two orphans that no
    category used, so eleven categories shared one stem.
    """
    from topic_background import CATEGORY_SCENES
    real = {p.stem for p in (ROOT / "content" / "topics").glob("*.json")}
    assert real, "no categories found on disk — check the path"
    missing = real - set(CATEGORY_SCENES)
    orphans = set(CATEGORY_SCENES) - real
    assert not missing, f"categories with no scenes: {sorted(missing)}"
    assert not orphans, f"scene keys no category uses: {sorted(orphans)}"
    for cat, scenes in CATEGORY_SCENES.items():
        assert len(scenes) >= 2, f"{cat} has one scene; two videos would match"


def test_the_prompt_space_is_large_enough_to_not_repeat():
    from topic_background import prompt_space
    space = prompt_space()
    assert space["categories"] == 20
    assert space["per_category_min"] >= 16, space
    assert space["total"] >= 300, space


def test_the_scrim_makes_a_bright_image_readable(tmp_path):
    """Contrast by construction, which is the whole point of the change."""
    from topic_background import apply_readability_scrim
    bright = np.full((1536, 1024, 3), 235, dtype=np.uint8)
    img = _write(tmp_path, bright, "bright.png")
    assert not gate.measure(img)["passes"], "a white frame should start failing"

    apply_readability_scrim(img)

    after = gate.measure(img)
    assert after["passes"], (
        f"the scrim must guarantee the floor, got {after['worst_ratio']:.2f}")


def test_the_scrim_leaves_the_edges_alone(tmp_path):
    """It is a band, not an exposure change. The picture must survive."""
    from topic_background import apply_readability_scrim
    bright = np.full((1536, 1024, 3), 220, dtype=np.uint8)
    img = _write(tmp_path, bright, "edges.png")
    apply_readability_scrim(img)

    out = np.array(Image.open(img).convert("RGB"))
    assert out[:60].mean() > 200, "the top of the frame was darkened"
    assert out[-60:].mean() > 200, "the bottom of the frame was darkened"


def test_the_scrim_has_no_seam(tmp_path):
    """A visible edge would be worse than the dark images this replaces."""
    from topic_background import apply_readability_scrim
    flat = np.full((1536, 1024, 3), 200, dtype=np.uint8)
    img = _write(tmp_path, flat, "seam.png")
    apply_readability_scrim(img)

    col = np.array(Image.open(img).convert("RGB"), dtype=float)[:, 512, 0]
    step = np.abs(np.diff(col)).max()
    assert step < 3.0, f"largest row-to-row step is {step:.2f}, that is a seam"

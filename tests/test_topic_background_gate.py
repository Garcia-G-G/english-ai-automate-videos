#!/usr/bin/env python3
"""A generated background must clear the contrast floor or not be used.

    python3 -m pytest tests/test_topic_background_gate.py

The previous photo set shipped with no gate and six of its eleven presets
measured at or under 3.7:1 behind the headline, against a 3.0 floor for large
text and the 4.5 this project holds its palettes to. Per-video generated
images put an unsupervised image generator on the main path, so the gate is
the whole safety story and it is tested rather than assumed.
"""

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


def test_the_prompt_pins_the_exposure():
    """The compositional instruction is what keeps text readable."""
    p = build_prompt("break the ice", "idioms")
    low = p.lower()
    assert "deep shadow" in low and "top third" in low and "bottom third" in low
    assert "no text" in low and "no legible faces" in low
    assert "break the ice" in p, "the topic has to reach the prompt"

#!/usr/bin/env python3
"""Asking for a different background must produce a different background.

    python3 -m pytest tests/test_background_cache_switches.py

render_static_once only rendered when _static_frame was None:

    if not hasattr(self, '_static_frame') or self._static_frame is None:
        self._static_frame = self.render_from_preset(0, preset_name, ...)
        self._cache_preset = preset_name

so the SECOND video in a process got the FIRST video's background, and every
one after it did too. _cache_preset was already being stored and nothing ever
read it.

Invisible to `main.py --batch`, where each video is its own process — which is
why the six-video batch looked fine. Guaranteed in the dashboard, which
renders every video in one long-running Streamlit process, and that is the
path the operator actually uses.

The second direction is the same bug reversed: gradient() consults
get_static_frame() BEFORE has_cache(), so a static frame left over from an
earlier preset also wins over an animated loop rendered afterwards.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backgrounds import BACKGROUND_PRESETS  # noqa: E402


@pytest.fixture
def generator():
    from backgrounds import BackgroundGenerator
    return BackgroundGenerator(width=270, height=480)


def _statics(generator, names):
    return [generator.render_static_once(n).copy() for n in names]


def test_switching_preset_renders_the_new_one(generator):
    a, b = _statics(generator, ["gen_001", "gen_030"])
    assert not np.array_equal(a, b), (
        "gen_030 returned gen_001's frame — the cache ignored the preset")


def test_every_preset_in_a_run_is_its_own(generator):
    """Six videos in one process, the dashboard case."""
    names = ["gen_001", "gen_030", "gen_056", "static_ocean", "gen_010", "gen_021"]
    frames = _statics(generator, names)
    seen = set()
    for name, f in zip(names, frames):
        key = f[::40, ::40].tobytes()
        assert key not in seen, f"{name} reused an earlier preset's frame"
        seen.add(key)


def test_switching_back_returns_the_original(generator):
    first = generator.render_static_once("gen_001").copy()
    generator.render_static_once("gen_030")
    again = generator.render_static_once("gen_001").copy()
    assert np.array_equal(first, again), "same preset should render the same"


def test_the_cached_preset_name_tracks_what_was_rendered(generator):
    for name in ("gen_001", "gen_030", "static_ocean"):
        generator.render_static_once(name)
        assert generator._cache_preset == name


@pytest.mark.skipif(
    not any(p.get("type") != "static_gradient" for p in BACKGROUND_PRESETS.values()),
    reason="no animated preset available")
def test_an_animated_preset_clears_the_stale_static_frame(generator):
    """gradient() checks get_static_frame() first, so it must be dropped."""
    generator.render_static_once("gen_001")
    assert generator.get_static_frame() is not None

    animated = next(n for n, p in BACKGROUND_PRESETS.items()
                    if p.get("type") != "static_gradient")
    generator.pre_render_loop(animated, loop_duration=0.2, fps=5,
                              show_progress=False)

    assert generator.get_static_frame() is None, (
        "a static frame from an earlier preset outranks the animated loop")

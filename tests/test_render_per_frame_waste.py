#!/usr/bin/env python3
"""Two per-frame costs the renderer pays for a value that never changes.

    python3 -m pytest tests/test_render_per_frame_waste.py

Measured on a real dashboard render (fill_blank, 34.4s audio, 1033 frames,
static_ocean, 219s total, cProfile sorted by tottime):

    yaml parsing         ~19.2s   9%   4.5M yaml/reader.forward calls
    static_gradient      ~23.3s  11%   150 calls for one distinct frame

Both are the same bug class: a result that is constant for the whole render
is recomputed per frame (or per cache slot), because the cheap path exists
but nothing routes to it.

CONFIG RELOAD. get_character_renderer() memoises into the module global
`_renderer`, but the disabled branch returns None *before* assigning it — and
`character.enabled` is false in config.yaml. So the memo never fills, and
every frame re-runs _load_config() -> yaml.safe_load over the whole
config.yaml. The renderer draws no character at all; the parse is pure waste.

STATIC LOOP. `static_ocean` is type "static_gradient" — render_from_preset
ignores t for it, so all frames are byte-identical. generate_video still
calls pre_render_loop(), which renders and retains 150 copies of one
1080x1920x3 frame (~930MB nominal). render_static_once() renders one and is
only reachable under fast_mode. 69 of the 76 enabled presets are
static_gradient, so ~91% of random picks pay this.

Neither test measures time. Both pin the call/allocation count that the
timing follows from, which is stable under load and on any machine.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.character as character                            # noqa: E402
from backgrounds import BACKGROUND_PRESETS, BackgroundGenerator  # noqa: E402


# ── config reload ────────────────────────────────────────────────────

@pytest.fixture
def fresh_character_module(monkeypatch):
    """Reset the renderer memo so each test starts un-resolved."""
    monkeypatch.setattr(character, "_renderer", None, raising=False)
    monkeypatch.setattr(character, "_renderer_resolved", False, raising=False)
    return character


def test_disabled_character_reads_config_once_not_per_frame(
        fresh_character_module, monkeypatch):
    """The disabled branch must memoise too, or every frame parses YAML."""
    calls = []

    def counting_load_config():
        # Stands in for the real yaml.safe_load so the count does not depend
        # on config.yaml still saying enabled: false.
        calls.append(1)
        return {"character": {"enabled": False}}

    monkeypatch.setattr(character, "_load_config", counting_load_config)

    for _ in range(50):
        assert character.get_character_renderer() is None

    assert len(calls) == 1, (
        f"config.yaml parsed {len(calls)} times for 50 frames; "
        "the disabled branch returns before filling the memo"
    )


# ── static background loop ───────────────────────────────────────────

def test_static_gradient_preset_caches_one_frame_not_a_loop():
    """A preset whose frames are identical must not retain a 150-frame loop."""
    preset = "static_ocean"
    assert BACKGROUND_PRESETS[preset]["type"] == "static_gradient"

    from video import prepare_background_cache

    bg = BackgroundGenerator(120, 200)          # small: this test renders
    prepare_background_cache(bg, preset, duration=34.4)

    assert bg.get_static_frame() is not None, \
        "static preset should be rendered once into the static slot"
    assert len(bg._frame_cache) == 0, (
        f"static preset retained {len(bg._frame_cache)} looped frames; "
        "one distinct frame needs one"
    )


@pytest.mark.parametrize("preset", ["static_ocean", "static_midnight", "static_fire"])
def test_static_preset_loop_and_single_frame_are_pixel_identical(preset):
    """What makes dropping the loop safe: the loop held one distinct frame.

    This is the invariant, not the optimisation. If a 'static_gradient'
    preset ever starts varying with t, this fails and the loop must come
    back for it — the speed tests above would stay green and say nothing.
    """
    assert BACKGROUND_PRESETS[preset]["type"] == "static_gradient"

    looped = BackgroundGenerator(180, 320)
    looped.pre_render_loop(preset, loop_duration=5.0, show_progress=False)
    once = BackgroundGenerator(180, 320)
    once.render_static_once(preset)

    assert len({f.tobytes() for f in looped._frame_cache.values()}) == 1, \
        "pre_render_loop produced frames that differ — preset is not static"

    static = once.get_static_frame()
    for t in (0.0, 1.3, 2.7, 4.9, 17.0, 33.9):
        assert np.array_equal(looped.get_cached_frame(t), static), \
            f"looped frame at t={t} differs from the single static render"


def test_animated_gradient_preset_still_pre_renders_its_loop():
    """The fix must not flatten backgrounds that genuinely animate."""
    preset = "purple_vibes"
    assert BACKGROUND_PRESETS[preset]["type"] == "animated_gradient"

    from video import prepare_background_cache

    bg = BackgroundGenerator(120, 200)
    prepare_background_cache(bg, preset, duration=34.4)

    assert len(bg._frame_cache) > 1, \
        "animated preset must keep its pre-rendered loop"

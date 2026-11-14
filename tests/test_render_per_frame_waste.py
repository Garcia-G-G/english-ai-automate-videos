#!/usr/bin/env python3
"""A per-frame cost the renderer paid for a value that never changes.

    python3 -m pytest tests/test_render_per_frame_waste.py

Measured on a real dashboard render (fill_blank, 34.4s audio, 1033 frames,
static_ocean, 219s total, cProfile sorted by tottime):

    yaml parsing         ~19.2s   9%   4.5M yaml/reader.forward calls

A result that is constant for the whole render was recomputed per frame,
because the cheap path existed but nothing routed to it.

CONFIG RELOAD. get_character_renderer() memoises into the module global
`_renderer`, but the disabled branch returns None *before* assigning it — and
`character.enabled` is false in config.yaml. So the memo never fills, and
every frame re-runs _load_config() -> yaml.safe_load over the whole
config.yaml. The renderer draws no character at all; the parse is pure waste.

The test does not measure time. It pins the call count that the
timing follows from, which is stable under load and on any machine.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.character as character                            # noqa: E402


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


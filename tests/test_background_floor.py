#!/usr/bin/env python3
"""The background cascade must land on footage, or refuse — never on a colour.

    python3 -m pytest tests/test_background_floor.py

THE RULE: un default solo puede renderizar MENOS, nunca algo falso. A flat
colour field where moving footage was promised is not less, it is something
else, and the operator cannot tell the two apart by looking at the job row.

THREE STRUCTURAL DEFECTS, all present before this file existed:

  1. THE FLOOR WAS 76 FLAT PRESETS. resolve_background's last tier picks at
     random from the enabled rotation. Expanded, that rotation is 69 static
     gradients and 7 animated ones — 76 names, none of them footage. So the
     moment Pexels declines for every query, the video silently becomes a
     colour field. 220 clips sit on disk and no tier had ever consulted them.

  2. FIVE OF SEVEN RETURN PATHS RECORDED NOTHING. `on_record` was threaded
     into the clip and image tiers only, so tiers 0, 1, 2, 5 and 6 returned
     without saying what they decided. That is why a pinned background wrote
     `background: null` — and it is why a null record could mean either "an
     instruction nobody logged" or "the floor fired", which are opposite
     situations.

  3. THE PRESET TIERS ARE GONE, and the tests that covered them were
     deleted rather than adjusted — fast_mode, the explicit preset name, the
     config pin and the v2 branch no longer exist to be tested. What this
     file still owns is the CACHE TIER and the REFUSAL; the shape of the
     cascade and the absence of the presets live in test_footage_only.py.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline  # noqa: E402
import topic_clips  # noqa: E402


@pytest.fixture
def no_network(monkeypatch):
    """Pexels declines every query, exactly as it would with no egress."""
    monkeypatch.setattr(topic_clips, "search", lambda *a, **k: [])
    monkeypatch.setattr(topic_clips, "api_key", lambda: None)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An isolated clip cache, so the real 102-slot one is never consulted."""
    root = tmp_path / "_cache"
    root.mkdir()
    monkeypatch.setattr(topic_clips, "CACHE_DIR", root)
    return root


def _cached_clip(cache_root: Path, query: str, name: str = "pexels_1.mp4"):
    """One cache slot, shaped exactly as topic_clips.fetch_query writes it."""
    slot = cache_root / topic_clips._slug(query)[:48]
    slot.mkdir(parents=True, exist_ok=True)
    (slot / name).write_bytes(b"\0" * 2048)
    (slot / "query.json").write_text(json.dumps({
        "query": query, "pexels_id": 1, "duration": 8.0,
        "width": 1080, "height": 1920, "fps": 30.0,
    }), encoding="utf-8")
    return slot / name


def _resolve(**kwargs):
    """resolve_background with a recorder attached, returning both."""
    seen = []
    value = pipeline.resolve_background(on_record=seen.append, **kwargs)
    return value, (seen[-1] if seen else None)


# ══════════════ §1 · the cache is a tier, between fetch and floor ══════════════

def test_the_cache_is_used_when_pexels_declines(no_network, cache, tmp_path):
    """220 clips were on disk and no tier had ever looked at one. A degraded
    background that is STILL FOOTAGE keeps the rule; a colour field does not."""
    _cached_clip(cache, "aerial drone shot waves on a wide beach")

    value, record = _resolve(topic="set up", category="phrasal_verbs",
                             dest_dir=tmp_path / "clips", duration=20.0)

    assert value.startswith("clips:"), f"landed on {value!r}, not footage"
    assert record["kind"] == "clips"
    assert record["source"] == "cache"


def test_the_cached_clip_is_placed_in_the_artifact(no_network, cache, tmp_path):
    """The cache is never handed to the renderer — an eviction must not pull
    footage out from under a rendered video. Same contract as the fetch tier."""
    _cached_clip(cache, "aerial drone shot waves on a wide beach")
    dest = tmp_path / "clips"

    value, record = _resolve(topic="set up", category="phrasal_verbs",
                             dest_dir=dest, duration=20.0)

    assert list(dest.glob("*.mp4")), "nothing was placed in the artifact"
    assert value == f"clips:{dest}"
    assert record["clip_count"] >= 1


def test_the_most_relevant_cached_clip_wins(no_network, cache, tmp_path):
    """HOW THE CLIP IS CHOSEN: token overlap between the cached slot's own
    stored query and the queries this video would have fetched. The cache is
    keyed by query, so this needs no similarity engine and no model — a set
    intersection over words. Random is the documented fallback, not the plan.
    """
    _cached_clip(cache, "close up hands typing on a laptop keyboard", "kb.mp4")
    _cached_clip(cache, "slow motion lava flowing down a volcano", "lava.mp4")

    _value, record = _resolve(topic="laptop keyboard", category="technology",
                              dest_dir=tmp_path / "clips", duration=8.0)

    assert Path(record["clips"][0]["path"]).name == "kb.mp4"


def test_an_unrelated_cache_is_still_footage(no_network, cache, tmp_path):
    """No overlap at all must not fall through to a colour field. A random
    clip from the cache is acceptable and better than a preset."""
    _cached_clip(cache, "slow motion lava flowing down a volcano", "lava.mp4")

    value, record = _resolve(topic="set up", category="phrasal_verbs",
                             dest_dir=tmp_path / "clips", duration=8.0)

    assert value.startswith("clips:")
    assert record["source"] == "cache"


def test_the_cache_tier_costs_nothing(no_network, cache, tmp_path):
    _cached_clip(cache, "aerial drone shot waves on a wide beach")

    _value, record = _resolve(topic="set up", category="phrasal_verbs",
                              dest_dir=tmp_path / "clips", duration=20.0)

    assert record["cost_usd"] == 0.0


# ═══════════════════ §2 · refusing beats substituting ═══════════════════

def test_an_empty_cache_refuses_rather_than_inventing_a_colour(no_network,
                                                               cache, tmp_path):
    """THE DEFECT. Every query declined, nothing cached, and the video used to
    become one of 76 flat presets and call itself complete."""
    with pytest.raises(pipeline.BackgroundUnavailable):
        pipeline.resolve_background(topic="set up", category="phrasal_verbs",
                                    dest_dir=tmp_path / "clips", duration=20.0)


def test_the_refusal_is_recorded_before_it_is_raised(no_network, cache, tmp_path):
    """A refusal nobody can read back is a crash. The record says which tier
    gave up and why, on the job row, next to every successful decision."""
    seen = []
    with pytest.raises(pipeline.BackgroundUnavailable):
        pipeline.resolve_background(topic="set up", category="phrasal_verbs",
                                    dest_dir=tmp_path / "clips", duration=20.0,
                                    on_record=seen.append)

    assert seen and seen[-1]["kind"] == "refused"
    assert seen[-1]["tier"] == "refused"


def test_the_profile_clip_directory_is_still_honoured(no_network, cache):
    value, record = _resolve(profile={"video": {"background_mode": "clips",
                                                "clips_dir": "assets/clips"}})

    assert value == "clips:assets/clips"
    assert record["kind"] == "clips" and record["tier"] == 2


# ═══════════════════ §3 · every tier records, in the resolver ═══════════════


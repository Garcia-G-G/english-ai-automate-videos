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

  3. use_v2 WAS DECIDED AFTER THE FETCH. studio/legacy_pipeline resolves a
     background at line 298 and only passes use_v2 at line 331, so
     `main.py --random --v2` downloaded footage and discarded every frame.
     The same defect was fixed in admin.py by the previous package; putting
     the fix in the CALLER is what left this copy behind, so it lives in the
     resolver now and both doors get it.
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
    # The image tier needs the network too, and declines for the same reason
    # — which is exactly what the observed run did before falling to a
    # random 'gen_028'. Stubbed so these tests measure the cascade's shape
    # rather than an OpenAI timeout.
    monkeypatch.setattr(pipeline, "_generated_background",
                        lambda *a, **k: (None, {"reason": "no network"}))


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


def test_fast_mode_still_gets_a_preset(no_network, cache):
    """fast_mode exists to be cheap and fast, and a preset is honest there.
    It is the ONLY door left to a flat background that nobody asked for."""
    value, record = _resolve(fast_mode=True, topic="set up")

    assert value == "dark_professional"
    assert record["kind"] == "preset"


def test_an_explicit_preset_is_still_an_instruction(no_network, cache):
    """Tier 1 is what the operator typed. Refusing it would be refusing the
    instruction, not the substitution — three of the flat videos on disk were
    exactly this, and none of them was the bug."""
    value, record = _resolve(background="static_fire", topic="set up")

    assert value == "static_fire"
    assert record["kind"] == "preset" and record["requested"] == "static_fire"


def test_a_config_pinned_preset_is_also_an_instruction(no_network, cache,
                                                       monkeypatch):
    """background_mode: fixed is a deliberate configuration, same class as
    tier 1. It is not the floor substituting behind anyone's back."""
    monkeypatch.setattr(pipeline, "_video_config",
                        lambda: {"background_mode": "fixed",
                                 "default_background": "static_ocean"})

    value, record = _resolve(topic="set up")

    assert value == "static_ocean"
    assert record["tier"] == 6


def test_the_profile_clip_directory_is_still_honoured(no_network, cache):
    value, record = _resolve(profile={"video": {"background_mode": "clips",
                                                "clips_dir": "assets/clips"}})

    assert value == "clips:assets/clips"
    assert record["kind"] == "clips" and record["tier"] == 2


# ═══════════════════ §3 · every tier records, in the resolver ═══════════════

@pytest.mark.parametrize("kwargs,expected_tier", [
    ({"fast_mode": True}, 0),
    ({"background": "static_fire"}, 1),
    ({"profile": {"video": {"background_mode": "clips",
                            "clips_dir": "assets/clips"}}}, 2),
])
def test_every_returning_tier_records_which_tier_decided(kwargs, expected_tier,
                                                         no_network, cache):
    """Five of seven return paths recorded nothing, so `background: null` was
    ambiguous between 'an instruction nobody logged' and 'the floor fired'."""
    _value, record = _resolve(**kwargs)

    assert record is not None, "returned without recording"
    assert record["tier"] == expected_tier


def test_no_return_in_the_resolver_bypasses_the_recorder():
    """THE INVARIANT, checked structurally rather than by enumerating tiers.

    resolve_background must have exactly one exit that a reader has to trust,
    so a tier added later cannot reintroduce the silent path. Every `return`
    in its body hands back through the recording helper.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(pipeline.resolve_background)))
    fn = tree.body[0]

    # Only the tier body. The nested helpers (decided/declined) return
    # normally by construction — it is the TIERS that must not.
    def tier_returns(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Return):
                yield child
            yield from tier_returns(child)

    returns = list(tier_returns(fn))

    assert returns, "no returns found — did the function move?"
    for node in returns:
        assert isinstance(node.value, ast.Call), (
            f"line {node.lineno}: returns a bare value, bypassing the record")
        name = getattr(node.value.func, "id", None) or \
            getattr(node.value.func, "attr", None)
        assert name == "decided", (
            f"line {node.lineno}: returns {name}(), not decided()")


def test_v2_never_pays_to_resolve_a_background_it_discards(cache, tmp_path,
                                                           monkeypatch):
    """video/__init__.py sets `background = None` whenever v2 is active.
    legacy_pipeline resolved one anyway and passed use_v2 thirty lines later,
    so `main.py --random --v2` fetched footage and threw every frame away.

    In the RESOLVER, not the caller: putting it in admin.py is what left the
    studio door still doing it.
    """
    called = []
    monkeypatch.setattr(topic_clips, "fetch_for_topic",
                        lambda *a, **k: called.append(1))

    value, record = _resolve(topic="set up", category="phrasal_verbs",
                             dest_dir=tmp_path / "clips", duration=20.0,
                             use_v2=True)

    assert not called, "v2 fetched footage it cannot use"
    assert record["kind"] == "engine" and record["engine"] == "v2"
    assert isinstance(value, str) and value


def test_the_studio_door_resolves_with_the_engine_it_will_render_with():
    """The shared fix has to actually be reachable from legacy_pipeline —
    otherwise this is the previous package's mistake a second time."""
    import inspect

    from studio import legacy_pipeline

    source = inspect.getsource(legacy_pipeline)
    call = source.split("self._resolve_background(")[1].split("progress(")[0]

    assert "use_v2" in call, (
        "legacy_pipeline resolves a background without telling the resolver "
        "which engine will render it")

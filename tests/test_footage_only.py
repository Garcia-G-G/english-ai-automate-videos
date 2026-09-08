#!/usr/bin/env python3
"""Footage is the only background. There is nothing else to fall back to.

    python3 -m pytest tests/test_footage_only.py

    "si es tan simple como quitar todo lo que no sean los videos y ya…
     el objetivo es poner los videos que tenemos de Pexels."

EIGHT WAYS A FLAT BACKGROUND USED TO REACH THE SCREEN, and the reason three
successive packages each ended with one still open is that each preserved an
escape hatch nobody had asked for:

    1  tier 0   fast_mode                  -> preset (no caller, still live)
    2  tier 1   explicit                   -> accepted a preset NAME
    3  tier 4   _generated_background      -> photo, $0.041
    4  tier 6   config pin                 -> preset
    5  pipeline v2 branch                  -> TERMINAL_PRESET
    6  video/v2/background.py              -> animated mesh gradient
    7  render_video's `background or TERMINAL_PRESET`
    8  admin Settings' background controls

NUMBER 6 IS WHY PIXELS ARE NOT ENOUGH TO VERIFY THIS. The v2 engine renders
its own animated mesh gradient with film grain, and grain produces the same
spatial-detail-plus-motion signature as real footage. A measurement that only
looks at the frames calls it footage — the previous package's table did
exactly that. So the assertions here read the RECORDED BACKGROUND, and the
tests below are mostly about what no longer exists.

The cascade is now five tiers, all footage, and a refusal:

    1 explicit clips dir -> 2 profile clips -> 3 pexels -> 4 cache -> refuse
"""

import ast
import inspect
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline  # noqa: E402
import topic_clips  # noqa: E402


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(topic_clips, "search", lambda *a, **k: [])
    monkeypatch.setattr(topic_clips, "api_key", lambda: None)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    root = tmp_path / "_cache"
    root.mkdir()
    monkeypatch.setattr(topic_clips, "CACHE_DIR", root)
    return root


# ═════════════════ the flat backgrounds are gone from the resolver ═════════

def test_no_tier_can_return_a_preset_name():
    """THE WHOLE PACKAGE, as one assertion.

    Every string the resolver can hand back is either a clips directory or a
    refusal. A preset name reaching the renderer is what produced four of the
    last five videos.
    """
    source = textwrap.dedent(inspect.getsource(pipeline.resolve_background))
    tree = ast.parse(source).body[0]

    returned = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "decided":
            if node.args:
                returned.append(node.args[0])

    assert returned, "no decided() calls found — did the resolver move?"
    for arg in returned:
        # A literal string constant that is not a clips: value is a preset.
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            assert arg.value.startswith("clips:"), (
                f"resolver can return the literal {arg.value!r}")


def test_the_terminal_preset_is_gone_entirely():
    """It was the floor, and `render_video` also used it as a default for a
    background the resolver can no longer fail to provide — it raises now."""
    assert not hasattr(pipeline, "TERMINAL_PRESET")
    assert not hasattr(pipeline, "_terminal_preset")


def test_fast_mode_is_gone_from_the_resolver():
    """Tier 0 returned "dark_professional" and had no caller in admin.py or
    main.py — only its own tests. The renderer's own `fast_mode` (ffmpeg
    preset, static background) is a different flag and is untouched."""
    assert "fast_mode" not in inspect.signature(pipeline.resolve_background).parameters


def test_the_generated_image_tier_is_gone():
    """$0.041 a call, 25 calls, $1.025 lifetime, nothing since 4 Sep. It sat
    between two footage tiers and could only fire when Pexels declined."""
    assert not hasattr(pipeline, "_generated_background")


def test_v2_is_no_longer_an_engine_choice():
    """v2 renders an animated mesh gradient — flat by design. Removing it as
    a CHOICE is the point; src/video/v2/ itself stays, because the v1 path
    imports timing_engine from it."""
    assert "use_v2" not in inspect.signature(pipeline.resolve_background).parameters
    assert "use_v2" not in inspect.signature(pipeline.render_video).parameters


def test_the_v2_package_is_still_importable_because_v1_needs_it():
    """THE TRAP. video/__init__.py imports timing_engine from .v2 on the V1
    path, so deleting the directory would break every render. It is untidy
    that a v1 dependency lives under a package named v2, and it is still
    correct to leave it."""
    from video.v2 import timing_engine

    assert hasattr(timing_engine, "compute_display_windows")


def test_config_no_longer_carries_a_preset_rotation():
    """enabled_backgrounds expanded to 76 names, none of them footage."""
    import yaml

    video_cfg = (yaml.safe_load((ROOT / "config.yaml").read_text()) or {}).get("video") or {}

    for key in ("enabled_backgrounds", "background_mode", "default_background"):
        assert key not in video_cfg, f"config.yaml still has video.{key}"


def test_the_profile_clips_directory_survived_the_cull():
    """profiles.children.video.background_mode is "clips" — tier 2, footage,
    and NOT the top-level background_mode that was deleted with tier 6."""
    import yaml

    config = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
    children = ((config.get("profiles") or {}).get("children") or {}).get("video") or {}

    assert children.get("background_mode") == "clips"


# ═════════════════ tier 1 is a directory, not a palette ═════════════════

def test_an_explicit_clips_directory_is_still_honoured(no_network, cache):
    value, record = _resolve(background="clips:assets/clips")

    assert value == "clips:assets/clips"
    assert record["kind"] == "clips" and record["tier"] == 1


def test_a_bare_directory_is_accepted_as_clips(no_network, cache, tmp_path):
    """`--background <dir>` is the natural thing to type and it means the
    same thing. Refusing it on a prefix would be pedantry."""
    clips = tmp_path / "mine"
    clips.mkdir()
    (clips / "a.mp4").write_bytes(b"\0" * 16)

    value, _record = _resolve(background=str(clips))

    assert value == f"clips:{clips}"


def test_an_explicit_preset_name_is_refused_not_rendered(no_network, cache):
    """`main.py --background static_fire` used to render a colour field. It
    now fails and says why, because a preset is no longer a background."""
    with pytest.raises(pipeline.BackgroundUnavailable) as excinfo:
        pipeline.resolve_background(background="static_fire")

    assert "static_fire" in str(excinfo.value)
    assert "clips" in str(excinfo.value).lower()


# ═════════════════════ what remains is footage or nothing ═════════════════

def test_the_cascade_is_five_footage_tiers_and_a_refusal():
    """Named tiers, read off the resolver itself, so the shape of the
    cascade is asserted rather than described in a comment."""
    source = textwrap.dedent(inspect.getsource(pipeline.resolve_background))
    tree = ast.parse(source).body[0]

    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "decided":
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                calls.append((node.lineno, node.args[2].value))
    # ast.walk is breadth-first; the cascade is an ORDER, so read it by line.
    names = [name for _lineno, name in sorted(calls)]

    # Deduped in order: "refused" appears twice in the source, once for a
    # preset name handed to tier 1 and once at the end of the cascade.
    unique = list(dict.fromkeys(names))

    assert unique == ["explicit_clips", "refused", "profile_clips", "pexels",
                      "clip_cache"]
    assert "generated_image" not in names and "config_fixed" not in names
    assert "fast_mode" not in names and "engine" not in names


def test_the_refusal_still_names_every_tier_it_tried(no_network, cache, tmp_path):
    seen = []
    with pytest.raises(pipeline.BackgroundUnavailable):
        pipeline.resolve_background(topic="set up", category="phrasal_verbs",
                                    dest_dir=tmp_path / "clips", duration=20.0,
                                    on_record=seen.append)

    assert seen[-1]["kind"] == "refused"
    assert "pexels" in seen[-1]["reason"]
    assert "clip_cache" in seen[-1]["reason"]


def test_no_return_in_the_resolver_bypasses_the_recorder():
    """Carried forward from f5ee109 unchanged: one exit, and a tier added
    later cannot reintroduce a silent path."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(pipeline.resolve_background)))
    fn = tree.body[0]

    def tier_returns(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Return):
                yield child
            yield from tier_returns(child)

    for node in tier_returns(fn):
        assert isinstance(node.value, ast.Call), (
            f"line {node.lineno}: returns a bare value, bypassing the record")
        name = getattr(node.value.func, "id", None)
        assert name == "decided", f"line {node.lineno}: returns {name}()"


# ═════════════════════ the doors offer nothing flat ═════════════════════

def test_the_dashboard_offers_no_preset_and_no_engine():
    """Two controls the previous package added are now gone: the Background
    selectbox listed 16 presets, and the v2 checkbox chose a mesh gradient."""
    import logging
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    import admin

    assert not hasattr(admin, "available_backgrounds")
    assert not hasattr(admin, "v2_supported")
    assert "use_v2" not in inspect.signature(
        admin.run_pipeline_with_tracking).parameters


def test_the_cli_no_longer_offers_v2():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "--v2" not in source
    assert "use_v2" not in source


def test_settings_no_longer_writes_a_background_choice():
    """admin.py's Settings tab wrote default_background and background_mode
    into config.yaml — the keys tier 6 read."""
    source = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")

    # The KEYS being written, not the words — a comment explaining what was
    # removed is not a regression.
    for key in ("default_background", "enabled_backgrounds", "background_mode"):
        assert f'"{key}":' not in source, f"admin still writes {key}"
        assert f"{key} =" not in source, f"admin still assigns {key}"


def test_the_scheduler_still_produces_every_type():
    """The cull must not have narrowed the type list — that was the last
    package's fix and it is unrelated to backgrounds."""
    import logging
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    import admin
    from script_generator import VIDEO_TYPES

    assert set(admin.scheduler_default_types()) == set(VIDEO_TYPES)


def _resolve(**kwargs):
    seen = []
    value = pipeline.resolve_background(on_record=seen.append, **kwargs)
    return value, (seen[-1] if seen else None)


def test_the_random_preset_fallback_died_with_the_image_tier():
    """topic_background.fallback_preset picked one of the 76 rotation names
    for when a generated image was refused. The image tier is gone, it had
    no callers left, and it was the last place that read the rotation."""
    import topic_background

    assert not hasattr(topic_background, "fallback_preset")

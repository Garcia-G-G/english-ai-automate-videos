#!/usr/bin/env python3
"""No type may exist in one list and be missing from another.

    python3 -m pytest tests/test_video_type_registry.py

THE DEFECT CLASS. Adding a video type meant editing fourteen places, four of
which were the same list of six names written out independently: the schema
tuple, the schema Literal, the generator's list, and the CLI's argparse
choices — plus the timing families, the contrast bands, the dashboard's
buttons and the layout tests' own map. A type could be legal in the schema,
illegal in the generator, absent from the CLI and missing from the dashboard
all at once, and nothing failed loudly. It simply did not appear.

NOT HYPOTHETICAL, AND NOT ONLY ABOUT FUTURE TYPES. When this registry was
written the dashboard's quick-button row listed four of the six types:
fill_blank and pronunciation had no Generate button, while admin.py:2264
documented having fixed that exact defect in the scheduler. It had regrown in
a different hand-written list in the same file.

These tests fail the moment a list drifts from the registry again.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import video_types as vt  # noqa: E402


def test_the_schema_agrees_with_the_registry():
    import script_schema
    assert tuple(script_schema.VIDEO_TYPES) == vt.VIDEO_TYPES


def test_the_generator_agrees_with_the_registry():
    import script_generator
    assert tuple(script_generator.VIDEO_TYPES) == vt.VIDEO_TYPES


def test_the_schema_literal_accepts_exactly_the_registry():
    """The Literal used to be the same six names typed a second time, so it
    could accept a type the tuple did not list, or refuse one it did."""
    from pydantic import BaseModel
    from script_schema import VideoType

    class Model(BaseModel):
        t: VideoType

    for name in vt.VIDEO_TYPES:
        assert Model(t=name).t == name
    with pytest.raises(Exception):
        Model(t="a_type_that_does_not_exist")


def test_every_type_belongs_to_exactly_one_timing_family():
    """A type in neither family is skipped silently by the timing contract;
    a type in both is a contradiction."""
    import timing_contract
    for name in vt.VIDEO_TYPES:
        in_v3 = name in timing_contract.V3_TYPES
        in_turbo = name in timing_contract.TURBO_TYPES
        assert in_v3 != in_turbo, f"{name} is in {'both' if in_v3 else 'neither'}"


def test_every_type_declares_a_text_band():
    """A type with no band gets no contrast check at all — the background is
    free to fight text nobody declared."""
    import clip_contrast
    for name in vt.VIDEO_TYPES:
        assert name in clip_contrast.TEXT_ZONES
        top, bottom = clip_contrast.TEXT_ZONES[name]
        assert 0 <= top < bottom


def test_every_type_has_a_dashboard_door():
    """THE ONE THIS REGISTRY EXISTS FOR. fill_blank and pronunciation were
    produced by the engine and unreachable from the Generate page."""
    with_doors = {vtype for _, vtype in vt.DASHBOARD_BUTTONS}
    missing = set(vt.VIDEO_TYPES) - with_doors
    assert not missing, f"types the engine can make and nobody can ask for: {missing}"


def test_every_type_names_a_renderer_that_actually_imports():
    """A registry entry pointing at a function that does not exist would move
    the failure from 'add a type' to 'render a video'."""
    for name in vt.VIDEO_TYPES:
        assert callable(vt.renderer_for(name)), name


def test_the_registry_imports_without_dragging_in_the_renderers():
    """video_types is imported by script_schema, which is imported by tools
    that never render. It must stay a leaf: the entries name their functions
    as strings precisely so importing the registry costs nothing."""
    import subprocess
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import video_types;"
        "print('numpy' in sys.modules or 'PIL' in sys.modules)" % str(ROOT / "src")
    )
    out = subprocess.run([sys.executable, "-c", probe],
                         capture_output=True, text=True)
    assert out.stdout.strip() == "False", "importing the registry pulled in the video stack"


def test_v3_types_are_exactly_the_ones_with_an_audio_generator():
    """The per-segment families are the ones with generate_<type>_audio_segmented."""
    for name in vt.VIDEO_TYPES:
        has_audio = vt.audio_generator_name(name) is not None
        assert has_audio == (name in vt.V3_TYPES), name

#!/usr/bin/env python3
"""STEP 62 §5: every door for fill_level, choose_level and phrases_level.

    python3 -m pytest tests/test_step62_doors.py

NOTHING HERE CALLS A PAID API.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

FIXTURES = {
    "fill_level": "fill_level_fc001.json",
    "choose_level": "choose_level_ec001.json",
    "phrases_level": "phrases_level_vf001.json",
}
NEW_OVER_OLD = {"choose_level": ("Elige la correcta", "quiz", "Quiz (antiguo)"),
                "fill_level": ("Completa (cascada)", "fill_blank", "Completa (antiguo)"),
                "phrases_level": ("¿Cómo se dice? frases", "vocabulary", "Vocabulario (antiguo)")}


def _script(vtype):
    return json.loads((ROOT / "tests" / "fixtures" / "scripts" / FIXTURES[vtype]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("vtype", sorted(FIXTURES))
def test_the_registry_shows_the_new_button_and_hides_the_old_one(vtype):
    """STEP 77 §0: the old neon type keeps its code but loses its button."""
    import video_types
    label, old, old_label = NEW_OVER_OLD[vtype]
    buttons = video_types.DASHBOARD_BUTTONS
    assert (label, vtype) in buttons and (old_label, old) not in buttons
    assert old in video_types.VIDEO_TYPES and vtype in video_types.V3_TYPES
    assert video_types.renderer_for(vtype).__name__ == "create_frame_level"
    assert video_types.audio_generator_name(vtype) == "generate_level_audio_segmented"
    assert video_types.spec(vtype)["text_band"] == video_types.spec("how_do_you_say")["text_band"]


def test_the_categories_feed_the_new_types():
    import yaml
    cats = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["type_categories"]
    assert cats["fill_level"] == cats["choose_level"] == ["grammar", "common_mistakes", "confusing_words"]
    assert cats["phrases_level"] == ["everyday_expressions", "social", "travel"]
    for c in cats["fill_level"] + cats["phrases_level"]:
        assert (ROOT / "content" / "topics" / f"{c}.json").exists()


@pytest.mark.parametrize("vtype", sorted(FIXTURES))
def test_hashtags_title_and_duration_band(vtype):
    import duration_spec
    import metadata_generator
    import yaml
    first = _script(vtype)["hashtags"][0]
    assert metadata_generator.TYPE_HASHTAGS[vtype][0] == first
    upload = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["upload"]["hashtags"]
    assert upload[vtype].split()[0] == first
    assert metadata_generator.TITLE_TEMPLATES[vtype]
    window = duration_spec.reject_window(vtype)
    assert window["max_seconds"] <= 95.0 and window["min_seconds"] < duration_spec.band(vtype)["target_seconds"]


@pytest.mark.parametrize("vtype", sorted(FIXTURES))
def test_openai_refuses(vtype, tmp_path):
    from tts_providers.openai_provider import OpenAITTSProvider
    with pytest.raises(NotImplementedError, match=vtype):
        OpenAITTSProvider().generate_from_script(_script(vtype), str(tmp_path / "a.mp3"))


@pytest.mark.parametrize("vtype", sorted(FIXTURES))
def test_elevenlabs_routes_to_the_level_generator(vtype, tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    import tts_providers.elevenlabs_provider as EP
    seen = []
    monkeypatch.setattr(TE, "generate_level_audio_segmented",
                        lambda script, output_path, voice_id=None: seen.append(script["type"]) or {"segments": []})
    try:
        EP.ElevenLabsTTSProvider().generate_from_script(_script(vtype), str(tmp_path / "a.mp3"))
    except Exception:                                   # noqa: BLE001 -- only the route is under test
        pass
    assert seen == [vtype]


@pytest.mark.parametrize("vtype, marks", [
    ("fill_level", ("#CompletaLaFrase", "____", '"translation"')),
    ("choose_level", ("#ElegirLaCorrecta", "____", '"options"')),
    ("phrases_level", ("#CómoSeDice", "Sin niveles", '"english"')),
])
def test_the_generator_prompt_names_the_type_and_its_rules(vtype, marks):
    from script_generator import build_prompt
    prompt = build_prompt("grammar", {"id": "x999", "theme": "prueba"}, vtype)
    assert f'"type": "{vtype}"' in prompt
    for mark in marks:
        assert mark in prompt


@pytest.mark.parametrize("vtype", sorted(FIXTURES))
def test_spoken_words_count_what_is_said(vtype):
    from duration_calibrate import spoken_words
    script = _script(vtype)
    english = sum(len(p.split()) for p in script["english_phrases"])
    assert spoken_words(script) > english

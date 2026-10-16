#!/usr/bin/env python3
"""STEP 61 Part B: true_false_level, the third mode of the notebook.

    python3 -m pytest tests/test_true_false_level.py

NOTHING HERE CALLS A PAID API.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

VTYPE = "true_false_level"
FIXTURE = ROOT / "tests" / "fixtures" / "scripts" / "true_false_level_tf001.json"


@pytest.fixture
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def _script():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _timeline(data):
    """A synthetic segment_times shaped like generate_level_audio_segmented's (no prompt)."""
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.5
    for i in range(1, 11):
        if i in (4, 8):
            st[f"tier_{i}"] = {"start": t, "end": t + 1.5}; t += 1.8
        st[f"think_{i}"] = {"start": t, "end": t + 4.0}; t += 4.0
        st[f"answer_{i}"] = {"start": t, "end": t + 1.2}; t += 1.6
    st["verdict"] = {"start": t, "end": t + 6.0}; t += 6.5
    st["outro"] = {"start": t, "end": t + 3.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 3.0


# ── schema and length ────────────────────────────────────────────────

def test_the_draft_and_the_fixture_validate():
    import script_schema
    from level_migrate import derive
    draft = json.loads((ROOT / "content" / "drafts" / VTYPE / "tf001_falsos_amigos.json").read_text(encoding="utf-8"))
    assert derive(draft) == _script()
    script_schema.SCRIPT_MODELS[VTYPE].model_validate(_script())


def _flip_truths(d, n_true):
    for i, it in enumerate(d["items"]):
        it["truth"] = i < n_true
        it.pop("correction", None)
        if not it["truth"]:
            it["correction"] = f"es otra cosa {i}"


@pytest.mark.parametrize("break_it, why", [
    (lambda d: _flip_truths(d, 2), "3 to 7"),
    (lambda d: _flip_truths(d, 8), "3 to 7"),
    (lambda d: d["items"][0].pop("correction"), "needs its correction"),
    (lambda d: d["items"][1].update(correction="es salida"), "has no correction"),
    (lambda d: d["items"][0].update(statement="Carpet significa carpeta."), "in «»"),
    (lambda d: d["items"][1].update(statement=d["items"][0]["statement"]), "duplicate statement"),
    (lambda d: d.update(hashtags=["#AprenderInglés"] * 5), "the first #VerdaderoOFalso"),
    (lambda d: d["items"].pop(), "exactly 10"),
])
def test_the_format_rules_are_the_schema(break_it, why):
    import script_schema
    data = _script()
    break_it(data)
    with pytest.raises(ValueError, match=why):
        script_schema.SCRIPT_MODELS[VTYPE].model_validate(data)


def test_length_spec_measures_the_statement_and_the_answer_line():
    import length_spec
    assert length_spec.check_script(_script()) == []
    long = _script()
    long["items"][0]["correction"] = "es una alfombra muy grande y muy larga de verdad"
    long["items"][1]["statement"] = "«Exit» significa salida de emergencia del edificio grande."
    assert {(v["where"], v["field"]) for v in length_spec.check_script(long)} == \
        {("items[0]", "answer"), ("items[1]", "statement")}


# ── renderer ─────────────────────────────────────────────────────────

def test_frames_are_a_pure_function_of_t(no_mascot):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    data, dur = _timeline(_script())
    t = data["segment_times"]["answer_4"]["start"] + 0.5
    a = create_frame_level(t, copy.deepcopy(data), dur)
    create_frame_level(2.0, data, dur)
    assert np.array_equal(a, create_frame_level(t, data, dur))


def test_no_hint_before_the_reveal(no_mascot, monkeypatch):
    """Before its answer every row draws the same grey placeholder at full blur; the real
    answer is never drawn, so neither its colour nor its length can leak."""
    import video.how_do_you_say as H
    drawn = []
    real = H._blurred_line
    monkeypatch.setattr(H, "_blurred_line", lambda text, size, color, radius:
                        drawn.append((text, color, radius)) or real(text, size, color, radius))
    data, dur = _timeline(_script())
    H.create_frame_level(0.0, data, dur)
    assert len(drawn) == 10
    assert set(drawn) == {(H.TF_PLACEHOLDER, H._color("secondary_text"), H.BLUR_MAX)}


def test_the_answer_comes_into_focus_in_two_pixel_steps(no_mascot, monkeypatch):
    import video.how_do_you_say as H
    drawn = []
    real = H._blurred_line
    monkeypatch.setattr(H, "_blurred_line", lambda text, size, color, radius:
                        drawn.append((text, radius)) or real(text, size, color, radius))
    data, dur = _timeline(_script())
    ans = data["segment_times"]["answer_4"]
    H.create_frame_level(ans["start"] + 0.25 * (ans["end"] - ans["start"]), data, dur)
    # a quarter in: the placeholder and the real line cross-fade at the same radius, 14 * 0.75 -> 10
    assert [d for d in drawn if 0 < d[1] < H.BLUR_MAX] == [(H.TF_PLACEHOLDER, 10), ("FALSO · es avergonzada", 10)]
    drawn.clear()
    H.create_frame_level(ans["end"] + 0.1, data, dur)
    assert ("FALSO · es avergonzada", 0) in drawn
    assert all(r % H.BLUR_STEP == 0 for _t, r in drawn)


def test_answer_lines_are_green_true_or_red_false_with_the_correction():
    from video.how_do_you_say import tf_answer
    items = _script()["items"]
    assert tf_answer(items[1]) == ("VERDADERO", "correct")
    assert tf_answer(items[0]) == ("FALSO · es alfombra", "error")


def test_the_pencil_points_at_the_active_row_and_does_not_write():
    from video.how_do_you_say import (PENCIL_MOVE, PENCIL_WAIT_X, LevelTimeline,
                                      level_pencil_position, row_centres)
    data, dur = _timeline(_script())
    tl, items, centres = LevelTimeline(data, dur), data["items"], row_centres(10)
    ans = data["segment_times"]["answer_2"]
    for t in (data["segment_times"]["think_2"]["start"] + PENCIL_MOVE + 0.01, ans["start"],
              (ans["start"] + ans["end"]) / 2, ans["end"]):
        x, _y = level_pencil_position(t, tl, items, None, centres, 0, writes=False)
        assert x == pytest.approx(PENCIL_WAIT_X)


# ── audio ────────────────────────────────────────────────────────────

def _tone(path, total=0.9):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*between(t,0.05,{total - 0.15})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_the_audio_is_spanish_only_with_a_four_second_think(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    calls = []
    monkeypatch.setattr(TE, "generate_segment_audio",
                        lambda text, output_path, **kw: calls.append(text) or _tone(output_path))
    monkeypatch.setattr(TE, "_onset_values", lambda path: pytest.fail("no English clip to gate"))
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    out = TE.generate_level_audio_segmented(_script(), str(tmp_path / "a.mp3"))

    order = ["intro"]
    for i in range(1, 11):
        order += [f"tier_{i}"] if i in TE.LEVEL_TIER_LINES else []
        order += [f"think_{i}", f"answer_{i}"]
    assert [s["id"] for s in out["segments"]] == order + ["verdict", "outro"]
    st = out["segment_times"]
    assert all(st[f"think_{i}"]["duration"] == pytest.approx(4.0, abs=0.002) for i in range(1, 11))
    texts = {s["id"]: s["text"] for s in out["segments"]}
    assert texts["answer_1"] == "Falso: es alfombra." and texts["answer_2"] == "Verdadero."
    assert not any("«" in c for c in calls)          # the statements are read off the page


# ── doors ────────────────────────────────────────────────────────────

def test_the_registry_puts_the_cascade_above_the_old_true_false():
    import video_types
    labels = [label for label, _t in video_types.DASHBOARD_BUTTONS]
    assert labels.index("Verdadero o falso (cascada)") + 1 == labels.index("Verdadero o falso (uno)")
    assert video_types.renderer_for(VTYPE).__name__ == "create_frame_level"
    assert video_types.spec(VTYPE)["text_band"] == video_types.spec("how_do_you_say")["text_band"]
    assert "true_false" in video_types.VIDEO_TYPES


def test_false_friends_feeds_both_true_false_types():
    import yaml
    cats = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["type_categories"]
    assert cats[VTYPE] == ["false_friends"] and "false_friends" in cats["true_false"]


def test_hashtags_title_and_duration_band():
    import duration_spec
    import metadata_generator
    assert metadata_generator.TYPE_HASHTAGS[VTYPE][0] == "#VerdaderoOFalso"
    assert metadata_generator.TITLE_TEMPLATES[VTYPE]
    assert duration_spec.reject_window(VTYPE)["max_seconds"] == 95.0


def test_openai_refuses(tmp_path):
    from tts_providers.openai_provider import OpenAITTSProvider
    with pytest.raises(NotImplementedError, match=VTYPE):
        OpenAITTSProvider().generate_from_script(_script(), str(tmp_path / "a.mp3"))


def test_the_generator_prompt_names_the_type_and_its_tag():
    from script_generator import build_prompt
    prompt = build_prompt("false_friends", {"id": "tf999", "theme": "falsos amigos"}, VTYPE)
    assert f'"type": "{VTYPE}"' in prompt and "#VerdaderoOFalso" in prompt and "«" in prompt


def test_spoken_words_count_the_answers_not_the_statements():
    from duration_calibrate import spoken_words
    script = _script()
    words = spoken_words(script)
    statements = sum(len(it["statement"].split()) for it in script["items"])
    no_statements = copy.deepcopy(script)
    for it in no_statements["items"]:
        it["statement"] = "«X»"
    assert spoken_words(no_statements) == words and words > 10 + 2
    assert statements > 0

#!/usr/bin/env python3
"""STEP 62 §1: fill_level, «Completa la frase» on the notebook.

    python3 -m pytest tests/test_fill_level.py

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

VTYPE = "fill_level"
FIXTURE = ROOT / "tests" / "fixtures" / "scripts" / "fill_level_fc001.json"


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
        st[f"think_{i}"] = {"start": t, "end": t + 3.0}; t += 3.0
        st[f"answer_{i}"] = {"start": t, "end": t + 1.5}; t += 1.9
    st["verdict"] = {"start": t, "end": t + 6.0}; t += 6.5
    st["outro"] = {"start": t, "end": t + 3.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 3.0


# ── schema and length ────────────────────────────────────────────────

def test_the_draft_and_the_fixture_validate():
    import script_schema
    from level_migrate import derive
    draft = json.loads((ROOT / "content" / "drafts" / VTYPE / "fc001_preposiciones.json").read_text(encoding="utf-8"))
    assert derive(draft) == _script()
    script_schema.SCRIPT_MODELS[VTYPE].model_validate(_script())
    assert _script()["english_phrases"][0] == "I live in Madrid."


@pytest.mark.parametrize("break_it, why", [
    (lambda d: d["items"][0].update(sentence="I live in Madrid."), "exactly one blank"),
    (lambda d: d["items"][0].update(sentence="I ____ ____ Madrid."), "exactly one blank"),
    (lambda d: d["items"][0].update(sentence="I live _____ Madrid."), "exactly one blank"),
    (lambda d: d["items"][0].update(answer="i____n"), "no blank of its own"),
    (lambda d: d["items"][1].update(sentence=d["items"][0]["sentence"]), "duplicate sentence"),
    (lambda d: d.update(hashtags=["#AprenderInglés"] * 5), "the first #CompletaLaFrase"),
    (lambda d: d["items"][0].update(cefr="C1"), "cefr not non-decreasing"),
    (lambda d: d["items"].pop(), "exactly 10"),
])
def test_the_format_rules_are_the_schema(break_it, why):
    import script_schema
    data = _script()
    break_it(data)
    with pytest.raises(ValueError, match=why):
        script_schema.SCRIPT_MODELS[VTYPE].model_validate(data)


def test_length_spec_measures_the_sentence_with_its_blank_and_the_translation():
    import length_spec
    assert length_spec.check_script(_script()) == []
    long = _script()
    # STEP 77 §4: lines wrap at 42 px; a field over LEVEL_MAX_LINES lines does not fit
    long["items"][1]["sentence"] = "See you ____ Monday morning at the big station downtown, " * 2
    long["items"][2]["translation"] = "La clase empieza a las nueve en punto de la mañana, sin falta. " * 2
    assert {(v["where"], v["field"]) for v in length_spec.check_script(long)} == \
        {("items[1]", "sentence"), ("items[2]", "translation")}


# ── renderer ─────────────────────────────────────────────────────────

def test_the_blank_is_one_width_on_the_page_and_holds_the_longest_answer():
    from video.how_do_you_say import BLANK_PAD, fredoka, level_layout
    lay = level_layout(VTYPE, _script()["items"])
    assert lay.blank >= fredoka(lay.size).getlength("with") + 2 * BLANK_PAD


def test_frame_zero_gives_no_hint_of_any_answer(no_mascot):
    """Two pages whose answers differ but whose longest answer is the same draw frame 0
    pixel for pixel alike: the blank and its grey bar do not depend on the answer."""
    import numpy as np
    from video.how_do_you_say import create_frame_level
    a, dur = _timeline(_script())
    b = copy.deepcopy(a)
    for it in b["items"]:
        if it["answer"] != "with":
            it["answer"] = "of"
    assert np.array_equal(create_frame_level(0.0, a, dur), create_frame_level(0.0, b, dur))


def test_frames_are_a_pure_function_of_t(no_mascot):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    data, dur = _timeline(_script())
    t = data["segment_times"]["answer_4"]["start"] + 0.5
    a = create_frame_level(t, copy.deepcopy(data), dur)
    create_frame_level(2.0, data, dur)
    assert np.array_equal(a, create_frame_level(t, data, dur))


def test_the_answer_is_written_into_the_blank_and_the_translation_comes_with_it(no_mascot, monkeypatch):
    import video.how_do_you_say as H
    drawn = []
    real_line = H._line_image
    monkeypatch.setattr(H, "_line_image", lambda text, size, color:
                        drawn.append(("line", text, color)) or real_line(text, size, color))
    data, dur = _timeline(_script())
    ans = data["segment_times"]["answer_5"]
    H.create_frame_level(ans["start"] - 0.1, data, dur)
    assert ("line", "Depende del tiempo.", H._color("secondary_text")) not in drawn   # row 5 not yet
    drawn.clear()
    H.create_frame_level((ans["start"] + ans["end"]) / 2, data, dur)
    assert ("line", "on", H._color("english_blue")) in drawn
    assert ("line", "Depende del tiempo.", H._color("secondary_text")) in drawn


def test_the_pencil_writes_inside_the_blank_on_the_sentence_line():
    from video.how_do_you_say import LevelTimeline, fill_spans, level_layout, level_pencil_position
    data, dur = _timeline(_script())
    tl, items = LevelTimeline(data, dur), data["items"]
    layout = level_layout(VTYPE, items)
    spans = fill_spans(items, layout)
    ans = data["segment_times"]["answer_2"]
    assert level_pencil_position(ans["start"], tl, items, layout, "fill") == \
        pytest.approx(spans[1][0::2], abs=2.0)                # ±2: the pencil wobbles as it writes
    assert level_pencil_position(ans["end"], tl, items, layout, "fill") == pytest.approx(spans[1][1:])


# ── audio ────────────────────────────────────────────────────────────

def _tone(path, total=0.9):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*between(t,0.05,{total - 0.15})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_each_answer_is_the_whole_sentence_in_english_through_the_onset_gate(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    calls, gated = [], []
    monkeypatch.setattr(TE, "generate_segment_audio",
                        lambda text, output_path, **kw: calls.append(text) or _tone(output_path))
    monkeypatch.setattr(TE, "_onset_values",
                        lambda path: gated.append(path) or {"start_db": -40.0, "fragment": None, "doubled_onset": None})
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    out = TE.generate_level_audio_segmented(_script(), str(tmp_path / "a.mp3"))

    order = ["intro"]
    for i in range(1, 11):
        order += [f"tier_{i}"] if i in TE.LEVEL_TIER_LINES else []
        order += [f"think_{i}", f"answer_{i}"]
    assert [s["id"] for s in out["segments"]] == order + ["verdict", "outro"]
    st = out["segment_times"]
    assert all(st[f"think_{i}"]["duration"] == pytest.approx(3.0, abs=0.002) for i in range(1, 11))
    texts = {s["id"]: s["text"] for s in out["segments"]}
    assert texts["answer_1"] == "I live in Madrid." and texts["answer_10"] == "It's up to you."
    assert not any("____" in c for c in calls)
    assert sum("answer_" in p for p in gated) == 10 and any("intro" in p for p in gated)   # every clip (STEP 76 §3)

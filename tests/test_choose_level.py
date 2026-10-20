#!/usr/bin/env python3
"""STEP 62 §2: choose_level, «Elige la correcta» on the notebook.

    python3 -m pytest tests/test_choose_level.py

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

VTYPE = "choose_level"
FIXTURE = ROOT / "tests" / "fixtures" / "scripts" / "choose_level_ec001.json"


@pytest.fixture
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def _script():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _timeline(data):
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
    draft = json.loads((ROOT / "content" / "drafts" / VTYPE / "ec001_make_do.json").read_text(encoding="utf-8"))
    assert derive(draft) == _script()
    script_schema.SCRIPT_MODELS[VTYPE].model_validate(_script())
    assert _script()["english_phrases"][:2] == ["I need to do my homework.", "She made a cake yesterday."]


def _all_first(d, n_first):
    for i, it in enumerate(d["items"]):
        it["answer"] = 0 if i < n_first else 1


@pytest.mark.parametrize("break_it, why", [
    (lambda d: _all_first(d, 8), "option 1 is right 8 times"),
    (lambda d: _all_first(d, 2), "option 1 is right 2 times"),
    (lambda d: d["items"][0].update(options=["make", "do", "did"]), "at most 2"),
    (lambda d: d["items"][0].update(options=["do", "Do"]), "the same"),
    (lambda d: d["items"][0].update(answer=2), "answer"),
    (lambda d: d["items"][0].update(sentence="I need to do my homework."), "exactly one blank"),
    (lambda d: d.update(hashtags=["#AprenderInglés"] * 5), "the first #ElegirLaCorrecta"),
    (lambda d: d["items"].pop(), "exactly 10"),
])
def test_the_format_rules_are_the_schema(break_it, why):
    import script_schema
    data = _script()
    break_it(data)
    with pytest.raises(ValueError, match=why):
        script_schema.SCRIPT_MODELS[VTYPE].model_validate(data)


def test_length_spec_measures_the_sentence_and_the_options_line():
    import length_spec
    assert length_spec.check_script(_script()) == []
    long = _script()
    long["items"][1]["sentence"] = "She ____ a cake for the whole family and the neighbours yesterday."
    long["items"][2]["options"] = ["make the bed every single", "do the dishes every single"]
    assert {(v["where"], v["field"]) for v in length_spec.check_script(long)} >= \
        {("items[1]", "sentence"), ("items[2]", "options")}


# ── renderer ─────────────────────────────────────────────────────────

def test_frames_are_a_pure_function_of_t(no_mascot):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    data, dur = _timeline(_script())
    t = data["segment_times"]["answer_4"]["start"] + 0.5
    a = create_frame_level(t, copy.deepcopy(data), dur)
    create_frame_level(2.0, data, dur)
    assert np.array_equal(a, create_frame_level(t, data, dur))


def test_frame_zero_does_not_say_which_option_is_right(no_mascot):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    a, dur = _timeline(_script())
    b = copy.deepcopy(a)
    for it in b["items"]:
        it["answer"] = 1 - it["answer"]
    assert np.array_equal(create_frame_level(0.0, a, dur), create_frame_level(0.0, b, dur))


def test_the_right_option_is_circled_and_the_wrong_one_struck(no_mascot, monkeypatch):
    import video.how_do_you_say as H
    circles, strikes = [], []
    real_c, real_s = H._hand_circle, H._strike
    monkeypatch.setattr(H, "_hand_circle", lambda draw, box, p: circles.append((box, p)) or real_c(draw, box, p))
    monkeypatch.setattr(H, "_strike", lambda draw, x0, x1, cy, p: strikes.append((x0, x1, p)) or real_s(draw, x0, x1, cy, p))
    data, dur = _timeline(_script())
    centres = list(H.level_rows(10, H.CHOOSE_TIER_GAP)[0])
    spans = H.choice_spans(data["items"], centres)
    ans = data["segment_times"]["answer_5"]           # row 5: «makes · does», does is right
    H.create_frame_level(ans["end"] + 0.1, data, dur)
    row5_circle = [c for c in circles if abs((c[0][1] + c[0][3]) / 2 - (centres[4] + H.LINE2_DY)) < 1]
    assert len(row5_circle) == 1 and row5_circle[0][0][0] < spans[4][1][0] < row5_circle[0][0][2]
    assert (spans[4][0][0], spans[4][0][1], 1.0) in strikes
    circles.clear(), strikes.clear()
    H.create_frame_level(ans["start"] - 0.1, data, dur)
    assert len(circles) == 4 and len(strikes) == 4    # rows 1-4 only


def test_the_countdown_sits_after_the_options_never_over_them(no_mascot, monkeypatch):
    import video.how_do_you_say as H
    dots = []
    monkeypatch.setattr(H, "_draw_countdown_at", lambda layer, x0, cy, p: dots.append(x0))
    data, dur = _timeline(_script())
    spans = H.choice_spans(data["items"], list(H.level_rows(10, H.CHOOSE_TIER_GAP)[0]))
    for i in range(10):
        dots.clear()
        th = data["segment_times"][f"think_{i + 1}"]
        H.create_frame_level((th["start"] + th["end"]) / 2, data, dur)
        assert dots and dots[0] - 11 > spans[i][1][1]


# ── audio ────────────────────────────────────────────────────────────

def _tone(path, total=0.9):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*between(t,0.05,{total - 0.15})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_each_answer_is_the_sentence_with_the_right_option(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    gated = []
    monkeypatch.setattr(TE, "generate_segment_audio", lambda text, output_path, **kw: _tone(output_path))
    monkeypatch.setattr(TE, "_onset_values",
                        lambda path: gated.append(path) or {"start_db": -40.0, "fragment": None, "doubled_onset": None})
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    out = TE.generate_level_audio_segmented(_script(), str(tmp_path / "a.mp3"))
    texts = {s["id"]: s["text"] for s in out["segments"]}
    assert texts["answer_1"] == "I need to do my homework." and texts["answer_10"] == "She makes the bed every morning."
    assert sum("answer_" in p for p in gated) == 10 and any("intro" in p for p in gated)   # Spanish too (STEP 76 §3)

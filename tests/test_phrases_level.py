#!/usr/bin/env python3
"""STEP 62 §3: phrases_level, «¿Cómo se dice?» with everyday sentences.

    python3 -m pytest tests/test_phrases_level.py

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

VTYPE = "phrases_level"
FIXTURE = ROOT / "tests" / "fixtures" / "scripts" / "phrases_level_vf001.json"


@pytest.fixture
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def _script():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _timeline(data):
    """No tiers and no verdict: intro, think_i, answer_i, outro."""
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.5
    for i in range(1, len(data["items"]) + 1):
        st[f"think_{i}"] = {"start": t, "end": t + 2.5}; t += 2.5
        st[f"answer_{i}"] = {"start": t, "end": t + 1.2}; t += 1.6
    st["outro"] = {"start": t, "end": t + 3.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 3.0


# ── schema and length ────────────────────────────────────────────────

def test_the_draft_and_the_fixture_validate():
    import script_schema
    from level_migrate import derive
    draft = json.loads((ROOT / "content" / "drafts" / VTYPE / "vf001_preguntas_pasado.json").read_text(encoding="utf-8"))
    assert derive(draft) == _script()
    script_schema.SCRIPT_MODELS[VTYPE].model_validate(_script())
    assert "verdict" not in _script() and "Ahora, nivel" not in _script()["full_script"]


@pytest.mark.parametrize("break_it, why", [
    (lambda d: d["items"].__delitem__(slice(7, None)), "at least 8"),
    (lambda d: d["items"].append(dict(d["items"][0], english="x")), "at most 10"),
    (lambda d: d["items"][0].update(cefr="A1"), "Extra inputs"),
    (lambda d: d.update(verdict="Si llegaste a la tres..."), "Extra inputs"),
    (lambda d: d["items"][1].update(english=d["items"][0]["english"]), "duplicate english"),
    (lambda d: d["items"][0].update(english="[excited] How did it go?"), "only allowed in intro and outro"),
    (lambda d: d.update(hashtags=["#AprenderInglés"] * 5), "the first #CómoSeDice"),
])
def test_the_format_rules_are_the_schema(break_it, why):
    import script_schema
    data = _script()
    break_it(data)
    with pytest.raises(ValueError, match=why):
        script_schema.SCRIPT_MODELS[VTYPE].model_validate(data)


def test_eight_rows_are_enough():
    import script_schema
    data = _script()
    del data["items"][8:]
    script_schema.SCRIPT_MODELS[VTYPE].model_validate(data)


def test_length_spec_measures_both_lines():
    import length_spec
    assert length_spec.check_script(_script()) == []
    long = _script()
    long["items"][0]["english"] = "How did it go yesterday afternoon at the big meeting downtown?"
    assert [(v["where"], v["field"]) for v in length_spec.check_script(long)] == [("items[0]", "english")]


# ── renderer ─────────────────────────────────────────────────────────

def test_no_tiers_no_pills_no_verdict(no_mascot, monkeypatch):
    import video.how_do_you_say as H
    pills = []
    real = H._tier_pill
    monkeypatch.setattr(H, "_tier_pill", lambda *a: pills.append(a) or real(*a))
    monkeypatch.setattr(H, "_verdict_note", lambda: pytest.fail("phrases_level has no verdict"))
    data, dur = _timeline(_script())
    for t in (0.0, data["segment_times"]["answer_10"]["end"] + 0.2, data["segment_times"]["outro"]["start"] + 1):
        H.create_frame_level(t, data, dur)
    assert pills == []


def test_frame_zero_gives_no_hint_of_any_answer(no_mascot):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    a, dur = _timeline(_script())
    b = copy.deepcopy(a)
    for it in b["items"]:
        it["english"] = it["english"][::-1]
    assert np.array_equal(create_frame_level(0.0, a, dur), create_frame_level(0.0, b, dur))


def test_the_last_row_stays_lit_until_the_outro():
    from video.how_do_you_say import LevelTimeline
    data, dur = _timeline(_script())
    tl = LevelTimeline(data, dur)
    assert tl.row_end(9) == data["segment_times"]["outro"]["start"]


# ── audio ────────────────────────────────────────────────────────────

def _tone(path, total=0.9):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*between(t,0.05,{total - 0.15})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


def test_the_audio_has_no_tier_lines_and_no_verdict(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    calls = []
    monkeypatch.setattr(TE, "generate_segment_audio",
                        lambda text, output_path, **kw: calls.append(text) or _tone(output_path))
    monkeypatch.setattr(TE, "_onset_values", lambda path: {"start_db": -40.0, "fragment": None, "doubled_onset": None})
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    out = TE.generate_level_audio_segmented(_script(), str(tmp_path / "a.mp3"))
    order = ["intro"] + [k for i in range(1, 11) for k in (f"think_{i}", f"answer_{i}")] + ["outro"]
    assert [s["id"] for s in out["segments"]] == order
    st = out["segment_times"]
    assert all(st[f"think_{i}"]["duration"] == pytest.approx(2.5, abs=0.002) for i in range(1, 11))
    assert not any(c in TE.LEVEL_TIER_LINES.values() for c in calls)
    assert not any("¿" in c for c in calls[1:-1])     # the Spanish is read off the page

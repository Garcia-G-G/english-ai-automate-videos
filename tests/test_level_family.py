#!/usr/bin/env python3
"""STEP 58: level_test and say_it_level, two modes of the how_do_you_say notebook.

    python3 -m pytest tests/test_level_family.py

NOTHING HERE CALLS A PAID API.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

FIXTURE = ROOT / "tests" / "fixtures" / "scripts" / "how_do_you_say_bv001.json"


@pytest.fixture
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def _hdys_timeline(data):
    """test_how_do_you_say._timeline, copied so this pin cannot drift with it."""
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.6
    for i in range(1, len(data["items"]) + 1):
        st[f"es_{i}"] = {"start": t, "end": t + 0.8}; t += 0.8
        st[f"think_{i}"] = {"start": t, "end": t + 1.8}; t += 1.8
        st[f"en_{i}"] = {"start": t, "end": t + 1.6, "reveal_end": t + 0.7}; t += 2.0
    st["recap"] = {"start": t, "end": t + 9.0}; t += 9.6
    st["outro"] = {"start": t, "end": t + 4.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 4.0


#: sha256[:16] of raw frames over a flat base, rendered by the renderer as it was
#: BEFORE the level modes (3c5ab68, computed in a worktree of that commit).
HDYS_PIN = {
    0.0: "e9748d62b6d5818a", 4.7: "0f9a322115eabb7a", 15.5: "075710f7c4db07e8",
    25.9: "3f5aa23f928a0a6e", 50.2: "86996ac9db397a43", 53.6: "32deada8b8f4df3e",
    63.7: "25a4d3e035ccd7f6",
}


def test_how_do_you_say_renders_byte_identically(no_mascot, monkeypatch):
    """A flat base frame, so the pin does not read whatever background global an
    earlier test left behind (video.backgrounds.CURRENT_BACKGROUND)."""
    from PIL import Image, ImageDraw
    import video.how_do_you_say as H

    def flat(t):
        frame = Image.new("RGBA", (1080, 1920), (40, 60, 90, 255))
        return frame, ImageDraw.Draw(frame, "RGBA")

    monkeypatch.setattr(H, "create_base_frame", flat)
    data, dur = _hdys_timeline(json.loads(FIXTURE.read_text(encoding="utf-8")))
    got = {t: hashlib.sha256(H.create_frame_how_do_you_say(t, copy.deepcopy(data), dur).tobytes()).hexdigest()[:16]
           for t in HDYS_PIN}
    assert got == HDYS_PIN


# ── fixtures ─────────────────────────────────────────────────────────

SCRIPTS = {"level_test": ROOT / "tests" / "fixtures" / "scripts" / "level_test_lv001.json",
           "say_it_level": ROOT / "tests" / "fixtures" / "scripts" / "say_it_level_sy001.json"}
QUEUED = {t: sorted((ROOT / "content" / "queue" / t).glob("*.json")) for t in SCRIPTS}


def _script(vtype):
    return json.loads(SCRIPTS[vtype].read_text(encoding="utf-8"))


def _timeline(data, speak_prompt=True):
    """A synthetic segment_times shaped like generate_level_audio_segmented's."""
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.5
    for i in range(1, 11):
        if i in (4, 8):
            st[f"tier_{i}"] = {"start": t, "end": t + 1.5}; t += 1.8
        if speak_prompt:
            st[f"prompt_{i}"] = {"start": t, "end": t + 1.0}; t += 1.0
        st[f"think_{i}"] = {"start": t, "end": t + 2.0}; t += 2.0
        st[f"answer_{i}"] = {"start": t, "end": t + 1.2}; t += 1.6
    st["verdict"] = {"start": t, "end": t + 6.0}; t += 6.5
    st["outro"] = {"start": t, "end": t + 3.0}
    data = copy.deepcopy(data)
    data["segment_times"] = st
    return data, t + 3.0


# ── schema and length ────────────────────────────────────────────────

@pytest.mark.parametrize("vtype", sorted(SCRIPTS))
def test_every_queued_script_validates(vtype):
    import script_schema
    assert len(QUEUED[vtype]) == 100
    for p in QUEUED[vtype]:
        script_schema.SCRIPT_MODELS[vtype].model_validate(json.loads(p.read_text(encoding="utf-8")))


@pytest.mark.parametrize("break_it, why", [
    (lambda d: d["items"].pop(), "exactly 10"),
    (lambda d: d["items"].reverse(), "non-decreasing"),
    (lambda d: d.update(verdict="Muy bien, sigue así."), "tier boundary"),
    (lambda d: d["items"][0].update(english="[excited] spoon"), "only allowed in intro and outro"),
    (lambda d: d.update(hashtags=["#AprenderInglés"] * 5), "the first #NivelDeInglés"),
    (lambda d: d["items"][1].update(english="spoon"), "duplicate english"),
])
def test_the_format_rules_are_the_schema(break_it, why):
    import script_schema
    data = _script("level_test")
    break_it(data)
    with pytest.raises(ValueError, match=why):
        script_schema.SCRIPT_MODELS["level_test"].model_validate(data)


def test_say_it_traps_need_a_tip():
    import script_schema
    data = _script("say_it_level")
    data["items"][9].pop("tip")
    with pytest.raises(ValueError, match="need a tip"):
        script_schema.SCRIPT_MODELS["say_it_level"].model_validate(data)


def test_length_spec_measures_with_the_renderers_line_and_note():
    import length_spec
    from video.how_do_you_say import LINE_W, fit_line
    assert length_spec.check_script(_script("level_test")) == []
    long = _script("say_it_level")
    before = {(v["where"], v["field"]) for v in length_spec.check_script(long)}
    long["items"][0]["spanish"] = "Una mesa para dos personas junto a la ventana, por favor."
    long["items"][1]["tip"] = "Una explicación muy larga " * 6
    bad = {(v["where"], v["field"]) for v in length_spec.check_script(long)}
    assert bad - before == {("items[0]", "spanish"), ("items[1]", "tip")}
    assert fit_line(long["items"][0]["spanish"])[2] > LINE_W


# ── renderer ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("vtype", sorted(SCRIPTS))
def test_level_frames_are_a_pure_function_of_t(no_mascot, vtype):
    import numpy as np
    from video.how_do_you_say import create_frame_level
    data, dur = _timeline(_script(vtype))
    t = data["segment_times"]["answer_5"]["start"] + 0.3
    a = create_frame_level(t, copy.deepcopy(data), dur)
    create_frame_level(2.0, data, dur)
    assert np.array_equal(a, create_frame_level(t, data, dur))


def test_no_segment_times_is_a_refusal_not_a_guess(no_mascot):
    from video.how_do_you_say import create_frame_level
    with pytest.raises(KeyError, match="segment_times"):
        create_frame_level(1.0, _script("level_test"), 60.0)


def test_an_unspoken_prompt_lights_its_row_at_the_pause():
    from video.how_do_you_say import LevelTimeline
    data, dur = _timeline(_script("say_it_level"), speak_prompt=False)
    tl = LevelTimeline(data, dur)
    assert tl.row == [s for s, _e in tl.think]
    assert tl.row_end(9) == tl.verdict[0]


def test_the_pencil_waits_off_the_prompts_then_writes_the_answer():
    from video.how_do_you_say import (LINE_X, PENCIL_MOVE, PENCIL_WAIT_X, LevelTimeline,
                                      fit_line, level_pencil_position, page_size, row_centres)
    data, dur = _timeline(_script("level_test"))
    tl, items = LevelTimeline(data, dur), data["items"]
    size = page_size(tuple(it["spanish"] for it in items))
    centres = row_centres(10)
    think = data["segment_times"]["think_2"]
    assert level_pencil_position(think["end"] - PENCIL_MOVE - 0.01, tl, items, "spanish", centres, size)[0] \
        == pytest.approx(PENCIL_WAIT_X)
    ans = data["segment_times"]["answer_2"]
    assert level_pencil_position(ans["start"], tl, items, "spanish", centres, size)[0] == pytest.approx(LINE_X)
    assert level_pencil_position(ans["end"], tl, items, "spanish", centres, size)[0] == \
        pytest.approx(LINE_X + fit_line(items[1]["spanish"], size)[2])


# ── audio ────────────────────────────────────────────────────────────

def _tone(path, total=0.9):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*440*t)*between(t,0.05,{total - 0.15})':s=44100:d={total}",
                    "-ac", "1", "-q:a", "2", path], check=True)


@pytest.mark.parametrize("vtype", sorted(SCRIPTS))
def test_generator_declares_every_segment_and_caches_the_tier_lines(tmp_path, monkeypatch, vtype):
    import tts_elevenlabs as TE
    calls = []

    def fake(text, output_path, **kw):
        calls.append(text)
        _tone(output_path)
        return 0.0

    monkeypatch.setattr(TE, "generate_segment_audio", fake)
    monkeypatch.setattr(TE, "_onset_clean", lambda path: True)
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    script = _script(vtype)
    out = TE.generate_level_audio_segmented(script, str(tmp_path / "a.mp3"))
    plan = TE.LEVEL_PLANS[vtype]

    order = ["intro"]
    for i in range(1, 11):
        order += [f"tier_{i}"] if i in TE.LEVEL_TIER_LINES else []
        order += [f"prompt_{i}"] if plan["speak_prompt"] else []
        order += [f"think_{i}", f"answer_{i}"]
    order += ["verdict", "outro"]
    assert [s["id"] for s in out["segments"]] == order
    st = out["segment_times"]
    assert all(st[f"think_{i}"]["duration"] == pytest.approx(plan["think"], abs=0.002) for i in range(1, 11))
    assert all(s["text"] == "[silence]" for s in out["segments"] if s["id"].startswith("think_"))
    starts = [st[k]["start"] for k in order]
    assert starts == sorted(starts)
    assert out["characters"] == sum(len(c) for c in calls)

    # the tier lines are not asked for again
    calls.clear()
    TE.generate_level_audio_segmented(script, str(tmp_path / "b.mp3"))
    assert not any(c in TE.LEVEL_TIER_LINES.values() for c in calls)


def test_a_dirty_english_onset_is_asked_again(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    calls, verdicts = [], iter([False, True] + [True] * 100)
    monkeypatch.setattr(TE, "generate_segment_audio", lambda text, output_path, **kw: calls.append(text) or _tone(output_path))
    monkeypatch.setattr(TE, "_onset_clean", lambda path: next(verdicts))
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    out = TE.generate_level_audio_segmented(_script("level_test"), str(tmp_path / "a.mp3"))
    assert out["onset_retakes"] == 1 and calls.count("spoon.") == 2


# ── the doors that read the registry ─────────────────────────────────

def test_registry_entries_share_the_notebook_band():
    import video_types
    for vtype in SCRIPTS:
        entry = video_types.spec(vtype)
        assert entry["text_band"] == video_types.spec("how_do_you_say")["text_band"]
        assert video_types.renderer_for(vtype).__name__ == "create_frame_level"


def test_each_category_feeds_its_type_only():
    import yaml
    cats = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["type_categories"]
    for vtype, category in (("level_test", "level_vocab"), ("say_it_level", "say_it")):
        assert cats[vtype] == [category]
        assert [t for t, cs in cats.items() if category in cs] == [vtype]


def test_openai_refuses_instead_of_narrating_full_script(tmp_path):
    from tts_providers.openai_provider import OpenAITTSProvider
    for vtype in SCRIPTS:
        with pytest.raises(NotImplementedError, match=vtype):
            OpenAITTSProvider().generate_from_script(_script(vtype), str(tmp_path / "a.mp3"))


@pytest.mark.parametrize("vtype", sorted(SCRIPTS))
def test_the_generator_prompt_names_the_type_and_its_tag(vtype):
    from script_generator import build_prompt
    from script_schema import LEVEL_TYPE_TAGS
    prompt = build_prompt("x", {"id": "lv999", "theme": "la playa"}, vtype)
    assert f'"type": "{vtype}"' in prompt and LEVEL_TYPE_TAGS[vtype] in prompt


def test_spoken_words_count_the_plan():
    from duration_calibrate import spoken_words
    script = _script("say_it_level")
    words = spoken_words(script)
    assert words > sum(len(it["english"].split()) for it in script["items"])

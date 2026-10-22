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


#: sha256[:16] of raw frames over a flat base. First pinned before the level modes (3c5ab68);
#: RE-PINNED at STEP 77 §1, when every mark started coming from the supersampled notebook kit
#: (the frames changed on purpose: anti-aliased edges; stills reviewed in _audit/stills/STEP77/), and
#: again at §2 (page tilted by cv2 once per state, the pencil drawn unrotated after the tilt),
#: and at §3 (motion: rise, cascade, hook, swipe, stroke ticks, feather, 200 px pencil, CTA).
HDYS_PIN = {
    0.0: "38a36cc013070f75",
    4.7: "4c0f682443d3f606",
    15.5: "4061f78307443edf",
    25.9: "841eb7d5d85e5334",
    50.2: "b55dad4ed5eeeddf",
    53.6: "3c898e316c3fd650",
    63.7: "04b15d530f3cb48d",
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
# Producing a video moves its script to queue/_done/: the corpus is both (STEP 60 §3).
from level_length_report import scripts as _corpus  # noqa: E402
QUEUED = {t: _corpus(t) for t in SCRIPTS}


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
    # ±WOBBLE: the pencil's hand while it writes (STEP 77 §3)
    assert level_pencil_position(ans["start"], tl, items, "spanish", centres, size)[0] == \
        pytest.approx(LINE_X, abs=2.0)
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
    monkeypatch.setattr(TE, "_onset_values", lambda path: CLEAN)
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
    assert [st[f"think_{i}"]["duration"] for i in range(1, 11)] == \
        pytest.approx(TE.level_thinks(script), abs=0.002)
    assert all(s["text"] == "[silence]" for s in out["segments"] if s["id"].startswith("think_"))
    starts = [st[k]["start"] for k in order]
    assert starts == sorted(starts)
    assert out["characters"] == sum(len(c) for c in calls)

    # the tier lines are not asked for again
    calls.clear()
    TE.generate_level_audio_segmented(script, str(tmp_path / "b.mp3"))
    assert not any(c in TE.LEVEL_TIER_LINES.values() for c in calls)


CLEAN = {"start_db": -40.0, "fragment": None, "doubled_onset": None}


def _rig(tmp_path, monkeypatch, values):
    """generate_level_audio_segmented with each take's tone length marking which take it is."""
    import tts_elevenlabs as TE
    calls, takes = [], iter(values)
    def fake(text, output_path, **kw):
        calls.append(text)
        _tone(output_path, total=0.9 + 0.1 * calls.count(text))
    monkeypatch.setattr(TE, "generate_segment_audio", fake)
    # Every clip is gated (STEP 76 §3); the scripted takes belong to prompt_1, the rest are clean.
    monkeypatch.setattr(TE, "_onset_values", lambda path: next(takes, CLEAN) if "prompt_1." in path else CLEAN)
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    monkeypatch.setattr(TE, "LEVEL_TIER_CACHE", tmp_path / "tiers")
    import tts_common
    monkeypatch.setattr(tts_common, "trim_clip_silence", lambda path: None)
    out = TE.generate_level_audio_segmented(_script("level_test"), str(tmp_path / "a.mp3"))
    return out, calls


def test_a_dirty_english_onset_is_asked_again(tmp_path, monkeypatch):
    dirty = {"start_db": -2.0, "fragment": None, "doubled_onset": None}
    out, calls = _rig(tmp_path, monkeypatch, [dirty, CLEAN])
    assert out["onset_retakes"] == 1 and calls.count("spoon.") == 2


def test_after_two_re_asks_the_cleanest_take_is_kept_not_the_last(tmp_path, monkeypatch):
    first = {"start_db": -5.0, "fragment": None, "doubled_onset": None}
    second = {"start_db": -1.0, "fragment": None, "doubled_onset": None}
    third = {"start_db": -40.0, "fragment": (70, 64.7), "doubled_onset": None}
    out, calls = _rig(tmp_path, monkeypatch, [first, second, third])
    assert out["onset_retakes"] == 2 and calls.count("spoon.") == 3
    st = out["segment_times"]["prompt_1"]
    assert st["end"] - st["start"] == pytest.approx(0.85, abs=0.03)   # take 0's speech: 1.0 s tone, 0.15 s tail


def test_cleanest_take_ranks_flaws_before_level():
    import tts_elevenlabs as TE
    takes = [{"start_db": -50.0, "fragment": None, "doubled_onset": "held nasal"},
             {"start_db": -5.0, "fragment": None, "doubled_onset": None},
             {"start_db": -3.0, "fragment": None, "doubled_onset": None}]
    assert TE.cleanest_take(takes) == 1
    assert TE.cleanest_take([dict(takes[1], start_db=-9.0), takes[1]]) == 0     # clean on v3 wins


def test_the_start_limit_is_per_model():
    import tts_elevenlabs as TE
    s_word = {"start_db": -9.0, "fragment": None, "doubled_onset": None}      # «sink» on v3
    assert TE.onset_clean(s_word, "eleven_v3") and not TE.onset_clean(s_word, "eleven_multilingual_v2")
    assert not TE.onset_clean(dict(s_word, start_db=-0.4), "eleven_v3")       # «oven» cut in at its peak


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


# ── STEP 60 §2: thinking time ───────────────────────────────────────

@pytest.mark.parametrize("length,seconds", [(1, 3.0), (20, 3.0), (21, 4.0), (27, 4.0), (28, 5.0), (60, 5.0)])
def test_say_it_level_thinks_longer_on_a_longer_sentence(length, seconds):
    import tts_elevenlabs as TE
    assert TE.level_think(TE.LEVEL_PLANS["say_it_level"], "x" * length) == seconds


def test_level_test_thinks_four_seconds_on_any_word():
    import tts_elevenlabs as TE
    plan = TE.LEVEL_PLANS["level_test"]
    assert {TE.level_think(plan, w) for w in ("oven", "cutting board", "x" * 40)} == {4.0}


@pytest.mark.parametrize("vtype", ["level_test", "say_it_level"])
def test_the_level_types_reject_over_95_seconds(vtype):
    import duration_spec
    assert duration_spec.reject_window(vtype)["max_seconds"] == 95.0


def test_the_predictor_adds_the_thinks_to_speech_gaps_and_the_card():
    import tts_elevenlabs as TE
    script = _script("say_it_level")
    base = TE.level_predict(script, [0.0] * 10)
    assert TE.level_predict(script, [3.0] * 10) == pytest.approx(base + 30.0)


# ── STEP 62 §0: pauses shrink to keep a level video under its ceiling ──

def _long(vtype, extra_chars):
    """A real script with its verdict padded, so speech alone pushes it over 95 s."""
    script = _script(vtype)
    script["verdict"] += " " + "a" * extra_chars
    return script


@pytest.mark.parametrize("vtype", ["level_test", "say_it_level"])
def test_a_script_under_the_ceiling_keeps_its_pauses(vtype):
    import tts_elevenlabs as TE
    script = _script(vtype)
    plan = TE.LEVEL_PLANS[vtype]
    assert TE.level_thinks(script) == [TE.level_think(plan, it[plan["prompt"][0]]) for it in script["items"]]


@pytest.mark.parametrize("vtype", ["level_test", "say_it_level"])
def test_an_overlong_script_shrinks_every_pause_by_one_fraction_to_fit(vtype):
    import tts_elevenlabs as TE
    plan = TE.LEVEL_PLANS[vtype]
    script = _script(vtype)
    full = TE.level_thinks(script)
    over = 95.0 - TE.level_predict(script, full) + 3.0          # 3 s over the ceiling
    script = _long(vtype, int(over / plan["s_per_char"]) + 1)
    thinks = TE.level_thinks(script)
    assert TE.level_predict(script, thinks) <= 95.0
    ratios = {round(t / f, 2) for t, f in zip(thinks, full)}
    assert len(ratios) == 1 and ratios.pop() < 1.0             # one fraction for every row
    assert min(thinks) >= plan["think_floor"]


@pytest.mark.parametrize("vtype", ["level_test", "say_it_level"])
def test_no_pause_goes_under_the_floor_and_the_script_stays_over(vtype):
    import tts_elevenlabs as TE
    plan = TE.LEVEL_PLANS[vtype]
    script = _long(vtype, 600)
    thinks = TE.level_thinks(script)
    assert min(thinks) == plan["think_floor"]
    assert TE.level_predict(script, thinks) > 95.0              # duration_calibrate lists it


def test_true_false_level_has_no_floor_and_never_shrinks():
    import tts_elevenlabs as TE
    assert "think_floor" not in TE.LEVEL_PLANS["true_false_level"]

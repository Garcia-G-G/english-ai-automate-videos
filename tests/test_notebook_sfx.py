"""STEP 77 §7: procedural sound effects under the notebook Shorts' voice."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import video.how_do_you_say as H  # noqa: E402
from video.notebook import sfx  # noqa: E402

RATE = 44100


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_effects_are_synthesised_and_deterministic():
    for name, seconds in (("pop", 0), ("swish", 0), ("scratch", 1.2)):
        a, b = sfx.render(name, RATE, seconds), sfx.render(name, RATE, seconds)
        assert np.array_equal(a, b) and np.isfinite(a).all() and np.abs(a).max() > 0
    assert sfx.render("scratch", RATE, 1.2).size == int(1.2 * RATE)
    assert sfx.render("pop", RATE).size == int(0.030 * RATE)


def test_an_effect_sits_22db_under_the_voice_and_6_more_on_a_word():
    t = np.arange(6 * RATE) / RATE
    voice = np.where((t > 1) & (t < 2), 0.2 * np.sin(2 * np.pi * 220 * t), 0.0)   # one «word» at 1-2 s
    spoken = [(1.0, 2.0)]
    vdb = sfx.voice_rms_db(voice, RATE, spoken)
    mixed, placed = sfx.mix(voice, RATE, [("pop", 4.0, 0), ("pop", 1.5, 0)], spoken)
    alone = mixed[int(4.0 * RATE):int(4.0 * RATE) + int(0.030 * RATE)]
    assert sfx.rms_db(alone) == pytest.approx(vdb - sfx.UNDER_DB, abs=0.2)
    assert placed[0]["ducked"] is False and placed[1]["ducked"] is True
    assert placed[1]["level_db"] == pytest.approx(vdb - sfx.UNDER_DB - sfx.DUCK_DB, abs=0.1)
    assert mixed.size == voice.size


def test_how_do_you_say_events_follow_its_timeline():
    T = _load("t_h7", ROOT / "tests" / "test_how_do_you_say.py")
    data, dur = T._timeline(T._script())
    events, spoken = H.sfx_events(data, dur)
    names = [e[0] for e in events]
    tl = H.Timeline(data, dur)
    assert events[0] == ("swish", 0.0, 0.0) and ("swish", dur - H.HANDOFF, 0.0) in events
    assert names.count("scratch") == tl.n and names.count("pop") == 2 * tl.n + 2   # emoji, tick; hook, CTA
    assert all(not (a <= (tl.think[0][0] + tl.think[0][1]) / 2 < b) for a, b in spoken)   # pauses are silence
    assert "music" not in names


@pytest.mark.parametrize("vtype, scratches", [("choose_level", 10), ("true_false_level", 0)])
def test_level_events_scratch_only_where_the_pencil_writes_and_swish_on_the_page_turn(vtype, scratches):
    data, dur = _load("t_s63_7", ROOT / "tests" / "test_level_step63_fixes.py")._timeline(vtype)
    events, _spoken = H.sfx_events(data, dur)
    names = [e[0] for e in events]
    assert names.count("scratch") == scratches
    layout = H.level_layout(vtype, data["items"])
    assert names.count("swish") == 2 + (len(layout.pages) - 1)                  # in, page turns, out


def test_the_mix_keeps_the_narrations_length_and_loudness(tmp_path):
    import loudness
    import pipeline
    T = _load("t_h7b", ROOT / "tests" / "test_how_do_you_say.py")
    data, dur = T._timeline(T._script())
    t = np.arange(int(dur * RATE)) / RATE
    voice = np.zeros_like(t)
    for v in data["segment_times"].values():
        a, b = v["start"], v["end"]
        voice += np.where((t >= a) & (t < b), 0.15 * np.sin(2 * np.pi * 180 * t), 0.0)
    wav = tmp_path / "n.wav"
    loudness._write_wav(voice, wav)
    data_path = tmp_path / "d.json"
    import json
    data_path.write_text(json.dumps({k: v for k, v in data.items() if not k.startswith("_")}), encoding="utf-8")
    before = loudness.measure(wav)
    info = pipeline.add_notebook_sfx(wav, data_path)
    after = loudness.measure(wav)
    assert info["effects"] > 20
    assert loudness.decode(wav).size == voice.size
    assert abs(after["I"] - before["I"]) < 0.3


def test_render_video_mixes_effects_only_for_the_notebook_types():
    src = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert "if video_type in PANEL_TYPES:\n        add_notebook_sfx(narration, data_path)" in src

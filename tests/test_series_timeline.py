"""STEP 78 §2: one timeline from the voice, the shared kit, and the render driver."""
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.series import beats as B  # noqa: E402
from video.series import render as R  # noqa: E402
from video.series import series_kit as K  # noqa: E402


def _draft(sid):
    return json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / f"{sid}.json").read_text(encoding="utf-8"))


def _words(lines):
    """Timed words as the TTS would return them: 0.3 s a word, 0.4 s between lines."""
    out, t = [], 0.0
    for line in lines:
        for tok in line.replace("[[", "").replace("]]", "").split():
            out.append({"word": tok, "start": round(t, 3), "end": round(t + 0.25, 3)})
            t += 0.3
        t += 0.4
    return out, t


def test_every_word_lands_on_its_line_and_every_english_phrase_is_timed():
    s = _draft("hc_m001")
    words, dur = _words(s["voice"])
    tl = B.build_beats(s, words, dur)
    assert [b["i"] for b in tl["beats"]] == list(range(len(s["voice"])))
    assert all(a["end"] <= b["start"] for a, b in zip(tl["beats"], tl["beats"][1:]))
    phrases = [e for b in tl["beats"] for e in b["english"]]
    assert [e["text"] for e in phrases] == [p for line in s["voice"] for p in B._MARK.findall(line)]
    assert not any(e.get("unheard") for e in phrases)
    third = tl["beats"][2]
    assert third["start"] <= phrases[0]["start"] < phrases[0]["end"] <= third["end"]


@pytest.mark.parametrize("sid, line", [("hc_c001", 1), ("hc_c002", 1), ("hc_c004", 1), ("hc_m001", None)])
def test_the_countdown_goes_after_its_line_or_before_the_reveal(sid, line):
    assert B.countdown_line(_draft(sid)) == line


def test_the_countdown_is_three_seconds_of_room_tone_and_moves_what_follows():
    s = _draft("hc_c001")
    words, dur = _words(s["voice"])
    tl = B.build_beats(s, words, dur)
    rate = 1000
    samples = np.ones(int(dur * rate)) * 0.5
    new, out = B.insert_countdown(tl, samples, rate, 1)
    a, b = new["countdown"]
    assert b - a == pytest.approx(B.COUNTDOWN) and out.size == samples.size + int(B.COUNTDOWN * rate)
    tone = out[int(a * rate) + 50:int(b * rate) - 50]
    assert 20 * np.log10(np.sqrt(np.mean(tone ** 2))) == pytest.approx(B.ROOM_TONE_DB, abs=1.5)
    assert new["beats"][2]["start"] == pytest.approx(tl["beats"][2]["start"] + B.COUNTDOWN)
    assert new["beats"][1]["end"] == tl["beats"][1]["end"] and new["beats"][1]["end"] < a < new["beats"][2]["start"]


def test_the_gate_is_25_to_60_seconds():
    assert B.gate(42) is None and B.gate(24.9).startswith("duration") and B.gate(60.1).startswith("duration")


def test_a_voiced_script_has_every_english_phrase_heard_and_its_countdown():
    path = ROOT / "output" / "rendering" / "step78_s2" / "hc_c001.timeline.json"
    if not path.exists():
        pytest.skip("hc_c001 has not been voiced on this machine")
    tl = json.loads(path.read_text(encoding="utf-8"))
    assert tl["countdown"][1] - tl["countdown"][0] == pytest.approx(B.COUNTDOWN)
    assert all(not e.get("unheard") for b in tl["beats"] for e in b["english"])
    assert B.gate(tl["duration"] + 4.0) is None


def test_eleven_v3_is_sent_no_context(monkeypatch, tmp_path):
    import tts_bilingual as TB
    import tts_cache
    import tts_elevenlabs as TE
    sent = {}

    class Stop(Exception):
        pass

    class Fake:
        class text_to_speech:
            @staticmethod
            def convert_with_timestamps(**kw):
                sent.update(kw)
                raise Stop()
    monkeypatch.setattr(TE, "get_client", lambda *a, **k: Fake)
    monkeypatch.setattr(tts_cache, "restore", lambda *a, **k: None)
    monkeypatch.setattr("cost_tracker.check_tts_budget", lambda *a, **k: None)
    call = {"index": 0, "text": "Hola", "lang": "es", "is_english": False, "voice_id": "v", "model_id": "eleven_v3",
            "speed": 1.0, "previous_text": "antes", "next_text": "después", "pause_after": 0.1}
    for model, has_context in (("eleven_v3", False), ("eleven_turbo_v2_5", True)):
        sent.clear()
        with pytest.raises(Exception):
            TB._synthesize_segment({**call, "model_id": model}, str(tmp_path / "a.mp3"),
                                   {**TB.resolve_settings(), "model_id": model})
        assert sent, "the fake client was not reached"
        assert ("previous_text" in sent and "next_text" in sent) == has_context, model


def test_text_fits_its_box_or_says_it_does_not():
    size, lines = K.fit("I have twenty-five years and nobody understands me", "fredoka", 600, 60, 30, 2)
    assert 30 <= size <= 60 and len(lines) <= 2
    with pytest.raises(K.Overflow):
        K.fit("palabra " * 60, "fredoka", 300, 40, 30, 2)
    assert K.in_safe_area((100, 300, 900, 600)) and not K.in_safe_area((100, 1450, 900, 1550))
    assert not K.in_safe_area((100, 100, 900, 200)) and not K.in_safe_area((900, 1000, 1000, 1100))


def test_the_outro_shows_the_answer_from_its_first_frame_inside_the_safe_area():
    """STEP 80: the answer was on screen only from the outro's second 2; now from its start."""
    from video import outro as O
    v = O.load_variants()["variants"][0]
    shown, blank = K.outro_frame(0.5, v, "My brother is 12."), K.outro_frame(0.5, v, " ")
    box = K.outro_answer_box("My brother is 12.")
    assert K.in_safe_area(box)
    y0, y1 = int(box[1]), int(box[3])
    assert np.abs(shown[y0:y1].astype(int) - blank[y0:y1].astype(int)).sum() > 10000


def _dummy_style():
    m = types.ModuleType("dummy_style")
    m.frame = lambda t, s, tl: Image.new("RGBA", (K.W, K.H), (30, 30, 30, 255))
    m.sfx_events = lambda s, tl: [("pop", 0.1, 0.0)]
    m.text_boxes = lambda s: []
    return m


def test_the_driver_renders_a_two_second_smoke_clip_without_tts(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "style_module", lambda style: _dummy_style())
    import tts_bilingual
    monkeypatch.setattr(tts_bilingual, "generate_bilingual_narration",
                        lambda *a, **k: pytest.fail("a smoke clip voiced something"))
    info = R.render_series(_draft("hc_e001"), tmp_path / "e.mp4", tmp_path / "w", silent=True, seconds=2.0, workers=1)
    assert info["duration"] == 2.0 and info["tts_usd"] == 0.0
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=color_primaries",
                                       "-of", "json", str(tmp_path / "e.mp4")], capture_output=True, text=True).stdout)
    assert abs(float(probe["format"]["duration"]) - 2.0) < 0.2
    assert any(s.get("color_primaries") == "bt709" for s in probe["streams"])
    assert json.loads((tmp_path / "e.json").read_text())["silent"] is True


@pytest.mark.parametrize("path", sorted((ROOT / "content" / "hecho_con_claude" / "drafts").glob("hc_*.json")),
                         ids=lambda p: p.stem)
def test_every_script_has_an_estimated_timeline(path):
    s = json.loads(path.read_text(encoding="utf-8"))
    tl = R.estimated_timeline(s)
    assert len(tl["beats"]) == len(s["voice"]) and tl["estimated"]
    assert (tl["countdown"] is not None) == (s["style"] == "comic")

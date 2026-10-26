"""The Manim voiceover cache must not hand back a stale beat.

Regression for 2026-10-08: third-person-s failed to render with
"There is no <bookmark mark='p0' />". The cache was keyed on the narration with
its bookmarks removed, so adding {{pause:3}} to a quiz (new bookmark, same words)
returned the old entry -- old bookmarks and old audio. The copied mp3 was also
named "<voice>-<beat>.mp3" for every lesson, so lessons overwrote each other.

manim_voiceover is only installed in the Mac's .venv, so it is stubbed here: the
test covers voices.py's own logic, which is where the bug was.
"""
import json
import re
import sys
import types
from pathlib import Path

import pytest

POC = Path(__file__).resolve().parent.parent / "experiments" / "manim_voiceover_poc"


@pytest.fixture()
def voices(monkeypatch):
    helper = types.ModuleType("manim_voiceover.helper")
    helper.remove_bookmarks = lambda s: re.sub(r"<bookmark\s*mark\s*=['\"]\w*['\"]\s*/>", "", s)

    class SpeechService:
        def __init__(self, cache_dir=None, **_):
            self.cache_dir = cache_dir
            self.entries = []

        def get_cached_result(self, input_data, cache_dir):
            for e in self.entries:
                if e["input_data"] == input_data:
                    return e
            return None

    base = types.ModuleType("manim_voiceover.services.base")
    base.SpeechService = SpeechService
    for name, mod in {"manim_voiceover": types.ModuleType("manim_voiceover"),
                      "manim_voiceover.helper": helper,
                      "manim_voiceover.services": types.ModuleType("manim_voiceover.services"),
                      "manim_voiceover.services.base": base}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.syspath_prepend(str(POC))
    sys.modules.pop("voices", None)
    import voices as v
    yield v
    sys.modules.pop("voices", None)


def make_lesson(root, lesson, text, audio=b"AUDIO-1"):
    folder = root / "audio" / lesson / "teacher"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "b26.mp3").write_bytes(audio)
    words = [{"word": w, "start": i * 0.3} for i, w in enumerate(text.split())]
    (folder / "b26.words.json").write_text(json.dumps(words))
    (folder / "manifest.json").write_text(json.dumps({"voice": "teacher", "beats": [
        {"id": "b26", "text": text, "mp3": "b26.mp3", "words": "b26.words.json"}]}))
    return folder


TEXT = "Primera pregunta. Piénsalo. Es lives."
NO_PAUSE = "Primera pregunta. Piénsalo. Es <bookmark mark='c0'/>lives."
WITH_PAUSE = "Primera pregunta. Piénsalo. <bookmark mark='p0'/>Es <bookmark mark='c0'/>lives."


def run(v, folder, cache, text):
    svc = v.PrerecordedService(folder, deess=False, cache_dir=str(cache))   # fake mp3 bytes: the keys, not the sound (STEP 80 §00 is tested in test_deesser)
    return svc, svc.generate_from_text(text, beat_id="b26")


def test_a_new_bookmark_is_not_answered_from_the_old_entry(voices, tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    folder = make_lesson(tmp_path, "third-person-s", TEXT)
    svc, old = run(voices, folder, cache, NO_PAUSE)
    svc.entries.append(old)
    new = svc.generate_from_text(WITH_PAUSE, beat_id="b26")
    assert "mark='p0'" in new["input_text"]
    assert new["input_data"] != old["input_data"]


def test_regenerated_audio_is_not_answered_from_the_old_entry(voices, tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    folder = make_lesson(tmp_path, "third-person-s", TEXT, b"OLD")
    svc, old = run(voices, folder, cache, WITH_PAUSE)
    svc.entries.append(old)
    make_lesson(tmp_path, "third-person-s", TEXT, b"NEW-WITH-SILENCE")
    new = svc.generate_from_text(WITH_PAUSE, beat_id="b26")
    assert new["original_audio"] != old["original_audio"]
    assert (cache / new["original_audio"]).read_bytes() == b"NEW-WITH-SILENCE"


def test_two_lessons_never_share_a_cached_file(voices, tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    a = make_lesson(tmp_path, "third-person-s", TEXT, b"A")
    b = make_lesson(tmp_path, "morning-phrasal-verbs", TEXT, b"B")
    _, ra = run(voices, a, cache, WITH_PAUSE)
    _, rb = run(voices, b, cache, WITH_PAUSE)
    assert ra["original_audio"] != rb["original_audio"]
    assert (cache / ra["original_audio"]).read_bytes() == b"A"
    assert (cache / rb["original_audio"]).read_bytes() == b"B"


def test_an_unchanged_beat_is_still_a_cache_hit(voices, tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    folder = make_lesson(tmp_path, "third-person-s", TEXT)
    svc, first = run(voices, folder, cache, WITH_PAUSE)
    svc.entries.append(first)
    assert svc.generate_from_text(WITH_PAUSE, beat_id="b26") is first

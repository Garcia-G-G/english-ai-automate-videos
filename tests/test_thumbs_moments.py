"""STEP 85b §1: the moment rule of the level formats and phrases_level, from the timestamps the renderer already knows."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import thumbs as T  # noqa: E402
from test_level_family import _script, _timeline as _level_timeline  # noqa: E402
from test_phrases_level import _script as _phrases_script, _timeline as _phrases_timeline  # noqa: E402
from video.how_do_you_say import LevelTimeline  # noqa: E402


@pytest.fixture(autouse=True)
def no_mascot():
    import video.character as character
    character._renderer, character._renderer_resolved = None, True


def test_a_level_question_is_shown_with_its_options_before_any_answer():
    for vtype, speak in (("level_test", True), ("say_it_level", False)):
        d, dur = _level_timeline(_script(vtype), speak_prompt=speak)
        tl = LevelTimeline(d, dur)
        m = dict(T.level_moments(d, dur))
        assert tl.row[0] <= m["A"] < tl.answer[0][0], vtype                    # lit, not yet answered
        assert m["B"] == 0.0 and tl.row[1] <= m["C"] < tl.answer[1][0], vtype  # C: the second question


def test_phrases_level_shows_the_spanish_before_the_english_and_c_is_the_sixth_reveal():
    d, dur = _phrases_timeline(_phrases_script())
    tl = LevelTimeline(d, dur)
    m = dict(T.level_moments(d, dur, sixth=True))
    assert tl.row[0] <= m["A"] < tl.answer[0][0]
    assert m["C"] > tl.answer[5][0] and m["C"] < tl.answer[6][0] + 1


def test_phrases_level_is_drawn_by_the_tablero_kit(tmp_path):
    d, dur = _phrases_timeline(_phrases_script())
    d["type"] = "phrases_level"
    info = T.make_for_video(tmp_path / "p.mp4", d, dur)
    assert info["chosen"] == "A" and info["metrics"]["A"]["source"] == "kit" and info["metrics"]["A"]["ok"]
    assert Image.open(T.thumb_dir(tmp_path / "p.mp4") / "cands" / "A.png").size == (1080, 1920)


def test_a_level_page_is_drawn_by_the_notebook_kit_with_the_looser_sharpness(tmp_path):
    d, dur = _level_timeline(_script("level_test"))
    d["type"] = "level_test"
    info = T.make_for_video(tmp_path / "l.mp4", d, dur)
    a = info["metrics"]["A"]
    assert info["chosen"] == "A" and a["source"] == "kit" and a["ok"] and a["sharp"] >= T.NOTEBOOK_SHARP_MIN


def test_a_kit_that_cannot_draw_falls_back_to_the_mp4(tmp_path, monkeypatch):
    import subprocess
    mp4 = tmp_path / "q.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=10:d=10", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    d, dur = _phrases_timeline(_phrases_script())
    d["type"] = "phrases_level"
    monkeypatch.setattr(T, "make_for_kit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    info = T.make_for_video(mp4, d, dur)
    assert info["metrics"]["A"]["source"] == "mp4"

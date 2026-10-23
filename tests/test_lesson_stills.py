"""STEP 79 §1: the lesson scene's stills mode — one still per beat at its midpoint, recorded
timings where cached and estimated otherwise, no TTS and nothing encoded."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "experiments" / "manim_voiceover_poc"
MANIM = STUDIO / ".venv" / "bin" / "manim"
PY = STUDIO / ".venv" / "bin" / "python"

pytestmark = pytest.mark.skipif(not MANIM.exists(), reason="the lesson studio's Manim venv is not installed")


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    """A two-beat lesson with no audio at all: everything estimated."""
    tmp = tmp_path_factory.mktemp("stills")
    lesson = json.loads((STUDIO / "lessons" / "demo-motion.json").read_text(encoding="utf-8"))
    lesson = {**lesson, "id": "stills-mini", "beats": [b for b in lesson["beats"] if b["id"] in ("b02", "b03")]}
    path = tmp / "stills-mini.json"
    path.write_text(json.dumps(lesson, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    env = {k: v for k, v in os.environ.items() if k not in ("VOICE_DIR", "PYTEST_CURRENT_TEST")}
    env.update(STILLS="1", STILLS_OUT=str(out), LESSON=str(path), TIMELINE_OUT=str(tmp / "timeline.json"),
               ELEVENLABS_LOCK="1")
    run = subprocess.run([str(MANIM), "-ql", "--dry_run", "--disable_caching", "lesson_scene.py", "Lesson"],
                         cwd=str(STUDIO), env=env, capture_output=True, text=True, timeout=600)
    return {"run": run, "out": out, "lesson": lesson, "tmp": tmp}


def test_one_still_per_beat_at_its_midpoint_with_nothing_encoded(mini):
    assert mini["run"].returncode == 0, mini["run"].stdout[-2000:] + mini["run"].stderr[-2000:]
    index = json.loads((mini["out"] / "stills.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in index["stills"]] == ["b02", "b03"]
    assert all((mini["out"] / s["file"]).exists() for s in index["stills"])
    assert not list(mini["tmp"].rglob("*.mp4")) and not list((STUDIO / "media" / "videos").rglob("stills-mini*"))


def test_with_no_audio_every_beat_is_estimated_from_the_fitted_rate(mini):
    index = json.loads((mini["out"] / "stills.json").read_text(encoding="utf-8"))
    assert index["estimated"] == ["b02", "b03"] and all(s["estimated"] for s in index["stills"])
    timeline = json.loads((mini["tmp"] / "timeline.json").read_text(encoding="utf-8"))
    starts = {b["id"]: b["start"] for b in timeline["beats"]}
    b03 = next(s for s in index["stills"] if s["id"] == "b03")
    assert b03["t"] > starts["b03"]                              # the still is inside its beat


def test_a_beat_with_matching_cached_audio_keeps_its_recorded_length():
    """make-vs-do is voiced: the service hands back the recorded beat, not an estimate."""
    voice_dir = STUDIO / "audio" / "make-vs-do" / "english-teacher"
    if not (voice_dir / "manifest.json").exists():
        pytest.skip("make-vs-do has no cached audio on this machine")
    code = """
import json, sys, tempfile
sys.path.insert(0, ".")
import lesson as L
from voices import StillsService
lesson = L.load("lessons/make-vs-do.json")
beat = lesson["beats"][3]
service = StillsService("audio/make-vs-do/english-teacher", lesson=lesson, cache_dir=tempfile.mkdtemp())
text, _marks = L.marked_narration(beat)
out = service.generate_from_text(text, beat_id=beat["id"])
fake = service.generate_from_text("Hola hola hola", beat_id="zz99")
print(json.dumps({"recorded": out["input_data"].get("service"), "fake": fake["input_data"]["service"],
                  "estimated": service.estimated}))
"""
    run = subprocess.run([str(PY), "-c", code], cwd=str(STUDIO), capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-2000:]
    got = json.loads(run.stdout.strip().splitlines()[-1])
    assert got == {"recorded": "prerecorded", "fake": "stills", "estimated": ["zz99"]}

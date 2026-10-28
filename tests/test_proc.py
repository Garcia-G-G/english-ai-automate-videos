"""STEP 75 §2: every external command has a time limit; a timeout raises, logs, frees the lock."""
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import proc  # noqa: E402

SLEEPER = [sys.executable, "-c",
           "import sys, time; sys.stderr.write('frame 41 of 900'); sys.stderr.flush(); time.sleep(30)"]


def test_a_hung_command_is_killed_raises_and_logs_its_stderr_tail(caplog):
    started = time.time()
    with caplog.at_level(logging.ERROR, logger="proc"):
        with pytest.raises(proc.CommandTimeout) as caught:
            proc.run(SLEEPER, timeout=0.5, capture_output=True, text=True)
    assert time.time() - started < 10
    assert isinstance(caught.value, subprocess.TimeoutExpired)       # old except clauses still catch it
    assert "exceeded 0.5s" in str(caught.value) and "frame 41 of 900" in str(caught.value)
    assert "timeout after 0.5s" in caplog.text and "frame 41 of 900" in caplog.text


def test_a_limit_is_required():
    with pytest.raises(ValueError):
        proc.run(["true"], timeout=None)


def test_a_timeout_inside_the_render_lock_releases_it():
    import dashboard_state as ds
    with pytest.raises(proc.CommandTimeout):
        with ds.RENDER_LOCK:
            proc.run(SLEEPER, timeout=0.3, capture_output=True)
    assert ds.RENDER_LOCK.acquire(blocking=False)
    ds.RENDER_LOCK.release()


def test_no_bare_subprocess_run_is_left_in_the_audited_modules():
    for rel in ("src/qa_gate.py", "src/video/outro.py", "src/studio/media_validation.py",
                "src/publishers/common.py", "src/tts_common.py", "src/manim_studio.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not re.search(r"subprocess\.(run|Popen|call|check_output)\(", text), rel


def test_a_manim_job_past_its_limit_fails_and_says_why(tmp_path):
    import manim_studio as M
    job = M.start_job("render", SLEEPER, {}, tmp_path, studio_dir=tmp_path, timeout=0.5)
    deadline = time.time() + 15
    while M.job_status(job, tmp_path).get("state") not in ("done", "failed") and time.time() < deadline:
        time.sleep(0.1)
    status = M.job_status(job, tmp_path)
    assert status["state"] == "failed" and status["code"] == -3
    assert "límite" in status["result"]["error"]
    assert "TIMEOUT" in M.job_log(job, studio_dir=tmp_path)


def test_a_render_gets_three_times_its_audio(tmp_path, monkeypatch):
    import manim_studio as M
    voice = tmp_path / "audio" / "lesson" / "teacher"
    voice.mkdir(parents=True)
    for n in (1, 2):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
                        str(voice / f"b0{n}.mp3")], check=True, timeout=30)
    assert M.lesson_audio_seconds("lesson", "teacher", tmp_path) == pytest.approx(2.0, abs=0.2)
    assert M.render_timeout("lesson", "teacher", tmp_path) == M.RENDER_TIMEOUT_FLOOR     # short: the floor
    monkeypatch.setattr(M, "lesson_audio_seconds", lambda *a, **k: 400.0)
    assert M.render_timeout("lesson", "teacher", tmp_path) == 1200.0
    monkeypatch.setattr(M, "lesson_audio_seconds", lambda *a, **k: 0.0)
    assert M.render_timeout("lesson", "teacher", tmp_path) == M.JOB_TIMEOUTS["render"]  # no audio found

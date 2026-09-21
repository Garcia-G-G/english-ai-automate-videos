#!/usr/bin/env python3
"""Manim Studio — the admin page's logic, without Streamlit, without network.

The class of bug this guards: the owner edits a sentence in the table, the audio on
disk still says the old sentence, and the render silently pairs new words with old
timings — or the scene waits for a word nobody says. The page must see staleness and
validation problems before any button spends money.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "experiments" / "manim_voiceover_poc"))
import manim_studio as ms  # noqa: E402
import lesson as L  # noqa: E402
import renders as R  # noqa: E402


def tiny_lesson():
    return {"id": "demo", "title": "Demo", "beats": [
        {"id": "b01", "type": "title", "narration": "Hola, hoy vemos [[has]]."},
        {"id": "b02", "type": "sentence", "text": "He has coffee.", "highlight": {"has": "green"},
         "narration": "Mira: [[He has coffee]]."},
    ]}


def wait_job(job, folder):
    for _ in range(200):
        status = ms.job_status(job, folder)
        if status.get("state") in ("done", "failed"):
            return status
        time.sleep(0.05)
    raise AssertionError("job never finished")


# ── staleness: the guard ───────────────────────────────────────────────────────

def test_stale_beats_lists_everything_when_no_audio_exists(tmp_path):
    assert ms.stale_beats(tiny_lesson(), "matilda", tmp_path) == ["b01", "b02"]


def test_stale_beats_is_empty_when_manifest_matches_and_flags_an_edit(tmp_path):
    lesson = tiny_lesson()
    folder = tmp_path / "audio" / "demo" / "matilda"
    folder.mkdir(parents=True)
    manifest = {"voice": "matilda", "beats": [{"id": b["id"], "text": L.spoken_text(b["narration"])} for b in lesson["beats"]]}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    assert ms.stale_beats(lesson, "matilda", tmp_path) == []
    lesson["beats"][1]["narration"] = "Mira bien: [[He has coffee]]."
    assert ms.stale_beats(lesson, "matilda", tmp_path) == ["b02"]


def test_table_roundtrip_edits_only_narration():
    lesson = tiny_lesson()
    rows = ms.beats_table(lesson)
    assert rows[1] == {"id": "b02", "tipo": "sentence", "narración": "Mira: [[He has coffee]]."}
    rows[1]["narración"] = "  Fíjate: [[He has coffee]].  "
    rows[1]["tipo"] = "quiz"                      # read-only column: must be ignored
    out = ms.apply_table(lesson, rows)
    assert out["beats"][1]["narration"] == "Fíjate: [[He has coffee]]."
    assert out["beats"][1]["type"] == "sentence"


def test_cost_is_per_thousand_spoken_characters():
    lesson = {"beats": [{"narration": "[[" + "a" * 500 + "]]"}, {"narration": "b" * 500}]}
    assert ms.estimate_cost_usd(lesson) == pytest.approx(0.10)
    assert ms.estimate_cost_usd(lesson, voices=2) == pytest.approx(0.20)


# ── commands the page launches ─────────────────────────────────────────────────

def test_commands_are_explicit_and_carry_no_secrets():
    assert ms.audio_command("demo", "matilda", "VID", "eleven_turbo_v2_5")[1:] == [
        "gen_audio.py", "--lesson", "lessons/demo.json", "--voices", "matilda=VID", "--model", "eleven_turbo_v2_5"]
    assert ms.audio_command("demo", "matilda", "VID", "eleven_turbo_v2_5", force=True)[-1] == "--force"
    argv = ms.script_command("Past simple", "A2", 6, "gpt-4o-mini", "  con diálogo ")
    assert argv[1:] == ["gen_script.py", "--topic", "Past simple", "--level", "A2", "--minutes", "6", "--model", "gpt-4o-mini",
                        "--extra", "con diálogo"]
    assert "--extra" not in ms.script_command("x", "A1", 3, "gpt-4o", "   ")
    assert ms.batch_command(["a", "b"], "matilda", "VID", "m", "eleven_turbo_v2_5")[1:] == [
        "batch_run.py", "--lessons", "a", "b", "--voices", "matilda=VID", "--quality", "m", "--model", "eleven_turbo_v2_5"]
    argv, env = R.render_command("/x/manim", "l", "demo", "matilda")
    assert argv == ["/x/manim", "-ql", "--disable_caching", "lesson_scene.py", "Lesson"]
    assert env == {"LESSON": "lessons/demo.json", "VOICE_DIR": "audio/demo/matilda"}
    with pytest.raises(ValueError):
        R.render_command("/x/manim", "ultra", "demo", "matilda")


def test_register_render_files_under_the_lesson_and_appends_one_row(tmp_path):
    source = tmp_path / "media" / "videos" / "lesson_scene" / "720p30"
    source.mkdir(parents=True)
    (source / "Lesson.mp4").write_bytes(b"\x00" * 2048)
    (source / "Lesson.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhola\n")
    row = R.register(R.rendered_output("m", tmp_path), "demo", "matilda", "m", 12.34, tmp_path, now=datetime(2026, 9, 16, 12, 0))
    assert row["file"] == "demo/20260916-120000_matilda_720p30.mp4" and row["lesson"] == "demo"
    assert (tmp_path / "renders" / row["file"]).exists()
    assert (tmp_path / "renders" / "demo" / "20260916-120000_matilda_720p30.srt").exists()
    assert R.ledger(tmp_path)[0]["render_seconds"] == 12.3


# ── environment panel ──────────────────────────────────────────────────────────

def test_env_file_roundtrip_keeps_other_lines_and_is_private(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nOTHER=keep me\nELEVENLABS_API_KEY='old'\n")
    ms.write_env_file(env, {"ELEVENLABS_API_KEY": "new-key-value-123456", "OPENAI_API_KEY": "sk-abcdefghijklmnop", "SKIP": None})
    text = env.read_text()
    assert "OTHER=keep me" in text and "# comment" in text and "old" not in text and "SKIP" not in text
    assert text.count("ELEVENLABS_API_KEY=") == 1
    assert ms.read_env_file(env)["OPENAI_API_KEY"] == "sk-abcdefghijklmnop"
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_effective_env_prefers_the_studio_over_the_repo_and_names_the_source(tmp_path, monkeypatch):
    root, studio = tmp_path / "repo", tmp_path / "repo" / "experiments" / "poc"
    studio.mkdir(parents=True)
    for key in ms.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    (root / ".env").write_text("ELEVENLABS_API_KEY=root-key-abcdefgh\nOPENAI_API_KEY=root-openai-key\n")
    env = ms.effective_env(studio, root)
    assert env["ELEVENLABS_API_KEY_SOURCE"] == "root" and env["OPENAI_API_KEY"] == "root-openai-key"
    assert env["ELEVENLABS_VOICE_ID_SOURCE"] == "missing"
    (studio / ".env").write_text("ELEVENLABS_VOICE_ID=studio-voice\n")
    env = ms.effective_env(studio, root)
    assert env["ELEVENLABS_VOICE_ID"] == "studio-voice" and env["ELEVENLABS_VOICE_ID_SOURCE"] == "studio"
    assert env["ELEVENLABS_API_KEY_SOURCE"] == "root"


def test_mask_never_shows_the_middle_of_a_key():
    assert ms.mask("") == "—" and ms.mask("short") == "••••" and ms.mask("sk_1234567890abcdefgh") == "sk_1…efgh"


# ── lessons on disk ────────────────────────────────────────────────────────────

def test_lesson_files_and_summary(tmp_path):
    (tmp_path / "lessons").mkdir()
    L.save(tiny_lesson(), tmp_path / "lessons" / "demo.json")
    files = ms.lesson_files(tmp_path)
    assert [f.name for f in files] == ["demo.json"]
    summary = ms.lesson_summary(files[0])
    assert summary["id"] == "demo" and summary["beats"] == 2 and summary["problems"] == 0
    assert ms.voices_with_audio("demo", tmp_path) == []


# ── background jobs ────────────────────────────────────────────────────────────

def test_background_job_success_runs_callback_and_keeps_a_log(tmp_path):
    seen = {}
    job = ms.start_job("test", [sys.executable, "-c", "print('hello from job')"], {"X": "1"}, tmp_path,
                       on_success=lambda s: seen.setdefault("ok", {"file": "x.mp4"}), studio_dir=tmp_path)
    status = wait_job(job, tmp_path)
    assert status["state"] == "done" and status["result"] == {"file": "x.mp4"}
    assert "hello from job" in ms.job_log(job, studio_dir=tmp_path)


def test_background_job_failure_is_recorded_not_raised(tmp_path):
    job = ms.start_job("test", [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"], {}, tmp_path, studio_dir=tmp_path)
    status = wait_job(job, tmp_path)
    assert status["state"] == "failed" and status["code"] == 3 and "boom" in ms.job_log(job, studio_dir=tmp_path)

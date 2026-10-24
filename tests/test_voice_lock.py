"""STEP 79 §00: the ElevenLabs lock. No STEP, test, tool or CLI run spends voice; only the
panel's own render / voicing click may, within the plan."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import voice_credits  # noqa: E402
import voice_lock  # noqa: E402


@pytest.fixture
def grants(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_lock, "GRANT_DIR", tmp_path / "grants")
    monkeypatch.delenv(voice_lock.GRANT_ENV, raising=False)
    monkeypatch.delenv(voice_lock.LOCK_ENV, raising=False)
    return tmp_path / "grants"


def _clean_env(**extra):
    """A process that is not pytest: what the CLI, a tool or a studio command would have."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST", "ELEVENLABS_GRANT"))}
    env.update(extra)
    return env


def _run(code, **env):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=str(ROOT), capture_output=True,
                          text=True, env=_clean_env(**env), timeout=120)


# ── the lock itself ──────────────────────────────────────────────────

def test_pytest_is_locked_and_check_raises_before_anything(grants):
    assert voice_lock.locked()
    with pytest.raises(voice_lock.VoiceLocked, match="Voz bloqueada"):
        voice_lock.check()


def test_a_grant_is_not_honoured_under_pytest(grants):
    with voice_lock.panel_grant():
        assert voice_lock.locked()


def test_a_panel_grant_unlocks_only_while_it_lasts(grants, monkeypatch):
    monkeypatch.setattr(voice_lock, "_ALLOW_IN_TESTS", True)
    with voice_lock.panel_grant() as token:
        assert not voice_lock.locked()
        assert (grants / token).exists()
    assert voice_lock.locked() and not list(grants.iterdir())


def test_the_env_or_config_lock_stops_even_the_panel(grants, monkeypatch, tmp_path):
    monkeypatch.setattr(voice_lock, "_ALLOW_IN_TESTS", True)
    with voice_lock.panel_grant():
        monkeypatch.setenv(voice_lock.LOCK_ENV, "1")
        assert voice_lock.locked()
        monkeypatch.delenv(voice_lock.LOCK_ENV)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("video:\n  fps: 30\ncosts:\n  monthly_ceiling_usd: 25\n  tts_lock: true\nother: 1\n")
        monkeypatch.setattr(voice_lock, "CONFIG", cfg)
        assert voice_lock.locked()
        cfg.write_text("costs:\n  tts_lock: false\n")
        assert not voice_lock.locked()
    monkeypatch.setenv(voice_lock.LOCK_ENV, "0")             # «0» never unlocks: no grant, locked
    assert voice_lock.locked()


def test_a_made_up_grant_token_does_not_unlock(grants, monkeypatch):
    monkeypatch.setattr(voice_lock, "_ALLOW_IN_TESTS", True)
    monkeypatch.setenv(voice_lock.GRANT_ENV, "0" * 32)
    assert voice_lock.locked()


# ── each entry point ─────────────────────────────────────────────────

def test_the_cli_and_tools_are_locked_by_default():
    """A plain process (main.py, anything under tools/): every ElevenLabs request is refused."""
    out = _run("""
        import sys; sys.path.insert(0, "src")
        import cost_tracker, voice_lock
        try:
            cost_tracker.check_tts_budget(100, "eleven_v3")
        except voice_lock.VoiceLocked:
            print("LOCKED")
    """)
    assert out.stdout.strip() == "LOCKED", out.stderr


def test_the_lesson_studios_audio_request_is_locked_outside_the_panel(monkeypatch):
    """gen_audio.eleven_segment (the studio's audio and batch commands) raises before urlopen."""
    sys.path.insert(0, str(ROOT / "experiments" / "manim_voiceover_poc"))
    import gen_audio
    import urllib.request

    def never(*a, **k):
        raise AssertionError("a request reached the network")
    monkeypatch.setattr(urllib.request, "urlopen", never)
    with pytest.raises(voice_lock.VoiceLocked):
        gen_audio.eleven_segment("k" * 20, "voice", "Hola", "es", "eleven_v3", {})


def test_a_studio_job_without_the_voicing_click_is_locked_and_with_it_granted(tmp_path, monkeypatch):
    import time
    import manim_studio as M
    monkeypatch.setenv("ELEVENLABS_GRANT_DIR", str(tmp_path / "grants"))
    monkeypatch.setattr(voice_lock, "GRANT_DIR", tmp_path / "grants")
    probe = [sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); import voice_lock; print('LOCKED' if voice_lock.locked() else 'GRANTED')"]
    env = {k: "" for k in os.environ if k.startswith("PYTEST")}
    plan = {"used": 0, "limit": 100_000, "remaining": 100_000, "resets": None}
    monkeypatch.setattr(voice_credits, "remaining", lambda *a, **k: plan)

    def finished(job_id):
        status = M.jobs_dir(tmp_path) / f"{job_id}.json"
        for _ in range(600):
            if status.exists() and json.loads(status.read_text()).get("state") in ("done", "failed"):
                return (M.jobs_dir(tmp_path) / f"{job_id}.log").read_text()
            time.sleep(0.05)
        raise AssertionError("job did not finish")

    monkeypatch.setattr(M, "datetime", type("D", (), {"now": staticmethod(lambda: __import__("datetime").datetime(2026, 1, 1, 1, 1, 1))}))
    plain = M.start_job("audio", probe, env, ROOT, studio_dir=tmp_path)
    assert "LOCKED" in finished(plain)
    monkeypatch.setattr(M, "datetime", type("D", (), {"now": staticmethod(lambda: __import__("datetime").datetime(2026, 1, 1, 1, 1, 2))}))
    clicked = M.start_job("audio", probe, env, ROOT, studio_dir=tmp_path, voice_chars=500)
    assert "GRANTED" in finished(clicked)
    assert not list((tmp_path / "grants").iterdir())          # the grant ends with the job


def test_with_the_lock_on_a_cache_hit_still_renders(tmp_path, monkeypatch):
    import tts_cache
    import tts_elevenlabs as T
    monkeypatch.setattr(tts_cache, "CACHE_DIR", tmp_path / "cache")
    request = {"voice_id": "v", "text": "Hola", "model_id": "eleven_v3"}
    k = tts_cache.key({**request, "endpoint": "convert"}, 0)
    src = tmp_path / "src.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.5",
                    str(src)], check=True)
    tts_cache.store(k, src, request)
    assert voice_lock.locked()
    out = tmp_path / "out.mp3"
    T._elevenlabs_with_retry(None, str(out), **request)          # no client: a request would crash
    assert out.exists() and out.stat().st_size > 0
    with pytest.raises(voice_lock.VoiceLocked):
        T._elevenlabs_with_retry(None, str(tmp_path / "miss.mp3"), **dict(request, text="Adiós"))


# ── the panel's plan check ───────────────────────────────────────────

PLAN = {"used": 90_000, "limit": 100_000, "remaining": 10_000, "resets": None}


def test_the_header_says_what_is_left():
    assert voice_credits.header_text(PLAN) == "Voz: 10.000 caracteres restantes"
    assert "solo audio en caché" in voice_credits.header_text(None)


def test_a_render_is_refused_past_the_plan_or_under_five_percent():
    assert voice_credits.refusal(4_000, PLAN) is None
    assert "Sin voz suficiente" in voice_credits.refusal(12_000, PLAN)
    assert "5 %" in voice_credits.refusal(6_000, PLAN)          # would leave 4 000 < 5 000


def test_panel_voice_grants_refuses_or_runs_cache_only(grants):
    with voice_credits.panel_voice(1_000, read=lambda: PLAN) as token:
        assert token and (grants / token).exists()
    with pytest.raises(voice_credits.VoiceRefused):
        with voice_credits.panel_voice(9_000, read=lambda: PLAN):
            pass
    notes = []
    with voice_credits.panel_voice(1_000, note=notes.append, read=lambda: None) as token:
        assert token is None
    assert "caché" in notes[0]


def test_the_remaining_read_is_cached_and_never_fetched_under_pytest(monkeypatch):
    monkeypatch.setattr(voice_credits, "_cache", {"at": 0.0, "value": None})
    assert voice_credits.remaining() is None
    calls = []
    fetch = lambda: calls.append(1) or PLAN
    assert voice_credits.remaining(fetch, now=lambda: 1000.0) == PLAN
    assert voice_credits.remaining(fetch, now=lambda: 1030.0) == PLAN and len(calls) == 1

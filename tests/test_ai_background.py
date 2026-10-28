"""STEP 80 §5: an AI background behind the notebook, as an A/B. Fake transport, no network."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import ai_background as AB  # noqa: E402


def _clip(path: Path, seconds=4, colour="0x3366aa"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=360x640:r=24:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def test_the_price_is_four_seconds_at_three_cents():
    assert AB.SECONDS == 4 and AB.estimate_usd() == pytest.approx(0.12)


def test_every_other_render_is_the_ai_group_when_the_topic_has_a_clip():
    _clip(AB.clip_dir("la cocina") / "clip.mp4")
    got = [AB.assign(f"a{i}", "how_do_you_say", "la cocina")["variant"] for i in range(4)]
    assert got == ["ia", "stock", "ia", "stock"]
    assert AB.assign("x", "how_do_you_say", "los animales")["variant"] == "stock"      # turn 4: ia, no clip
    assert AB.assign("q", "quiz", "la cocina") == {"variant": None, "background": None, "why": "fuera del A/B"}
    assert AB.variants() == {"a0": "ia", "a1": "stock", "a2": "ia", "a3": "stock", "x": "stock"}
    ia = AB.assign("a5", "how_do_you_say", "la cocina")                                # turn 5: stock
    assert ia["variant"] == "stock" and AB.assign("a6", "how_do_you_say", "la cocina")["background"].startswith("clips:")


def test_one_clip_loops_with_a_slow_crossfade(tmp_path):
    from video import clip_background as CB
    _clip(tmp_path / "c" / "clip.mp4")
    bg = CB.ClipLibraryBackground(str(tmp_path / "c"), 360, 640, duration=12.0, seed=1)
    assert bg._xfade == CB.LOOP_CROSSFADE > CB.CROSSFADE
    assert len(bg._playlist) >= 3 and bg._cut_near(4.0) is not None and bg._cut_near(2.0) is None
    bg.close()


def test_the_comparison_waits_for_eight_mature_videos_a_group():
    vids = [{"background_variant": g, "days": 5, "views": v} for g, v in [("ia", 100)] * 8 + [("stock", 50)] * 7]
    vids.append({"background_variant": "stock", "days": 1, "views": 999})                # too young
    r = AB.compare(vids)
    assert not r["ready"] and r["groups"]["stock"]["n"] == 7
    r = AB.compare(vids + [{"background_variant": "stock", "days": 9, "views": 60}])
    assert r["ready"] and r["groups"]["ia"]["median"] == 100 and r["groups"]["stock"]["median"] == 50


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_generation_is_locked_outside_the_panel():
    import voice_lock
    with pytest.raises(voice_lock.VoiceLocked):
        AB.generate("la cocina", opener=lambda *a, **k: pytest.fail("the network was reached"))


def test_the_cap_stops_a_clip_before_anything_is_sent(monkeypatch):
    import tts_openrouter
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)

    def capped(usd, settings=None):
        raise tts_openrouter.OpenRouterRefused("Tope mensual de OpenRouter")
    monkeypatch.setattr(tts_openrouter, "check_caps", capped)
    with pytest.raises(tts_openrouter.OpenRouterRefused):
        AB.generate("la cocina", opener=lambda *a, **k: pytest.fail("asked past the cap"))


def test_a_panel_click_submits_polls_downloads_caches_and_logs(monkeypatch, tmp_path):
    import cost_tracker
    import tts_openrouter
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(tts_openrouter, "check_caps", lambda usd, settings=None: None)
    cost_tracker.reset_tracker("ab-test")
    _clip(tmp_path / "src.mp4")
    mp4 = (tmp_path / "src.mp4").read_bytes()
    calls = []

    def opener(req, timeout=None):
        calls.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None))
        if req.get_method() == "POST":
            return _Resp(json.dumps({"id": "job1", "status": "pending"}).encode())
        if req.full_url.endswith("/content?index=0"):
            return _Resp(mp4)
        n = sum(1 for c in calls if c[1].endswith("/job1"))
        state = {"id": "job1", "status": "completed" if n >= 2 else "in_progress"}
        if n >= 2:
            state["usage"] = {"cost": 0.12}
        return _Resp(json.dumps(state).encode())

    path = AB.generate("la cocina", opener=opener, sleep=lambda s: None)
    body = calls[0][2]
    assert body["model"] == "google/veo-3.1-lite" and body["duration"] == 4 and body["aspect_ratio"] == "9:16"
    assert body["resolution"] == "720p" and body["generate_audio"] is False and "cocina" in body["prompt"]
    assert path == AB.cached("la cocina") and path.read_bytes() == mp4
    assert [(r["api_type"], r["cost_usd"]) for r in cost_tracker.get_tracker().entries] == [("openrouter_video", 0.12)]
    assert AB.generate("la cocina", opener=lambda *a, **k: pytest.fail("asked again")) == path    # cached forever


def test_a_failed_job_writes_nothing(monkeypatch):
    import tts_openrouter
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(tts_openrouter, "check_caps", lambda usd, settings=None: None)

    def opener(req, timeout=None):
        if req.get_method() == "POST":
            return _Resp(b'{"id": "j", "status": "pending"}')
        return _Resp(b'{"id": "j", "status": "failed", "error": "moderation"}')
    with pytest.raises(RuntimeError, match="failed"):
        AB.generate("la playa", opener=opener, sleep=lambda s: None)
    assert AB.cached("la playa") is None


def test_the_panel_offers_the_clip_with_its_price_and_records_the_group():
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    body = admin[admin.index("def ai_background_panel"):admin.index("def script_for_upload")]
    assert "Fondo IA" in body and "voice_lock.panel_grant()" in body and "estimate_usd" in body
    assert '"background_ab": background_ab' in (ROOT / "src" / "jobs.py").read_text(encoding="utf-8")

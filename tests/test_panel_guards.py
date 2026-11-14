"""STEP 75 §3: .env writes, damaged sidecars, the paid batch button, ready_for_review kept."""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from config import secrets as S  # noqa: E402

ENV = "# keys\nOPENROUTER_API_KEY=sk-or-v1-" + "a" * 30 + "\nELEVENLABS_VOICE_ID=" + "A" * 20 + "\n"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "envdir" / ".env"
    path.parent.mkdir()
    path.write_text(ENV)
    path.chmod(0o600)
    for key in ("OPENROUTER_API_KEY", "ELEVENLABS_VOICE_ID", "OPENROUTER_VOICE_ID"):
        monkeypatch.setenv(key, os.environ.get(key, ""))        # restored after the test
    return path


def test_a_valid_value_replaces_one_line_atomically_and_keeps_the_mode(env_file):
    S.save_env_key("ELEVENLABS_VOICE_ID", "B" * 20, env_path=env_file)
    assert env_file.read_text() == ENV.replace("A" * 20, "B" * 20)
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert list(env_file.parent.iterdir()) == [env_file]            # no temp file left
    S.save_env_key("OPENROUTER_VOICE_ID", "C" * 20, env_path=env_file)
    assert env_file.read_text().endswith("OPENROUTER_VOICE_ID=" + "C" * 20 + "\n")


@pytest.mark.parametrize("key,value", [
    ("ELEVENLABS_VOICE_ID", "B" * 20 + "\nOPENROUTER_API_KEY=sk-evil"),   # a second key smuggled in
    ("ELEVENLABS_VOICE_ID", "nope"),                                      # fails its pattern
    ("OPENROUTER_API_KEY", "not-a-key"),
    ("ELEVENLABS_VOICE_ID", ""),
    ("NOT_A_KEY", "x"),
    ("OPENAI_API_KEY", "sk-" + "a" * 30),          # the dead keys are no longer accepted
    ("ELEVENLABS_API_KEY", "sk_" + "0f" * 24),
])
def test_a_bad_value_is_refused_and_the_file_is_untouched(env_file, key, value):
    with pytest.raises(ValueError):
        S.save_env_key(key, value, env_path=env_file)
    assert env_file.read_text() == ENV


def test_a_damaged_sidecar_is_listed_as_damaged_instead_of_crashing(tmp_path, monkeypatch):
    import admin
    pending = tmp_path / "pending" / "quiz"
    pending.mkdir(parents=True)
    (pending / "good.mp4").write_bytes(b"")
    (pending / "good.json").write_text(json.dumps({"script_data": {}}))
    (pending / "bad.mp4").write_bytes(b"")
    (pending / "bad.json").write_text('{"script_data": {')
    monkeypatch.setattr(admin, "PENDING_DIR", tmp_path / "pending")
    videos = {v["name"]: v for v in admin.get_pending_videos()}
    assert videos["good"]["damaged"] is None
    assert videos["bad"]["damaged"] == "archivo dañado: bad.json (JSONDecodeError)" and videos["bad"]["meta"] == {}
    assert admin.read_sidecar(tmp_path / "missing.json")[1].startswith("archivo dañado")


def test_generate_batch_now_asks_states_the_cost_and_goes_through_the_queue(tmp_path, monkeypatch):
    import admin
    assert admin.scheduler_batch(["quiz", "true_false"], 3) == [
        {"type": "quiz", "category": None, "topic": None},
        {"type": "true_false", "category": None, "topic": None},
        {"type": "quiz", "category": None, "topic": None}]
    assert admin.batch_estimate_usd(5, tmp_path) is None              # no cost history
    import cost_tracker
    monkeypatch.setattr(cost_tracker, "per_video_costs", lambda d: [
        {"video_id": "a", "total_usd": 0.10, "openai_usd": 0.02, "elevenlabs_usd": 0.08},
        {"video_id": "b", "total_usd": 0.20, "openai_usd": 0.05, "elevenlabs_usd": 0.15}])
    assert admin.batch_estimate_usd(4, tmp_path) == 0.6
    src = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    block = src[src.index("🚀 Generate Batch Now") - 1200:src.index("🚀 Generate Batch Now") + 600]
    assert "batch_add(scheduler_batch(" in block and "start_generation(" not in block
    assert 'disabled=not (_ok and selected_types)' in block


def test_cleanup_keeps_an_old_ready_for_review_artifact(tmp_path):
    import subprocess
    import time
    import cleanup as C
    root = tmp_path / "repo"
    (root / "output/artifacts/done").mkdir(parents=True)
    meta = root / "output/artifacts/done/artifact.json"
    meta.write_text(json.dumps({"state": "ready_for_review"}))
    old = time.time() - 40 * 86400
    os.utime(meta, (old, old))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    plan = C.rule_artifacts(root, C.guards(root), time.time())
    assert plan["paths"] == [] and plan["kept"] == [(root / "output/artifacts/done", "estado ready_for_review")]

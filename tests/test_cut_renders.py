#!/usr/bin/env python3
"""STEP 59 §6: a cut render never reaches the review queue.

    python3 -m pytest tests/test_cut_renders.py

bv010 (job a384ee18) hit the 1200 s render limit; a 46 s mp4 stayed in
pending/ with no sidecar, was approved and went up as 8yA7dbOZeUY. The render
now happens under output/rendering/ and is moved into pending/ only whole,
measured and with its sidecar. Nothing here renders or calls a paid API.
"""
import json
import logging
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("streamlit").setLevel(logging.CRITICAL)

import admin  # noqa: E402

BV010 = {"type": "how_do_you_say", "theme": "la ciudad", "video_title": "x",
         "_meta": {"topic_id": "bv010", "video_type": "how_do_you_say"}}


class _Pipeline:
    """The pipeline admin drives, with no TTS, no footage and no renderer."""
    RENDER_TIMEOUT_S = 1200

    class PipelineError(RuntimeError):
        pass

    def __init__(self, render):
        self.render = render

    def resolve_profile(self, name=None):
        return {"name": "adults", "content": {"categories": None}}

    def resolve_provider_name(self):
        return "fake"

    def generate_tts(self, script_data, audio_path, script_path=None, dry_run=False):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"0")
        json_path = Path(audio_path).with_suffix(".json")
        json_path.write_text(json.dumps({"duration": 69.33}))
        return Path(audio_path), json_path

    def merge_script_into_tts(self, script_data, json_path):
        return None

    def resolve_background(self, profile, background, **kw):
        return "clips:/x"

    def render_video(self, audio_path, data_path, video_path, **kw):
        Path(video_path).parent.mkdir(parents=True, exist_ok=True)
        Path(video_path).write_bytes(b"0" * 4096)      # what ffmpeg had written so far
        return self.render(self, Path(video_path))

    def finalize_video(self, video_path, json_path, variant_seed=None):
        return {"gate": "PASS", "video": str(video_path), "blocking_flags": []}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    ledger = tmp_path / "generation_jobs.json"
    ledger.write_text(json.dumps({"active": [], "history": []}))
    monkeypatch.setattr(admin, "JOBS_FILE", ledger)
    for name, sub in (("SCRIPTS_DIR", "scripts"), ("AUDIO_DIR", "audio"), ("PENDING_DIR", "pending"),
                      ("CLIPS_DIR", "clips"), ("RENDERING_DIR", "rendering"), ("CUT_DIR", "rejected/_cut")):
        monkeypatch.setattr(admin, name, tmp_path / sub)
    monkeypatch.setattr(admin, "reset_tracker", lambda video_id=None: None)
    monkeypatch.setattr(admin, "queue_pick", lambda video_type=None: None)

    def run(render, probe=69.4):
        import qa_gate
        monkeypatch.setattr(admin, "pipeline", _Pipeline(render))
        monkeypatch.setattr(qa_gate, "probe_duration", lambda path: probe)
        job_id = admin.create_job("how_do_you_say")
        return job_id, admin.run_pipeline_with_tracking(job_id, "how_do_you_say", "basic_vocab", "la ciudad",
                                                        script_data=dict(BV010), use_queue=False)
    return tmp_path, run


def _mp4s(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.mp4"))


def test_a_killed_render_leaves_no_mp4_in_pending(rig):
    tmp, run = rig

    def killed(pipe, path):
        raise pipe.PipelineError("Video render timed out after 1200s")
    job_id, result = run(killed)
    assert not result.get("success")
    assert not list((tmp / "pending").rglob("*.mp4"))
    cut = [p for p in _mp4s(tmp) if p.startswith("rejected/_cut/")]
    assert len(cut) == 1 and not list((tmp / "rendering").rglob("*.mp4"))
    reason = (tmp / cut[0]).parent.joinpath("reason.txt").read_text()
    assert "timed out after 1200s" in reason and "frames+encode (failed)" in reason


def test_a_render_shorter_than_its_timeline_is_cut(rig):
    tmp, run = rig
    _job, result = run(lambda pipe, path: path, probe=46.0)
    assert not result.get("success") and "46.0s" in result["error"]
    assert not list((tmp / "pending").rglob("*.mp4"))
    assert len([p for p in _mp4s(tmp) if p.startswith("rejected/_cut/")]) == 1


def test_a_whole_render_reaches_pending_with_its_sidecar_and_stage_times(rig):
    tmp, run = rig
    _job, result = run(lambda pipe, path: path)
    assert result.get("success"), result.get("error")
    [mp4] = (tmp / "pending").rglob("*.mp4")
    sidecar = json.loads(mp4.with_suffix(".json").read_text())
    assert sidecar["gate"] == "PASS"
    assert set(sidecar["stage_seconds"]) == {"script", "tts", "clips", "frames+encode", "gate+outro"}
    assert not list((tmp / "rendering").rglob("*.mp4")) and not (tmp / "rejected").exists()


def test_two_submits_of_the_same_script_give_one_job(rig, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(admin, "run_pipeline_with_tracking", lambda *a, **k: release.wait(10))
    monkeypatch.setattr(admin, "batch_advance", lambda: None)
    try:
        admin.start_generation("how_do_you_say", script_data=dict(BV010))
        with pytest.raises(admin.AlreadyRendering, match="Ya se está renderizando bv010"):
            admin.start_generation("how_do_you_say", script_data=dict(BV010))
        assert [j.get("script_key") for j in admin.get_active_jobs()] == ["bv010:how_do_you_say"]
    finally:
        release.set()
        admin.wait_for_generations(timeout=10)


def test_the_queue_skips_a_script_another_job_holds(rig, monkeypatch, tmp_path):
    job_id = admin.create_job("how_do_you_say")
    admin.update_job(job_id, script_key="bv010:how_do_you_say")
    assert admin.rendering_job_for("bv010:how_do_you_say")["id"] == job_id
    assert admin.rendering_job_for("bv010:how_do_you_say", exclude=job_id) is None
    assert admin.rendering_job_for("bv011:how_do_you_say") is None


def test_review_ignores_a_sidecar_less_mp4(rig):
    tmp, _run = rig
    d = tmp / "pending" / "how_do_you_say"
    d.mkdir(parents=True)
    (d / "cut.mp4").write_bytes(b"0")
    (d / "whole.mp4").write_bytes(b"0")
    (d / "whole.json").write_text(json.dumps({"gate": "PASS"}))
    (d / "x.mp4.part").write_bytes(b"0")
    assert [v["name"] for v in admin.get_pending_videos()] == ["whole"]


def test_a_dashboard_restart_moves_the_unfinished_render_to_cut(rig, monkeypatch):
    tmp, _run = rig
    stage = tmp / "rendering" / "how_do_you_say" / "cómo_se_dice_x.mp4"
    stage.parent.mkdir(parents=True)
    stage.write_bytes(b"0")
    job_id = admin.create_job("how_do_you_say")
    admin.update_job(job_id, stage_path=str(stage))
    monkeypatch.setattr(admin, "_owner_alive", lambda job: False)
    assert admin.reap_orphaned_jobs() == 1
    assert not stage.exists()
    assert (tmp / "rejected" / "_cut" / "cómo_se_dice_x" / "cómo_se_dice_x.mp4").exists()

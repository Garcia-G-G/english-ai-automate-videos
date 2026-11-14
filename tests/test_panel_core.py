"""STEP 85 §0: the engine facade has no UI, and admin.py behaves as before through it."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def test_importing_panel_core_never_imports_streamlit():
    code = "import sys; sys.path.insert(0, 'src'); import panel_core.videos; assert not any(m.startswith('streamlit') for m in sys.modules)"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]


def test_admin_delegates_with_its_own_directories(tmp_path, monkeypatch):
    import admin
    from panel_core import videos
    assert admin.read_sidecar is videos.read_sidecar
    monkeypatch.setattr(admin, "PENDING_DIR", tmp_path / "p")
    (tmp_path / "p" / "quiz").mkdir(parents=True)
    (tmp_path / "p" / "quiz" / "x.mp4").write_bytes(b"x")
    (tmp_path / "p" / "quiz" / "x.json").write_text("{}")
    assert [v["name"] for v in admin.get_pending_videos()] == ["x"]            # admin's patched directory still rules


def test_lists_and_actions_read_the_directories_from_jobs(tmp_path, monkeypatch):
    import jobs
    from panel_core import videos
    for name in ("PENDING_DIR", "APPROVED_DIR", "REJECTED_DIR"):
        monkeypatch.setattr(jobs, name, tmp_path / name.lower())
    d = jobs.PENDING_DIR / "quiz"
    d.mkdir(parents=True)
    (d / "a.mp4").write_bytes(b"x")
    (d / "a.json").write_text(json.dumps({"gate": "PASS"}))
    (d / "b.mp4").write_bytes(b"x")                                         # no sidecar: not listed
    (d / "c.mp4").write_bytes(b"x")
    (d / "c.json").write_text("not json")
    got = {v["name"]: v for v in videos.get_pending_videos()}
    assert set(got) == {"a", "c"} and got["a"]["meta"] == {"gate": "PASS"} and got["c"]["damaged"].startswith(videos.DAMAGED)
    videos.approve_video(d / "a.mp4")
    assert (jobs.APPROVED_DIR / "quiz" / "a.mp4").exists() and (jobs.APPROVED_DIR / "quiz" / "a.json").exists()
    assert [v["name"] for v in videos.get_approved_videos()] == ["a"]
    videos.reject_video(d / "c.mp4")
    assert (jobs.REJECTED_DIR / "quiz" / "c.mp4").exists() and not (d / "c.mp4").exists()


# ── STEP 85 §1: queue, schedule, costs, review actions, job progress and thumbs, all without streamlit ──

def test_every_panel_core_module_imports_without_streamlit():
    mods = ["videos", "queue_read", "schedule", "costs", "review", "jobstate", "thumbnails"]
    code = ("import sys; sys.path.insert(0, 'src'); import importlib\n"
            + "".join(f"importlib.import_module('panel_core.{m}')\n" for m in mods)
            + "assert not any(m.startswith('streamlit') for m in sys.modules), [m for m in sys.modules if m.startswith('streamlit')]")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]


def test_schedule_info_has_every_contract_field_and_the_next_free_slot():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from panel_core import schedule
    cr = ZoneInfo("America/Costa_Rica")
    rows = [{"platform": "youtube", "artifact": "a", "published_title": "MÉDICO", "published_at": "x",
             "extra": {"scheduled_for": "2026-11-14T08:30:00-06:00"}}]
    got = schedule.schedule_info(rows, datetime(2026, 11, 14, 7, 0, tzinfo=cr))
    assert set(got) == {"tz", "utcOffset", "slots", "taken", "minLeadMin", "spacingH", "maxPerDay", "next"}
    assert got["utcOffset"] == "-06:00" and got["minLeadMin"] == 15 and got["spacingH"] == 2.5 and got["maxPerDay"] == 4
    assert got["taken"] == [{"at": "2026-11-14T08:30:00-06:00", "title": "MÉDICO"}]
    assert got["next"] == "2026-11-14T12:00:00-06:00"                      # 08:30 is taken
    assert schedule.check_time is not None


def test_the_queue_facade_ranks_and_reports_without_a_ui(monkeypatch):
    import jobs
    from panel_core import queue_read
    monkeypatch.setattr(jobs, "next_best", lambda: ("p.json", {"type": "quiz"}, "porque sí"))
    monkeypatch.setattr(queue_read, "next_best", jobs.next_best)
    assert queue_read.next_best_summary() == {"path": "p.json", "type": "quiz", "why": "porque sí"}
    monkeypatch.setattr(queue_read, "next_best", lambda: None)
    assert queue_read.next_best_summary() is None
    assert queue_read.queue_order(["b", "a"]) is not None and queue_read.queue_order is jobs.queue_order


def test_gate_records_and_the_costs_snapshot(monkeypatch):
    from panel_core import costs
    assert costs.gate_record(None) == {"gate": None, "flags": [], "passed": None}
    assert costs.gate_record({"gate": "FAIL", "blocking_flags": ["audio"]}) == {"gate": "FAIL", "flags": ["audio"], "passed": False}
    import cost_tracker
    monkeypatch.setattr(cost_tracker, "get_monthly_total", lambda: 1.5)
    monkeypatch.setattr(cost_tracker, "get_daily_costs", lambda d: {"2026-11-14": {"total_usd": 0.2}})
    monkeypatch.setattr(cost_tracker, "per_video_costs", lambda: [])
    snap = costs.costs_snapshot()
    assert snap["month_usd"] == 1.5 and snap["videos"]["videos"] == 0 and isinstance(snap["voice_locked"], bool)


def _tree(tmp_path, monkeypatch):
    import jobs
    for name in ("PENDING_DIR", "APPROVED_DIR", "REJECTED_DIR"):
        monkeypatch.setattr(jobs, name, tmp_path / name.lower())
    d = jobs.PENDING_DIR / "quiz"
    d.mkdir(parents=True)
    for n in ("a", "b", "c"):
        (d / f"{n}.mp4").write_bytes(b"x")
        (d / f"{n}.json").write_text("{}")
    return d


def test_approve_only_moves_the_video_and_uploads_nothing(tmp_path, monkeypatch):
    import jobs
    from panel_core import review
    d = _tree(tmp_path, monkeypatch)
    got = review.approve(d / "a.mp4")
    assert got == {"state": "approved", "publishAt": None, "results": [], "warnings": []}
    assert (jobs.APPROVED_DIR / "quiz" / "a.mp4").exists()


def test_approve_with_a_time_checks_the_lead_rule_first_then_schedules(tmp_path, monkeypatch):
    import jobs
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from panel_core import review
    d = _tree(tmp_path, monkeypatch)
    cr = ZoneInfo("America/Costa_Rica")
    now = datetime(2026, 11, 14, 17, 0, tzinfo=cr)
    import pytest
    with pytest.raises(ValueError, match="ya pasó"):
        review.approve(d / "a.mp4", now - timedelta(minutes=30), scheduler=lambda *a: {}, now=now)
    assert (d / "a.mp4").exists()                                         # refused: nothing moved
    sent = []
    taken = [(now.replace(hour=19, minute=30), "OTRO")]
    got = review.approve(d / "a.mp4", now.replace(hour=21, minute=15), ["youtube"],
                         scheduler=lambda p, pl, at: sent.append((p, pl, at)) or {}, now=now, taken=taken)
    assert got["state"] == "scheduled" and got["results"] == [{"platform": "youtube", "ok": True, "note": None}]
    assert len(got["warnings"]) == 1 and sent[0][0] == jobs.APPROVED_DIR / "quiz" / "a.mp4"
    bad = review.approve(d / "b.mp4", now.replace(hour=21, minute=15), ["youtube"], scheduler=lambda *a: {"youtube": "cuota"}, now=now)
    assert bad["state"] == "approved" and bad["results"][0]["note"] == "cuota"


def test_reject_saves_the_reason_and_rerender_starts_a_job(tmp_path, monkeypatch):
    import jobs
    from panel_core import review
    d = _tree(tmp_path, monkeypatch)
    review.reject(d / "a.mp4", "audio", "ruido")
    side = jobs.REJECTED_DIR / "quiz" / "a.json"
    assert json.loads(side.read_text())["rejected"]["reason"] == "audio"
    import pytest
    with pytest.raises(ValueError):
        review.reject(d / "b.mp4", "porque sí")
    monkeypatch.setattr(jobs, "start_generation", lambda t, **kw: f"job-{t}-{kw['rerender']}")
    assert review.rerender(d / "c.mp4", {"x": 1}) == "job-quiz-True" and not (d / "c.mp4").exists()


def test_a_job_carries_per_step_progress_and_listeners_hear_it(tmp_path, monkeypatch):
    import jobs
    from panel_core import jobstate
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    heard = []
    off = jobstate.on_progress(lambda jid, steps: heard.append((jid, steps)))
    jid = jobs.create_job("quiz")
    try:
        assert jobstate.get_job(jid)["steps"] == {"guion": 0.0, "voz": 0.0, "sonido": 0.0, "montaje": 0.0, "control": 0.0}
        jobs.update_job(jid, progress=60)
        steps = jobstate.get_job(jid)["steps"]
        assert steps["guion"] == 1.0 and steps["voz"] == 1.0 and steps["sonido"] == 1.0 and steps["montaje"] == round(5 / 35, 3) and steps["control"] == 0.0
        assert heard[-1] == (jid, steps)
        jobs.complete_job(jid, True)
        assert jobstate.get_job(jid)["steps"]["control"] == 1.0
    finally:
        off()
    old = {"id": "z", "progress": 30}                                       # a row from before steps existed
    assert jobstate.with_steps(old)["steps"]["guion"] == 1.0 and jobstate.with_steps(old)["steps"]["voz"] == 0.0


def test_thumb_paths_list_what_exists_and_none_when_there_is_no_folder(tmp_path):
    from panel_core import thumbnails
    mp4 = tmp_path / "v.mp4"
    assert thumbnails.thumb_paths(mp4) is None
    f = tmp_path / "v.thumb"
    (f / "cands").mkdir(parents=True)
    (f / "thumb.jpg").write_bytes(b"j")
    (f / "cands" / "A.webp").write_bytes(b"w")
    (f / "thumb.json").write_text(json.dumps({"chosen": "A", "placeholder": "data:image/webp;base64,AA", "metrics": {"A": "frame at 1s", "B": "frame at 0s"}}))
    got = thumbnails.thumb_paths(mp4)
    assert got["jpg"] == f / "thumb.jpg" and got["webp270"] is None and got["chosen"] == "A" and got["placeholder"].startswith("data:")
    assert [(c["label"], c["webp"] is not None) for c in got["candidates"]] == [("A", True), ("B", False)]

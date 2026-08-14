#!/usr/bin/env python3
"""Generation must not run inside the Streamlit script thread.

    python3 -m pytest tests/test_admin_async_jobs.py

All four call sites did `with st.spinner(...): run_pipeline_with_tracking(...)`,
which runs a ~2-minute render synchronously in the thread Streamlit uses to
draw the page. Three consequences, all observed in output/generation_jobs.json:

  frozen UI   the tab is unresponsive for the whole job, and the progress the
              ledger is faithfully recording cannot be drawn while it runs.

  contention  a second tab is a second script thread, so it starts a SECOND
              concurrent render. On 2026-08-14 two jobs launched 12s apart
              took ~4.5 min each against a 109s median — the renderer is CPU
              bound, so overlapping two halves the throughput of both.

  orphans     the thread dies with the browser session or the server, and the
              job stays "running" in the ledger forever. Two such rows were
              sitting in active[] with no process behind them.

The ledger also had no lock: load_jobs/save_jobs is a read-modify-write of one
JSON file, which is safe only while exactly one thread ever runs it. Moving
work off the script thread is what makes that assumption false, so the lock
is part of this change rather than a follow-up.
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


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the job ledger at tmp_path (conftest does not cover JOBS_FILE)."""
    path = tmp_path / "generation_jobs.json"
    path.write_text(json.dumps({"active": [], "history": []}))
    monkeypatch.setattr(admin, "JOBS_FILE", path)
    return path


def test_start_generation_returns_before_the_pipeline_finishes(ledger, monkeypatch):
    """The call that a button handler makes must not block on the render."""
    release = threading.Event()
    entered = threading.Event()

    def blocking_pipeline(job_id, video_type, *a, **kw):
        entered.set()
        assert release.wait(timeout=10), "pipeline never released"
        return {"success": True, "video_path": None, "error": None}

    monkeypatch.setattr(admin, "run_pipeline_with_tracking", blocking_pipeline)

    job_id = admin.start_generation("quiz")

    # If start_generation blocked, control never reaches here until release.
    assert entered.wait(timeout=10), "worker never started"
    assert release.is_set() is False, "start_generation waited for the pipeline"

    active = {j["id"] for j in admin.load_jobs()["active"]}
    assert job_id in active

    release.set()
    admin.wait_for_generations(timeout=10)


def test_only_one_generation_runs_at_a_time(ledger, monkeypatch):
    """A second tab must queue behind the first, not contend with it."""
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def counting_pipeline(job_id, video_type, *a, **kw):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            threading.Event().wait(0.15)
        finally:
            with lock:
                state["now"] -= 1
        return {"success": True, "video_path": None, "error": None}

    monkeypatch.setattr(admin, "run_pipeline_with_tracking", counting_pipeline)

    for _ in range(4):
        admin.start_generation("quiz")

    assert admin.wait_for_generations(timeout=30), "generations did not finish"
    assert state["peak"] == 1, \
        f"{state['peak']} renders ran concurrently; the CPU-bound renderer needs 1"


def test_concurrent_job_updates_do_not_lose_each_other(ledger):
    """Read-modify-write on one JSON file, from many threads."""
    ids = [admin.create_job("quiz") for _ in range(12)]

    def bump(job_id):
        for pct in range(0, 100, 10):
            admin.update_job(job_id, progress=pct)

    threads = [threading.Thread(target=bump, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    surviving = {j["id"] for j in admin.load_jobs()["active"]}
    assert surviving == set(ids), \
        f"lost {len(set(ids) - surviving)} of {len(ids)} jobs to interleaved writes"


def test_orphaned_active_jobs_are_failed_not_left_running(ledger):
    """A job with no live thread must not read as 'running' forever."""
    ledger.write_text(json.dumps({
        "active": [{
            "id": "dead1234", "video_type": "quiz", "category": None,
            "topic": "left over from a killed server", "status": "running",
            "progress": 60, "current_step": "Rendering video...",
            "step_number": 4, "total_steps": 4,
            "created_at": "2026-08-14T12:57:30", "updated_at": "2026-08-14T12:58:03",
            "video_path": None, "error": None,
        }],
        "history": [],
    }))

    admin.reap_orphaned_jobs()

    jobs = admin.load_jobs()
    assert jobs["active"] == [], "orphan still shown as active"
    orphan = next(j for j in jobs["history"] if j["id"] == "dead1234")
    assert orphan["status"] == "failed"
    assert "interrupted" in (orphan["error"] or "").lower()

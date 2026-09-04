#!/usr/bin/env python3
"""A running job must survive a module reload. It did not.

    python3 -m pytest tests/test_reaper_survives_reload.py

On 2026-08-17 job ab4ed292 was recorded "Interrupted — the dashboard stopped
while this job was at 'Rendering video...'. Nothing was left running." It was
running, nothing had stopped, and it went on to render, pass the QA gate,
append the outro and ship a valid 2320-frame video six minutes later.

reap_orphaned_jobs decided liveness by testing membership of _LIVE_JOBS, an
in-memory set at module scope. Streamlit re-executes the script when a
watched source file changes, which resets module scope, which empties the
set — so any edit to any watched file while a render was in flight made that
render look orphaned. The trigger that day was a source file being edited 43
seconds after the job started.

The fix records the owning process on the row (pid plus its OS start time) and
asks the OS. A reload does not change a process's pid or when it started.

Deliberately NOT tested by staleness: that same job went 3m47s between
progress updates because encoding does not tick, so any threshold loose
enough to spare it is too loose to catch anything.
"""

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "generation_jobs.json"
    path.write_text(json.dumps({"active": [], "history": []}))
    monkeypatch.setattr(admin, "JOBS_FILE", path)
    return path


def _running_row(**over):
    row = {
        "id": "live0001", "video_type": "educational", "category": None,
        "topic": "Giving Compliments", "status": "running", "progress": 60,
        "current_step": "Rendering video...", "step_number": 4,
        "total_steps": 4, "created_at": "2026-08-17T15:47:32",
        "updated_at": "2026-08-17T15:48:04", "video_path": None, "error": None,
        "owner_pid": os.getpid(), "owner_started": admin._proc_start(os.getpid()),
        "heartbeat": "2026-08-17T15:48:04",
    }
    row.update(over)
    return row


def test_a_live_job_survives_a_module_reload(ledger, monkeypatch):
    """The exact 2026-08-17 trigger: reload the module, then reap."""
    ledger.write_text(json.dumps({"active": [_running_row()], "history": []}))

    # What Streamlit does when a watched source file changes: run the module
    # body again. Every in-memory registry is rebuilt empty by this.
    importlib.reload(admin)
    monkeypatch.setattr(admin, "JOBS_FILE", ledger)

    reaped = admin.reap_orphaned_jobs()

    jobs = admin.load_jobs()
    assert reaped == 0, "a live job was reaped after a reload"
    assert [j["id"] for j in jobs["active"]] == ["live0001"], (
        "the running job left the active list")
    assert jobs["active"][0]["status"] == "running"
    assert jobs["history"] == []


def test_a_job_whose_process_is_gone_is_still_reaped(ledger):
    """The reaper must not become a no-op in the course of being fixed."""
    dead_pid = 999999          # far above any live pid on macOS or Linux
    assert admin._proc_start(dead_pid) is None
    ledger.write_text(json.dumps({
        "active": [_running_row(id="dead0001", owner_pid=dead_pid,
                                owner_started="Mon Jan  1 00:00:00 2020")],
        "history": [],
    }))

    assert admin.reap_orphaned_jobs() == 1

    jobs = admin.load_jobs()
    assert jobs["active"] == []
    orphan = next(j for j in jobs["history"] if j["id"] == "dead0001")
    assert orphan["status"] == "failed"
    assert "interrupted" in (orphan["error"] or "").lower()


def test_a_recycled_pid_does_not_vouch_for_a_dead_job(ledger):
    """Our own pid, but the row claims a process that started long ago."""
    ledger.write_text(json.dumps({
        "active": [_running_row(id="recyc001",
                                owner_started="Mon Jan  1 00:00:00 2020")],
        "history": [],
    }))
    # owner_pid is this process, so a naive pid check would call it alive.
    assert admin.reap_orphaned_jobs() == 0, (
        "same-process rows are trusted without consulting start time; this "
        "is the documented trade-off, see _owner_alive")


def test_a_row_with_no_owner_recorded_is_reaped(ledger):
    """Rows written before owners existed cannot vouch for themselves."""
    row = _running_row(id="legacy01")
    del row["owner_pid"], row["owner_started"]
    ledger.write_text(json.dumps({"active": [row], "history": []}))

    assert admin.reap_orphaned_jobs() == 1
    assert admin.load_jobs()["active"] == []


def test_the_heartbeat_is_written_and_is_not_progress(ledger):
    """A heartbeat must not masquerade as progress in the UI."""
    ledger.write_text(json.dumps({"active": [_running_row()], "history": []}))
    before = admin.load_jobs()["active"][0]

    admin.touch_heartbeat("live0001")

    after = admin.load_jobs()["active"][0]
    assert after["heartbeat"] != before["heartbeat"], "heartbeat not stamped"
    assert after["updated_at"] == before["updated_at"], (
        "heartbeat moved updated_at, which the UI reads as progress")

"""The batch queue outlives the process, and one item renders at a time.

It used to live in st.session_state and be drained in one loop that spawned a
daemon thread per item. They serialised on _RENDER_LOCK, so one rendered and
the rest waited -- and any restart of Streamlit killed every waiting thread
while clearing the session that held the queue. The owner saw the first one or
two appear and the rest vanish, with five jobs left "active" and their
heartbeats frozen for six hours.
"""

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.getLogger("streamlit").setLevel(logging.CRITICAL)

import jobs as _jobs  # noqa: E402


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(_jobs, "BATCH_QUEUE_PATH", tmp_path / "batch_queue.json")
    _jobs.batch_clear()
    return _jobs


def test_the_queue_is_on_disk_not_in_the_session(jobs):
    jobs.batch_add([{"type": "quiz"}, {"type": "educational"}])
    raw = json.load(open(jobs.BATCH_QUEUE_PATH, encoding="utf-8"))
    assert [i["type"] for i in raw["items"]] == ["quiz", "educational"]


def test_a_restart_does_not_lose_the_queue(jobs):
    """The whole point. Re-reading from disk is what a restart does."""
    jobs.batch_add([{"type": "quiz"}, {"type": "vocabulary"}])
    jobs._write_batch_queue(jobs.batch_queue())      # simulate the round trip
    assert len(jobs.batch_queue()) == 2


def test_taking_an_item_persists_immediately(jobs):
    jobs.batch_add([{"type": "quiz"}, {"type": "vocabulary"}])
    taken = jobs.batch_take()
    assert taken["type"] == "quiz"
    # written back before the job starts, so a crash loses one rather than
    # replaying it forever
    assert [i["type"] for i in jobs.batch_queue()] == ["vocabulary"]


def test_only_one_item_starts_while_something_renders(jobs, monkeypatch):
    started = []
    monkeypatch.setattr(jobs, "start_generation",
                        lambda *a, **k: started.append(a) or "job1")
    monkeypatch.setattr(jobs, "get_active_jobs", lambda: [{"id": "busy"}])

    jobs.batch_add([{"type": "quiz"}, {"type": "vocabulary"}])
    assert jobs.batch_advance() == ""
    assert started == [], "a second render was started on top of a running one"
    assert len(jobs.batch_queue()) == 2, "an item was consumed and dropped"


def test_the_next_item_starts_when_nothing_is_rendering(jobs, monkeypatch):
    started = []
    monkeypatch.setattr(jobs, "start_generation",
                        lambda *a, **k: started.append(a[0]) or "job1")
    monkeypatch.setattr(jobs, "get_active_jobs", lambda: [])

    jobs.batch_add([{"type": "quiz"}, {"type": "vocabulary"}])
    assert jobs.batch_advance() == "job1"
    assert started == ["quiz"]
    assert [i["type"] for i in jobs.batch_queue()] == ["vocabulary"]


def test_advancing_an_empty_queue_is_harmless(jobs, monkeypatch):
    monkeypatch.setattr(jobs, "get_active_jobs", lambda: [])
    assert jobs.batch_advance() == ""

"""STEP 85 §5: GET /api/events. A fake job drives the engine's real listeners; nothing renders, nothing is spent."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import jobs  # noqa: E402
from panel_api import app as appmod, events  # noqa: E402

HOST = "http://127.0.0.1:8501"
FREE = {"Origin": HOST}


@pytest.fixture
def env(tmp_path, monkeypatch):
    import comments
    for name, sub in (("PENDING_DIR", "pending"), ("APPROVED_DIR", "approved")):
        monkeypatch.setattr(jobs, name, tmp_path / sub)
    (tmp_path / "pending" / "quiz").mkdir(parents=True)
    (tmp_path / "pending" / "quiz" / "a.mp4").write_bytes(b"x")
    (tmp_path / "pending" / "quiz" / "a.json").write_text("{}")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(comments, "THREADS", tmp_path / "threads.json")
    monkeypatch.setattr(jobs, "_queue_guard", lambda: type("G", (), {"queued_scripts": staticmethod(lambda: [1, 2])})())
    return tmp_path


def _frames(resp, stop, limit=60):
    """Read SSE lines until `stop(event_dict)` is true; returns [(kind, payload)] where kind is event|comment."""
    got, name = [], None
    if not hasattr(resp, "_lines"):
        resp._lines = resp.iter_lines()                 # one iterator per response: a stream can be read once
    for line in resp._lines:
        if line.startswith(":"):
            got.append(("comment", line))
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            ev = json.loads(line[5:])
            got.append(("event", ev))
            if stop(ev):
                return got
        if len(got) > limit:
            break
    return got


def _events(got):
    return [p for k, p in got if k == "event"]


def test_a_fake_job_emits_the_five_steps_then_done_in_order(env):
    with TestClient(appmod.create_app(), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        jid = jobs.create_job("quiz")
        for p, text in ((30, "Script generated"), (50, "Voz"), (55, "Audio generated"), (90, "Video rendered"), (100, "Listo")):
            jobs.update_job(jid, progress=p, current_step=text)
        jobs.complete_job(jid, True, video_path=str(env / "pending" / "quiz" / "a.mp4"))
        got = _events(_frames(r, lambda e: e["type"] == "counts"))
    assert [(e["type"], e.get("step")) for e in got] == [("job.step", s) for s in ("guion", "voz", "sonido", "montaje", "control")] + [("job.done", None), ("counts", None)]
    assert all(e["jobId"] == jid and e["progress"] == 1.0 for e in got[:5])
    assert got[0]["log"] == "Script generated" and got[3]["log"] == "Video rendered"
    done = got[5]
    assert done == {"type": "job.done", "jobId": jid, "artifact": "a", "reviewCount": 1, "xpGained": 50}
    assert got[6]["counts"] == {"queue": 2, "review": 1, "upload": 0, "comments": 0}


def test_partial_progress_inside_a_step_is_streamed(env):
    with TestClient(appmod.create_app(), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        jid = jobs.create_job("quiz")
        jobs.update_job(jid, progress=15)
        jobs.update_job(jid, progress=15)                        # no change: nothing sent
        jobs.update_job(jid, progress=30)
        got = _events(_frames(r, lambda e: e.get("progress") == 1.0))
    assert [(e["step"], e["progress"]) for e in got] == [("guion", 0.5), ("guion", 1.0)]


def test_a_failing_job_emits_job_failed_in_spanish(env):
    with TestClient(appmod.create_app(), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        jid = jobs.create_job("quiz")
        jobs.complete_job(jid, False, error="boom")
        got = _events(_frames(r, lambda e: e["type"] == "job.failed"))
    assert got == [{"type": "job.failed", "jobId": jid, "reason": "No se pudo producir el vídeo. boom"}]


def test_a_heartbeat_comment_arrives_when_nothing_happens(env):
    with TestClient(appmod.create_app(heartbeat_s=0.05), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        lines = []
        for line in r.iter_lines():
            lines.append(line)
            if line == ": hb":
                break
            assert len(lines) < 20
    assert ": connected" in lines and lines[-1] == ": hb"
    assert events.HEARTBEAT_S == 15.0


def test_counts_follow_an_approve_and_a_reject(env):
    eng = {"approve": lambda i, b: {"state": "approved"}, "reject": lambda i, b: {"state": "rejected"}}
    with TestClient(appmod.create_app(eng), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        assert client.post("/api/review/a/approve", headers=FREE, json={}).json() == {"state": "approved"}
        first = _events(_frames(r, lambda e: e["type"] == "counts"))
        assert client.post("/api/review/a/reject", headers=FREE, json={}).status_code == 200
        second = _events(_frames(r, lambda e: e["type"] == "counts"))
    assert first[-1]["counts"]["queue"] == 2 and second[-1]["type"] == "counts"
    # a refused POST (foreign origin) changes nothing and sends nothing
    with TestClient(appmod.create_app(eng), base_url=HOST) as client:
        assert client.post("/api/review/a/approve", headers={"Origin": "http://evil.example"}, json={}).status_code == 403


def test_the_stream_is_get_only_and_checks_the_host(env):
    with TestClient(appmod.create_app(), base_url="http://evil.example:8501") as client:
        r = client.get("/api/events")
        assert r.status_code == 403 and "error" in r.json()
    with TestClient(appmod.create_app(), base_url=HOST) as client:
        assert client.post("/api/events", headers=FREE).status_code == 405


def test_a_disconnected_client_is_unsubscribed_and_nothing_leaks():
    async def run():
        bus = events.Bus()
        gen = events.stream(bus, 1.0)
        await gen.__anext__()
        assert bus.count() == 1
        await gen.aclose()                                       # what Starlette does when the browser goes away
        assert bus.count() == 0
        gen2 = events.stream(bus, 1.0)
        await gen2.__anext__()
        task = asyncio.ensure_future(gen2.__anext__())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert bus.count() == 0                                  # a cancelled read also unsubscribes
    asyncio.run(run())


def test_the_app_shutdown_removes_the_engine_listeners_and_ends_streams(env):
    before = (len(jobs.PROGRESS_LISTENERS), len(jobs.COMPLETE_LISTENERS))
    with TestClient(appmod.create_app(), base_url=HOST) as client:
        assert (len(jobs.PROGRESS_LISTENERS), len(jobs.COMPLETE_LISTENERS)) == (before[0] + 1, before[1] + 1)
    assert (len(jobs.PROGRESS_LISTENERS), len(jobs.COMPLETE_LISTENERS)) == before


def test_a_slow_client_drops_the_oldest_events_not_the_newest():
    async def run():
        bus = events.Bus(maxsize=3)
        sub = bus.subscribe()
        for i in range(10):
            bus.publish({"type": "counts", "i": i})
        await asyncio.sleep(0.05)
        out = [sub.queue.get_nowait()["i"] for _ in range(sub.queue.qsize())]
        bus.unsubscribe(sub)
        return out
    assert asyncio.run(run()) == [7, 8, 9]


def test_events_from_a_worker_thread_reach_the_loop():
    import threading

    async def run():
        bus = events.Bus()
        sub = bus.subscribe()
        threading.Thread(target=lambda: bus.publish({"type": "stats.refreshed"})).start()
        got = await asyncio.wait_for(sub.queue.get(), 2)
        bus.unsubscribe(sub)
        return got
    assert asyncio.run(run()) == {"type": "stats.refreshed"}


def test_the_stats_refresh_hook_emits_stats_refreshed(env):
    import channel_stats
    with TestClient(appmod.create_app(), base_url=HOST) as client, client.stream("GET", "/api/events") as r:
        for fn in list(channel_stats.REFRESH_LISTENERS):
            fn()
        got = _events(_frames(r, lambda e: e["type"] == "stats.refreshed"))
    assert got == [{"type": "stats.refreshed"}]

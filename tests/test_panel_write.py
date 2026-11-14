"""STEP 85 §4: the write endpoints over the real engine handlers. The pipeline and the upload manager are mocked;
no network, no real token, no real output tree."""
import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import jobs  # noqa: E402
import voice_lock  # noqa: E402
from panel_api import app as appmod, gate  # noqa: E402

CR = ZoneInfo("America/Costa_Rica")
PAID = {"Origin": "http://127.0.0.1:8501", gate.HEADER: gate.TOKEN}
FREE = {"Origin": "http://127.0.0.1:8501"}


class FakeManager:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def upload(self, platform, path, on_session=None, **kw):
        self.calls.append((platform, path, kw))
        if platform in self.fail:
            return {"success": False, "error": "cuota agotada"}
        return {"success": True, "upload_id": f"id-{platform}", "url": "u"}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import publication_log
    import upload_limits
    import uploader
    out = tmp_path / "output"
    for name, sub in (("PENDING_DIR", "pending"), ("APPROVED_DIR", "approved"), ("REJECTED_DIR", "rejected"),
                      ("UPLOADED_DIR", "uploaded"), ("SCRIPTS_DIR", "scripts")):
        monkeypatch.setattr(jobs, name, out / sub)
    monkeypatch.setattr(jobs, "JOBS_FILE", out / "jobs.json")
    monkeypatch.setattr(voice_lock, "GRANT_DIR", tmp_path / "grants")
    monkeypatch.setattr(upload_limits, "claim", lambda *a: True)
    monkeypatch.setattr(upload_limits, "release", lambda *a: None)
    manager = FakeManager()
    monkeypatch.setattr(uploader, "get_upload_manager", lambda: manager)
    d = out / "pending" / "how_do_you_say"
    d.mkdir(parents=True)
    (d / "uno.mp4").write_bytes(b"x" * 10)
    (d / "uno.json").write_text(json.dumps({"gate": "PASS", "metadata": {"title": "¿Cómo se dice la CASA?", "description": "d",
                                                                         "hashtags": {"youtube": ["#a"], "facebook": ["#b"]}}}))
    script = {"type": "how_do_you_say", "theme": "casa", "video_title": "x", "items": [{"english": "house"}],
              "_meta": {"topic_id": "t1", "topic": "casa"}}
    (out / "scripts" / "how_do_you_say").mkdir(parents=True)
    (out / "scripts" / "how_do_you_say" / "uno.json").write_text(json.dumps(script))
    app = appmod.create_app()
    client = TestClient(app, base_url="http://127.0.0.1:8501")
    return client, app, manager, out, publication_log, script


def _body(**kw):
    return {"publishAt": None, "platforms": ["youtube"], "title": "Título nuevo", "description": "Texto nuevo", "hashtags": ["#x", "#y"], **kw}


def _future(days=2, hh=21, mm=15):
    d = (datetime.now(CR) + timedelta(days=days)).date()
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=CR)


def _join(app):
    for t in app.state.jobs:
        t.join(5)


# ── approve ──

def test_approve_without_a_time_moves_to_por_subir_saves_the_edit_and_uploads_nothing(rig):
    client, _, manager, out, *_ = rig
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body())
    assert r.status_code == 200 and r.json() == {"state": "approved", "publishAt": None, "results": [], "warnings": []}
    assert (out / "approved" / "how_do_you_say" / "uno.mp4").exists() and not (out / "pending" / "how_do_you_say" / "uno.mp4").exists()
    meta = json.loads((out / "approved" / "how_do_you_say" / "uno.json").read_text())["metadata"]
    assert meta["title"] == "Título nuevo" and meta["description"] == "Texto nuevo" and meta["hashtags"]["youtube"] == ["#x", "#y"]
    assert meta["hashtags"]["facebook"] == ["#b"] and meta["source"] == "edited"
    assert manager.calls == []


def test_approve_with_a_time_schedules_at_that_exact_minute_with_warnings_and_scheduled_by_garcia(rig):
    client, _, manager, out, PL, _ = rig
    at = _future()
    rows = [{"platform": "youtube", "artifact": f"o{i}", "published_title": f"OTRO {i}", "upload_id": f"o{i}",
             "published_at": "x", "extra": {"scheduled_for": at.replace(hour=h, minute=m).isoformat()}}
            for i, (h, m) in enumerate([(8, 30), (12, 0), (16, 0), (19, 30)])]
    PL.LEDGER_PATH.write_text("".join(json.dumps(r) + "\n" for r in rows))
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(publishAt=at.isoformat(), platforms=["youtube", "facebook"]))
    j = r.json()
    assert r.status_code == 200 and j["state"] == "scheduled" and [x["ok"] for x in j["results"]] == [True, True]
    assert len(j["warnings"]) == 2 and "1 h 45 min" in j["warnings"][0] and "5.º" in j["warnings"][1]
    yt = next(c for c in manager.calls if c[0] == "youtube")[2]
    assert yt["publish_at"] == at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")     # the exact minute
    assert "publish_at" not in next(c for c in manager.calls if c[0] == "facebook")[2]
    assert yt["title"] == "Título nuevo"
    assert (out / "uploaded" / "how_do_you_say" / "uno.mp4").exists()
    info = json.loads((out / "uploaded" / "how_do_you_say" / "uno.json").read_text())["upload_info"]
    assert info["scheduled_by"] == "garcia"
    ledger = [json.loads(x) for x in PL.LEDGER_PATH.read_text().splitlines()]
    mine = [x for x in ledger if x["artifact"] == "uno"]
    assert {x["platform"] for x in mine} == {"youtube", "facebook"}
    assert next(x for x in mine if x["platform"] == "youtube")["extra"]["scheduled_by"] == "garcia"


def test_a_failing_platform_leaves_the_video_in_por_subir_and_says_why(rig, monkeypatch):
    client, _, _, out, *_ = rig
    import uploader
    manager = FakeManager(fail={"facebook"})
    monkeypatch.setattr(uploader, "get_upload_manager", lambda: manager)
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(publishAt=_future().isoformat(), platforms=["youtube", "facebook"]))
    j = r.json()
    assert r.status_code == 200 and j["state"] == "approved"
    assert {x["platform"]: (x["ok"], x["note"]) for x in j["results"]} == {"youtube": (True, None), "facebook": (False, "cuota agotada")}
    assert (out / "approved" / "how_do_you_say" / "uno.mp4").exists() and not (out / "uploaded" / "how_do_you_say" / "uno.mp4").exists()


def test_a_time_under_the_lead_rule_is_refused_and_nothing_moves(rig):
    client, _, manager, out, *_ = rig
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(publishAt=(datetime.now(CR) + timedelta(minutes=5)).isoformat()))
    assert r.status_code == 400 and "15 min" in r.json()["error"]
    assert (out / "pending" / "how_do_you_say" / "uno.mp4").exists() and manager.calls == []
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(publishAt="2026-12-01T10:00:00"))
    assert r.status_code == 400 and "zona horaria" in r.json()["error"]
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(publishAt=_future().isoformat(), platforms=["tiktok"]))
    assert r.status_code == 400 and "plataforma" in r.json()["error"]
    assert client.post("/api/review/nope/approve", headers=FREE, json=_body()).status_code == 404


def test_a_title_with_leftovers_is_not_saved(rig):
    client, _, _, out, *_ = rig
    r = client.post("/api/review/uno/approve", headers=FREE, json=_body(title="¿Cómo se dice «» en inglés?"))
    assert r.status_code == 400 and "No se guardó" in r.json()["error"]
    assert (out / "pending" / "how_do_you_say" / "uno.mp4").exists()


# ── reject ──

def test_reject_writes_the_reason_into_the_sidecar_and_moves_the_video(rig):
    client, _, _, out, *_ = rig
    r = client.post("/api/review/uno/reject", headers=FREE, json={"reason": "audio", "note": "ruido al final"})
    assert r.status_code == 200 and r.json() == {"state": "rejected"}
    side = json.loads((out / "rejected" / "how_do_you_say" / "uno.json").read_text())
    assert side["rejected"]["reason"] == "audio" and side["rejected"]["note"] == "ruido al final"
    assert client.post("/api/review/uno/reject", headers=FREE, json={"reason": "x"}).status_code == 404            # already gone


def test_reject_with_an_unknown_reason_is_400(rig):
    client, _, _, out, *_ = rig
    assert client.post("/api/review/uno/reject", headers=FREE, json={"reason": "porque sí", "note": ""}).status_code == 400
    assert (out / "pending" / "how_do_you_say" / "uno.mp4").exists()


# ── produce / rerender ──

def _mock_pipeline(monkeypatch, tmp_path, seen):
    monkeypatch.setattr(jobs.voice_credits, "panel_voice", lambda chars: nullcontext())
    monkeypatch.setattr(jobs, "attach_run_log", lambda name: tmp_path / f"{name}.log")
    monkeypatch.setattr(jobs, "detach_run_log", lambda p: None)
    monkeypatch.setattr(jobs, "batch_advance", lambda: None)

    def pipeline(job_id, video_type, category, topic_name, **kw):
        seen["row_existed"] = any(j["id"] == job_id for j in jobs.load_jobs()["active"])
        seen["grant_open"] = len(list((tmp_path / "grants").glob("*"))) == 1
        seen["kw"] = (video_type, kw)
        jobs.complete_job(job_id, True, "v.mp4")
    monkeypatch.setattr(jobs, "run_pipeline_with_tracking", pipeline)


def test_produce_creates_the_job_row_first_and_runs_the_pipeline_under_a_grant(rig, monkeypatch, tmp_path):
    client, app, _, _, _, script = rig
    seen = {}
    _mock_pipeline(monkeypatch, tmp_path, seen)
    import panel_core.queue_read as qr
    monkeypatch.setattr(qr, "next_best", lambda: (tmp_path / "bv1.json", script, "porque sí"))
    assert client.post("/api/produce", headers=FREE, json={"confirm": True}).status_code == 403              # paid: no token
    r = client.post("/api/produce", headers=PAID, json={"confirm": True})
    assert r.status_code == 200 and set(r.json()) == {"jobId", "etaS"}
    job_id = r.json()["jobId"]
    assert client.get(f"/api/jobs/{job_id}").status_code in (200,)                                              # exists at once
    _join(app)
    assert seen["row_existed"] and seen["grant_open"] and seen["kw"] == ("how_do_you_say", {"use_queue": True})
    assert list((tmp_path / "grants").glob("*")) == [] and voice_lock._ACTIVE == set()                       # closed after
    assert client.get(f"/api/jobs/{job_id}").json()["state"] == "done"


def test_produce_with_an_empty_queue_is_409_in_spanish(rig, monkeypatch):
    client, *_ = rig
    import panel_core.queue_read as qr
    monkeypatch.setattr(qr, "next_best", lambda: None)
    r = client.post("/api/produce", headers=PAID, json={"confirm": True})
    assert r.status_code == 409 and "cola está vacía" in r.json()["error"]


def test_produce_refuses_a_script_that_is_not_the_next_of_its_type(rig, monkeypatch, tmp_path):
    client, *_ = rig
    q = tmp_path / "q"
    q.mkdir()
    (q / "bv9.json").write_text(json.dumps({"type": "how_do_you_say"}))
    monkeypatch.setattr(jobs, "_queue_guard", lambda: type("G", (), {"queued_scripts": staticmethod(lambda: [q / "bv9.json"])})())
    monkeypatch.setattr(jobs, "queue_pick", lambda *a, **k: (q / "other.json", {}))
    r = client.post("/api/produce", headers=PAID, json={"confirm": True, "scriptId": "bv9"})
    assert r.status_code == 409 and "siguiente" in r.json()["error"]
    assert client.post("/api/produce", headers=PAID, json={"confirm": True, "scriptId": "nope"}).status_code == 404


def test_a_video_already_rendering_is_409_in_spanish(rig, monkeypatch, tmp_path):
    client, _, _, _, _, script = rig
    import panel_core.queue_read as qr
    monkeypatch.setattr(qr, "next_best", lambda: (tmp_path / "bv1.json", script, ""))
    def busy(*a, **k):
        raise jobs.AlreadyRendering("Ya se está renderizando bv1")
    monkeypatch.setattr(jobs, "prepare_generation", busy)
    r = client.post("/api/produce", headers=PAID, json={"confirm": True})
    assert r.status_code == 409 and r.json() == {"error": "Ya se está renderizando bv1"}


def test_rerender_is_paid_rejects_the_old_video_and_makes_it_again(rig, monkeypatch, tmp_path):
    client, app, _, out, *_ = rig
    seen = {}
    _mock_pipeline(monkeypatch, tmp_path, seen)
    assert client.post("/api/review/uno/rerender", headers=FREE, json={"confirm": True}).status_code == 403
    assert client.post("/api/review/uno/rerender", headers=PAID, json={}).status_code == 400
    assert (out / "pending" / "how_do_you_say" / "uno.mp4").exists()                                           # refused: untouched
    r = client.post("/api/review/uno/rerender", headers=PAID, json={"confirm": True})
    assert r.status_code == 200
    _join(app)
    assert (out / "rejected" / "how_do_you_say" / "uno.mp4").exists() and not (out / "pending" / "how_do_you_say" / "uno.mp4").exists()
    assert seen["kw"][0] == "how_do_you_say" and seen["kw"][1]["rerender"] is True and seen["kw"][1]["script_data"]["theme"] == "casa"
    assert seen["row_existed"] and seen["grant_open"]


def test_rerender_of_a_script_already_rendering_is_409_and_the_video_stays(rig):
    client, _, _, out, _, script = rig
    jid = jobs.create_job("how_do_you_say")
    jobs.update_job(jid, script_key=jobs.script_key(script), status="running")
    r = client.post("/api/review/uno/rerender", headers=PAID, json={"confirm": True})
    assert r.status_code == 409 and "renderizando" in r.json()["error"]
    assert (out / "pending" / "how_do_you_say" / "uno.mp4").exists()
    assert client.post("/api/review/nope/rerender", headers=PAID, json={"confirm": True}).status_code == 404


def test_streamlit_and_the_api_share_one_start_path():
    import ast
    src = (ROOT / "src" / "jobs.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    start = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "start_generation")
    names = {n.func.id for n in ast.walk(start) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "prepare_generation" in names and "run_pipeline_with_tracking" not in names

"""STEP 85 §3: the spend gate. TestClient only, mocked engine; nothing listens, nothing is spent."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from panel_api import app as appmod, gate  # noqa: E402
import voice_lock  # noqa: E402

GOOD = {"Origin": "http://127.0.0.1:8501", gate.HEADER: gate.TOKEN}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_lock, "GRANT_DIR", tmp_path / "grants")
    monkeypatch.delenv(gate.DEV_ENV, raising=False)
    seen = {}

    def produce(script_id):
        def runner():
            seen["during"] = (sorted(p.name for p in (tmp_path / "grants").glob("*")), set(voice_lock._ACTIVE))
        seen["script"] = script_id
        return "job1", 120, runner

    def rerender(item_id):
        return "job2", None, lambda: seen.setdefault("rerender", item_id)

    app = appmod.create_app({"produce": produce, "rerender": rerender,
                             "approve": lambda i, b: {"state": "approved", "id": i}, "reject": lambda i, b: {"ok": True}})
    client = TestClient(app, base_url="http://127.0.0.1:8501")
    return client, app, seen, tmp_path


def _post(client, url, headers=None, body=None):
    return client.post(url, headers=headers if headers is not None else GOOD, json=body if body is not None else {"confirm": True})


def _join(app):
    for t in app.state.jobs:
        t.join(5)


def test_no_token_is_403(rig):
    client, *_ = rig
    h = {"Origin": GOOD["Origin"]}
    r = _post(client, "/api/produce", h)
    assert r.status_code == 403 and "sesión" in r.json()["error"]


def test_a_wrong_token_is_403(rig):
    client, *_ = rig
    assert _post(client, "/api/produce", {**GOOD, gate.HEADER: "x" * len(gate.TOKEN)}).status_code == 403
    assert _post(client, "/api/produce", {**GOOD, gate.HEADER: ""}).status_code == 403


def test_a_foreign_or_missing_origin_is_403_even_with_the_token(rig):
    client, *_ = rig
    assert _post(client, "/api/produce", {**GOOD, "Origin": "http://evil.example"}).status_code == 403
    assert _post(client, "/api/produce", {**GOOD, "Origin": "http://127.0.0.1:9999"}).status_code == 403
    assert _post(client, "/api/produce", {gate.HEADER: gate.TOKEN}).status_code == 403          # no Origin at all
    wrong_host = TestClient(client.app, base_url="http://evil.example:8501")
    assert _post(wrong_host, "/api/produce").status_code == 403                                  # Host not the panel


def test_no_confirm_is_400(rig):
    client, *_ = rig
    for body in ({}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1}):
        r = _post(client, "/api/produce", body=body)
        assert r.status_code == 400 and "confirmación" in r.json()["error"], body
    assert client.post("/api/produce", headers=GOOD, content=b"not json").status_code == 400


def test_a_valid_produce_runs_the_engine_with_the_voice_grant_open_then_closed(rig):
    client, app, seen, tmp = rig
    assert not list((tmp / "grants").glob("*")) if (tmp / "grants").exists() else True
    r = _post(client, "/api/produce", body={"confirm": True, "scriptId": "bv1"})
    assert r.status_code == 200 and r.json() == {"jobId": "job1", "etaS": 120} and seen["script"] == "bv1"
    _join(app)
    files, active = seen["during"]
    assert len(files) == 1 and len(files[0]) == 32 and files[0] in active              # open while the job ran
    assert list((tmp / "grants").glob("*")) == [] and voice_lock._ACTIVE == set()      # closed when it ended


def test_the_grant_closes_even_when_the_job_fails(rig):
    client, app, seen, tmp = rig
    app2 = appmod.create_app({"produce": lambda s: ("j", None, lambda: (_ for _ in ()).throw(RuntimeError("boom")))})
    c2 = TestClient(app2, base_url="http://127.0.0.1:8501")
    assert _post(c2, "/api/produce").status_code == 200
    _join(app2)
    assert list((tmp / "grants").glob("*")) == [] and voice_lock._ACTIVE == set()


def test_rerender_is_paid_too(rig):
    client, app, seen, _ = rig
    assert _post(client, "/api/review/x/rerender", {"Origin": GOOD["Origin"]}).status_code == 403
    assert _post(client, "/api/review/x/rerender", body={}).status_code == 400
    assert _post(client, "/api/review/x/rerender").json() == {"jobId": "job2", "etaS": None}
    _join(app)
    assert seen["rerender"] == "x"


def test_free_posts_need_the_origin_but_no_token(rig):
    client, *_ = rig
    assert _post(client, "/api/review/x/approve", {"Origin": GOOD["Origin"]}, {"publishAt": None}).json()["state"] == "approved"
    assert _post(client, "/api/review/x/reject", {"Origin": GOOD["Origin"]}, {"reason": "audio"}).json() == {"ok": True}
    for url in ("/api/review/x/approve", "/api/review/x/reject"):
        assert _post(client, url, {"Origin": "http://evil.example"}, {}).status_code == 403
        assert _post(client, url, {}, {}).status_code == 403


def test_the_dev_origin_is_allowed_only_with_the_dev_flag(rig, monkeypatch):
    client, *_ = rig
    dev = TestClient(client.app, base_url="http://localhost:5173")
    h = {**GOOD, "Origin": "http://localhost:5173"}
    assert _post(dev, "/api/produce", h).status_code == 403
    monkeypatch.setenv(gate.DEV_ENV, "1")
    assert _post(dev, "/api/produce", h).status_code == 200


def test_the_token_appears_only_in_the_served_index_meta(rig, tmp_path, monkeypatch):
    client, *_ = rig
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
    monkeypatch.setattr(gate, "DIST", dist)
    idx = client.get("/")
    assert f'<meta name="eu-session" content="{gate.TOKEN}">' in idx.text and idx.headers["cache-control"] == "no-store"
    assert client.get("/index.html").text == idx.text
    leaks = []
    probes = [client.get(u) for u in ("/api/meta", "/api/home", "/api/review", "/api/jobs/nope", "/media/nope", "/api/nope")]
    probes += [_post(client, "/api/produce", h, b) for h, b in (({}, {}), ({"Origin": GOOD["Origin"]}, {}), (GOOD, {}), (GOOD, None))]
    probes += [_post(client, "/api/review/x/approve", {"Origin": "http://evil.example"}, {})]
    for r in probes:
        blob = r.text + json.dumps(dict(r.headers))
        if gate.TOKEN in blob:
            leaks.append(r.request.url.path)
    assert leaks == []
    assert gate.TOKEN not in json.dumps([r.json() for r in probes if r.headers.get("content-type", "").startswith("application/json")])


def test_the_spa_fallback_serves_the_injected_index_and_assets_but_never_leaves_dist(rig, tmp_path, monkeypatch):
    client, *_ = rig
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><head></head><body>app</body></html>")
    (dist / "assets" / "app-abc.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setattr(gate, "DIST", dist)
    assert gate.TOKEN in client.get("/revisar").text and gate.TOKEN in client.get("/openapi.json").text   # a client route: the app
    js = client.get("/assets/app-abc.js")
    assert js.status_code == 200 and js.text == "console.log(1)" and gate.TOKEN not in js.text
    assert js.headers["cache-control"] == "public, max-age=31536000, immutable"
    for bad in ("../secret.txt", "..%2Fsecret.txt", "assets/../../secret.txt"):
        assert "no" != client.get(f"/{bad}").text and gate.TOKEN in client.get(f"/{bad}").text, bad   # falls back to the index, never the file
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"error": "No existe esa ruta."} and gate.TOKEN not in r.text
    assert client.get("/media/nope.png").status_code == 404


def test_the_front_ends_empty_placeholder_is_filled_not_duplicated():
    html = '<head><meta name="eu-session" content="" /><title>x</title></head>'
    out = gate.inject_token(html)
    assert out.count('name="eu-session"') == 1 and f'content="{gate.TOKEN}"' in out
    assert gate.inject_token('<head></head>').count('name="eu-session"') == 1


def test_the_real_built_index_gets_exactly_one_filled_token_tag():
    built = ROOT / "panel" / "dist" / "index.html"
    if not built.exists():
        pytest.skip("panel/dist is not built")
    out = gate.inject_token(built.read_text(encoding="utf-8"))
    assert out.count('name="eu-session"') == 1 and f'content="{gate.TOKEN}"' in out


def test_without_a_built_panel_the_index_is_a_404_not_a_crash(rig, tmp_path, monkeypatch):
    client, *_ = rig
    monkeypatch.setattr(gate, "DIST", tmp_path / "nope")
    r = client.get("/")
    assert r.status_code == 404 and gate.TOKEN not in r.text


def test_the_token_is_random_per_process_and_long():
    import subprocess
    code = "import sys; sys.path.insert(0,'src'); from panel_api import gate; print(gate.TOKEN)"
    a = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    b = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert a != b and len(a) >= 40 and a != gate.TOKEN


def test_voice_stays_locked_under_pytest_outside_a_request(rig):
    assert voice_lock.locked() and voice_lock._ACTIVE == set()
    with pytest.raises(voice_lock.VoiceLocked):
        voice_lock.check()
    client, app, *_ = rig
    _post(client, "/api/produce")
    _join(app)
    assert voice_lock.locked()                                                          # and even a granted job is refused under pytest

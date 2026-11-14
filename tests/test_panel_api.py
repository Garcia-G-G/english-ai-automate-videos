"""STEP 85 §2: the read endpoints. Every GET is compared with panel/contract-fixtures/<name>.json (same keys, same
JSON types, null where allowed) over a fixture tree in tmp_path, so nothing here reads or writes real content."""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = ROOT / "panel" / "contract-fixtures"
CR = ZoneInfo("America/Costa_Rica")
OPTIONAL = {"src2x", "placeholder", "mock"}                  # `?` fields of contract.ts


def shape_diffs(got, want, path="$"):
    """Recursive comparer: same keys, same JSON types. None is accepted on either side (a nullable field); a field
    that is optional in the contract may be absent. Lists compare the first element of each."""
    if got is None or want is None:
        return []
    kind = lambda x: "number" if isinstance(x, (int, float)) and not isinstance(x, bool) else type(x).__name__   # noqa: E731
    if kind(got) != kind(want):
        return [f"{path}: {kind(got)} != {kind(want)}"]
    out = []
    if isinstance(want, dict):
        for k in want.keys() - got.keys() - OPTIONAL:
            out.append(f"{path}.{k}: missing")
        for k in got.keys() - want.keys() - OPTIONAL:
            out.append(f"{path}.{k}: not in the contract")
        for k in got.keys() & want.keys():
            out += shape_diffs(got[k], want[k], f"{path}.{k}")
    elif isinstance(want, list) and got and want:
        out += shape_diffs(got[0], want[0], f"{path}[0]")
    return out


def test_the_shape_comparer_catches_what_it_should():
    assert shape_diffs({"a": 1, "b": "x"}, {"a": 2.5, "b": "y"}) == []
    assert shape_diffs({"a": None}, {"a": 1}) == [] and shape_diffs({"a": 1}, {"a": None}) == []
    assert shape_diffs({"a": "1"}, {"a": 1}) == ["$.a: str != number"]
    assert shape_diffs({}, {"a": 1}) == ["$.a: missing"] and shape_diffs({"z": 1}, {}) == ["$.z: not in the contract"]
    assert shape_diffs({"l": [{"a": 1}]}, {"l": [{"a": "x"}]}) == ["$.l[0].a: number != str"]
    assert shape_diffs({"src": "x"}, {"src": "x", "src2x": "y"}) == []


def _mp4(path: Path, seconds=4):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=270x480:r=10:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture
def api(tmp_path, monkeypatch):
    import channel_stats
    import comments
    import cost_tracker
    import jobs
    import publication_log
    import senal
    from panel_api import app as appmod, build, media
    out = tmp_path / "output"
    for name, sub in (("PENDING_DIR", "pending"), ("APPROVED_DIR", "approved"), ("REJECTED_DIR", "rejected"), ("SCRIPTS_DIR", "scripts")):
        monkeypatch.setattr(jobs, name, out / sub)
    monkeypatch.setattr(jobs, "JOBS_FILE", out / "jobs.json")
    monkeypatch.setattr(media, "MEDIA_ROOT", out)
    monkeypatch.setattr(build, "THUMBS_ROOT", out / "thumbs" / "scripts")
    monkeypatch.setattr(publication_log, "LEDGER_PATH", out / "ledger.jsonl")
    monkeypatch.setattr(channel_stats, "STATS_DIR", out / "stats")
    monkeypatch.setattr(senal, "SENAL_DIR", out / "senal")
    monkeypatch.setattr(comments, "THREADS", out / "threads.json")
    monkeypatch.setattr(cost_tracker, "COSTS_DIR", out / "costs")
    (out / "costs").mkdir(parents=True)
    (out / "stats").mkdir()
    (out / "senal").mkdir()
    today = datetime.now(CR).date()
    (out / "stats" / f"youtube_{today}.json").write_text(json.dumps({"read_at": f"{today}T03:00:00", "videos": [
        {"id": f"v{i}", "type": "how_do_you_say", "title": "t", "views": 800 + i, "likes": 3, "days": 5 + i, "category": "ANIMALES",
         "subs_gained": 1} for i in range(6)] + [{"id": "q", "type": "level_test", "title": "q", "views": 100, "likes": 1, "days": 9, "category": "x"}]}))
    pub = today - timedelta(days=40)
    (out / "senal" / "senal.json").write_text(json.dumps({"data_until": str(today - timedelta(days=2)), "videos": [
        {"id": "v0", "published": str(pub), "daily": [10, 20, 30]}, {"id": "v1", "published": str(today - timedelta(days=10)), "daily": [5, 6, 7]}]}))
    (out / "threads.json").write_text(json.dumps([{"replies": []}, {"replies": [1]}]))
    (out / "ledger.jsonl").write_text(json.dumps({"platform": "youtube", "artifact": "a", "published_title": "MÉDICO 🩺", "upload_id": "v0",
                                                  "published_at": f"{today}T08:30:00", "extra": {"scheduled_for": f"{today}T08:30:00-06:00"}}) + "\n")
    d = out / "pending" / "how_do_you_say"
    d.mkdir(parents=True)
    _mp4(d / "uno.mp4")
    (d / "uno.json").write_text(json.dumps({"gate": "PASS", "deesser": {"input_lufs": -14.0},
                                            "metadata": {"title": "¿Cómo se dice MÁS ANIMALES?", "description": "d", "hashtags": ["#a", "b"]}}))
    (out / "scripts" / "how_do_you_say").mkdir(parents=True)
    (out / "scripts" / "how_do_you_say" / "uno.json").write_text(json.dumps({"type": "how_do_you_say", "items": [{"english": "cat"}], "design_variant": "tablero"}))
    qdir = tmp_path / "q"
    qdir.mkdir()
    (qdir / "q1.json").write_text("{}")
    monkeypatch.setattr(jobs, "_queue_guard", lambda: type("G", (), {"queued_scripts": staticmethod(lambda: [qdir / "q1.json"] * 3)})())
    monkeypatch.setattr(jobs, "_queue_bad", lambda *a, **k: set())
    import panel_core.queue_read as qr
    script = qdir / "bv1_carro.json"
    script.write_text("{}")
    monkeypatch.setattr(qr, "next_best", lambda: (script, {"type": "level_test", "video_title": "El CARRO en inglés 🚗", "theme": "carro",
                                                           "items": [{"english": "car", "emoji": "🚗"}]}, "porque sí"))
    build._CACHE.clear()
    return TestClient(appmod.create_app()), out


@pytest.mark.parametrize("name,url", [("meta", "/api/meta"), ("home", "/api/home"), ("review", "/api/review")])
def test_each_get_matches_its_contract_fixture(api, name, url):
    client, _ = api
    r = client.get(url)
    assert r.status_code == 200, r.text[:500]
    want = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert shape_diffs(r.json(), want) == []


def test_meta_counts_equal_the_sidebars(api, monkeypatch):
    import jobs
    client, _ = api
    c = client.get("/api/meta").json()["counts"]
    import admin
    monkeypatch.setattr(admin, "PENDING_DIR", jobs.PENDING_DIR)             # admin copied the directories when first imported
    monkeypatch.setattr(admin, "APPROVED_DIR", jobs.APPROVED_DIR)
    monkeypatch.setattr(admin, "_queue_guard", jobs._queue_guard)
    sidebar = admin._badge_counts()
    assert (c["queue"], c["review"], c["comments"]) == (sidebar["Queue"], sidebar["Review"], sidebar["Comments"])
    assert c["upload"] == len(admin.get_approved_videos()) and c == {"queue": 3, "review": 1, "upload": 0, "comments": 1}


def test_review_item_reads_the_sidecar_and_never_ticks_what_it_does_not_know(api):
    client, out = api
    item = client.get("/api/review").json()["items"][0]
    assert item["id"] == "uno" and item["design"] == "Tablero" and item["items"] == 1 and item["hashtags"] == ["#a", "#b"]
    by = {c["key"]: c for c in item["checks"]}
    assert by["loudness"]["ok"] is True and by["loudness"]["detail"] == "-14.0 LUFS"
    assert by["sync"]["ok"] is None and by["sync"]["detail"] is None
    assert len(item["strip"]) == 6 and item["frame0"]["src"].startswith("/media/pending/")
    assert item["videoUrl"] == "/media/pending/how_do_you_say/uno.mp4" and item["gate"]["total"] == 6 and item["gate"]["reason"] is None
    sched = client.get("/api/review").json()["schedule"]
    assert sched["utcOffset"] == "-06:00" and sched["minLeadMin"] == 15


def test_home_next_views_and_agenda_come_from_the_engine(api):
    client, _ = api
    h = client.get("/api/home").json()
    assert h["next"]["scriptId"] == "bv1_carro" and h["next"]["topic"] == "CARRO" and h["next"]["xp"] is None
    assert h["next"]["thumb"] is None                                          # not a Tablero script: no drawn frame 0, so null
    assert [s["time"] for s in h["agenda"]["today"]] == ["08:30", "12:00", "16:00", "19:30"]
    assert h["agenda"]["today"][0]["title"] == "MÉDICO 🩺" and h["agenda"]["today"][0]["emoji"] == "🩺"
    assert h["views"]["periodDays"] == 28 and len(h["views"]["daily"]) == 28 and h["views"]["dataUntil"]
    assert h["formats"][0]["key"] == "how_do_you_say" and h["formats"][0]["label"] == "Cómo se dice"


def test_a_missing_senal_file_is_null_not_a_guess(api):
    client, out = api
    (out / "senal" / "senal.json").unlink()
    from panel_api import build
    build._CACHE.clear()
    assert client.get("/api/home").json()["views"] is None


def test_the_job_endpoint_returns_steps_and_404s_an_unknown_id(api):
    client, _ = api
    import jobs
    jid = jobs.create_job("quiz", topic="PRUEBA")
    jobs.update_job(jid, progress=40)
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["state"] == "running" and j["steps"]["guion"] == 1.0 and j["steps"]["voz"] == 0.5 and j["error"] is None
    want = {"id": "", "scriptId": "", "title": "", "topic": "", "startedAt": "", "etaS": 0, "state": "", "steps": dict.fromkeys(["guion", "voz", "montaje", "sonido", "control"], 0.5), "log": [], "error": None}
    assert shape_diffs(j, want) == []
    jobs.complete_job(jid, False, error="boom")
    assert client.get(f"/api/jobs/{jid}").json()["state"] == "failed"
    r = client.get("/api/jobs/nope")
    assert r.status_code == 404 and "error" in r.json()


def test_the_result_is_cached_on_mtimes_until_a_file_changes(api, monkeypatch):
    client, out = api
    from panel_api import build
    calls = []
    real = build._meta
    monkeypatch.setattr(build, "_meta", lambda: calls.append(1) or real())
    client.get("/api/meta"), client.get("/api/meta")
    assert len(calls) == 1
    (out / "threads.json").write_text(json.dumps([{"replies": []}]))
    import os
    os.utime(out / "threads.json", (1, 1))
    client.get("/api/meta")
    assert len(calls) == 2


# ── /media ──

def test_media_serves_only_files_under_output_and_answers_range(api, tmp_path):
    client, out = api
    mp4 = out / "pending" / "how_do_you_say" / "uno.mp4"
    size = mp4.stat().st_size
    full = client.get("/media/pending/how_do_you_say/uno.mp4")
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes" and len(full.content) == size
    part = client.get("/media/pending/how_do_you_say/uno.mp4", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == mp4.read_bytes()[10:20] and part.headers["content-range"] == f"bytes 10-19/{size}"
    assert client.get("/media/pending/how_do_you_say/uno.mp4", headers={"Range": "bytes=-5"}).content == mp4.read_bytes()[-5:]
    assert client.get("/media/pending/how_do_you_say/uno.mp4", headers={"Range": f"bytes={size + 5}-"}).status_code == 416
    (tmp_path / "secret.txt").write_text("no")
    for bad in ("../secret.txt", "..%2Fsecret.txt", "pending/../../secret.txt", "%00", "pending", "nope.mp4"):
        assert client.get(f"/media/{bad}").status_code == 404, bad
    (out / "link.txt").symlink_to(tmp_path / "secret.txt")
    assert client.get("/media/link.txt").status_code == 404                     # a symlink out of output/ is refused


def test_thumbnails_get_long_cache_headers(api):
    client, out = api
    (out / "t.webp").write_bytes(b"RIFFxxxxWEBP")
    r = client.get("/media/t.webp")
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable" and r.headers["content-type"] == "image/webp"


def test_the_api_package_never_imports_streamlit_and_binds_localhost():
    code = "import sys; sys.path.insert(0,'src'); import panel_api.app as a; assert a.HOST == '127.0.0.1'; assert not any(m.startswith('streamlit') for m in sys.modules)"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]

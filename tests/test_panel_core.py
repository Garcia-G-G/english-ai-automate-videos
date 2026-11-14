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

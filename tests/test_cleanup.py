"""STEP 74 §1: tools/cleanup.py on a temp tree: each rule, the never-delete list, the git refusal."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cleanup as C  # noqa: E402

NOW = time.time()
DAY = 86400


def put(root: Path, rel: str, data: bytes = b"x", age_days: float = 0) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    t = NOW - age_days * DAY
    os.utime(p, (t, t))
    return p


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def track(root: Path, rel: str):
    put(root, rel)
    subprocess.run(["git", "-C", str(root), "add", rel], check=True)


def planned(root, rule):
    return {p.relative_to(root).as_posix() for p in rule(root, C.guards(root), NOW)["paths"]}


def test_whole_folders_rules_take_their_contents_and_leave_the_folder(tree):
    for rel in ("output/uploaded/quiz/a.mp4", "output/rejected/b.mp4", "output/clips/c.mp4",
                "output/frames/f.png", "output/r1_verify/r.mp4", "output/step3_verify/s.mp4",
                "output/voice_tests_elevenlabs/v.mp3", "_to_delete/old.mp4",
                "experiments/manim_voiceover_poc/media/videos/x.mp4"):
        put(tree, rel)
    assert planned(tree, C.rule_uploaded) == {"output/uploaded/quiz"}
    assert planned(tree, C.rule_rejected) == {"output/rejected/b.mp4"}
    assert planned(tree, C.rule_intermediates) == {
        "output/clips/c.mp4", "output/frames/f.png", "output/r1_verify/r.mp4",
        "output/step3_verify/s.mp4", "output/voice_tests_elevenlabs/v.mp3"}
    assert planned(tree, C.rule_to_delete) == {"_to_delete/old.mp4"}
    assert planned(tree, C.rule_manim_media) == {"experiments/manim_voiceover_poc/media/videos"}
    plans = C.plan(tree, now=NOW)
    C.delete([p for pl in plans for p in pl["paths"]], root=tree)
    assert (tree / "output/uploaded").is_dir() and not any((tree / "output/uploaded").iterdir())


def test_artifacts_go_after_14_days_unless_approved_queued_or_in_doubt(tree):
    put(tree, "output/artifacts/fresh/artifact.json", b"{}", age_days=13.9)
    put(tree, "output/artifacts/old/artifact.json", b"{}", age_days=14.1)
    put(tree, "output/artifacts/approved_one/artifact.json", b"{}", age_days=30)
    put(tree, "output/approved/quiz/approved_one.mp4")
    put(tree, "output/artifacts/queued/artifact.json", b"{}", age_days=30)
    put(tree, "output/published/meta_queue.json", json.dumps([{"artifact": "queued"}]).encode())
    put(tree, "output/artifacts/doubt/artifact.json", b"{}", age_days=30)
    put(tree, "output/published/attempts.jsonl",
        b'{"artifact": "doubt", "platform": "youtube", "status": "unknown"}\n')
    put(tree, "output/artifacts/held/artifact.json", json.dumps({"state": "approved"}).encode(), age_days=30)
    put(tree, "output/artifacts/broken/artifact.json", b"{not json", age_days=30)
    plan = C.rule_artifacts(tree, C.guards(tree), NOW)
    assert {p.name for p in plan["paths"]} == {"old"}
    assert {p.name: why for p, why in plan["kept"]} == {
        "approved_one": "aprobado y sin subir a todo", "queued": "en la cola de Meta",
        "doubt": "intento unknown, sin confirmar", "held": "estado approved",
        "broken": "artifact.json ilegible"}


def test_manim_keeps_the_newest_set_per_lesson_and_theme_and_what_was_approved_or_published(tree):
    r = "experiments/manim_voiceover_poc/renders"
    for stem in ("20261001-100000_t_1080p30_sand", "20261002-100000_t_1080p30_sand",
                 "20261003-100000_t_1080p30_sand", "20261001-100000_t_720p30"):
        for ext in (".mp4", ".srt", ".timeline.json", ".jpg"):
            put(tree, f"{r}/lesson/{stem}{ext}")
    put(tree, f"{r}/reviews.jsonl", json.dumps(
        {"file": "lesson/20261002-100000_t_1080p30_sand.mp4", "status": "aprobada"}).encode() + b"\n")
    put(tree, f"{r}/ledger.jsonl")
    put(tree, f"{r}/jobs/job.json")
    put(tree, "output/published/ledger.jsonl", b'{"artifact": "nothing", "platform": "youtube"}\n')
    gone = planned(tree, C.rule_manim_renders)
    assert gone == {f"{r}/lesson/20261001-100000_t_1080p30_sand{e}" for e in (".mp4", ".srt", ".timeline.json", ".jpg")}


def test_the_pexels_cache_drops_unused_slots_then_caps_oldest_first(tree, monkeypatch):
    monkeypatch.setattr(C, "CLIP_CACHE_CAP_BYTES", 250)
    put(tree, "assets/clips/_cache/stale/p.mp4", b"x" * 100, age_days=31)
    put(tree, "assets/clips/_cache/older/p.mp4", b"x" * 100, age_days=20)
    put(tree, "assets/clips/_cache/old/p.mp4", b"x" * 100, age_days=10)
    put(tree, "assets/clips/_cache/new/p.mp4", b"x" * 100, age_days=1)
    put(tree, "assets/outro/keep.mp4", age_days=400)
    assert planned(tree, C.rule_clip_cache) == {"assets/clips/_cache/stale", "assets/clips/_cache/older"}


def test_pycache_outside_venv(tree):
    put(tree, "src/__pycache__/a.pyc")
    put(tree, ".pytest_cache/v")
    put(tree, ".venv/lib/__pycache__/b.pyc")
    put(tree, "experiments/manim_voiceover_poc/.venv/lib/__pycache__/c.pyc")
    assert planned(tree, C.rule_pycache) == {".pytest_cache", "src/__pycache__"}


def test_nothing_on_the_never_list_is_planned_even_inside_a_rule_folder(tree):
    never = [".env", ".env.local", ".tokens/yt.json", "content/queue/a.json", "output/approved/quiz/a.mp4",
             "output/audio/a.mp3", "output/cache/x", "output/published/ledger.jsonl", "output/costs/c.json",
             "output/scripts/s.json", "output/qa/design_proposals/p.png", "logs/l.log",
             "experiments/manim_voiceover_poc/audio/a.mp3", "assets/outro/o.mp4", ".venv/x"]
    for rel in never:
        put(tree, rel, age_days=400)
    put(tree, "output/uploaded/.env", age_days=400)              # a never-name inside a rule folder
    plans = C.plan(tree, now=NOW)
    planned_all = {p.resolve() for pl in plans for p in pl["paths"]}
    assert not planned_all
    for rel in never:
        with pytest.raises(C.RefusedPath):
            C.delete([tree / rel], root=tree)
        assert (tree / rel).exists()


def test_a_git_tracked_path_is_kept_by_the_plan_and_refused_by_delete(tree):
    track(tree, "output/uploaded/tracked.mp4")
    put(tree, "output/uploaded/loose.mp4")
    plan = C.rule_uploaded(tree, C.guards(tree), NOW)
    assert [p.name for p in plan["paths"]] == ["loose.mp4"]
    assert plan["kept"] == [(tree / "output/uploaded/tracked.mp4", "git lo sigue")]
    with pytest.raises(C.RefusedPath, match="git lo sigue"):
        C.delete([tree / "output/uploaded/loose.mp4", tree / "output/uploaded/tracked.mp4"], root=tree)
    assert (tree / "output/uploaded/loose.mp4").exists()        # refused whole: nothing went
    with pytest.raises(C.RefusedPath):
        C.delete([tree / "output"], root=tree)                   # a folder holding a tracked file


def test_main_dry_run_deletes_nothing_and_only_s_deletes(tree, monkeypatch, capsys):
    target = put(tree, "output/rejected/b.mp4", b"x" * 10)
    monkeypatch.setattr(C, "ROOT", tree)
    real_plan, real_delete = C.plan, C.delete
    monkeypatch.setattr(C, "plan", lambda: real_plan(tree, now=NOW))
    monkeypatch.setattr(C, "delete", lambda paths: real_delete(paths, root=tree))
    assert C.main(["--dry-run"]) == 0 and target.exists()
    assert "2 output/rejected" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert C.main([]) == 1 and target.exists()
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    assert C.main([]) == 0 and not target.exists()
    assert "Liberado: 10 B" in capsys.readouterr().out


def test_tests_and_files_a_test_reads_are_never_deleted(tree):
    put(tree, "tests/fixtures/layout/quiz.mp3", age_days=400)
    put(tree, "tests/test_x.py", b'FIX = "output/clips/run1/fixture.mp3"  # and output/rejected/ in prose\n')
    put(tree, "output/clips/run1/fixture.mp3")
    put(tree, "output/clips/run2/loose.mp3")
    put(tree, "output/rejected/b.mp4")
    plan = C.rule_intermediates(tree, C.guards(tree), NOW)
    assert [p.name for p in plan["paths"]] == ["run2"]
    assert plan["kept"] == [(tree / "output/clips/run1", "un test lo usa")]
    assert planned(tree, C.rule_rejected) == {"output/rejected/b.mp4"}    # a folder named in prose is not a file
    for rel in ("tests/fixtures/layout/quiz.mp3", "tests", "output/clips/run1/fixture.mp3"):
        with pytest.raises(C.RefusedPath):
            C.delete([tree / rel], root=tree)

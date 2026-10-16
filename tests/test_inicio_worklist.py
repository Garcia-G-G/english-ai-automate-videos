#!/usr/bin/env python3
"""Inicio names artifacts and their next action, and proves its own counts.

    python3 -m pytest tests/test_inicio_worklist.py

The page it replaced opened with Total Videos, Pending, Approved, Uploaded,
Active Jobs, Storage MB and "By Type 40%". Every one of those is an aggregate
ABOUT the system and none of them is a thing an operator can act on. The rule
now is that a block either names specific artifacts and the one button that
moves each of them forward, or it is not on the page.

Two of those properties are worth pinning in tests rather than in a
screenshot, because both have already failed in this repo once:

  ABSENCE STAYS VISIBLE.  A video with no QA verdict on file must not render
  as one that passed. Five of the artifacts in output/pending/ predate the
  commit that started writing the verdict into the sidecar, and a page that
  shows nothing for them is indistinguishable from a page that shows a tick.
  gate_record has three outcomes, never two.

  THE COUNTS ARE CHECKED.  The number on the page comes from the list the
  page draws; independent_disk_census counts the same artifacts again by a
  walk that shares no code with the listers. If one of them ever skips a
  directory, the two disagree and the page says so. A test that only used the
  listers would be checking the broken half against itself.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.getLogger("streamlit").setLevel(logging.CRITICAL)

import admin  # noqa: E402
import thumbnails  # noqa: E402


# ─────────────────────────── fixtures ───────────────────────────

def _mp4(path: Path, seconds: float = 3.0) -> Path:
    """A real, tiny, decodable mp4 — ffmpeg is what the thumbnailer shells to,
    so a stub file would test nothing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=size=108x192:rate=10:duration={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True)
    return path


def _artifact(root: Path, stage: str, vtype: str, stem: str,
              gate=..., real_video: bool = False) -> Path:
    """One artifact in <stage>/<type>/, with the sidecar Review reads.

    gate=...      no `gate` key at all (an artifact from before D0)
    gate=None     the key exists and is null
    gate="PASS"   a recorded verdict
    """
    d = root / stage / vtype
    d.mkdir(parents=True, exist_ok=True)
    mp4 = d / f"{stem}.mp4"
    if real_video:
        _mp4(mp4)
    else:
        mp4.write_bytes(b"\x00" * 32)
    meta = {"artifact": stem, "video_type": vtype, "topic": stem}
    if gate is not ...:
        meta["gate"] = gate
    (d / f"{stem}.json").write_text(json.dumps(meta), encoding="utf-8")
    return mp4


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """An output tree with the shape the real one has today."""
    out = tmp_path / "out"
    for name, attr in (("video", "VIDEO_DIR"), ("pending", "PENDING_DIR"),
                       ("approved", "APPROVED_DIR"), ("uploaded", "UPLOADED_DIR"),
                       ("rejected", "REJECTED_DIR")):
        (out / name).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(admin, attr, out / name)
    monkeypatch.setattr(admin, "OUTPUT_DIR", out)
    return out


# ──────────────── absence is not approval ────────────────

def test_no_gate_record_is_not_a_pass():
    """The whole lesson of D0, as an assertion.

    A missing sidecar, a sidecar with no `gate` key, and a null value all
    mean the same thing — nobody recorded a verdict — and none of them may
    come back as PASS or as a quiet blank.
    """
    for meta in (None, {}, {"gate": None}, {"artifact": "x", "topic": "y"}):
        rec = admin.gate_record(meta)
        assert rec["known"] is False
        assert rec["verdict"] is None
        assert rec["label"] == admin.GATE_MISSING_LABEL == "sin registro"
        assert rec["tone"] == "unknown"
        # The tone drives the CSS class. If it were ever "pass", the badge
        # would come out green.
        assert rec["tone"] != "pass"
        assert rec["label"] != "PASS"


def test_recorded_verdicts_keep_their_own_tone():
    assert admin.gate_record({"gate": "PASS"})["tone"] == "pass"
    assert admin.gate_record({"gate": "PASS"})["known"] is True
    assert admin.gate_record({"gate": "REJECT"})["tone"] == "reject"
    assert admin.gate_record({"gate": "NO_REPORT"})["tone"] == "unknown"
    assert admin.gate_record({"gate": "NO_REPORT"})["label"] == "sin informe"
    # A verdict nobody anticipated is shown verbatim, not swallowed.
    assert admin.gate_record({"gate": "WEIRD"})["label"] == "WEIRD"
    assert admin.gate_record({"gate": "WEIRD"})["known"] is True


def test_blocking_flags_travel_with_a_reject():
    rec = admin.gate_record({"gate": "REJECT", "blocking_flags": ["dead_air", "drift"]})
    assert rec["flags"] == ["dead_air", "drift"]


def test_the_gate_split_counts_missing_records_separately(tree):
    """Three PASS and five with no record must not add up to eight PASS."""
    for i in range(3):
        _artifact(tree, "pending", "quiz", f"passer_{i}", gate="PASS")
    for i in range(5):
        _artifact(tree, "pending", "educational", f"predates_d0_{i}", gate=...)

    census = admin.independent_disk_census()
    assert census["pending"] == 8
    assert census["pending_gate_pass"] == 3
    assert census["pending_gate_missing"] == 5
    assert census["pending_gate_other"] == 0

    # And the lister and the census agree about which is which.
    listed = admin.get_pending_videos()
    known_pass = sum(1 for v in listed
                     if admin.gate_record(v["meta"])["verdict"] == "PASS")
    unknown = sum(1 for v in listed if not admin.gate_record(v["meta"])["known"])
    assert (known_pass, unknown) == (3, 5)


def test_an_unreadable_sidecar_counts_as_no_record_not_as_a_pass(tree):
    """Corruption must fail towards "nobody knows", never towards approval."""
    mp4 = _artifact(tree, "pending", "quiz", "broken", gate="PASS")
    mp4.with_suffix(".json").write_text("{ this is not json", encoding="utf-8")
    census = admin.independent_disk_census()
    assert census["pending_gate_pass"] == 0
    assert census["pending_gate_missing"] == 1


# ──────────────── the counts are checked twice ────────────────

def test_census_agrees_with_every_lister(tree):
    _artifact(tree, "video", "quiz", "b1")
    _artifact(tree, "video", "educational", "b2")
    _artifact(tree, "pending", "quiz", "p1", gate="PASS")
    _artifact(tree, "approved", "true_false", "a1", gate="PASS")
    _artifact(tree, "uploaded", "quiz", "u1")
    _artifact(tree, "uploaded", "vocabulary", "u2")

    census = admin.independent_disk_census()
    assert census["batch"] == len(admin.get_library_videos()) == 2
    assert census["pending"] == len(admin.get_pending_videos()) == 1
    assert census["approved"] == len(admin.get_approved_videos()) == 1
    assert census["uploaded"] == len(admin.get_uploaded_videos()) == 2


def test_census_is_a_genuinely_separate_walk(tree):
    """The point of the second count is catching what the first one misses.

    get_library_videos globs one level down (<type>/*.mp4). The census walks
    recursively. An artifact nested deeper is invisible to the lister and
    visible to the census — which is exactly the disagreement the page is
    built to surface, so it must actually arise.
    """
    deep = tree / "video" / "quiz" / "subdir"
    deep.mkdir(parents=True)
    (deep / "hidden.mp4").write_bytes(b"\x00")
    _artifact(tree, "video", "quiz", "visible")

    assert len(admin.get_library_videos()) == 1
    assert admin.independent_disk_census()["batch"] == 2


def test_census_on_an_empty_tree_is_zero_not_an_error(tree):
    census = admin.independent_disk_census()
    assert census["batch"] == census["pending"] == census["approved"] == 0
    assert census["ledger_rows"] == 0


def test_ledger_rows_are_counted_without_the_ledger_reader(tree):
    """Lines counted straight off disk, so a bug in read_ledger shows up as a
    disagreement instead of propagating to both halves of the check."""
    d = tree / "published"
    d.mkdir(parents=True)
    (d / "ledger.jsonl").write_text(
        '{"artifact":"a","platform":"youtube"}\n'
        '\n'
        '{"artifact":"b","platform":"youtube"}\n', encoding="utf-8")
    assert admin.independent_disk_census()["ledger_rows"] == 2


# ──────────────── failures ────────────────

def test_a_gate_reject_is_not_a_failed_job(tmp_path, monkeypatch):
    """"failed" means the pipeline raised. A refused video is a successful
    render of a bad artifact and carries its verdict on the artifact; merging
    the two would corrupt both counts."""
    jobs = tmp_path / "generation_jobs.json"
    jobs.write_text(json.dumps({"active": [], "history": [
        {"id": "1", "status": "completed", "gate": "REJECT",
         "current_step": "Gate: REJECT", "completed_at": "2026-08-21T10:00:00"},
        {"id": "2", "status": "failed", "error": "boom",
         "log_path": "/logs/2.log", "completed_at": "2026-08-22T10:00:00"},
        {"id": "3", "status": "completed", "gate": "PASS",
         "completed_at": "2026-08-23T10:00:00"},
    ]}))
    monkeypatch.setattr(admin, "JOBS_FILE", jobs)

    failed = admin.get_failed_jobs()
    assert [j["id"] for j in failed] == ["2"]
    assert failed[0]["error"] == "boom"
    assert failed[0]["log_path"] == "/logs/2.log"


def test_failed_jobs_come_back_newest_first(tmp_path, monkeypatch):
    jobs = tmp_path / "generation_jobs.json"
    jobs.write_text(json.dumps({"active": [], "history": [
        {"id": "old", "status": "failed", "completed_at": "2026-08-01T00:00:00"},
        {"id": "new", "status": "failed", "completed_at": "2026-08-25T00:00:00"},
        {"id": "mid", "status": "failed", "completed_at": "2026-08-10T00:00:00"},
    ]}))
    monkeypatch.setattr(admin, "JOBS_FILE", jobs)
    assert [j["id"] for j in admin.get_failed_jobs()] == ["new", "mid", "old"]
    assert [j["id"] for j in admin.get_failed_jobs(limit=2)] == ["new", "mid"]


# ──────────────── money, one line ────────────────

def _costs(d: Path, day: str, amounts) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"costs_{day}.jsonl").write_text(
        "".join(json.dumps({"timestamp": f"{day}T12:00:00", "cost_usd": a}) + "\n"
                for a in amounts), encoding="utf-8")


def test_cost_snapshot_separates_today_from_the_month(tmp_path):
    costs = tmp_path / "costs"
    _costs(costs, "2026-08-24", [0.10, 0.05])
    _costs(costs, "2026-08-26", [0.25])
    cfg = tmp_path / "config.yaml"
    cfg.write_text("costs:\n  monthly_ceiling_usd: 25.0\n")

    snap = admin.cost_snapshot(config_path=cfg, costs_dir=costs, today="2026-08-26")
    assert snap["today_usd"] == 0.25
    assert snap["month_usd"] == 0.40
    assert snap["ceiling_usd"] == 25.0
    assert snap["pct_of_ceiling"] == pytest.approx(1.6)


def test_a_day_with_no_spend_is_zero_not_missing(tmp_path):
    costs = tmp_path / "costs"
    _costs(costs, "2026-08-24", [0.10])
    cfg = tmp_path / "config.yaml"
    cfg.write_text("costs:\n  monthly_ceiling_usd: 25.0\n")
    snap = admin.cost_snapshot(config_path=cfg, costs_dir=costs, today="2026-08-26")
    assert snap["today_usd"] == 0.0
    assert snap["month_usd"] == 0.10


def test_no_ceiling_in_config_is_reported_not_invented(tmp_path):
    """A made-up ceiling nobody set is worse than a visible gap."""
    costs = tmp_path / "costs"
    _costs(costs, "2026-08-26", [1.0])
    cfg = tmp_path / "config.yaml"
    cfg.write_text("video:\n  fps: 30\n")
    snap = admin.cost_snapshot(config_path=cfg, costs_dir=costs, today="2026-08-26")
    assert snap["ceiling_usd"] is None
    assert snap["pct_of_ceiling"] is None
    assert snap["month_usd"] == 1.0


def test_a_corrupt_cost_line_does_not_take_the_line_down(tmp_path):
    costs = tmp_path / "costs"
    costs.mkdir()
    (costs / "costs_2026-08-26.jsonl").write_text(
        '{"cost_usd": 0.10}\nnot json at all\n{"cost_usd": 0.05}\n'
        '{"cost_usd": null}\n', encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("costs:\n  monthly_ceiling_usd: 1.0\n")
    snap = admin.cost_snapshot(config_path=cfg, costs_dir=costs, today="2026-08-26")
    assert snap["today_usd"] == pytest.approx(0.15)


def test_the_real_config_carries_a_ceiling():
    """config.yaml is where the page reads it from; if the key is dropped the
    line silently degrades to "sin techo"."""
    snap = admin.cost_snapshot(costs_dir=Path("/nonexistent"), today="2026-08-26")
    assert snap["ceiling_usd"] is not None and snap["ceiling_usd"] > 0


# ──────────────── the button lands on the artifact ────────────────

def test_focus_first_moves_the_pressed_artifact_to_the_top():
    videos = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    assert [v["name"] for v in admin.focus_first(videos, "c")] == ["c", "a", "b"]


def test_focus_first_keeps_everything_else(tmp_path):
    """Order only. The operator may well keep going down the list."""
    videos = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    assert len(admin.focus_first(videos, "b")) == 3
    assert [v["name"] for v in admin.focus_first(videos, None)] == ["a", "b", "c"]
    # An artifact that vanished between the press and the draw changes nothing.
    assert [v["name"] for v in admin.focus_first(videos, "gone")] == ["a", "b", "c"]


# ──────────────── thumbnails ────────────────

def test_the_thumbnail_key_survives_the_artifact_moving(tmp_path):
    """An artifact travels video/ -> pending/ -> approved/ -> uploaded/. The
    cache is keyed on <type>/<stem>, which is stable across all four, so the
    still is extracted once for the artifact's whole life rather than once
    per stage."""
    stem = "hang_in_there_20260820"
    stages = [tmp_path / s / "educational" / f"{stem}.mp4"
              for s in ("video", "pending", "approved", "uploaded")]
    keys = {thumbnails.thumbnail_path(p, thumbs_dir=tmp_path / "t") for p in stages}
    assert len(keys) == 1


def test_the_thumbnail_key_separates_types(tmp_path):
    """vocabulary/blue.mp4 and quiz/blue.mp4 can both exist."""
    a = thumbnails.thumbnail_path(tmp_path / "pending" / "quiz" / "blue.mp4",
                                  thumbs_dir=tmp_path / "t")
    b = thumbnails.thumbnail_path(tmp_path / "pending" / "vocabulary" / "blue.mp4",
                                  thumbs_dir=tmp_path / "t")
    assert a != b


def test_a_thumbnail_is_extracted_once_and_then_reused(tmp_path):
    mp4 = _mp4(tmp_path / "pending" / "quiz" / "clip.mp4")
    thumbs = tmp_path / "thumbs"

    first = thumbnails.ensure_thumbnail(mp4, thumbs_dir=thumbs)
    assert first and Path(first).stat().st_size > 0
    stamp = Path(first).stat().st_mtime_ns

    second = thumbnails.ensure_thumbnail(mp4, thumbs_dir=thumbs)
    assert second == first
    assert Path(second).stat().st_mtime_ns == stamp, "re-extracted a cached still"


def test_a_rerendered_artifact_gets_a_new_thumbnail(tmp_path):
    """Otherwise the page shows the previous render's frame for the new file."""
    import os
    mp4 = _mp4(tmp_path / "pending" / "quiz" / "clip.mp4")
    thumbs = tmp_path / "thumbs"
    out = Path(thumbnails.ensure_thumbnail(mp4, thumbs_dir=thumbs))
    old = out.stat().st_mtime_ns

    os.utime(mp4, (out.stat().st_mtime + 60, out.stat().st_mtime + 60))
    thumbnails.ensure_thumbnail(mp4, thumbs_dir=thumbs)
    assert out.stat().st_mtime_ns != old


def test_a_clip_shorter_than_the_seek_still_gets_a_picture(tmp_path):
    """The default seek is 1.5s. A one-second artifact must fall back to frame
    zero rather than come back blank."""
    mp4 = _mp4(tmp_path / "pending" / "quiz" / "short.mp4", seconds=0.5)
    got = thumbnails.ensure_thumbnail(mp4, thumbs_dir=tmp_path / "t")
    assert got and Path(got).stat().st_size > 0


def test_an_undecodable_file_yields_none_and_leaves_nothing_behind(tmp_path):
    """These calls run inside a render loop. A broken artifact means "no
    picture", never a traceback that blanks the page."""
    bad = tmp_path / "pending" / "quiz" / "junk.mp4"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"definitely not an mp4")
    thumbs = tmp_path / "thumbs"
    assert thumbnails.ensure_thumbnail(bad, thumbs_dir=thumbs) is None
    assert not thumbnails.thumbnail_path(bad, thumbs_dir=thumbs).exists()


def test_a_missing_artifact_yields_none(tmp_path):
    assert thumbnails.ensure_thumbnail(
        tmp_path / "pending" / "quiz" / "nope.mp4", thumbs_dir=tmp_path / "t") is None

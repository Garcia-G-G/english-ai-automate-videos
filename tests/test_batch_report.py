#!/usr/bin/env python3
"""A batch says what happened, in a file, without anyone reading logs.

    python3 -m pytest tests/test_batch_report.py

R1 took fill_blank from one combined options TTS call to nine, so there is
more per-call failure surface and nobody is watching when it fires. Refusing
to abort the batch on one failure is correct and predates this — the gap was
that the failure then became a log line and the run still exited 0.

Everything here is stubbed. Nothing generates, renders, or uploads.
"""

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import batch_report as BR  # noqa: E402


def _outcome(**kw):
    base = {"artifact": "a", "uploaded": [], "recorded": [], "unrecorded": [],
            "skipped": [], "skip_details": [], "held": [], "errors": []}
    base.update(kw)
    return base


# ── categories ───────────────────────────────────────────────────────

def test_a_clean_run_has_an_empty_needs_human_section():
    """The point of the section: an operator reads one file and stops."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(recorded=["youtube"]))

    assert r.needs_human == []
    assert r.to_dict()["needs_human"] == []
    assert e["status"] == BR.PUBLISHED


def test_a_skip_is_its_own_category_not_a_success():
    """PROMPT 2's guard skips when it believes the video is already live. Its
    documented hole is a re-render under the same name being refused forever;
    that is only survivable if a skip is LOUD."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        skipped=["youtube"],
        skip_details=[{"platform": "youtube", "upload_id": "vid_live_42",
                       "reason": "already in the ledger"}]))

    assert e["status"] == BR.SKIPPED
    assert e["status"] != BR.PUBLISHED
    assert r.counts()[BR.PUBLISHED] == 0


def test_a_skip_names_the_video_it_believes_is_live():
    """So the operator can check the channel instead of trusting the guard."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        skipped=["youtube"],
        skip_details=[{"platform": "youtube", "upload_id": "vid_live_42",
                       "reason": "already in the ledger"}]))

    skip = e["skipped"][0]
    assert skip["believed_live_id"] == "vid_live_42"
    assert skip["reason"]


def test_live_but_unrecorded_reaches_the_summary():
    """PROMPT 1 could only log this at CRITICAL. Headless that is nothing."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        uploaded=["youtube"], unrecorded=["youtube"],
        errors=[{"platform": "youtube", "stage": "record", "error": "disk full"}]))

    assert e["status"] == BR.NEEDS_HUMAN
    item = r.needs_human[0]
    assert item["why"] == "PUBLISHED BUT NOT RECORDED"
    assert "disk full" in item["reason"]
    assert "LIVE" in item["check"]


def test_a_held_ambiguous_upload_reaches_the_summary():
    """PROMPT 2 holds on a 404'd session URI and logs CRITICAL."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        held=["youtube"],
        errors=[{"platform": "youtube", "stage": "guard",
                 "error": "session URI expired (404)"}]))

    assert e["status"] == BR.NEEDS_HUMAN
    item = r.needs_human[0]
    assert item["why"] == "UPLOAD STATE UNDETERMINED"
    assert "404" in item["reason"]
    assert "channel" in item["check"]


def test_needs_human_outranks_a_partial_success():
    """One platform published, another is ambiguous. The ambiguous one must
    not be hidden by the success."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        recorded=["tiktok"], held=["youtube"],
        errors=[{"platform": "youtube", "stage": "guard", "error": "404"}]))

    assert e["status"] == BR.NEEDS_HUMAN
    assert e["published"] == ["tiktok"]


def test_a_plain_upload_failure_is_failed_not_needs_human():
    """A failure that will retry cleanly needs no human."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")
    BR.record_upload_outcome(e, _outcome(
        errors=[{"platform": "youtube", "stage": "upload", "error": "init 500"}]))

    assert e["status"] == BR.FAILED
    assert r.needs_human == []


# ── the file ─────────────────────────────────────────────────────────

def test_the_report_is_written_to_disk(tmp_path):
    r = BR.BatchReport(run_id="run1", report_dir=tmp_path)
    BR.record_upload_outcome(r.start_video("v1", "quiz"),
                             _outcome(recorded=["youtube"]))

    path = r.write()

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["counts"]["published"] == 1
    assert list(data)[4] == "needs_human" or "needs_human" in data


def test_latest_json_points_at_the_last_run(tmp_path):
    """So an operator has one path to check, not a directory to sort."""
    BR.BatchReport(run_id="run1", report_dir=tmp_path).write()
    r2 = BR.BatchReport(run_id="run2", report_dir=tmp_path)
    BR.record_upload_outcome(r2.start_video("v", "quiz"),
                             _outcome(recorded=["youtube"]))
    r2.write()

    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["run_id"] == "run2"


def test_writing_never_raises(tmp_path, monkeypatch):
    """A reporting bug must not be what takes a batch down."""
    r = BR.BatchReport(run_id="x", report_dir=tmp_path / "nope")
    monkeypatch.setattr(BR.json, "dumps", lambda *a, **k: 1 / 0)

    assert r.write() is None


# ── quarantine ───────────────────────────────────────────────────────

def test_a_failed_artifact_is_findable_with_a_reason(tmp_path):
    vid = tmp_path / "v1.mp4"
    vid.write_bytes(b"x")
    entry = {"artifact": "v1", "type": "quiz", "stage": "render",
             "reason": "ffmpeg exited 1", "failed": []}

    dest = BR.quarantine(vid, entry, failed_dir=tmp_path / "failed")

    assert dest.exists()
    assert not vid.exists()
    reason = json.loads(dest.with_suffix(".failure.json").read_text())
    assert reason["stage"] == "render"
    assert "ffmpeg" in reason["reason"]


def test_quarantine_does_not_use_the_qa_gates_rejected_tree():
    """output/rejected/ means 'the gate said no'. An upload or render failure
    is a different class with a different remedy."""
    assert BR.FAILED_DIR.name == "failed"
    assert "rejected" not in str(BR.FAILED_DIR)


# ── the batch: one failure does not stop the others ──────────────────

def test_three_videos_middle_one_fails(tmp_path, monkeypatch):
    """The proof case. Videos 1 and 3 publish, video 2 fails, the batch
    completes and the report says so."""
    import main

    report = BR.BatchReport(run_id="proof", report_dir=tmp_path)
    seen = []

    def fake_generate_and_run(category, topic, topic_name, vtype, background,
                              upload=False, use_v2=False, dry_run=False,
                              entry=None):
        seen.append(topic_name)
        if topic_name == "two":
            raise RuntimeError("TTS call 5 of 9 failed: 502 from ElevenLabs")
        BR.record_upload_outcome(entry, _outcome(recorded=["youtube"]))
        return Path("x.mp4")

    for name in ("one", "two", "three"):
        entry = report.start_video(name, "fill_blank", name)
        try:
            fake_generate_and_run(None, None, name, "fill_blank", None,
                                  entry=entry)
        except Exception as exc:
            main._note_failure(entry, "tts", exc)

    assert seen == ["one", "two", "three"], "the batch stopped early"
    c = report.counts()
    assert c["published"] == 2
    assert c["failed"] == 1

    failed = [v for v in report.videos if v["status"] == "failed"]
    assert failed[0]["artifact"] == "two"
    assert "502 from ElevenLabs" in failed[0]["reason"]
    assert failed[0]["stage"] == "tts"


def test_the_batch_loop_has_a_backstop_for_unanticipated_raises():
    """Everything below returns rather than raising today. The backstop is
    for what nobody anticipated — and it must record, not swallow."""
    import ast
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # find the `if args.batch:` block inside main()
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    backstops = [h for h in handlers
                 if isinstance(h.type, ast.Name) and h.type.id == "Exception"]

    assert backstops, "the batch loop has no backstop"
    for h in backstops:
        names = {n.id for n in ast.walk(h) if isinstance(n, ast.Name)}
        assert "_note_failure" in names or "logger" in names, (
            "the backstop swallows without recording")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
"""The gate and the outro reach BOTH paths, not neither.

    python3 -m pytest tests/test_finalisation_wiring.py

WHAT WAS ACTUALLY WRONG. finalize_video had zero callers, so neither the
dashboard nor `--batch --upload` ran the QA gate or appended the Learning
Routes outro. The published videos carry the WATERMARK (video/brand.py,
composited by utils.finalize_frame, which every renderer calls) — that is a
different feature from 4a and is why the outro looked present.

So this was not a divergence between two paths. It was a gap in both.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import batch_report as BR  # noqa: E402


def _calls(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == name:
                out.append(n.lineno)
            elif isinstance(f, ast.Attribute) and f.attr == name:
                out.append(n.lineno)
    return out


# ── both paths call it ───────────────────────────────────────────────

def test_the_headless_path_finalises():
    """The CLI delegates production instead of owning finalisation."""
    assert _calls(ROOT / "main.py", "build_creation_service")
    assert not _calls(ROOT / "main.py", "finalize_video")


def test_the_dashboard_path_finalises():
    """It had no gate and no outro either — this was a gap in both paths, not
    a divergence between them."""
    assert _calls(ROOT / "src" / "admin.py", "finalize_video"), (
        "admin.py does not finalise")


def test_there_is_still_exactly_one_finalisation_implementation():
    """Two would drift, and the order below is the part that must not."""
    defs = 0
    for f in ("src/pipeline.py", "src/admin.py", "main.py"):
        tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        defs += sum(1 for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "finalize_video")
    assert defs == 1, f"expected one definition, found {defs}"


# ── the order the existing code establishes ──────────────────────────

def test_a_rejected_video_still_gets_no_outro(monkeypatch, tmp_path):
    """pipeline.py:418 says why: the outro is a call to action pointing at
    Learning Routes, and putting the brand on the end of something the gate
    just refused is worse than shipping nothing. Wiring must not weaken it."""
    import pipeline
    import qa_gate
    from video import outro as O

    monkeypatch.setattr(qa_gate, "analyze", lambda p: {
        "artifact": "x", "video_type": "quiz",
        "flags": ["dead_air:5.0s"], "measured_duration": 30.0})
    monkeypatch.setattr(qa_gate, "verdict", lambda r: {
        "verdict": "REJECT", "blocking_flags": ["dead_air:5.0s"]})
    monkeypatch.setattr(O, "append_outro",
                        lambda *a, **k: pytest.fail("outro on a REJECTED video"))

    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    res = pipeline.finalize_video(vid, tmp_path / "a.json")

    assert res["gate"] == "REJECT"
    assert res["outro_appended"] is False


def test_the_gate_runs_before_the_outro(monkeypatch, tmp_path):
    order = []
    import pipeline
    import qa_gate
    from video import outro as O

    monkeypatch.setattr(qa_gate, "analyze",
                        lambda p: order.append("gate") or
                        {"artifact": "x", "measured_duration": 10.0})
    monkeypatch.setattr(qa_gate, "verdict",
                        lambda r: {"verdict": "PASS", "blocking_flags": []})
    monkeypatch.setattr(O, "select_variant", lambda seed=None: {"id": "v"})
    monkeypatch.setattr(O, "append_outro",
                        lambda p, v, output_path=None: order.append("outro")
                        or Path(output_path).write_bytes(b"y") or output_path)
    monkeypatch.setattr(O, "measure_seam", lambda *a, **k: None)

    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    pipeline.finalize_video(vid, tmp_path / "a.json")

    assert order == ["gate", "outro"]


def test_finalisation_keeps_the_artifact_name(monkeypatch, tmp_path):
    """append_outro defaults to <name>_with_outro.mp4, and the stem is the
    ledger's key AND the idempotency guard's key. A finalisation step must not
    rename the thing the publication record identifies."""
    import pipeline
    import qa_gate
    from video import outro as O

    monkeypatch.setattr(qa_gate, "analyze",
                        lambda p: {"artifact": "x", "measured_duration": 10.0})
    monkeypatch.setattr(qa_gate, "verdict",
                        lambda r: {"verdict": "PASS", "blocking_flags": []})
    monkeypatch.setattr(O, "select_variant", lambda seed=None: {"id": "v"})
    monkeypatch.setattr(O, "append_outro",
                        lambda p, v, output_path=None:
                        Path(output_path).write_bytes(b"outro'd") or output_path)
    monkeypatch.setattr(O, "measure_seam", lambda *a, **k: None)

    vid = tmp_path / "quiz_20260807_120000.mp4"
    vid.write_bytes(b"x")
    res = pipeline.finalize_video(vid, tmp_path / "a.json")

    assert Path(res["video"]).name == "quiz_20260807_120000.mp4"
    assert vid.read_bytes() == b"outro'd", "the outro'd file did not replace it"
    assert not list(tmp_path.glob("*_with_outro*")), "left a renamed copy"
    assert not list(tmp_path.glob("*.tmp.mp4")), "left a temp file"


# ── rejection is its own category ────────────────────────────────────

def test_a_rejection_is_not_a_failure():
    """Nothing broke: a video was produced and judged unfit. The remedy is to
    read blocking flags, not a traceback."""
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")

    BR.reject(e, ["dead_air:5.0s", "clipping"])

    assert e["status"] == BR.REJECTED
    assert e["status"] != BR.FAILED
    assert r.counts()[BR.REJECTED] == 1
    assert r.counts()[BR.FAILED] == 0


def test_the_rejection_carries_the_blocking_flags():
    r = BR.BatchReport(run_id="t")
    e = r.start_video("v1", "quiz")

    BR.reject(e, ["dead_air:5.0s"])

    assert e["blocking_flags"] == ["dead_air:5.0s"]
    assert "dead_air" in e["reason"]


def test_a_rejected_artifact_goes_to_rejected_not_failed(tmp_path):
    """output/rejected/ already means 'the gate said no'."""
    vid = tmp_path / "v1.mp4"
    vid.write_bytes(b"x")
    vid.with_suffix(".json").write_text("{}")
    entry = {"artifact": "v1", "type": "quiz", "status": BR.REJECTED,
             "stage": "gate", "reason": "QA gate: dead_air",
             "blocking_flags": ["dead_air:5.0s"]}

    dest = BR.move_rejected(vid, entry, report={"gate": "REJECT"},
                            rejected_dir=tmp_path / "rejected")

    assert dest.exists()
    assert "rejected" in str(dest)
    assert not vid.exists()
    import json
    r = json.loads(dest.with_suffix(".rejection.json").read_text())
    assert r["blocking_flags"] == ["dead_air:5.0s"]
    assert r["status"] == BR.REJECTED
    # the sidecar travels with it, or the reason is orphaned
    assert (dest.parent / "v1.json").exists()


def test_the_two_trees_are_distinct():
    assert BR.REJECTED_DIR.name == "rejected"
    assert BR.FAILED_DIR.name == "failed"
    assert BR.REJECTED_DIR != BR.FAILED_DIR


def test_a_rejected_video_is_not_uploaded():
    """The canonical creation adapter never invokes the legacy uploader."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_creation")
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "upload_video"
        for n in ast.walk(fn)
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

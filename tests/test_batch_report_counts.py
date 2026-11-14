#!/usr/bin/env python3
"""A run that produced videos must not read like a run that produced nothing.

    python3 -m pytest tests/test_batch_report_counts.py

The batch report is the artefact a scheduled run leaves behind. On the
2026-08-18 six-video batch it lied three ways, and all three come from the
same assumption — that publishing is the only outcome worth counting:

  counts.attempted was 2 for a --batch 1 run, because ATTEMPTED was seeded
  from len(videos) and then incremented again in the loop.

  With --upload off every bucket stayed at zero, so six good videos and a run
  that died during script generation printed the same summary line.

  stage stayed "script" and artifact_path stayed None on videos that had
  rendered, gated and had their outro appended, because both were written
  only inside the upload branch.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from batch_report import BatchReport, record_render  # noqa: E402


@pytest.fixture
def report(tmp_path):
    return BatchReport(run_id="test_run", report_dir=tmp_path)


def test_attempted_counts_each_video_once(report):
    report.start_video("one", "educational", "one")
    assert report.counts()["attempted"] == 1, "a one-video run reported 2"
    report.start_video("two", "quiz", "two")
    assert report.counts()["attempted"] == 2


def test_a_rendered_gated_run_is_visible_without_upload(report):
    """The whole point: upload off must not read as 'nothing happened'."""
    for i in range(6):
        entry = report.start_video(f"v{i}", "quiz", f"topic {i}")
        record_render(entry, f"/out/v{i}.mp4", gate="PASS")

    c = report.counts()
    assert c["attempted"] == 6
    assert c["rendered"] == 6, "six videos rendered and the report said nothing"
    assert c["gate_passed"] == 6
    # Publishing genuinely did not happen; those stay zero.
    assert c["published"] == 0 and c["failed"] == 0 and c["rejected"] == 0


def test_render_records_stage_and_path(report):
    entry = report.start_video("v", "educational", "t")
    assert entry["stage"] == "script" and entry["artifact_path"] is None

    record_render(entry, "/out/v.mp4", gate="PASS")

    assert entry["artifact_path"] == "/out/v.mp4"
    assert entry["stage"] == "gated"
    assert entry["gate"] == "PASS"


def test_a_rendered_but_rejected_video_counts_as_rendered_not_gated(report):
    entry = report.start_video("v", "quiz", "t")
    record_render(entry, "/out/v.mp4", gate="REJECT")

    c = report.counts()
    assert c["rendered"] == 1, "it was produced; the gate refusing it is separate"
    assert c["gate_passed"] == 0
    assert entry["stage"] == "rendered"


def test_a_run_that_produced_nothing_still_reads_as_nothing(report):
    """The counter must not make an empty run look productive either."""
    report.start_video("v", "educational", "t")
    c = report.counts()
    assert c["attempted"] == 1
    assert c["rendered"] == 0 and c["gate_passed"] == 0


def test_record_render_tolerates_a_missing_entry():
    """Reporting must never be what takes a batch down."""
    record_render(None, "/out/v.mp4", gate="PASS")   # must not raise

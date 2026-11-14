#!/usr/bin/env python3
"""Every run must leave a file behind, and the row must say which file.

    python3 -m pytest tests/test_run_log.py

Step 0's logging.basicConfig installs a StreamHandler on stderr. No
FileHandler has ever existed in this repo, so every render log went to the
console that launched the process and nowhere else. On 2026-08-17 that
console belonged to a dashboard started six days earlier, and a failure left
no record at all.

Under 5a this runs unattended twice a day.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import run_log  # noqa: E402


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_log, "LOG_DIR", tmp_path)
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level
    yield tmp_path
    for h in list(root.handlers):
        if h not in before:
            h.close()
            root.removeHandler(h)
    root.setLevel(before_level)


def test_a_run_writes_a_file_that_survives_the_process(log_dir):
    path = run_log.attach_run_log("job-ab4ed292")
    logging.getLogger("video.compositor").info("RENDER DONE 2320 frames")
    run_log.detach_run_log(path)

    assert path.exists(), "no log file was written"
    body = path.read_text()
    assert "RENDER DONE 2320 frames" in body
    assert "video.compositor" in body, "logger name missing; useless at 3am"


def test_records_from_modules_that_never_configure_logging_are_captured(log_dir):
    """The interesting records come from modules that only call getLogger."""
    path = run_log.attach_run_log("job-propagation")
    for name in ("pipeline", "video", "qa_gate", "tts_bilingual"):
        logging.getLogger(name).info("hello from %s", name)
    run_log.detach_run_log(path)

    body = path.read_text()
    for name in ("pipeline", "video", "qa_gate", "tts_bilingual"):
        assert f"hello from {name}" in body, f"{name} did not reach the file"


def test_a_traceback_reaches_the_file(log_dir):
    """The 2026-08-17 complaint was 'there is NO log anywhere'."""
    path = run_log.attach_run_log("job-crash")
    try:
        raise RuntimeError("moov atom not found")
    except RuntimeError:
        logging.getLogger("pipeline").exception("render failed")
    run_log.detach_run_log(path)

    body = path.read_text()
    assert "moov atom not found" in body
    assert "Traceback" in body, "exception logged without its traceback"


def test_attaching_twice_does_not_double_every_line(log_dir):
    """Streamlit re-executes its script on every rerun."""
    p1 = run_log.attach_run_log("job-rerun")
    p2 = run_log.attach_run_log("job-rerun")
    assert p1 == p2
    logging.getLogger("pipeline").info("only once please")
    run_log.detach_run_log(p1)

    assert p1.read_text().count("only once please") == 1


def test_it_rotates_rather_than_growing_without_bound(log_dir, monkeypatch):
    monkeypatch.setattr(run_log, "MAX_BYTES", 2048)
    monkeypatch.setattr(run_log, "BACKUP_COUNT", 2)
    path = run_log.attach_run_log("job-rotate")
    for i in range(400):
        logging.getLogger("video").info("frame %d of a very long render", i)
    run_log.detach_run_log(path)

    rotated = sorted(log_dir.glob("*job-rotate*"))
    assert len(rotated) > 1, "never rotated"
    assert len(rotated) <= 3, f"kept {len(rotated)} files, backupCount is 2"


def test_detach_closes_the_handler(log_dir):
    root = logging.getLogger()
    path = run_log.attach_run_log("job-close")
    assert any(isinstance(h, logging.handlers.RotatingFileHandler)
               for h in root.handlers)
    run_log.detach_run_log(path)
    assert not any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and Path(getattr(h, "baseFilename", "")) == path
        for h in root.handlers), "handler left attached after detach"

#!/usr/bin/env python3
"""Tests cannot write into the real output/ tree. Structurally.

    python3 -m pytest tests/test_output_isolation.py

SECOND LEAK, SAME CLASS. PROMPT 3 stopped tests writing to the ledger. The
same test run had also left output/uploaded/test_a_raising_platform_does_n0/
behind via move_uploaded_artifact, which the ledger guard did not cover.

Every test below aims at the REAL tree deliberately, bypassing the redirect,
and must be refused. Nothing here writes anything that survives.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from output_guard import (REAL_LOGS, REAL_OUTPUT, REAL_QUEUE,  # noqa: E402
                          OutputTreeWriteRefused)

TARGET = REAL_OUTPUT / "uploaded" / "POISON_from_a_test.mp4"


def _clean():
    """Belt and braces: if a guard ever regresses, do not leave the evidence."""
    try:
        if TARGET.exists():
            os.remove(str(TARGET))
    except OSError:
        pass


# ── the proof ────────────────────────────────────────────────────────

def test_writing_a_file_into_the_real_output_tree_is_refused():
    """THE PROOF. A test that aims straight at the real tree and is stopped."""
    try:
        with pytest.raises(OutputTreeWriteRefused) as exc:
            with open(TARGET, "w") as fh:
                fh.write("poison")

        assert "REFUSING" in str(exc.value)
        assert not TARGET.exists()
    finally:
        _clean()


def test_the_historical_leak_is_now_refused(tmp_path, monkeypatch):
    """Replay of the actual escape: move_uploaded_artifact with OUTPUT_DIR
    pointing at the real tree, which is what happened before that fixture
    isolated it."""
    import main

    monkeypatch.setattr(main, "OUTPUT_DIR", REAL_OUTPUT)   # deliberately hostile
    src = tmp_path / "test_fixture_video.mp4"
    src.write_bytes(b"x" * 17)
    strays = REAL_OUTPUT / "uploaded" / tmp_path.name

    try:
        with pytest.raises(OutputTreeWriteRefused):
            main.move_uploaded_artifact(src, {"recorded": ["youtube"]})

        assert src.exists(), "the fixture was moved out of tmp_path"
        assert not (REAL_OUTPUT / "uploaded" / src.name).exists()
    finally:
        # If the guard ever regresses, do not leave behind the very artifact
        # this test exists to prevent.
        if strays.exists():
            shutil.rmtree(str(strays), ignore_errors=True)


# ── each primitive ───────────────────────────────────────────────────

def test_shutil_move_is_refused(tmp_path):
    src = tmp_path / "f.mp4"
    src.write_bytes(b"x")
    try:
        with pytest.raises(OutputTreeWriteRefused):
            shutil.move(str(src), str(TARGET))
        assert not TARGET.exists()
    finally:
        _clean()


def test_shutil_copy_is_refused(tmp_path):
    src = tmp_path / "f.mp4"
    src.write_bytes(b"x")
    try:
        with pytest.raises(OutputTreeWriteRefused):
            shutil.copy(str(src), str(TARGET))
    finally:
        _clean()


def test_path_write_text_is_refused():
    """pathlib does not route through builtins.open, so patching that alone
    would have left this hole."""
    try:
        with pytest.raises(OutputTreeWriteRefused):
            TARGET.write_text("poison")
        assert not TARGET.exists()
    finally:
        _clean()


def test_path_write_bytes_is_refused():
    try:
        with pytest.raises(OutputTreeWriteRefused):
            TARGET.write_bytes(b"poison")
    finally:
        _clean()


def test_os_replace_into_the_tree_is_refused(tmp_path):
    src = tmp_path / "f.mp4"
    src.write_bytes(b"x")
    try:
        with pytest.raises(OutputTreeWriteRefused):
            os.replace(str(src), str(TARGET))
    finally:
        _clean()


def test_deleting_from_the_real_tree_is_refused():
    """A test that removes real corpus artifacts is as damaging as one that
    adds to it — the QA gate baseline is measured against that corpus.

    Aimed at a path that does NOT exist, deliberately. The guard refuses
    before calling through, so this proves the refusal without the test
    itself being destructive if the guard ever regresses — it would raise
    FileNotFoundError instead of deleting anything.
    """
    victim = REAL_OUTPUT / "published" / "NO_SUCH_FILE_from_a_test.jsonl"
    assert not victim.exists()

    with pytest.raises(OutputTreeWriteRefused):
        os.remove(str(victim))


def test_rmtree_on_the_real_tree_is_refused():
    """Same safety construction. Pointing this at output/published for real
    would mean a regressed guard deletes the append-only ledger — the one
    file with no recovery story."""
    victim = REAL_OUTPUT / "published" / "NO_SUCH_DIR_from_a_test"
    assert not victim.exists()

    with pytest.raises(OutputTreeWriteRefused):
        shutil.rmtree(str(victim))

    assert (REAL_OUTPUT / "published").exists()


def test_creating_a_new_directory_is_refused():
    """The leak was a DIRECTORY full of fixture: output/uploaded/test_a.../"""
    d = REAL_OUTPUT / "uploaded" / "POISON_dir_from_a_test"
    try:
        with pytest.raises(OutputTreeWriteRefused):
            d.mkdir(parents=True)
        assert not d.exists()
    finally:
        # Only if the refusal failed: on Python 3.12 Path.rmdir goes through the guarded os.rmdir.
        if d.exists():
            d.rmdir()


# ── what must still work ─────────────────────────────────────────────

def test_reading_real_artifacts_still_works():
    """Many tests read the real corpus — the gate fixtures, audio artifacts,
    rendered mp4s. Blocking reads would gut the suite for no safety gain."""
    some = next(REAL_OUTPUT.rglob("*.json"), None)
    if some is None:
        pytest.skip("no real artifact to read")

    assert some.read_text(encoding="utf-8") is not None
    with open(some) as fh:
        assert fh.read() is not None


def test_a_noop_mkdir_on_an_existing_directory_is_allowed():
    """main.py does exactly this at import. An import is not pollution."""
    (REAL_OUTPUT / "scripts").mkdir(parents=True, exist_ok=True)


def test_writing_in_tmp_path_is_unaffected(tmp_path):
    (tmp_path / "a.txt").write_text("fine")
    with open(tmp_path / "b.txt", "w") as fh:
        fh.write("fine")
    shutil.copy(str(tmp_path / "a.txt"), str(tmp_path / "c.txt"))

    assert (tmp_path / "c.txt").read_text() == "fine"


# ── layer 1 ──────────────────────────────────────────────────────────

def test_the_output_dir_globals_are_redirected():
    """So the common case never even reaches the refusal."""
    import main
    import batch_report as BR
    import publication_log as PL

    for value in (main.OUTPUT_DIR, BR.REPORT_DIR, BR.FAILED_DIR,
                  BR.REJECTED_DIR, PL.LEDGER_PATH, PL.ATTEMPTS_PATH):
        assert REAL_OUTPUT not in Path(value).resolve().parents, (
            f"{value} still points into the real tree")


def test_the_real_output_path_is_captured_before_redirection():
    assert REAL_OUTPUT == (ROOT / "output").resolve()


def test_the_guard_is_inert_outside_pytest():
    """Production must be able to write its own output tree. The guard is
    installed by a fixture, so it simply does not exist outside a test — this
    asserts the mechanism, not an env-var check."""
    import output_guard
    assert not hasattr(output_guard, "_ALWAYS_ON")
    assert callable(output_guard.install)


# ═══════════════════════════════════════════════════════════════════════
# THIRD LEAK, SAME CLASS, ONE DIRECTORY OVER.
#
# The two leaks above were both inside output/, which is regenerable. This
# one was not. `run_pipeline_with_tracking` takes `use_queue=True` by
# default, so every test that called it claimed a real script out of
# content/queue/ and — on success — shelved it into content/queue/_done/.
# The scripts are hand-written by the owner and are the only copy.
#
# Six of them were consumed that way before anyone noticed, and NONE of the
# six produced a video: the recorder fixture in test_dashboard_doors.py
# stubs the renderer, so the run "succeeded", shelved the script, and left
# no artifact. `git status` showed them as deleted and the reason was not
# obvious from the diff.
#
# run_log/ was the same oversight with a smaller blast radius: LOG_DIR is a
# module global pointing at the repo, so a test run opened real rotating log
# files under logs/. 13 of them in one afternoon, 752 accumulated.
# ═══════════════════════════════════════════════════════════════════════

QUEUE_TARGET = REAL_QUEUE / "POISON_from_a_test.json"
LOG_TARGET = REAL_LOGS / "POISON_from_a_test.log"


def _clean_path(target):
    try:
        if target.exists():
            os.remove(str(target))
    except OSError:
        pass


# ── layer 1: the globals a test sees point somewhere disposable ──────

def test_the_queue_a_test_sees_is_not_the_owners_queue():
    """THE PIN. queue_guard reads QUEUE_DIR at call time and shelves through
    DONE_DIR, so redirecting both is what stops the shelve reaching a real
    script — and topic_history must agree with it about where the queue is."""
    import queue_guard
    import topic_history

    for value in (queue_guard.QUEUE_DIR, queue_guard.DONE_DIR,
                  topic_history.QUEUE_DIR):
        resolved = Path(value).resolve()
        assert resolved != REAL_QUEUE and REAL_QUEUE not in resolved.parents, (
            f"{value} still points into the owner's queue")


def test_the_run_log_writes_somewhere_disposable():
    import run_log

    resolved = Path(run_log.LOG_DIR).resolve()
    assert resolved != REAL_LOGS and REAL_LOGS not in resolved.parents, (
        f"{run_log.LOG_DIR} still points at the real logs/")


# ── layer 2: aiming at the real tree anyway is refused ───────────────

def test_shelving_a_script_into_the_real_queue_is_refused(tmp_path):
    """THE ACTUAL ESCAPE. queue_guard.main(["--done", ...]) is a shutil.move
    into content/queue/_done/, and that is how the six were lost."""
    src = tmp_path / "cu001_saludos.json"
    src.write_text("{}", encoding="utf-8")
    target = REAL_QUEUE / "_done" / "POISON_from_a_test.json"
    try:
        with pytest.raises(OutputTreeWriteRefused) as exc:
            shutil.move(str(src), str(target))

        assert "REFUSING" in str(exc.value)
        assert not target.exists()
    finally:
        _clean_path(target)


def test_writing_a_file_into_the_real_queue_is_refused():
    try:
        with pytest.raises(OutputTreeWriteRefused):
            with open(QUEUE_TARGET, "w") as fh:
                fh.write("poison")
        assert not QUEUE_TARGET.exists()
    finally:
        _clean_path(QUEUE_TARGET)


def test_deleting_a_real_queued_script_is_refused():
    """A queued script is the only copy. Removal must be refused as loudly
    as creation — the damage from this class was deletion, not litter."""
    with pytest.raises(OutputTreeWriteRefused):
        os.remove(str(next((REAL_QUEUE / "vocabulary").glob("*.json"))))


def test_writing_a_real_log_file_is_refused():
    try:
        with pytest.raises(OutputTreeWriteRefused):
            with open(LOG_TARGET, "w") as fh:
                fh.write("poison")
        assert not LOG_TARGET.exists()
    finally:
        _clean_path(LOG_TARGET)


def test_reading_the_real_queue_is_still_allowed():
    """Reads stay untouched, as they are for output/. queue_guard's audit
    reads every queued script and several tests read real fixtures; blocking
    that would gut the suite for no safety gain."""
    assert REAL_QUEUE.exists()
    names = sorted(p.name for p in REAL_QUEUE.rglob("*.json"))
    assert names, "the real queue should be readable from a test"


def test_the_real_queue_and_log_paths_are_captured_before_redirection():
    assert REAL_QUEUE == (ROOT / "content" / "queue").resolve()
    assert REAL_LOGS == (ROOT / "logs").resolve()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

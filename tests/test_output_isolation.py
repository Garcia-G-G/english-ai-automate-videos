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

from output_guard import REAL_OUTPUT, OutputTreeWriteRefused  # noqa: E402

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
        try:
            d.rmdir()
        except OSError:
            pass


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

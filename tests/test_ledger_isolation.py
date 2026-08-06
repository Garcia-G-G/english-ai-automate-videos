#!/usr/bin/env python3
"""Tests cannot write to the real publication ledger. Structurally.

    python3 -m pytest tests/test_ledger_isolation.py

An early idempotency test run wrote 13 fixture rows into the real
output/published/attempts.jsonl. Caught and cleaned, ledger untouched — that
time.

The ledger is append-only and records irreversible events: a publication
cannot be un-happened, so a poisoned row cannot be rewritten away, only
appended around. Same category as .tokens/ — no recovery story. So the
protection is structural rather than remembered:

  tests/conftest.py     autouse fixture redirecting both paths to tmp_path
  _refuse_real_path()   a runtime refusal for what a fixture cannot cover
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import publication_log as PL  # noqa: E402


# ── the refusal ──────────────────────────────────────────────────────

def test_writing_to_the_real_ledger_is_refused():
    """THE PROOF. A test that deliberately aims at the real file and is
    stopped — even though it passes the path explicitly, bypassing the
    fixture entirely."""
    assert "PYTEST_CURRENT_TEST" in os.environ

    with pytest.raises(PL.PublicationRecordError) as exc:
        PL.record_publication(
            artifact="POISON", video_path="/x.mp4", platform="youtube",
            upload_id="fake", url=None, published_title="t",
            published_description="d",
            ledger_path=PL._REAL_LEDGER,
        )

    assert "REFUSING" in str(exc.value)
    assert not _has_row("POISON", PL._REAL_LEDGER)


def test_writing_to_the_real_attempts_file_is_refused():
    """The file that actually got polluted."""
    with pytest.raises(PL.PublicationRecordError) as exc:
        PL.record_attempt(artifact="POISON", platform="youtube",
                          status="started",
                          attempts_path=PL._REAL_ATTEMPTS)

    assert "REFUSING" in str(exc.value)
    assert not _has_row("POISON", PL._REAL_ATTEMPTS)


def test_the_refusal_survives_patching_the_global_back():
    """The failure mode a fixture cannot cover: a test that restores the
    module global and then writes with no explicit path."""
    PL.ATTEMPTS_PATH = PL._REAL_ATTEMPTS          # deliberately hostile
    try:
        with pytest.raises(PL.PublicationRecordError):
            PL.record_attempt(artifact="POISON2", platform="youtube",
                              status="started")
    finally:
        pass    # conftest's monkeypatch restores it

    assert not _has_row("POISON2", PL._REAL_ATTEMPTS)


def test_the_refusal_is_keyed_on_the_resolved_path():
    """A relative or dot-laden path pointing at the same file is still it."""
    sneaky = PL._REAL_ATTEMPTS.parent / "." / PL._REAL_ATTEMPTS.name

    with pytest.raises(PL.PublicationRecordError):
        PL.record_attempt(artifact="POISON3", platform="youtube",
                          status="started", attempts_path=sneaky)


# ── the fixture ──────────────────────────────────────────────────────

def test_the_autouse_fixture_redirects_by_default():
    """The common case needs no ceremony: a plain write in a plain test goes
    to tmp_path, so existing tests keep working unchanged."""
    PL.record_attempt(artifact="harmless", platform="youtube",
                      status="started")

    assert PL.ATTEMPTS_PATH.exists()
    assert PL.ATTEMPTS_PATH != PL._REAL_ATTEMPTS
    assert "harmless" in PL.ATTEMPTS_PATH.read_text()


def test_the_fixture_gives_each_test_a_fresh_ledger():
    assert PL.read_attempts() == []
    PL.record_attempt(artifact="x", platform="youtube", status="started")
    assert len(PL.read_attempts()) == 1


def test_the_real_paths_are_captured_before_any_patching():
    """_REAL_* must be the true files, not whatever the fixture set."""
    assert PL._REAL_LEDGER == ROOT / "output" / "published" / "ledger.jsonl"
    assert PL._REAL_ATTEMPTS == ROOT / "output" / "published" / "attempts.jsonl"


# ── production is unaffected ─────────────────────────────────────────

def test_the_refusal_is_inert_outside_pytest(monkeypatch):
    """It must not be reachable in production — the batch has to be able to
    write the real ledger."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    PL._refuse_real_path(PL._REAL_LEDGER)      # must not raise


def _has_row(marker: str, path: Path) -> bool:
    if not Path(path).exists():
        return False
    return marker in Path(path).read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

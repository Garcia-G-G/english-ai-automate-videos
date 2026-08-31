#!/usr/bin/env python3
"""Tests cannot write to the real ledger, or anywhere else in output/.

TWO LEAKS, SAME CLASS. An idempotency test wrote 13 fixture rows into the
real output/published/attempts.jsonl. The same run also left
output/uploaded/test_a_raising_platform_does_n0/ behind, via
move_uploaded_artifact — caught only when a later prompt happened to list the
uploaded tree.

The ledger is append-only and records irreversible events, so a poisoned row
cannot be rewritten away, only appended around. The rest of output/ is
recoverable by deletion, but a stray artifact is still state that the
dashboard lists, the QA gate corpus counts, and the idempotency guard reads.
Neither should depend on a future test author remembering to monkeypatch a
module global.

TWO LAYERS, for both:

  redirect    every module-level output directory points at tmp_path for the
              duration of each test, so the common case needs no ceremony and
              existing tests keep working unchanged.

  refuse      a write that still resolves inside the real tree raises.
              For the ledger that lives in production code
              (publication_log._refuse_real_path), because record_publication
              is a single chokepoint. The output tree has no chokepoint —
              anything can shutil.move into it — so the chokepoint is the
              filesystem API, patched in tests/output_guard.py.

Reads are deliberately untouched: many tests read real artifacts (the gate
corpus, audio fixtures, rendered mp4s), and blocking those would gut the
suite for no safety gain.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from output_guard import install as _install_output_guard  # noqa: E402


def _import_main_once():
    """Import main BEFORE the guard is active.

    main.py creates output/scripts, output/audio and output/video at module
    scope. Those already exist, so the mkdirs are no-ops — but the import has
    to happen outside the guard's window regardless, and doing it here once
    keeps it out of every individual test.
    """
    try:
        import main  # noqa: F401
    except Exception:                                      # noqa: BLE001
        pass


_import_main_once()


@pytest.fixture(autouse=True)
def _isolate_output_tree(tmp_path, monkeypatch):
    """Point every writable output location at this test's tmp_path, then
    refuse anything that still aims at the real tree."""
    out = tmp_path / "_output"
    out.mkdir(exist_ok=True)

    # ── layer 1: redirect ────────────────────────────────────────────
    import publication_log as PL

    ledger_dir = out / "published"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PL, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(PL, "LEDGER_PATH", ledger_dir / "ledger.jsonl")
    monkeypatch.setattr(PL, "ATTEMPTS_PATH", ledger_dir / "attempts.jsonl")

    try:
        import batch_report as BR
        monkeypatch.setattr(BR, "REPORT_DIR", out / "batch_reports")
        monkeypatch.setattr(BR, "FAILED_DIR", out / "failed")
        monkeypatch.setattr(BR, "REJECTED_DIR", out / "rejected")
    except ImportError:
        pass

    if "main" in sys.modules:
        monkeypatch.setattr(sys.modules["main"], "OUTPUT_DIR", out)

    # Admin reload re-executes thumbnail warming, so isolate its cache too.
    import thumbnails
    monkeypatch.setattr(thumbnails, "THUMBS_DIR", out / "thumbs")

    # admin imports streamlit, so it is only redirected if a test already
    # pulled it in — importing it here would cost every test that run.
    admin = sys.modules.get("admin")
    if admin is not None:
        for name, sub in (("OUTPUT_DIR", ""), ("VIDEO_DIR", "video"),
                          ("PENDING_DIR", "pending"),
                          ("APPROVED_DIR", "approved"),
                          ("UPLOADED_DIR", "uploaded"),
                          ("REJECTED_DIR", "rejected")):
            if hasattr(admin, name):
                monkeypatch.setattr(admin, name, out / sub if sub else out)

    # ── layer 2: refuse ──────────────────────────────────────────────
    _install_output_guard(monkeypatch)
    yield

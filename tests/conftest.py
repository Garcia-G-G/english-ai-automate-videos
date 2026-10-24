#!/usr/bin/env python3
"""Tests cannot write to the real ledger, to output/, to the queue, or to logs/.

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

THIRD LEAK, AND THE ONLY ONE THAT LOST SOMETHING. Both layers were scoped to
output/, and the third leak was not in output/. content/queue/ holds scripts
the owner wrote by hand, run_pipeline_with_tracking claims one by default,
and a "successful" stubbed run shelves it into content/queue/_done/. Six
were consumed with no video produced. logs/ went the same way with less at
stake. Both roots are now redirected below and refused in output_guard, and
tests/test_output_isolation.py pins it.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

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

    # The Instagram publisher refreshes and stores its token; never in the real .tokens/.
    import uploader
    monkeypatch.setattr(uploader, "TOKEN_DIR", out / ".tokens")

    # The TTS cache (STEP 76 §4): a test's fake clip must never be served to a real render.
    import tts_cache
    monkeypatch.setattr(tts_cache, "CACHE_DIR", out / "cache" / "tts")
    tts_cache.STATS.update(hits=0, misses=0)

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

    # ── the queue and the logs: same class, outside output/ ──────────
    #
    # THE ONE THAT COST SOMETHING. run_pipeline_with_tracking defaults to
    # use_queue=True, so every test that called it claimed a real
    # hand-written script out of content/queue/ and — on success — shelved
    # it into content/queue/_done/. The recorder fixture in
    # test_dashboard_doors.py stubs the renderer, so the run "succeeded"
    # without producing anything, and six of the owner's scripts were
    # consumed with no video to show for them.
    #
    # An EMPTY queue rather than a copy of the real one, deliberately. No
    # test asserts anything about queue contents, so a copy would only buy
    # back the behaviour that did the damage; an empty queue makes
    # queue_pick return None and the run falls through to the generator the
    # test already stubs. A test that ever needs a queued script should put
    # one here rather than reach for the owner's.
    queue = out / "queue"
    (queue / "_done").mkdir(parents=True, exist_ok=True)

    import queue_guard
    monkeypatch.setattr(queue_guard, "QUEUE_DIR", queue)
    monkeypatch.setattr(queue_guard, "DONE_DIR", queue / "_done")

    import topic_history
    monkeypatch.setattr(topic_history, "QUEUE_DIR", queue)

    # run_log attaches a rotating handler to the ROOT logger at a path under
    # logs/. 13 real log files in one afternoon, 752 accumulated.
    import run_log
    monkeypatch.setattr(run_log, "LOG_DIR", out / "logs")

    # ── layer 2: refuse ──────────────────────────────────────────────
    _install_output_guard(monkeypatch)
    yield


@pytest.fixture
def queue_sandbox(tmp_path):
    """The disposable queue this test's pipeline runs actually read.

    Same path _isolate_output_tree redirects to, named here so a test that
    wants to exercise the queue route can put a script in it instead of
    reaching for content/queue/.
    """
    return tmp_path / "_output" / "queue"

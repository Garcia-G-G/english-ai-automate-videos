#!/usr/bin/env python3
"""Tests can never write to the real publication ledger.

An early idempotency test run wrote 13 fixture rows into the real
output/published/attempts.jsonl. It was caught and cleaned, and the ledger
itself was untouched — that time.

WHY THIS IS NOT "REMEMBER TO PATCH IT". The ledger is append-only and records
irreversible events: a publication cannot be un-happened, so a poisoned row
cannot be rewritten away, only appended around. It is the same category as
.tokens/ — no recovery story. A rule that depends on every future test author
remembering to monkeypatch two module globals is a rule that will be broken.

TWO LAYERS, deliberately:

  this fixture      redirects LEDGER_PATH / ATTEMPTS_PATH to tmp_path for
                    every test, so the common case needs no ceremony and
                    existing tests keep working unchanged.

  the runtime       publication_log._refuse_real_path() raises under pytest
  refusal           if a write still resolves to the real file. That covers
                    what the fixture cannot: a test that re-imports the
                    module, patches it back, computes a path itself, or runs
                    in a subprocess that inherits PYTEST_CURRENT_TEST.

The fixture alone would be defeated by any of those. The refusal alone would
break every existing test. Both.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_publication_ledger(tmp_path, monkeypatch):
    """Point the ledger and the attempt log at this test's tmp_path."""
    import publication_log as PL

    ledger_dir = tmp_path / "_ledger"
    ledger_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(PL, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(PL, "LEDGER_PATH", ledger_dir / "ledger.jsonl")
    monkeypatch.setattr(PL, "ATTEMPTS_PATH", ledger_dir / "attempts.jsonl")
    yield

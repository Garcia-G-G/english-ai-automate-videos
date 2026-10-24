#!/usr/bin/env python3
"""What each video cost, OpenAI vs ElevenLabs.

    python3 -m pytest tests/test_cost_per_video.py

The ledger already had one row per API call with a video_id; what was
missing was the per-video view, and a tracker that kept the script's GPT
cost on the video that paid for it.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cost_tracker as ct  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """An isolated output/costs/ -- nothing here may touch the real one."""
    monkeypatch.setattr(ct, "COSTS_DIR", tmp_path)
    return tmp_path


def _write(path: Path, *rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(vid, api_type, cost, ts="2026-09-22T10:00:00"):
    return {"video_id": vid, "api_type": api_type, "cost_usd": cost,
            "timestamp": ts, "model": "m"}


# ── the tracker ──────────────────────────────────────────────────────

def test_saving_twice_does_not_write_a_call_twice(ledger):
    """admin saves on success AND in its finally; the ledger must count each
    call once."""
    t = ct.CostTracker("v1")
    t.log_elevenlabs_tts(characters=1000)
    t.save()
    t.save()
    t.log_openai_chat(prompt_tokens=1000, completion_tokens=100)
    t.save()

    lines = [l for f in ledger.glob("*.jsonl") for l in f.read_text().splitlines()]
    assert len(lines) == 2


def test_rename_carries_the_calls_already_logged(ledger):
    """THE BUG THIS FIXES. The script is paid for before the video has a
    name; the rename must move that call onto the video, not leave it on a
    job id."""
    t = ct.CostTracker("job_abc")
    t.log_openai_chat(prompt_tokens=2000, completion_tokens=500)
    t.rename("go_viral_20260929_120000")
    t.log_elevenlabs_tts(characters=500)
    t.save()

    rows = ct.per_video_costs(ledger)
    assert [r["video_id"] for r in rows] == ["go_viral_20260929_120000"]
    assert rows[0]["calls"] == 2
    assert rows[0]["openai_usd"] > 0 and rows[0]["elevenlabs_usd"] > 0


def test_summary_splits_by_provider(ledger):
    t = ct.CostTracker("v")
    t.log_openai_chat(prompt_tokens=1_000_000, completion_tokens=0)   # $0.15
    t.log_elevenlabs_tts(characters=1000)                             # $0.22
    s = t.summary()
    assert s["openai_usd"] == pytest.approx(0.15)
    assert s["elevenlabs_usd"] == pytest.approx(0.22)
    assert s["total_usd"] == pytest.approx(0.37)
    assert s["calls"] == 2


@pytest.mark.parametrize("api_type,provider", [
    ("openai_chat", "openai"), ("openai_tts", "openai"),
    ("openai_image", "openai"), ("openai_whisper", "openai"),
    ("dalle3", "openai"), ("elevenlabs_tts", "elevenlabs"),
    ("something_new", "other"),
])
def test_provider_of(api_type, provider):
    """An unknown type is "other", not silently billed to ElevenLabs as the
    old two-way split did."""
    assert ct.provider_of(api_type) == provider


# ── the per-video report ─────────────────────────────────────────────

def test_rows_are_per_video_across_days_and_newest_first(ledger):
    _write(ledger / "costs_2026-09-21.jsonl",
           _row("old", "elevenlabs_tts", 0.10, "2026-09-21T09:00:00"),
           _row("spans", "openai_chat", 0.01, "2026-09-21T23:59:00"))
    _write(ledger / "costs_2026-09-22.jsonl",
           _row("spans", "elevenlabs_tts", 0.05, "2026-09-22T00:01:00"),
           _row("new", "elevenlabs_tts", 0.02, "2026-09-22T12:00:00"))

    rows = ct.per_video_costs(ledger)
    assert [r["video_id"] for r in rows] == ["new", "spans", "old"]
    spans = rows[1]
    assert spans["openai_usd"] == pytest.approx(0.01)
    assert spans["elevenlabs_usd"] == pytest.approx(0.05)
    assert spans["total_usd"] == pytest.approx(0.06)
    assert spans["first_at"] == "2026-09-21T23:59:00"
    assert spans["last_at"] == "2026-09-22T00:01:00"


def test_the_per_video_total_reconciles_with_the_ledger(ledger):
    """Nothing is dropped: session rows are kept in the rows, so the sum of
    rows is the sum of the ledger."""
    _write(ledger / "costs_2026-09-22.jsonl",
           _row("a", "elevenlabs_tts", 0.10),
           _row("session_20260922_1", "openai_chat", 0.03),
           _row("b", "openai_image", 0.05))
    rows = ct.per_video_costs(ledger)
    assert sum(r["total_usd"] for r in rows) == pytest.approx(0.18)


def test_a_bad_line_is_skipped_not_fatal(ledger):
    (ledger / "costs_2026-09-22.jsonl").write_text(
        json.dumps(_row("a", "elevenlabs_tts", 0.1)) + "\n{not json\n\n")
    assert [r["video_id"] for r in ct.per_video_costs(ledger)] == ["a"]


def test_no_ledger_is_an_empty_report(tmp_path):
    assert ct.per_video_costs(tmp_path / "missing") == []
    assert ct.video_cost_stats([])["videos"] == 0


def test_stats_exclude_sessions_and_flag_outliers(ledger):
    _write(ledger / "costs_2026-09-22.jsonl",
           _row("a", "elevenlabs_tts", 0.05),
           _row("b", "elevenlabs_tts", 0.06),
           _row("c", "elevenlabs_tts", 0.07),
           _row("pricey", "elevenlabs_tts", 0.30),
           _row("session_x", "openai_chat", 5.00))
    stats = ct.video_cost_stats(ct.per_video_costs(ledger))
    assert stats["videos"] == 4, "a session is not a video"
    assert stats["median_usd"] == pytest.approx(0.065)
    assert stats["outliers"] == ["pricey"]

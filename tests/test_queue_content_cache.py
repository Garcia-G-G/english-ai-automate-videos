"""The per-script content cache in queue_guard: fast, and never stale.

Regression for 2026-10-13: the dashboard's Generate page took ~15 s to load,
11 of them re-measuring every queued script's text with the real font each
time anything in the queue changed.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import queue_guard  # noqa: E402


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(queue_guard, "CONTENT_CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(queue_guard, "_code_signature", lambda: "sig-1")
    queue_guard._CONTENT_MEMO.update(sig=None, entries=None)

    def fake(data, rel="<script>"):
        calls.append(rel)
        return [f"length: probe {data['n']}"]
    monkeypatch.setattr(queue_guard, "_content_problems", fake)
    yield queue_guard, calls
    queue_guard._CONTENT_MEMO.update(sig=None, entries=None)


def write(path, n):
    path.write_text(json.dumps({"n": n}))


def test_an_unchanged_script_is_judged_once(guard, tmp_path):
    g, calls = guard
    script = tmp_path / "s.json"; write(script, 1)
    assert g._content_problems_cached(script, {"n": 1}) == ["length: probe 1"]
    assert g._content_problems_cached(script, {"n": 1}) == ["length: probe 1"]
    assert len(calls) == 1


def test_the_verdict_survives_a_new_process(guard, tmp_path):
    g, calls = guard
    script = tmp_path / "s.json"; write(script, 1)
    g._content_problems_cached(script, {"n": 1})
    g._CONTENT_MEMO.update(sig=None, entries=None)          # a fresh dashboard
    assert g._content_problems_cached(script, {"n": 1}) == ["length: probe 1"]
    assert len(calls) == 1


def test_an_edited_script_is_judged_again(guard, tmp_path):
    g, calls = guard
    script = tmp_path / "s.json"; write(script, 1)
    g._content_problems_cached(script, {"n": 1})
    write(script, 22)
    os.utime(script, ns=(1, 1))                               # mtime moves for sure
    assert g._content_problems_cached(script, {"n": 22}) == ["length: probe 22"]
    assert len(calls) == 2


def test_a_code_change_rejudges_everything(guard, tmp_path, monkeypatch):
    g, calls = guard
    script = tmp_path / "s.json"; write(script, 1)
    g._content_problems_cached(script, {"n": 1})
    monkeypatch.setattr(g, "_code_signature", lambda: "sig-2")
    g._content_problems_cached(script, {"n": 1})
    assert len(calls) == 2


def test_a_new_topic_file_reaches_a_long_running_process(tmp_path, monkeypatch):
    """A dashboard started before a category existed must still see it."""
    import script_generator
    topics = tmp_path / "topics"; topics.mkdir()
    (topics / "old.json").write_text(json.dumps([{"id": "o1"}]))
    monkeypatch.setattr(queue_guard, "TOPICS_DIR", topics)
    monkeypatch.setattr(script_generator, "list_categories",
                        lambda: sorted(f.stem for f in topics.glob("*.json")))
    monkeypatch.setattr(script_generator, "load_topics",
                        lambda c: json.loads((topics / f"{c}.json").read_text()))
    monkeypatch.setattr(queue_guard, "_REAL_TOPICS", None)
    assert "basic_vocab" not in queue_guard._real_topics()
    (topics / "basic_vocab.json").write_text(json.dumps([{"id": "bv002"}]))
    assert queue_guard._real_topics()["basic_vocab"] == {"bv002"}

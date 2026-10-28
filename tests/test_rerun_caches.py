"""The per-click caches never serve a stale answer.

yaml_cache and topic_history memoise on a file's stat so the dashboard stops
re-parsing on every click (2026-10-13: Generate rerun 0.5-3 s -> 0.07 s). The
only acceptable failure of a cache like that is being slow; these pin that an
edit is seen on the very next call and that callers cannot poison each other.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yaml_cache import load_yaml  # noqa: E402
import topic_history  # noqa: E402


def _bump(path: Path):
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_yaml_edit_is_seen_next_call(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("a: 1\n")
    assert load_yaml(cfg) == {"a": 1}
    cfg.write_text("a: 2\n")          # same size on purpose
    _bump(cfg)
    assert load_yaml(cfg) == {"a": 2}


def test_yaml_callers_get_copies(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("profiles:\n  adults: {voice: x}\n")
    first = load_yaml(cfg)
    first["profiles"]["adults"]["voice"] = "MUTATED"
    assert load_yaml(cfg)["profiles"]["adults"]["voice"] == "x"


def test_usage_counts_sees_a_rewritten_script(tmp_path):
    script = tmp_path / "a.json"
    script.write_text(json.dumps({"_meta": {"category": "social", "topic_id": "so001"}}))
    assert topic_history.usage_counts(tmp_path)[("social", "so001")] == 1
    script.write_text(json.dumps({"_meta": {"category": "social", "topic_id": "so002"}}))
    _bump(script)
    counts = topic_history.usage_counts(tmp_path)
    assert counts[("social", "so002")] == 1 and counts[("social", "so001")] == 0


def test_usage_counts_forgets_a_deleted_script(tmp_path):
    script = tmp_path / "a.json"
    script.write_text(json.dumps({"_meta": {"category": "social", "topic_id": "so001"}}))
    assert sum(topic_history.usage_counts(tmp_path).values()) == 1
    script.unlink()
    assert sum(topic_history.usage_counts(tmp_path).values()) == 0

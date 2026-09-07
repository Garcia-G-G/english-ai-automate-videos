#!/usr/bin/env python3
"""The topic draw is uniform over topics, and it remembers what it made.

    python3 -m pytest tests/test_topic_history.py

TWO DEFECTS, both reported by Garcia as "ya se me han repetido como 4 videos
con el mismo tema", both measured before this file existed:

  720 topics on disk · 160 ever generated · social/so008 eleven times
  a kids_animals topic (5 in its file) drawn 21x more often than a
  phrasal_verbs one (105 in its file)

The second is why the first hurt so much: the biased draw kept returning to the
small categories, and nothing remembered it had been there.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from script_generator import get_random_topic, list_categories, load_topics  # noqa: E402
from topic_history import coverage, partition, usage_counts  # noqa: E402


def _write_script(root: Path, category: str, topic_id: str, name: str):
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(
        {"type": category, "_meta": {"category": category, "topic_id": topic_id}}
    ), encoding="utf-8")


# ── the history ──────────────────────────────────────────────────────

def test_it_counts_every_script_that_names_a_topic(tmp_path):
    _write_script(tmp_path, "social", "so008", "a")
    _write_script(tmp_path, "social", "so008", "b")
    _write_script(tmp_path, "business", "bz022", "c")
    counts = usage_counts(tmp_path)
    assert counts[("social", "so008")] == 2
    assert counts[("business", "bz022")] == 1


def test_a_broken_script_is_skipped_not_fatal(tmp_path):
    """History is an optimisation; a video must not fail over an old file."""
    _write_script(tmp_path, "social", "so008", "good")
    (tmp_path / "social" / "broken.json").write_text("{not json", encoding="utf-8")
    assert usage_counts(tmp_path)[("social", "so008")] == 1


def test_a_script_with_no_topic_id_is_not_counted(tmp_path):
    d = tmp_path / "social"
    d.mkdir(parents=True)
    (d / "x.json").write_text(json.dumps({"_meta": {"category": "social"}}),
                              encoding="utf-8")
    (d / "y.json").write_text(json.dumps(
        {"_meta": {"category": "social", "topic_id": "unknown"}}), encoding="utf-8")
    assert usage_counts(tmp_path) == Counter()


def test_missing_directory_is_empty_not_an_error(tmp_path):
    assert usage_counts(tmp_path / "nope") == Counter()


# ── the partition ────────────────────────────────────────────────────

def test_stale_comes_back_least_used_first():
    """The fallback must never hand back the topic seen eleven times."""
    pool = [("c", {"id": "a"}), ("c", {"id": "b"}), ("c", {"id": "d"})]
    counts = Counter({("c", "a"): 11, ("c", "b"): 1})
    fresh, stale = partition(pool, counts)
    assert [t["id"] for _, t in fresh] == ["d"]
    assert [t["id"] for _, t in stale] == ["b", "a"]


# ── the draw ─────────────────────────────────────────────────────────

def test_the_draw_is_uniform_over_topics_not_over_categories():
    """THE 21x BIAS. Two uniform stages are not one uniform draw.

    random.choice(categories) then random.choice(topics) weights each topic by
    1/len(its category), so a 5-topic file beat a 105-topic file 21 to 1 and
    the 187 topics in phrasal_verbs and idioms were effectively unreachable.
    """
    sizes = {c: len(load_topics(c)) for c in list_categories()}
    small = min(sizes, key=sizes.get)
    large = max(sizes, key=sizes.get)
    assert sizes[large] > sizes[small] * 5, "fixture assumption: files differ in size"

    draws = Counter(get_random_topic(prefer_unused=False)[0] for _ in range(1200))
    # Proportional to file size, within a generous band for sampling noise.
    ratio = draws[large] / max(1, draws[small])
    expected = sizes[large] / sizes[small]
    assert ratio > expected * 0.5, (
        f"{large} ({sizes[large]}) drawn {draws[large]}x vs {small} "
        f"({sizes[small]}) {draws[small]}x — the draw is still category-first")


def test_it_prefers_a_topic_it_has_never_made(monkeypatch):
    """With 560 untouched topics on disk, a fresh draw must never repeat."""
    import topic_history
    used = usage_counts()
    if not used:
        pytest.skip("no generation history on disk to prefer against")
    for _ in range(60):
        category, topic = get_random_topic()
        assert used.get((category, str(topic.get("id"))), 0) == 0


def test_an_unknown_category_list_falls_back_instead_of_failing():
    """The pre-existing contract, kept: a filter that matches nothing widens.

    This is deliberately NOT a raise. type_categories.resolve() is what refuses
    an impossible type/audience pairing, loudly and before this point; by the
    time a list reaches here it has already been validated, and a stale name in
    a profile should not take down a generation run.
    """
    category, topic = get_random_topic(
        allowed_categories=["not_a_category_on_disk"], prefer_unused=False)
    assert category in list_categories()
    assert topic.get("id")


# ── the screen ───────────────────────────────────────────────────────

def test_coverage_reports_what_a_dashboard_needs():
    cov = coverage()
    assert cov["total"] == cov["used"] + cov["unused"]
    assert cov["total"] > 0
    assert {"category", "total", "used", "unused"} <= set(cov["by_category"][0])
    for row in cov["repeats"]:
        assert row["times"] > 1

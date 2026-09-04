#!/usr/bin/env python3
"""The query space cannot quietly collapse to one stem.

    python3 -m pytest tests/test_topic_clips.py

THE DEFECT THESE PIN. F3 generated fourteen background images and eleven
came out looking alike. CATEGORY_SCENES had 11 keys for 20 real categories,
so 9 categories plus every unknown one fell through to a single DEFAULT
stem. Nothing caught it, because the only measurement in the loop was
contrast, and eleven copies of one room score exactly as well as eleven
different rooms.

Doing that again with video would be worse: a repeated clip is recognisable
within a second, where a repeated still can pass as a house style. So the
table is checked against the directory listing rather than against memory,
and an unknown category raises instead of borrowing a neighbour's footage.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import topic_clips as tc  # noqa: E402


# ───────────────────── no catch-all, checked on disk ─────────────────────

def test_every_category_on_disk_has_footage_and_none_is_orphaned():
    """The F3 bug, stated as an assertion. Not `>= some number` — the exact
    key set, so adding content/topics/foo.json fails until foo gets footage."""
    on_disk = set(tc.categories())
    assert on_disk, "content/topics/ is empty — the fixture is wrong, not the code"
    assert set(tc.CATEGORY_FOOTAGE) == on_disk


def test_an_unknown_category_raises_rather_than_borrowing_a_default():
    with pytest.raises(tc.UnknownCategory):
        tc.build_queries("anything", "not_a_category")


@pytest.mark.parametrize("missing", [None, ""])
def test_a_missing_category_is_also_a_refusal(missing):
    """A video with no category is not a video that needs no footage."""
    with pytest.raises(tc.UnknownCategory):
        tc.build_queries("anything", missing)


def test_the_query_space_is_reported_and_is_not_one_stem():
    space = tc.query_space()
    assert space["missing_from_table"] == []
    assert space["orphan_in_table"] == []
    # The number that matters: the SMALLEST category, not the total. A total
    # of 600 would still hide a category with one query in it.
    assert space["per_category"] >= 20
    assert space["total"] == sum(
        len(v) * len(tc.MOTION) for v in tc.CATEGORY_FOOTAGE.values())


def test_every_category_offers_several_subjects():
    """One subject per category means two videos in that category share
    their footage. `social` alone appears six times in the job history."""
    for category, subjects in tc.CATEGORY_FOOTAGE.items():
        assert len(subjects) >= 4, category
        assert len(set(subjects)) == len(subjects), f"{category} repeats a subject"


def test_no_subject_is_shared_between_two_categories():
    """A shared subject is a quieter version of the same failure: two
    categories that look identical without either being empty."""
    seen = {}
    for category, subjects in tc.CATEGORY_FOOTAGE.items():
        for subject in subjects:
            assert subject not in seen, (
                f"{subject!r} appears in both {seen.get(subject)} and {category}")
            seen[subject] = category


# ─────────────────────── the queries for one video ───────────────────────

def test_queries_for_one_video_are_all_distinct():
    """Enforced by construction, not left to chance: the subject walks the
    list from a topic-seeded offset, so a video cannot search twice for the
    same footage and then wonder why its background repeats."""
    for category in tc.CATEGORY_FOOTAGE:
        queries = tc.build_queries("Any Topic At All", category, count=4)
        assert len(set(queries)) == 4, category


def test_two_topics_in_one_category_do_not_get_the_same_footage():
    a = tc.build_queries("At the Airport - Check-in", "travel", count=3)
    b = tc.build_queries("Booking a Hotel Room", "travel", count=3)
    assert a != b
    assert set(a) != set(b)


def test_the_same_topic_reproduces_its_own_queries():
    """Deterministic on the topic, so a re-run reproduces the video rather
    than fetching different footage and making a render bug unrepeatable."""
    first = tc.build_queries("Break the Ice", "idioms", count=3)
    second = tc.build_queries("Break the Ice", "idioms", count=3)
    assert first == second


def test_a_query_names_both_a_subject_and_a_camera_move():
    """The motion axis is what makes a stock search return film rather than
    a slideshow, so it must actually reach the query string."""
    for query in tc.build_queries("At the Airport - Check-in", "travel", count=3):
        assert any(query.startswith(m) for m in tc.MOTION), query
        assert len(query.split()) > 3, query


def test_more_clips_are_requested_than_the_list_can_repeat():
    """count above the list length is clamped, never wrapped into a repeat."""
    longest = max(len(v) for v in tc.CATEGORY_FOOTAGE.values())
    queries = tc.build_queries("Some Topic", "travel", count=longest + 5)
    assert len(set(queries)) == len(queries)


# ────────────────────────── coverage arithmetic ──────────────────────────

@pytest.mark.parametrize("duration,floor", [(0, 3), (15, 3), (38.4, 3), (75, 4), (600, 8)])
def test_clip_count_covers_the_duration_and_stays_bounded(duration, floor):
    count = tc.clips_needed(duration)
    assert tc.MIN_CLIPS <= count <= tc.MAX_CLIPS
    assert count >= floor


def test_clip_count_never_returns_one():
    """One clip is a video file playing behind text, not footage — and it
    makes a single unreadable clip the whole background."""
    assert all(tc.clips_needed(d) >= 2 for d in (0, 1, 5, 12, 30, 90))


# ───────────────────────── fetching, without a network ─────────────────────

def test_fetch_refuses_to_write_outside_an_artifact():
    """Footage belongs to ONE artifact. A global directory is what made the
    Studio path skip the topic tier in the first place."""
    with pytest.raises(ValueError, match="out_dir"):
        tc.fetch_for_topic("Any", "travel", duration=30.0)


def test_search_without_a_key_returns_empty_rather_than_raising(monkeypatch):
    """A background problem must cost a background, never the video."""
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert tc.search("anything") == []


def test_a_cache_slot_is_stable_and_query_specific():
    one = tc._cache_slot("aerial drone shot an airplane flying over a river")
    again = tc._cache_slot("aerial drone shot an airplane flying over a river")
    other = tc._cache_slot("slow motion a kayak paddling across open sea")
    assert one == again
    assert one != other
    assert one.parent == tc.CACHE_DIR


def test_the_cached_file_is_reused_rather_than_downloaded_again(tmp_path, monkeypatch):
    """The point of the cache: a repeated query costs zero requests."""
    query = "aerial drone shot an airplane flying over a river"
    monkeypatch.setattr(tc, "CACHE_DIR", tmp_path / "cache")
    slot = tc._cache_slot(query)
    slot.mkdir(parents=True)
    (slot / "pexels_1.mp4").write_bytes(b"not really an mp4")

    def _explode(*args, **kwargs):
        raise AssertionError("a cached query must not reach the network")

    monkeypatch.setattr(tc, "search", _explode)
    assert tc.fetch_query(query) == slot / "pexels_1.mp4"


def test_a_portrait_file_nearest_1920_is_chosen():
    video = {"video_files": [
        {"link": "a", "width": 640, "height": 1138},
        {"link": "b", "width": 1080, "height": 1920},
        {"link": "c", "width": 2160, "height": 3840},
        {"link": "wide", "width": 1920, "height": 1080},
    ]}
    assert tc._pick_file(video)["link"] == "b"


def test_a_result_with_no_portrait_file_is_skipped():
    assert tc._pick_file({"video_files": [
        {"link": "wide", "width": 1920, "height": 1080},
        {"link": "tiny", "width": 240, "height": 426},
    ]}) is None


def test_the_attribution_line_names_pexels():
    """The license does not require attribution; the API terms ask for a
    visible link. It lives with the code that incurs the obligation."""
    assert "pexels.com" in tc.ATTRIBUTION_LINE.lower()

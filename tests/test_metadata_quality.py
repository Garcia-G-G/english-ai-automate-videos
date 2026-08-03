#!/usr/bin/env python3
"""Metadata quality: hashtag tiers, per-platform counts, no duplication.

    python3 -m pytest tests/test_metadata_quality.py

Numbers are researched, not chosen; see docs/metadata-best-practices.md.
No API calls — generate_metadata and adapt_for_platform are deterministic.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import metadata_generator as MG  # noqa: E402
from uploader import VideoMetadata  # noqa: E402

SCRIPT = {
    "video_title": "¿Qué significa 'fabric' en inglés?",
    "video_description": "Descubre el significado real de esta palabra.",
    "question": "¿Qué significa 'fabric' en inglés?",
    "hashtags": ["#EnglishQuiz", "#AprendeIngles"],
}


# ── the count ────────────────────────────────────────────────────────

def test_pool_has_at_least_the_target_hashtags():
    meta = MG.generate_metadata(SCRIPT, "quiz", "false_friends")

    assert len(meta["hashtags"]) >= MG.HASHTAG_TARGET
    assert MG.HASHTAG_TARGET >= 10, "the brief asked for at least 10"


def test_hashtags_are_unique_case_insensitively():
    """The old builder snapshotted its seen-set once and could emit a tag
    twice when it appeared in two tiers."""
    tags = MG._ensure_hashtags(["#AprendeIngles", "aprendeingles", "#LearnEnglish"],
                               "quiz", "false_friends")
    lowered = [t.lstrip("#").lower() for t in tags]

    assert len(lowered) == len(set(lowered))


def test_every_tag_is_well_formed():
    for tag in MG.generate_metadata(SCRIPT, "quiz")["hashtags"]:
        assert tag.startswith("#")
        assert " " not in tag
        assert len(tag) > 1


def test_the_mix_is_tiered_not_flat():
    """Broad tags must lead — they are what YouTube renders above the title."""
    tags = [t.lower() for t in MG.generate_metadata(SCRIPT, "quiz")["hashtags"]]
    broad = {b.lstrip("#").lower() for b in MG.BROAD_HASHTAGS}

    assert broad & {t.lstrip("#") for t in tags}, "no broad-reach tag present"
    niche = {n.lstrip("#").lower() for n in MG.NICHE_HASHTAGS}
    assert niche & {t.lstrip("#") for t in tags}, "no niche/audience tag present"


# ── per-platform limits ──────────────────────────────────────────────

@pytest.mark.parametrize("platform", ["youtube", "instagram", "tiktok"])
def test_each_platform_gets_its_own_count(platform):
    meta = MG.generate_metadata(SCRIPT, "quiz")
    adapted = MG.adapt_for_platform(meta, platform)

    assert len(adapted["hashtags"]) == MG.PLATFORM_HASHTAGS[platform]


def test_youtube_never_crosses_the_nullification_cliff():
    """Past 15, YouTube discards EVERY hashtag on the video. This is a
    platform rule, not a preference — the cap must hold even if someone
    raises PLATFORM_HASHTAGS."""
    meta = MG.generate_metadata(SCRIPT, "quiz")
    meta["hashtags"] = [f"#tag{i}" for i in range(40)]

    adapted = MG.adapt_for_platform(meta, "youtube")

    assert len(adapted["hashtags"]) <= MG.YOUTUBE_HASHTAG_HARD_CAP
    assert MG.YOUTUBE_HASHTAG_HARD_CAP == 15


def test_youtube_title_carries_shorts_and_no_other_hashtag():
    """Hashtags belong in the description; they eat the keyword space a
    search surface needs. #Shorts is the required exception."""
    adapted = MG.adapt_for_platform(MG.generate_metadata(SCRIPT, "quiz"), "youtube")

    assert "#Shorts" in adapted["title"]
    assert adapted["title"].count("#") == 1


def test_youtube_title_stays_within_the_platform_limit():
    long = dict(SCRIPT, video_title="¿" + "palabra " * 40 + "?")
    adapted = MG.adapt_for_platform(MG.generate_metadata(long, "quiz"), "youtube")

    assert len(adapted["title"]) <= 100


# ── the duplication defect ───────────────────────────────────────────

@pytest.mark.parametrize("platform", ["youtube", "instagram", "tiktok"])
def test_hashtag_block_is_not_published_twice(platform):
    """LIVE DEFECT this fixes: adapt_for_platform appends the tags, and
    VideoMetadata.full_description appended them again, so every published
    video carried its hashtag block twice."""
    meta = MG.generate_metadata(SCRIPT, "quiz")
    adapted = MG.adapt_for_platform(meta, platform)
    body = VideoMetadata(adapted["title"], adapted["description"],
                         adapted["hashtags"]).full_description

    first = adapted["hashtags"][0].lstrip("#")
    assert body.count(first) == 1, f"{platform}: hashtag block duplicated"


def test_the_uploader_does_not_compose_at_all():
    """Ownership: metadata_generator.compose_description composes, the
    uploader transports. A raw description passed to VideoMetadata comes back
    unchanged — the caller is responsible for composing first."""
    body = VideoMetadata("T", "A plain description", ["#Alpha", "#Beta"]).full_description

    assert body == "A plain description"


def test_compose_description_is_the_single_composer():
    body = MG.compose_description("Body text", ["Alpha", "#Beta"])

    assert body == "Body text\n\n#Alpha #Beta"


def test_compose_is_idempotent_as_a_backstop():
    """A future third caller must not be able to reintroduce the duplicate."""
    once = MG.compose_description("Body", ["Alpha", "Beta"])
    twice = MG.compose_description(once, ["Alpha", "Beta"])

    assert once == twice


def test_compose_handles_an_empty_body_and_empty_tags():
    assert MG.compose_description("", ["Alpha"]) == "#Alpha"
    assert MG.compose_description("Body", []) == "Body"


def test_the_operator_path_still_gets_its_hashtags():
    """resolve_upload_metadata composes for the session branch, because the
    operator edits body and hashtags in two separate fields and the uploader
    no longer joins them."""
    import logging
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    sys.path.insert(0, str(ROOT / "src"))
    import admin

    tk, dk, gk = admin.metadata_session_keys("vid")
    state = {tk: "Operator title", dk: "Operator body", gk: "#One #Two"}

    got = admin.resolve_upload_metadata("vid", SCRIPT, "youtube", "quiz", "", state)

    assert got["source"] == "session"
    assert "#One" in got["description"], "operator hashtags were dropped"
    assert got["description"].count("#One") == 1


# ── description shape ────────────────────────────────────────────────

def test_description_leads_with_content_not_hashtags():
    """The first line is the hook on every platform."""
    adapted = MG.adapt_for_platform(MG.generate_metadata(SCRIPT, "quiz"), "youtube")

    assert not adapted["description"].lstrip().startswith("#")


def test_description_stays_within_platform_limits():
    meta = MG.generate_metadata(SCRIPT, "quiz")
    for platform, cap in (("youtube", 5000), ("instagram", 2200), ("tiktok", 2200)):
        assert len(MG.adapt_for_platform(meta, platform)["description"]) <= cap


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

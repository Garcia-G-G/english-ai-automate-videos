#!/usr/bin/env python3
"""Video type and topic category are no longer independent draws.

    python3 -m pytest tests/test_type_categories.py

THE DEFECT THIS PINS. legacy_pipeline's author resolved the video type from
the request or the profile, then called _random_topic() without consulting
it. Nothing constrained which categories a type could draw from, so any
pairing was possible. Measured across 221 rendered artifacts that record
both, 43 (19%) drew a category that did not suit the type.

The pronunciation column was total: 0 of 20 pronunciation videos ever drew
from content/topics/pronunciation.json, a file of 56 minimal pairs and
stress shifts built for exactly that type. It drew "Asking for Help" from
social and "Double negatives (grammatical error)" from spanish_specific —
neither of which is a word anyone can pronounce.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import type_categories as tc  # noqa: E402

KIDS = ["kids_colors", "kids_numbers", "kids_animals"]
TYPES = ["educational", "pronunciation", "vocabulary",
         "true_false", "fill_blank", "quiz"]


# ─────────────────── the mapping is config, not code ───────────────────

def test_the_mapping_lives_in_config_and_not_in_this_module():
    """An editorial judgement that content owners will revise must not
    require a code change — same reason the duration band is config."""
    import inspect
    src = inspect.getsource(tc)
    for category in ("false_friends", "phrasal_verbs", "kids_animals"):
        assert f'"{category}"' not in src and f"'{category}'" not in src


def test_the_picker_does_not_hardcode_a_mapping():
    import inspect

    from studio import legacy_pipeline
    src = inspect.getsource(legacy_pipeline.TopicScriptAuthor.generate)
    assert "type_categories" in src
    assert "pronunciation" not in src.split("_eligible_categories")[-1]


def test_every_type_declares_a_list():
    for t in TYPES:
        assert tc.allowed_for(t), t


def test_every_declared_category_exists_on_disk():
    on_disk = set(tc.known_categories())
    for t in TYPES:
        for c in tc.allowed_for(t):
            assert c in on_disk, f"{t} lists {c}, which has no topic file"


# ──────────────────────── the mapping's substance ────────────────────────

def test_pronunciation_draws_only_from_pronunciation():
    """The one obvious case, and the one that was 100% wrong."""
    assert tc.allowed_for("pronunciation") == ["pronunciation"]


@pytest.mark.parametrize("video_type", ["educational", "quiz"])
def test_no_type_but_pronunciation_may_draw_pronunciation_topics(video_type):
    """A single word chosen for how it SOUNDS is not a lesson these types
    can teach — text karaoke and a silent quiz card cannot convey sound."""
    assert "pronunciation" not in tc.allowed_for(video_type)


def test_vocabulary_excludes_the_pair_and_rule_categories():
    """It needs a SET of terms to fill 10-12 card rows. Pairs belong to
    quiz; grammar rules are not word pairs."""
    allowed = tc.allowed_for("vocabulary")
    for excluded in ("pronunciation", "false_friends", "confusing_words", "grammar"):
        assert excluded not in allowed


def test_fill_blank_excludes_idioms_and_false_friends():
    """Removing one word from an idiom usually destroys it, and for a false
    friend the PAIR is the lesson rather than the slot. Three of the
    measured mismatches were fill_blank drawing idioms."""
    allowed = tc.allowed_for("fill_blank")
    assert "idioms" not in allowed and "false_friends" not in allowed


def test_true_false_keeps_only_categories_with_a_truth_value():
    """'the bill means la cuenta — true' teaches nothing."""
    allowed = tc.allowed_for("true_false")
    assert "false_friends" in allowed and "common_mistakes" in allowed
    for topical in ("travel", "food_restaurant", "business"):
        assert topical not in allowed


# ──────────────── intersection with the audience profile ────────────────

def test_the_profile_axis_is_intersected_not_replaced():
    """The children profile keeps gating kids content; this adds the type
    axis that was missing. Both questions must hold."""
    assert set(tc.resolve("quiz", KIDS)) == set(KIDS)
    assert len(tc.resolve("quiz")) > len(KIDS)


def test_a_profile_with_no_list_means_no_audience_restriction():
    """How the adults profile is configured today."""
    assert tc.resolve("vocabulary", None) == tc.allowed_for("vocabulary")
    assert tc.resolve("vocabulary", []) == tc.allowed_for("vocabulary")


@pytest.mark.parametrize("video_type", ["pronunciation", "true_false"])
def test_an_empty_intersection_raises_rather_than_drawing_at_random(video_type):
    """THE POINT. A fallback to an unconstrained draw is how a
    pronunciation video ended up teaching 'Asking for Help'. An impossible
    combination is a configuration question for a human, and only a loud
    failure asks it.

    These two combinations are genuinely impossible today: there is no kids
    pronunciation file and no kids category with a truth value.
    """
    with pytest.raises(tc.NoEligibleCategory):
        tc.resolve(video_type, KIDS)


def test_the_refusal_names_both_lists_so_it_can_be_acted_on():
    with pytest.raises(tc.NoEligibleCategory) as caught:
        tc.resolve("pronunciation", KIDS)
    message = str(caught.value)
    assert "pronunciation" in message and "kids_animals" in message
    assert "config.yaml" in message


def test_an_undeclared_type_raises_rather_than_permitting_everything():
    """Silently allowing all 20 would reinstate the unconstrained draw."""
    with pytest.raises(tc.NoEligibleCategory):
        tc.allowed_for("banana")
    with pytest.raises(tc.NoEligibleCategory):
        tc.resolve("banana", None)


# ──────────────────── the corpus this was measured on ────────────────────

def test_the_mapping_would_have_caught_the_measured_mismatches():
    """Spot-checks from the 43 real mismatches, so the mapping is pinned to
    the evidence that motivated it rather than to taste."""
    for video_type, category in [
        ("pronunciation", "social"),           # 'Asking for Help'
        ("pronunciation", "cultural"),         # 'Apologies (British ...)'
        ("pronunciation", "spanish_specific"),  # 'Double negatives'
        ("vocabulary", "pronunciation"),       # a word list from one word
        ("fill_blank", "idioms"),
        ("true_false", "business"),
    ]:
        assert category not in tc.allowed_for(video_type), (video_type, category)

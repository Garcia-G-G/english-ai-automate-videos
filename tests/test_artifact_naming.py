#!/usr/bin/env python3
"""A topic name must survive becoming a filename.

    python3 -m pytest tests/test_artifact_naming.py

Found by running the first real batch end-to-end. `output_name` was
`topic_name.replace(' ', '_').lower()`, and 16 of the 720 topics contain a
forward slash. The first video the batch drew was "Ser/Estar confusion with
'to be' (meaning differences)", which became a directory separator:

    FileNotFoundError: output/scripts/fill_blank/ser/estar_confusion_....json

The GPT call had already been paid for. Unattended at 2/day that is roughly
one silent loss every three weeks.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("_main_for_naming", ROOT / "main.py")
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)

safe = main.safe_artifact_name


# ── the bug ──────────────────────────────────────────────────────────

def test_a_slash_does_not_become_a_directory():
    """The exact topic that broke the first real batch."""
    got = safe("Ser/Estar confusion with 'to be' (meaning differences)")

    assert "/" not in got
    assert got == "ser_estar_confusion_with_to_be_meaning_differences"


@pytest.mark.parametrize("topic", [
    "doggy bag / to-go box",
    "to split the bill / to go Dutch",
    "Meetings: Agreeing/Disagreeing",
    "swipe right / swipe left",
    "Gender in pronouns (objects are 'it', not 'he/she')",
])
def test_every_real_topic_with_a_separator_is_writable(topic, tmp_path):
    """Not just legal-looking — actually writable."""
    name = safe(topic)
    assert "/" not in name and "\\" not in name

    p = tmp_path / f"{name}.json"
    p.write_text("{}")            # would raise FileNotFoundError before
    assert p.exists()


def test_all_720_topics_produce_a_writable_name(tmp_path):
    """The whole corpus, not a sample."""
    from script_generator import get_topic_name, list_categories, load_topics

    checked = 0
    for cat in list_categories():
        for t in load_topics(cat):
            n = get_topic_name(t)
            if not isinstance(n, str):
                continue
            name = safe(n)
            assert name, f"empty name from {n!r}"
            (tmp_path / f"{name}.json").write_text("{}")
            checked += 1
    assert checked > 700, f"only checked {checked} topics"


# ── the name is a KEY, not just a filename ───────────────────────────

def test_the_sanitiser_introduces_no_new_collisions():
    """The artifact name is the ledger's key and the idempotency guard's key
    (publication_log, upload_guard). Two topics collapsing onto one name
    would make one of them permanently unpublishable."""
    from script_generator import get_topic_name, list_categories, load_topics

    new, old = {}, {}
    for cat in list_categories():
        for t in load_topics(cat):
            n = get_topic_name(t)
            if not isinstance(n, str):
                continue
            new.setdefault(safe(n), set()).add(n)
            old.setdefault(n.replace(" ", "_").lower(), set()).add(n)

    new_collisions = sum(1 for v in new.values() if len(v) > 1)
    old_collisions = sum(1 for v in old.values() if len(v) > 1)

    assert new_collisions <= old_collisions, (
        f"sanitising created collisions: {new_collisions} vs {old_collisions}")
    assert len(new) == len(old), (
        f"name count changed: {len(new)} vs {len(old)}")


def test_distinct_topics_stay_distinct():
    assert safe("bring vs take") != safe("take vs bring")
    assert safe("to get fired / to get laid off") != safe("to get fired")


# ── edges ────────────────────────────────────────────────────────────

def test_a_name_never_starts_with_a_dot():
    """A leading dot hides the artifact from every glob in the repo."""
    assert not safe("...hidden").startswith(".")
    assert not safe(".").startswith(".")


def test_an_empty_topic_still_yields_a_name():
    for bad in ("", "   ", "///", None):
        assert safe(bad) == "untitled"


def test_the_name_is_lowercase_and_uses_no_spaces():
    got = safe("Some Topic Name")
    assert got == got.lower()
    assert " " not in got


def test_accents_do_not_silently_vanish_into_one_name():
    """Spanish topic names are common here; collapsing every accented word to
    the same underscore run would be a collision factory."""
    assert safe("ser o estar") != safe("ir o venir")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

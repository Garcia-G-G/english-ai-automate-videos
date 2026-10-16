#!/usr/bin/env python3
"""A written blank is a silence, not a deleted word.

    python3 -m pytest tests/test_blank_is_spoken_as_a_pause.py

THE DEFECT. clean_for_tts removed `___` without replacing it, so the
sentence the learner heard was not the sentence on the screen and was not
English:

    screen: The dog wagged ___ tail happily.
    voice : The dog wagged tail happily.

Measured on the queue at the time of the fix: 9 quiz scripts, 25 questions,
7 of them carrying a blank, plus 14 fill_blank scripts through the same
function. Multi-item quizzes raised the count of broken spoken sentences
from 3 to 7, because items 2 and 3 are now spoken as well.

fc702a9 fixed the opposite half -- scripts that read the blank aloud as
"guion bajo". A blank is neither its own name nor nothing.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import clean_for_tts  # noqa: E402

#: Spelled out rather than imported from tts_common. Importing the constant
#: would make this file fail to COLLECT against a tree where the fix is
#: absent or reverted -- and a collection error aborts the entire run, which
#: is the failure mode da82ac6 was written to remove. A pin must go red on
#: its own assertion and leave the other 1600 tests reporting.
BLANK_SPOKEN = "..."


# ── the pin ──────────────────────────────────────────────────────────

def test_a_blank_does_not_vanish_from_the_spoken_sentence():
    """THE ONE THE OWNER HEARD AND REJECTED."""
    spoken = clean_for_tts("I need to ___ a phone call.")

    assert spoken != "I need to a phone call.", (
        "the blank was deleted and the sentence is no longer English")
    assert BLANK_SPOKEN in spoken
    assert spoken == "I need to ... a phone call."


@pytest.mark.parametrize("written,spoken", [
    ("The dog wagged ___ tail happily.", "The dog wagged ... tail happily."),
    ("If I ___ time, I will call you tonight.",
     "If I ... time, I will call you tonight."),
    ("She ___ you if she finds the keys.", "She ... you if she finds the keys."),
    # any length an author types
    ("A __ B", "A ... B"),
    ("A _____ B", "A ... B"),
    # a blank at the end does not become four dots
    ("I need to ___.", "I need to ..."),
])
def test_every_blank_becomes_the_same_audible_pause(written, spoken):
    assert clean_for_tts(written) == spoken


def test_the_words_around_the_blank_are_untouched():
    """The fix must not reflow the sentence -- only the hole changes."""
    spoken = clean_for_tts("If it ___ tomorrow, we'll stay home.")
    assert spoken.startswith("If it ")
    assert spoken.endswith(" tomorrow, we'll stay home.")


def test_a_single_underscore_inside_a_word_still_becomes_a_space():
    """snake_case is a word the narrator should say as two, not a blank."""
    assert clean_for_tts("snake_case stays") == "snake case stays"


def test_text_with_no_blank_is_unchanged():
    assert clean_for_tts("Nada que rellenar aqui.") == "Nada que rellenar aqui."


# ── the queue, as it would actually be spoken ────────────────────────

def test_no_queued_quiz_or_fill_blank_speaks_a_hole():
    """THE CORPUS PIN. Every item finding 3 now speaks, read back.

    A unit test on one string proves the function; this proves the content.
    If a future edit reintroduces the deletion, the failure names the script
    and the sentence rather than an abstract example.
    """
    import json

    offenders = []
    for folder in ("quiz", "fill_blank"):
        for path in sorted((ROOT / "content" / "queue" / folder).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            items = [data] + list((data.get("questions") or [])[1:])
            for index, item in enumerate(items, 1):
                for field in ("question", "sentence"):
                    written = item.get(field)
                    if not isinstance(written, str) or "___" not in written:
                        continue
                    spoken = clean_for_tts(written)
                    if BLANK_SPOKEN not in spoken:
                        offenders.append(f"{path.name} item {index} {field}: {spoken}")

    assert not offenders, (
        "these are spoken with the blank deleted:\n  " + "\n  ".join(offenders))

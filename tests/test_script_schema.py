#!/usr/bin/env python3
"""Unit tests for src/script_schema.py — runnable standalone or with pytest.

    python3 tests/test_script_schema.py

Two jobs:

1. PIN the fixture corpus. The expected pass/fail of all 12 fixtures is
   spelled out below, failures included. These are real historical output, so
   a fixture that fails is information about the corpus, not a broken test —
   but a fixture that *changes* verdict must show up in a test diff.

2. Prove the shape hazards are actually encoded: options dict-vs-list,
   correct letter-vs-bool-vs-word, translation-vs-translations.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from script_schema import (  # noqa: E402
    FillBlankScript,
    QuizScript,
    ScriptValidationError,
    TrueFalseScript,
    check_script,
    validate_script,
)

FIXTURES = ROOT / "tests" / "fixtures" / "scripts"

# ── Pinned corpus verdicts ───────────────────────────────────────────────
# Maps "<type>/<file>" -> the exact field-level failures expected, or [] for
# a fixture that validates clean. Derived by running the schema, then reading
# each failure and confirming it is a genuine defect in the file:
#
#   educational/actually.json     no `type` key at all. Renders today only
#                                 because video/__init__.py:100 defaults to
#                                 "educational" — the exact silent-default
#                                 class of bug this schema exists to stop.
#   educational/fabric_...json    the known-bad schema case from
#                                 tests/fixtures/known_bad/manifest.json:
#                                 no full_script (only `segments`), and no
#                                 `hook` either.
EXPECTED = {
    "educational/actually.json": ["type: Field required"],
    "educational/fabric_20260116_192025.json": [
        "full_script: Field required",
        "hook: Field required",
    ],
    "fill_blank/desert_vs_dessert_20260210_175642.json": [],
    "fill_blank/heads_up_20260210_181915.json": [],
    "pronunciation/asking_for_help_20260207_151200.json": [],
    "quiz/accepting_invitations.json": [],
    "quiz/cool_20260416_084217.json": [],
    "quiz/fabric_20260116_201133.json": [],
    "quiz/lay_vs_lie_20260416_082045.json": [],
    "quiz/scared_stiff_20260416_083126.json": [],
    "true_false/actually.json": [],
    "vocabulary/pull_vs_pool_20260210_183300.json": [],
}


#: `scripts/current/` is the present-tense tier and is tested separately by
#: tests/test_current_fixtures.py. Excluded here on purpose — mixing the two
#: would make a regenerated `current` file look like corpus drift.
NOT_HISTORICAL = {"current"}


def corpus():
    return sorted(p for p in FIXTURES.glob("*/*.json")
                  if p.parent.name not in NOT_HISTORICAL)


def load(rel):
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


def test_corpus_is_fully_pinned():
    found = {f"{p.parent.name}/{p.name}" for p in corpus()}
    assert found == set(EXPECTED), (
        "fixture corpus changed; update EXPECTED deliberately")


@pytest.mark.parametrize("rel", sorted(EXPECTED))
def test_corpus_verdict_is_pinned(rel):
    video_type = rel.split("/")[0]
    _, errors, _ = check_script(load(rel), video_type=video_type, source=rel)
    assert errors == EXPECTED[rel]


# ── Shape hazards ────────────────────────────────────────────────────────

def test_quiz_options_is_a_dict_and_fill_blank_options_is_a_list():
    quiz = load("quiz/fabric_20260116_201133.json")
    fill = load("fill_blank/desert_vs_dessert_20260210_175642.json")
    assert isinstance(validate_script(quiz).options, dict)
    assert isinstance(validate_script(fill).options, list)

    # And the shapes are not interchangeable.
    swapped = dict(quiz, options=["a", "b", "c", "d"])
    with pytest.raises(ScriptValidationError):
        validate_script(swapped)


def test_correct_is_a_letter_a_bool_and_a_word():
    assert validate_script(load("quiz/fabric_20260116_201133.json")).correct == "B"
    assert validate_script(load("true_false/actually.json")).correct is False
    assert validate_script(
        load("fill_blank/desert_vs_dessert_20260210_175642.json")
    ).correct == "desert"


def test_true_false_correct_rejects_a_string():
    """A quoted "false" is truthy in Python and would render as TRUE."""
    data = dict(load("true_false/actually.json"), correct="false")
    with pytest.raises(ScriptValidationError, match="correct"):
        validate_script(data)


def test_quiz_correct_must_be_a_key_of_options():
    data = dict(load("quiz/fabric_20260116_201133.json"), correct="E")
    with pytest.raises(ScriptValidationError, match="correct"):
        validate_script(data)


def test_fill_blank_correct_must_be_one_of_options():
    data = dict(load("fill_blank/desert_vs_dessert_20260210_175642.json"),
                correct="oasis")
    with pytest.raises(ScriptValidationError, match="not one of options"):
        validate_script(data)


def test_fill_blank_sentence_must_carry_the_blank():
    data = dict(load("fill_blank/desert_vs_dessert_20260210_175642.json"),
                sentence="The Sahara is a vast desert")
    with pytest.raises(ScriptValidationError, match="blank marker"):
        validate_script(data)


def test_translation_and_translations_are_different_keys():
    fill = validate_script(
        load("fill_blank/desert_vs_dessert_20260210_175642.json"))
    quiz = validate_script(load("quiz/fabric_20260116_201133.json"))
    assert isinstance(fill.translation, str)
    assert isinstance(quiz.translations, dict)
    assert not hasattr(FillBlankScript, "translations") or \
        "translations" not in FillBlankScript.model_fields
    assert "translation" not in QuizScript.model_fields


# ── The failure this whole step exists to produce ────────────────────────

def test_missing_correct_names_the_field_and_the_file():
    data = load("quiz/fabric_20260116_201133.json")
    del data["correct"]
    with pytest.raises(ScriptValidationError) as exc:
        validate_script(data, source="tests/fixtures/scripts/quiz/x.json")
    msg = str(exc.value)
    assert "quiz" in msg
    assert "correct" in msg
    assert "tests/fixtures/scripts/quiz/x.json" in msg


def test_declared_type_must_match_the_caller_expectation():
    data = load("quiz/fabric_20260116_201133.json")
    with pytest.raises(ScriptValidationError, match="expected 'true_false'"):
        validate_script(data, video_type="true_false")


# ── Dead payload ─────────────────────────────────────────────────────────

def test_dead_arrays_are_optional_and_preserved():
    """questions/statements/sentences are read by nothing (verified by grep
    across src/ and main.py). Optional here, and not stripped."""
    with_q = validate_script(load("quiz/cool_20260416_084217.json"))
    assert with_q.questions is not None and len(with_q.questions) == 3

    without_q = validate_script(load("quiz/fabric_20260116_201133.json"))
    assert without_q.questions is None

    assert TrueFalseScript.model_fields["statements"].default is None
    assert FillBlankScript.model_fields["sentences"].default is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

#!/usr/bin/env python3
"""The narrator's own lines vary, and stay reachable by everything that reads them.

    python3 -m pytest tests/test_narration_phrases.py

THE DEFECT. Three phrases in every quiz were string literals in the
generator -- "Escucha las opciones." / "¡Piensa bien!" / "Correcto. La
respuesta es A, its." Identical in every video ever made, flat, and no
script could change them. Multi-item quizzes turned the answer line into
three identical readings inside one sixty-second video.

WHAT IS EASY TO GET WRONG HERE is not the pool. It is that two other pieces
of machinery match on the words inside these lines -- add_natural_pauses
inserts the pre-reveal beat, and resolve_quiz_timestamps' word-timeline
fallback locates `think` and `answer` -- and a new pool entry whose wording
drifts past either of them fails SILENTLY, in the audio, with nothing red.
That is what most of this file pins.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from narration_phrases import (KEYWORDS, POOLS, REVEAL_CUE,  # noqa: E402
                               pick, topic_id_of)

FIELDS = {"L": "B", "text": "have"}


def _rendered(kind):
    for line in POOLS[kind]:
        yield line.format(**FIELDS)


# ── determinism ──────────────────────────────────────────────────────

def test_the_same_script_says_the_same_thing_every_render():
    """A render is not reproducible if the narration moves underneath it,
    and the owner compares takes of one script."""
    first = [pick("quiz.answer", "gr004", i, **FIELDS) for i in (1, 2, 3)]
    again = [pick("quiz.answer", "gr004", i, **FIELDS) for i in (1, 2, 3)]
    assert first == again


def test_the_choice_survives_a_new_process():
    """md5, NOT hash(). Python salts hash() per process, so hash() would
    have given a different line on every run -- invisible until someone
    compared two renders of the same script."""
    import subprocess

    code = ("import sys; sys.path.insert(0, %r);"
            "from narration_phrases import pick;"
            "print(pick('quiz.answer', 'gr004', 1, L='B', text='have'))"
            % str(ROOT / "src"))
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == pick("quiz.answer", "gr004", 1, **FIELDS)


def test_the_three_items_of_one_video_do_not_repeat():
    """The whole point: the listener hears the answer line three times."""
    for kind in ("quiz.transition", "quiz.think", "quiz.answer"):
        lines = [pick(kind, "gr004", i, **FIELDS) for i in (1, 2, 3)]
        assert len(set(lines)) == 3, f"{kind} repeats within one video: {lines}"


def test_different_scripts_do_not_all_open_the_same_way():
    openers = {pick("quiz.transition", t, 1)
               for t in ("gr004", "cw006", "sl001", "pv033", "id016")}
    assert len(openers) > 1, "every script picked the same line"


def test_an_unknown_kind_raises_instead_of_falling_back():
    """A typo must not silently restore the flat phrase this replaces."""
    with pytest.raises(KeyError):
        pick("quiz.transitoin", "gr004", 1)


# ── the machinery that reads these lines ─────────────────────────────

@pytest.mark.parametrize("kind", [k for k in POOLS if k.endswith(".answer")])
def test_every_answer_line_still_gets_its_pre_reveal_pause(kind):
    """add_natural_pauses inserts the beat by matching REVEAL_CUE. A line
    that drifts past it loses the pause with nothing to notice but the ear."""
    from tts_elevenlabs import add_natural_pauses

    for line in POOLS[kind]:
        rendered = line.format(**FIELDS)
        assert REVEAL_CUE in rendered, (
            f"{rendered!r} cannot receive the pre-reveal pause")
        assert "..." in add_natural_pauses(rendered, "answer")


@pytest.mark.parametrize("kind", [k for k in POOLS
                                  if k.split(".")[1] in KEYWORDS])
def test_every_line_carries_a_word_the_fallback_can_find(kind):
    """resolve_quiz_timestamps locates `think` and `answer` in a word
    timeline when segment_times is absent. A line with none of its kind's
    keywords leaves think_start at 0 and the countdown starts from a guess."""
    wanted = KEYWORDS[kind.split(".")[1]]
    for line in POOLS[kind]:
        words = {w.strip(".,!?¡¿:'\"").lower()
                 for w in line.format(**FIELDS).split()}
        assert words & wanted, (
            f"{line!r} contains none of {sorted(wanted)} — invisible to the "
            "word-timeline fallback")


def test_the_renderer_and_the_pools_share_one_keyword_list():
    """Typed twice, they drift; the accented "piénsalo" is how it would
    have happened first."""
    from video import quiz

    assert quiz._THINK_WORDS is KEYWORDS["think"]
    assert quiz._ANSWER_WORDS is KEYWORDS["answer"]
    assert "piénsalo" in quiz._THINK_WORDS


def test_the_legacy_answer_line_is_paused_exactly_as_before():
    """Stored scripts and re-renders of old artifacts must not shift."""
    from tts_elevenlabs import add_natural_pauses

    assert (add_natural_pauses("Correcto. La respuesta es B, have.", "answer")
            == "Correcto... ... La respuesta es B, have.")


# ── the tags in them ─────────────────────────────────────────────────

def test_every_line_is_tagged_and_every_tag_is_one_the_model_knows():
    from audio_tags import unknown_tags

    for kind, pool in POOLS.items():
        for line in pool:
            rendered = line.format(**FIELDS)
            assert rendered.startswith("["), f"{kind}: {rendered!r} has no tag"
            assert not unknown_tags(rendered), (
                f"{kind}: model would speak this aloud: {rendered!r}")


# ── identity ─────────────────────────────────────────────────────────

def test_the_topic_id_is_what_the_queue_keys_on():
    assert topic_id_of({"_meta": {"topic_id": "gr004"}}) == "gr004"


def test_a_script_without_meta_still_gets_a_stable_identity():
    """Falling back to the question keeps scripts apart; collapsing them to
    "" would give every meta-less script the same narration."""
    a = topic_id_of({"question": "¿Cual es?"})
    b = topic_id_of({"question": "¿Otra pregunta?"})
    assert a and b and a != b

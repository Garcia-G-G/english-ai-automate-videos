"""An audio tag is spoken as delivery and never drawn as text.

The owner asked for narration with emotion; eleven_v3 takes it as inline tags.
The renderer builds its on-screen word list by SPLITTING THE INPUT TEXT rather
than from the API's alignment, so without a filter the tag becomes a word and
gets drawn. These tests fail against the tree before src/audio_tags.py existed.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from audio_tags import TAGS, is_tag, strip_tags, unknown_tags  # noqa: E402


TAGGED = ("[excited] ¡Hola! Hoy vemos algo bueno. "
          "[laughs] Y esto te va a encantar.")


def test_a_tag_is_recognised_and_a_word_is_not():
    assert is_tag("[excited]")
    assert is_tag("[clears throat]")
    assert not is_tag("excited")
    assert not is_tag("¡Hola!")


def test_stripping_leaves_the_sentence_readable():
    assert strip_tags(TAGGED) == "¡Hola! Hoy vemos algo bueno. Y esto te va a encantar."


def test_a_tag_the_model_does_not_know_is_reported():
    # An unknown tag is not ignored by the model -- it is READ ALOUD. So it is
    # a defect at write time, not a nuance.
    assert unknown_tags("[excited] hola") == []
    assert unknown_tags("[emocionado] hola") == ["[emocionado]"]


def test_no_tag_is_ever_drawn_as_a_word():
    """The one that matters: the word list the renderer draws from."""
    from tts_elevenlabs import estimate_word_timestamps

    words, _ = estimate_word_timestamps(TAGGED, duration=8.0)
    drawn = [w["word"] for w in words]

    assert drawn, "the word list should not be empty"
    for token in drawn:
        assert not is_tag(token), f"{token!r} would be drawn on the video"
    assert "[excited]" not in drawn
    assert "[laughs]" not in drawn
    # and the real words survived
    assert any("Hola" in w for w in drawn)
    assert any("encantar" in w for w in drawn)


def test_sentence_boundaries_ignore_tags():
    from video.educational import add_sentence_boundaries
    from tts_elevenlabs import estimate_word_timestamps

    words, _ = estimate_word_timestamps(TAGGED, duration=8.0)
    marked = add_sentence_boundaries(words, TAGGED)
    assert marked, "boundaries should still be assigned"
    assert len({w.get("segment_id") for w in marked}) >= 2, \
        "the tagged text still has more than one sentence"


@pytest.mark.parametrize("tag", sorted(TAGS))
def test_every_declared_tag_is_shaped_like_one(tag):
    assert is_tag(f"[{tag}]")


def test_no_tag_survives_into_the_renderer_input():
    """quiz.py:618 draws data['explanation'] DIRECTLY, never via the word list.

    So the word-builder filter does not protect the structured fields. This is
    the one that would have put "[excited]" on the answer card.
    """
    from video import _strip_audio_tags

    data = _strip_audio_tags({
        "type": "quiz",
        "question": "[curious] ¿Cuál va aquí?",
        "options": {"A": "[excited] its", "B": "it's"},
        "explanation": "[excited] La respuesta es A.",
        "questions": [{"explanation": "[serious] Cuidado con esta."}],
        "full_script": "[warm] Hola.",
    })

    assert data["question"] == "¿Cuál va aquí?"
    assert data["options"]["A"] == "its"
    assert data["explanation"] == "La respuesta es A."
    assert data["questions"][0]["explanation"] == "Cuidado con esta."
    assert data["full_script"] == "Hola."

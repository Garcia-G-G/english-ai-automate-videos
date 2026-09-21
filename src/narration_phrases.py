#!/usr/bin/env python3
"""The lines the narrator says that no script wrote.

    from narration_phrases import pick
    pick("quiz.transition", "gr004", 1)   -> "[curious] Mira bien las opciones."

WHY THIS EXISTS. Three phrases in every quiz were string literals in the
generator: "Escucha las opciones." / "¡Piensa bien!" / "Correcto. La
respuesta es A, its." Identical in every video ever made, flat, and
unreachable by any script. Multi-item quizzes made it three times per video
instead of once -- the listener now hears the same answer line three times
in sixty seconds. fill_blank and true_false carry their own copies of the
same idea.

DETERMINISTIC, NOT RANDOM, and that is the whole design:

  · the same script re-rendered says the SAME thing. A render is not
    reproducible if the narration changes underneath it, and the owner
    compares takes of the same script.
  · the three items of ONE video do not repeat. The offset is the item
    index, so items 1, 2 and 3 of a three-entry pool always differ.
  · md5 of the topic_id, NOT hash(). Python salts hash() per process, so
    hash() would have given a different line on every run -- the exact
    opposite of the first guarantee, and invisible until someone compared
    two renders of one script.

THE TAGS ARE PART OF THE LINE. These go to eleven_v3 through the same path
as the script's own text; ac1faac is what lets them survive, and
_strip_audio_tags keeps them off the screen.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Tuple

#: kind -> the lines that kind can be. Every entry of a pool must be
#: interchangeable: same meaning, same job, different words.
#:
#: `{L}` is the option letter, `{text}` the option's own words.
#:
#: EVERY TAG HERE IS IN audio_tags.TAGS, and that is enforced by a test
#: rather than by care. The lines as first drafted used "[playful]", which
#: is not on the allowlist -- v3 falls back to SPEAKING a tag it does not
#: know, so the narrator would have said the word "playful" out loud in
#: every other quiz. "[cheerful]" carries the same intent and is known.
#: Widening the allowlist instead would have meant trusting an unverified
#: guess about the model, which is the thing the allowlist exists to stop.
POOLS: Dict[str, Tuple[str, ...]] = {
    "quiz.transition": (
        "[curious] Mira bien las opciones.",
        "[cheerful] Ahí van las cuatro.",
        "[curious] Escucha las opciones, que hay trampa.",
    ),
    "quiz.think": (
        "[thoughtful] Piénsalo un segundo.",
        "[cheerful] ¿La tienes? Piensa.",
        "[thoughtful] Tómate tu tiempo y piensa.",
    ),
    # EVERY ANSWER LINE KEEPS "La respuesta es". Two pieces of machinery
    # match on it and both would have failed silently otherwise:
    # add_natural_pauses inserts the pre-reveal "..." by replacing that
    # exact phrase, and resolve_quiz_timestamps' word-timeline fallback
    # looks for "la" followed by "respuesta". The variation lives in the
    # lead-in and the tag, which is where the personality is anyway.
    "quiz.answer": (
        "[excited] ¡Eso es! La respuesta es {L}, {text}.",
        "[cheerful] ¡Correcto! La respuesta es la {L}: {text}.",
        "[excited] ¡Bien! La respuesta buena es la {L}, {text}.",
    ),
    "fill_blank.transition": (
        "[curious] Aquí van las opciones.",
        "[cheerful] Estas son las cuatro.",
        "[curious] Mira las opciones antes de decidir.",
    ),
    "fill_blank.think": (
        "[thoughtful] Piénsalo un segundo.",
        "[cheerful] ¿Ya la tienes? Piensa.",
        "[thoughtful] Tómate tu tiempo y piensa.",
    ),
    # fill_blank names the WORD, not the letter -- its options are numbered
    # and the reveal has always said the missing word itself.
    "fill_blank.answer": (
        "[excited] ¡Eso es! La respuesta es '{text}'.",
        "[cheerful] ¡Correcto! La respuesta correcta es '{text}'.",
        "[excited] ¡Bien! La respuesta buena es '{text}'.",
    ),
    "true_false.think": (
        "[thoughtful] Piénsalo un segundo.",
        "[cheerful] ¿Verdadero o falso? Piensa.",
        "[thoughtful] Tómate tu tiempo y piensa.",
    ),
    "true_false.answer": (
        "[excited] ¡Eso es! La respuesta es {text}.",
        "[cheerful] ¡Correcto! La respuesta era {text}.",
        "[excited] ¡Bien! La respuesta es {text}.",
    ),
}

#: Words the word-timeline fallback looks for when segment_times is missing
#: (video/quiz.py resolve_quiz_timestamps). A pool entry that contains none
#: of its kind's keywords is invisible to that fallback, so
#: test_narration_phrases pins that every entry carries at least one. This
#: is why "Tómate tu tiempo" gained "y piensa" and why every answer line
#: keeps the word "respuesta".
#:
#: ACCENTS COUNT. The fallback lowercases a word and compares it to this
#: set; "piénsalo" and "piensalo" are different strings, and the hardcoded
#: list this replaces carried only the unaccented one. A think line the
#: fallback cannot see leaves think_start at 0 and the countdown starts from
#: a guess.
KEYWORDS: Dict[str, frozenset] = {
    "think": frozenset({"piensa", "piénsalo", "piensalo", "think", "bien"}),
    "answer": frozenset({"respuesta", "answer"}),
}

#: The phrase add_natural_pauses replaces to put a beat before the reveal.
#: Named here so a new answer line cannot silently lose its pause.
REVEAL_CUE = "La respuesta"


def _index(pool_size: int, topic_id: str, item_index: int) -> int:
    """Stable across processes, machines and reruns."""
    digest = hashlib.md5((topic_id or "").encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) + max(0, item_index - 1)) % pool_size


def pick(kind: str, topic_id: str, item_index: int = 1, **fields) -> str:
    """One line from `kind`'s pool, chosen for this script and this item.

    `fields` fills the template ({L}, {text}). A kind with no pool raises --
    a typo must not silently fall back to the flat phrase this module
    exists to replace.
    """
    pool = POOLS.get(kind)
    if not pool:
        raise KeyError(f"no narration pool named {kind!r}")
    line = pool[_index(len(pool), topic_id, item_index)]
    return line.format(**fields) if fields else line


def topic_id_of(script: dict) -> str:
    """The script's stable identity, for choosing its lines.

    `_meta.topic_id` is what the queue and topic_history key on. Falling
    back to the question text keeps the choice stable for a script that has
    no meta rather than collapsing every such script onto one line.
    """
    meta = (script or {}).get("_meta") or {}
    return str(meta.get("topic_id")
               or (script or {}).get("topic_id")
               or (script or {}).get("question")
               or (script or {}).get("statement")
               or (script or {}).get("sentence")
               or "")

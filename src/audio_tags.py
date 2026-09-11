#!/usr/bin/env python3
"""ElevenLabs v3 audio tags — spoken as delivery, never drawn as text.

    from audio_tags import strip_tags, is_tag, TAGS
    strip_tags("[excited] ¡Hola!")   -> "¡Hola!"
    is_tag("[excited]")              -> True

WHY THIS EXISTS. The owner asked for narration with emotion, and eleven_v3
takes it as inline tags: "[excited] ¡Hola!". The model reads the tag as a
DIRECTION and does not speak it.

The renderer does. `tts_elevenlabs._build_words` constructs the on-screen word
list by SPLITTING THE INPUT TEXT -- not from the alignment ElevenLabs returns
-- so every token in the script becomes a word that gets drawn. A tag would
appear on screen as the literal string "[excited]". Nothing in the pipeline
sanitised anything: no re.sub in subtitle_processor, none in karaoke.py, none
anywhere. The only filter that existed was for "..." pause markers, three lines
above where this is now used, which is the proof that the shape of the problem
was already known and simply never extended.

THE TAG STAYS IN THE TEXT SENT TO THE API and is removed from the text that is
DRAWN. Those are two different consumers of the same string, and conflating
them is what would have put a stage direction on screen in every video.

Timing note: a dropped tag keeps its share of the character budget, so the
words around it absorb its time. The timing model here is proportional to
character count rather than real alignment, so this is already an estimate; a
tag that produces audio ([laughs], [sighs]) is covered by leaving its
characters in the accounting.
"""

from __future__ import annotations

import re

#: Tags eleven_v3 recognises. Kept as a set so a typo is a caught error rather
#: than a word spoken aloud in the middle of a lesson -- "[emocionado]" is not
#: a tag, it is a noun the narrator would read out.
TAGS = frozenset({
    # delivery
    "excited", "happy", "sad", "angry", "curious", "sarcastic", "serious",
    "calm", "nervous", "surprised", "whispers", "shouting", "warm",
    "cheerful", "thoughtful", "confused", "hesitant", "reassuring",
    # non-verbal, these produce audio
    "laughs", "chuckles", "sighs", "gasps", "clears throat", "exhales",
    # pacing
    "pause", "short pause", "long pause", "rushed", "drawn out",
})

#: A bracketed token, e.g. "[excited]" or "[clears throat]".
TAG_RE = re.compile(r"\[[a-zA-Z][a-zA-Z ']{0,24}\]")


def is_tag(token: str) -> bool:
    """Whether a whitespace-separated token is an audio tag.

    Used by the word builder, so it is deliberately generous: anything shaped
    like a bracketed direction is kept off the screen, whether or not it is a
    tag this module knows. Drawing "[whatever]" on a video is never right.
    """
    return bool(TAG_RE.fullmatch(token.strip()))


def strip_tags(text: str) -> str:
    """The same text with every tag removed and spacing tidied."""
    if not text or "[" not in text:
        return text
    return re.sub(r"\s{2,}", " ", TAG_RE.sub("", text)).strip()


def unknown_tags(text: str) -> list:
    """Tags in the text that eleven_v3 will not recognise.

    A tag the model does not know is not silently ignored -- it is read as
    text. So an unknown tag is a defect at write time, not a nuance.
    """
    found = []
    for match in TAG_RE.findall(text or ""):
        name = match[1:-1].strip().lower()
        if name not in TAGS:
            found.append(match)
    return found

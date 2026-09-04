"""Which timing artefact each video type must carry. ONE definition.

WHY THIS MODULE EXISTS. The rule below was written twice. qa_gate.py stated
it per type, with its reasoning, and rejected an artifact that lacked the
right one. studio/media_validation.py re-implemented it as "words AND
segments must both be non-empty", for every type — stricter, and with no
notion of type at all. The two disagreed in both directions:

    quiz          words 0..37   segments 0..20      fails on words
    true_false    words 0..24   segments 0..8       fails on words
    vocabulary    words 0..0    segments 7..8       ALWAYS fails on words
    quiz_openai   words 51      segments 0          fails on segments

Nothing could satisfy both, so every type was blocked at production and
`output/artifacts/` stayed empty until 2026-09-02. Loosening the stricter
copy would have left two implementations in place for the next person to
choose wrongly between, so the sets live here and both import them.

WHY A NEW MODULE RATHER THAN AN EXISTING ONE.

  qa_gate.py     is the natural owner by history, but it is a stdlib-only
                 CLI analysis tool. studio/ importing it would point the
                 typed-contracts layer at an ffmpeg-driven script with an
                 argparse main(), which is the wrong direction.
  script_schema  already owns the type vocabulary, but it is pydantic. qa_gate
                 imports nothing outside the stdlib and runs standalone as
                 `python3 src/qa_gate.py`; giving it a pydantic dependency to
                 borrow four frozensets is a bad trade.
  tts_common     is TTS text and timing helpers, and qa_gate does not import
                 it today. Adding the edge to host a constant is arbitrary.

So: stdlib only, no imports, nothing to drag in either direction. Both
qa_gate and studio.media_validation import from here, and neither learns
anything about the other.

THE RULE ITSELF, unchanged from qa_gate's statement of it:

    quiz / true_false / fill_blank / vocabulary  ->  segment_times
    educational / pronunciation                  ->  word timeline
    neither                                      ->  REJECT

A quiz without segment_times has no measured option boundaries and the
renderer falls back to the /4 estimator at video/quiz.py:130 — inventing
timing and presenting it as sound. An educational without a word timeline
has nothing to drive its karaoke. Different types, different requirement;
one global rule is wrong for both, which is exactly what the second
implementation was.
"""

#: Types rendered from a per-segment assembly: the TTS emits one clip per
#: segment and `segment_times` carries the measured boundaries.
V3_TYPES = frozenset({"quiz", "true_false", "fill_blank", "vocabulary"})

#: Types rendered word by word, driven by a Whisper word timeline.
TURBO_TYPES = frozenset({"educational", "pronunciation"})

#: The two halves of the contract, named for what they require.
REQUIRES_SEGMENT_TIMES = V3_TYPES
REQUIRES_WORD_TIMELINE = TURBO_TYPES

#: Every type the contract knows. A type outside this set has no defined
#: timing requirement, and per the rule above that is a REJECT rather than a
#: pass — an unknown type is not a type with no requirements.
KNOWN_TYPES = V3_TYPES | TURBO_TYPES

#: The metadata key each requirement is satisfied by.
SEGMENTS_KEY = "segments"
WORDS_KEY = "words"


class UnknownVideoType(ValueError):
    """A type with no declared timing requirement.

    Raised rather than defaulted. The whole defect this module fixes was a
    validator that applied one rule to types it did not recognise; guessing
    for an unknown type would be the same mistake with a smaller blast
    radius.
    """


def required_timeline(video_type) -> str:
    """Which collection this type must carry: "segments" or "words".

    Raises UnknownVideoType for anything else, including None — a missing
    type is not a type that needs nothing.
    """
    if video_type in REQUIRES_SEGMENT_TIMES:
        return SEGMENTS_KEY
    if video_type in REQUIRES_WORD_TIMELINE:
        return WORDS_KEY
    raise UnknownVideoType(
        f"no timing requirement declared for video type {video_type!r}; "
        f"known types are {', '.join(sorted(KNOWN_TYPES))}"
    )


def describe(video_type) -> str:
    """One line for an error message, so the failure explains the rule."""
    try:
        needs = required_timeline(video_type)
    except UnknownVideoType as exc:
        return str(exc)
    other = WORDS_KEY if needs == SEGMENTS_KEY else SEGMENTS_KEY
    return (f"{video_type} is rendered from {needs}; a non-empty {needs!r} "
            f"is required and {other!r} is optional")

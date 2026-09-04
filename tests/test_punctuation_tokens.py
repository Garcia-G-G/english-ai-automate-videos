#!/usr/bin/env python3
"""A punctuation-only token never reaches the word timeline, or the grouper.

    python3 -m pytest tests/test_punctuation_tokens.py

THE DEFECT. ElevenLabs' character alignment returns punctuation as SEPARATE
tokens with their own start and end — _chars_to_words splits on whitespace,
and "hola , que" really does contain a lone comma. Nothing merged them back,
so a token whose entire content is a mark survived into the word timeline
and was treated as a word:

    , que significa uno.        leading orphan comma
    ' four ' balloons           quote marks floating as words
    a different size? .         a period highlighted by the karaoke

Measured across the corpus: 63 orphan tokens in 10 of 118 sidecars —
'.' 45, ',' 6, '=' 4, "'" 4, '¿' 3, '?' 1.

WHY THE FIX IS IN THE TIMELINE AND NOT IN group_words. An orphan carries its
own SPAN, and spans feed measure_speech_end, the declared-silence envelope
and the QA gate. The C work measured '(noun)' holding 3.07 -> 4.12, a full
second of declared speech for something never said. Fixing the display alone
would have left the timing polluted and the gate still reading a span that
is not speech.

subtitle_processor already knew the marks were not content — line 296 does
`text.lower().strip('.,!?¿¡')` to classify — it just never removed the
token. A '.' left `lower = ''`, and at line 312 `len(last_lower) <= 4` is
true for the empty string, so a period passed the short-connector test and
was pulled into the English phrase. That is `' four ' balloons` exactly.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import (  # noqa: E402
    is_punctuation_token, merge_punctuation_tokens,
)

MARKS = [".", ",", "'", "=", "¿", "?", "!", "¡", '"', "…", "—"]


def w(word, start, end, **extra):
    return {"word": word, "start": start, "end": end, **extra}


# ───────────────────────── recognising a mark ─────────────────────────

@pytest.mark.parametrize("mark", MARKS)
def test_every_mark_seen_in_the_corpus_is_recognised(mark):
    assert is_punctuation_token(mark)


@pytest.mark.parametrize("token", ["hola", "a", "four", "(noun)", "REcord", "1"])
def test_real_content_is_never_treated_as_punctuation(token):
    """'(noun)' contains parentheses but also letters — it is a word with
    marks attached, not a mark."""
    assert not is_punctuation_token(token)


def test_an_empty_token_is_not_punctuation():
    """It is nothing, and merging it into a neighbour would change that
    neighbour's span for no reason."""
    assert not is_punctuation_token("")
    assert not is_punctuation_token("   ")


# ──────────────────── no token dropped, no time lost ────────────────────

def test_a_mark_is_absorbed_into_the_preceding_word():
    merged = merge_punctuation_tokens(
        [w("uno", 0.0, 1.0), w(",", 1.0, 1.4), w("que", 1.5, 2.0)])
    assert [x["word"] for x in merged] == ["uno,", "que"]


def test_the_preceding_word_keeps_its_start_and_takes_the_marks_end():
    """The span is ABSORBED, not deleted. Time the audio really occupies
    must stay covered by the timeline."""
    merged = merge_punctuation_tokens([w("uno", 0.0, 1.0), w(",", 1.0, 1.4)])
    assert merged[0]["start"] == 0.0
    assert merged[0]["end"] == 1.4


def test_a_leading_mark_merges_into_the_following_word():
    """', que significa uno' — there is no preceding word to attach to."""
    merged = merge_punctuation_tokens([w(",", 0.0, 0.3), w("que", 0.4, 1.0)])
    assert [x["word"] for x in merged] == [",que"]
    assert merged[0]["start"] == 0.0 and merged[0]["end"] == 1.0


def test_a_trailing_mark_with_nothing_after_it_is_still_absorbed():
    merged = merge_punctuation_tokens([w("size", 0.0, 1.0), w(".", 1.1, 1.5)])
    assert len(merged) == 1 and merged[0]["end"] == 1.5


def test_no_time_is_lost_anywhere_in_the_timeline():
    words = [w("a", 0.0, 0.5), w(".", 0.5, 0.9), w("b", 1.0, 1.6),
             w("'", 1.6, 1.8), w("c", 1.9, 2.4), w("?", 2.4, 2.9)]
    merged = merge_punctuation_tokens(words)
    assert min(x["start"] for x in merged) == min(x["start"] for x in words)
    assert max(x["end"] for x in merged) == max(x["end"] for x in words)


def test_consecutive_marks_all_land_on_the_same_word():
    merged = merge_punctuation_tokens(
        [w("si", 0.0, 0.4), w("!", 0.4, 0.6), w("!", 0.6, 0.8)])
    assert [x["word"] for x in merged] == ["si!!"]
    assert merged[0]["end"] == 0.8


def test_a_clean_timeline_is_returned_unchanged():
    words = [w("hola", 0.0, 0.4), w("mundo", 0.5, 1.0)]
    assert [x["word"] for x in merge_punctuation_tokens(words)] == ["hola", "mundo"]


def test_other_fields_survive_the_merge():
    """is_english drives the karaoke colour; losing it would repaint the
    line."""
    merged = merge_punctuation_tokens(
        [w("four", 0.0, 0.5, is_english=True), w("'", 0.5, 0.7)])
    assert merged[0]["is_english"] is True


# ─────────────────────── segment boundaries hold ───────────────────────

def test_a_mark_never_attaches_across_a_segment_boundary():
    """A period ending one sentence must not become part of the first word
    of the next — that would declare speech spanning the pause between
    them, which is the timing defect this fix exists to remove."""
    merged = merge_punctuation_tokens([
        w("uno", 0.0, 1.0, segment_id=0),
        w(".", 4.0, 4.3, segment_id=1),
        w("dos", 4.4, 5.0, segment_id=1),
    ])
    assert [x["word"] for x in merged] == ["uno", ".dos"]
    assert merged[0]["end"] == 1.0, "the first segment's span must not stretch"


# ──────────────────── the grouper never sees a mark ────────────────────

def test_a_punctuation_only_token_never_reaches_the_grouper():
    """THE PIN. group_words classifies with `text.lower().strip('.,!?¿¡')`,
    so a '.' becomes '' — and at line 312 `len(last_lower) <= 4` is true for
    the empty string, which is how a period got pulled into an English
    phrase as `' four ' balloons`. With the timeline clean the branch never
    sees one."""
    from animations.subtitle_processor import SubtitleProcessor

    timeline = merge_punctuation_tokens([
        w("Es", 0.0, 0.3), w("de", 0.4, 0.6),
        w("'", 0.6, 0.7), w("four", 0.7, 1.1, is_english=True),
        w("'", 1.1, 1.2), w("balloons", 1.3, 1.9, is_english=True),
        w(".", 1.9, 2.3),
    ])
    assert not any(is_punctuation_token(x["word"]) for x in timeline)

    groups = SubtitleProcessor().group_words(timeline)
    assert groups
    for group in groups:
        for word in group["words"]:
            assert not is_punctuation_token(word["word"]), word
        # and nothing floating in the rendered line either
        for token in group["text"].split():
            assert not is_punctuation_token(token), group["text"]


def test_no_group_begins_with_a_floating_mark():
    from animations.subtitle_processor import SubtitleProcessor

    timeline = merge_punctuation_tokens([
        w("size", 0.0, 0.5), w("?", 0.5, 0.8),
        w(".", 0.9, 1.2), w("Genial", 1.3, 1.9),
    ])
    for group in SubtitleProcessor().group_words(timeline):
        assert group["words"], "an empty group is a slot a mark used to occupy"
        assert not is_punctuation_token(group["words"][0]["word"])
        assert not is_punctuation_token(group["text"].split()[0]), group["text"]


# ──────────────────────── every producer is wired ────────────────────────

@pytest.mark.parametrize("module,marker", [
    ("tts_bilingual", "merge_punctuation_tokens"),
    ("asr_timings", "merge_punctuation_tokens"),
])
def test_the_timeline_producers_all_absorb_marks(module, marker):
    """Fixing one producer would leave the others emitting orphans."""
    source = (ROOT / "src" / f"{module}.py").read_text()
    assert marker in source, module


def test_the_provider_and_whisper_helper_absorb_marks_too():
    assert "merge_punctuation_tokens" in (
        ROOT / "src" / "tts_providers" / "elevenlabs_provider.py").read_text()
    assert "merge_punctuation_tokens" in (
        ROOT / "src" / "tts_openai.py").read_text()


# ═══════════ sentence-final punctuation stays with its own chunk ═══════════
#
# THE SECOND HALF OF THE SAME DEFECT. The orphan-token merge left the
# timeline clean, but four of 92 segments in art_20260903_175853 still
# OPENED with a closing mark, glued to the next word:
#
#     '.Este verbo es muy útil y significa aparecer'
#     ".Por ejemplo, si digo He didn't show up to the meeting"
#     '.Un tip para recordar esto: piensa en una fiesta.'
#     '.Excelente,'
#
# The cause is upstream of the timeline: _policy_segments cuts chunks at the
# boundaries of the English spans inside a sentence, so the Spanish chunk
# after an English term begins at the character right after it — which is
# the full stop that ended that sentence.
#
# Fixed at the CHUNK boundary, not by merging backwards in the timeline: a
# backwards merge there would stretch a word's declared end across the gap
# between two TTS clips and re-create the timing defect the
# declared-silence work removed. Moving a chunk boundary costs nothing,
# because nothing has been synthesised yet.

from tts_segmenter import (  # noqa: E402
    LANGUAGE_POLICIES, _CLOSING_MARKS, segment_text,
)

_SAMPLE = ("Hoy vamos a aprender el phrasal verb 'show up'. Este verbo es "
           "muy útil y significa aparecer. Por ejemplo, si digo "
           "'He didn't show up to the meeting', significa que no apareció. "
           "¿Entiendes? ¡Genial! ¿Qué tal?")
_TERMS = ["show up", "He didn't show up to the meeting"]


def _segments():
    return segment_text(_SAMPLE, _TERMS, "es",
                        language_policy=LANGUAGE_POLICIES["es"])


def test_no_segment_begins_with_a_closing_mark():
    """THE PIN. A chunk must end with its own closing punctuation and must
    not begin with someone else's."""
    for seg in _segments():
        assert seg["text"], seg
        assert seg["text"][0] not in _CLOSING_MARKS, seg["text"]


def test_the_opening_spanish_marks_are_never_reclaimed():
    """¿ and ¡ OPEN their clause. A fix that ate them would be worse than
    the bug it fixes."""
    assert "¿" not in _CLOSING_MARKS and "¡" not in _CLOSING_MARKS
    joined = " ".join(s["text"] for s in _segments())
    assert "¿Entiendes?" in joined
    assert "¡Genial!" in joined
    assert "¿Qué tal?" in joined


def test_the_closing_mark_lands_on_the_chunk_it_ends():
    segments = _segments()
    english = [s for s in segments if s["lang"] != "es"]
    assert english, "the sample must produce an English span"
    assert english[0]["text"].endswith("."), english[0]["text"]


def test_a_reclaimed_quote_never_reaches_the_voice():
    """The English spans are matched INSIDE their quotes, so the chunk after
    one starts with the term's closing quote. Reclaiming it must not hand
    the narrator "show up'." to say."""
    for seg in _segments():
        assert "'" not in seg["text"].replace("didn't", ""), seg["text"]


def test_a_real_apostrophe_survives_the_cleanup():
    """don't / Let's / didn't keep theirs — the quote strip only removes
    marks that are not between letters."""
    joined = " ".join(s["text"] for s in _segments())
    assert "didn't" in joined


def test_boundaries_stay_contiguous_and_lossless():
    """Every character of the script still belongs to exactly one chunk, so
    source_start/source_end remain a faithful map back onto it."""
    segments = _segments()
    assert segments[0]["source_start"] == 0
    for previous, following in zip(segments, segments[1:]):
        assert previous["source_end"] == following["source_start"], (
            previous["source_text"], following["source_text"])


def test_a_script_with_no_english_span_is_untouched():
    plain = "Hoy aprendemos algo nuevo. ¿Listo? ¡Vamos!"
    segments = segment_text(plain, [], "es",
                            language_policy=LANGUAGE_POLICIES["es"])
    assert len(segments) == 1
    assert segments[0]["text"] == plain

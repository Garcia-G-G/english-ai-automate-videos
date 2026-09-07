#!/usr/bin/env python3
"""Educational: nothing reaches the watermark, and a card is a whole sentence.

    python3 -m pytest tests/test_educational_floor_and_groups.py

TWO HALVES OF ONE STEP. The grouping cannot ship onto a floor that is wrong,
and the floor cannot be verified without the grouping that stresses it.

§1 THE FLOOR — three defects, and fixing only the clamp leaves the worst.

    card_y = SAFE_AREA_TOP + (safe_h - total_h) // 2 + bounce_offset_y
    card_y = max(SAFE_AREA_TOP, card_y)
    if card_y + total_h > SAFE_AREA_BOTTOM:
        card_y = SAFE_AREA_BOTTOM - total_h

  a. The clamp aimed at SAFE_AREA_BOTTOM (1632) while watermark_top() is
     1559, so a clamped card was placed 73px into the mark. quiz.py:847 and
     true_false.py:601 were fixed for this; educational never was.
  b. THE CLAMP IS NOT THE FIRST THING THAT COLLIDES. Measured against the
     live constants, centring alone put the card on the mark at
     total_h > 1199 and the clamp did not run until 1345 — a 146px band in
     which the card sat on the watermark and the clamp never executed. A
     clamp-only fix leaves that band alive, which is why the test below is
     driven THROUGH it.
  c. bounce_offset_y was added before the clamp, so an animation
     displacement fed the layout budget and moved both thresholds down 60px
     — quiz.py's slide_offset defect in another skin.

§2 GROUPING — max_words_per_group was 8, and it was the primary rule. On the
count_to_five timeline that produced 8 of 26 groups (31%) that either ended
on a comma or cut mid-phrase, including "Empezamos con one," / "que significa
uno." out of one sentence. A group is a declared sentence now.
"""

import itertools
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from animations.subtitle_processor import SubtitleProcessor  # noqa: E402
from tts_common import merge_punctuation_tokens  # noqa: E402
from config.layout import CARD_PADDING, CARD_WIDTH, SAFE_AREA_TOP  # noqa: E402
from video.brand import watermark_top  # noqa: E402
import video.educational as edu  # noqa: E402
import video.utils as vutils  # noqa: E402

SIDECARS = sorted((ROOT / "output/audio/educational").glob("*.json"))


def _code_only(source: str) -> str:
    """Source with comment lines removed.

    These assertions are about what the function DOES. The comments here
    quote the old constants by name to explain what was wrong with them, and
    an assertion that reads them cannot tell an explanation from a
    regression — the first version of this test failed on its own prose.
    """
    return "\n".join(line for line in source.splitlines()
                      if not line.lstrip().startswith("#"))


# ═══════════════════════════ §1 · the floor ═══════════════════════════

def _draw_group(text, t=9.0, translations=None):
    """Render one group and capture every line that reached the canvas."""
    drawn = []
    original = vutils.draw_text_solid

    def spy(draw, line, x, y, f, color, alpha, *args, **kwargs):
        if alpha > 0:
            drawn.append({"text": line, "y": y, "font": f,
                          "bottom": y + vutils.font_line_height(f)})
        return original(draw, line, x, y, f, color, alpha, *args, **kwargs)

    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.18,
              "is_english": False, "segment_id": 0}
             for i, w in enumerate(text.split())]
    group = {"words": words, "text": text, "start": 0.0, "end": 30.0,
             "english": False, "display_end": 30.0, "fade_out": 0.0}

    vutils.draw_text_solid = spy
    try:
        frame = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        draw = ImageDraw.Draw(frame, "RGBA")
        edu._render_group_tiktok(t, group, draw, frame, translations or {})
    finally:
        vutils.draw_text_solid = original
    return drawn


#: Sentence lengths chosen to land ON and INSIDE the 1199-1345 band the old
#: clamp never covered — the band a clamp-only fix leaves broken.
_LENGTHS = [4, 12, 24, 36, 48, 64, 80]


@pytest.mark.parametrize("n_words", _LENGTHS)
@pytest.mark.parametrize("t", [0.05, 0.20, 9.0])   # inside the bounce, and at rest
def test_nothing_educational_draws_reaches_the_watermark(n_words, t):
    """THE PIN, driven through the dead band and through the bounce. The
    bounce matters: it used to be an input to the clamp, so the collision
    started 60px earlier while it ran."""
    floor = watermark_top()
    text = " ".join(["palabra"] * n_words)
    for item in _draw_group(text, t=t):
        assert item["bottom"] <= floor, (
            f"{n_words} words at t={t}: {item['text']!r} ends "
            f"{item['bottom']}, watermark starts {floor}")


def test_the_budget_is_the_room_to_the_mark_not_two_lines():
    """max_h was int(line_height(90) * 2.2) — 242px, two lines — while the
    room between SAFE_AREA_TOP and the mark is 1271px. fit_text_font was
    handed a fifth of the space it had, which is why its overflow path was
    reachable from here and why a sentence could not go on one card."""
    import inspect

    source = _code_only(inspect.getsource(edu._render_group_tiktok))
    assert "* 2.2" not in source
    assert "_card_floor()" in source
    expected = watermark_top() - SAFE_AREA_TOP - CARD_PADDING * 2
    assert expected > 1000, expected


def test_one_function_decides_the_floor():
    """Not three places agreeing — one deciding, the way _text_left_edge
    decides vocabulary's column origin."""
    import inspect

    assert edu._card_floor() == watermark_top()
    source = _code_only(inspect.getsource(edu._render_group_tiktok))
    assert "SAFE_AREA_BOTTOM" not in source, "still measures to the wrong floor"


def test_the_bounce_is_not_an_input_to_the_clamp():
    """It is applied to a settled position and bounded by the floor."""
    import inspect

    source = _code_only(inspect.getsource(edu._render_group_tiktok))
    placement = source.split("card_y = SAFE_AREA_TOP")[1]
    clamp, _, bounce = placement.partition("if bounce_offset_y")
    assert "bounce_offset_y" not in clamp, "bounce still feeds the clamp"
    assert "min(card_y + bounce_offset_y" in bounce


def test_a_card_taller_than_the_whole_band_is_still_clear():
    """The clamp's own case, at the right floor."""
    floor = watermark_top()
    for item in _draw_group(" ".join(["extraordinariamente"] * 60)):
        assert item["bottom"] <= floor


# ═══════════════════════ §2 · a group is a sentence ═══════════════════════

def _timelines():
    found = []
    for path in SIDECARS:
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        words = data.get("words") or []
        # Fed through the punctuation merge, because that is what the
        # pipeline now does before a timeline ever reaches the grouper.
        # Legacy sidecars on disk predate it and still carry lone '.' and
        # ',' tokens; grouping those produces a card whose whole text is a
        # full stop, which is the punctuation defect and not this one.
        words = merge_punctuation_tokens(words)
        if words and any("segment_id" in w for w in words):
            found.append((path.name, words))
    if not found:
        pytest.skip("no educational timeline declares segment_id")
    return found


def _defects(groups):
    comma, mid = [], []
    for group in groups:
        text = group["text"].strip()
        if not text:
            continue
        if text.endswith(","):
            comma.append(text)
        elif not text.endswith((".", "!", "?", "…", ":")):
            mid.append(text)
    return comma, mid


def test_no_card_spans_two_sentences_and_no_word_is_lost():
    """THE PIN, restated for the line ceiling.

    "One card per sentence" was the contract until the ceiling arrived; a
    sentence over four lines is now several cards on purpose. What must
    still hold is the part Garcia actually asked for — a card never mixes
    two sentences, and splitting never drops a word.
    """
    failures = []
    for name, words in _timelines():
        declared = {}
        for sid, run in itertools.groupby(words, key=lambda w: w.get("segment_id")):
            declared.setdefault(sid, []).extend(
                w["word"] for w in run)
        seen = {}
        for group in SubtitleProcessor().group_words(words):
            ids = {w.get("segment_id") for w in group["words"]}
            if len(ids) > 1:
                failures.append(f"{name}: card spans sentences {ids}")
                continue
            seen.setdefault(ids.pop(), []).extend(
                w["word"] for w in group["words"])
        for sid, original in declared.items():
            got = seen.get(sid, [])
            if len(got) != len(original):
                failures.append(
                    f"{name}: sentence {sid} had {len(original)} words, "
                    f"cards carry {len(got)}")
    assert not failures, chr(10).join(failures[:10])


def test_the_fresh_timeline_has_no_comma_endings():
    """The one Garcia photographed. count_to_five is today's output.

    Only the comma rule is asserted: a continuation card ends mid-sentence
    by design now, so "does not end in a full stop" is no longer a defect —
    it is what a split looks like.
    """
    path = ROOT / "output/audio/educational/count_to_five_20260904_121130.json"
    if not path.exists():
        pytest.skip("fresh timeline not present")
    words = merge_punctuation_tokens(json.loads(path.read_text())["words"])
    processor = SubtitleProcessor()
    cards = processor.group_words(words)
    assert not [c["text"] for c in cards if c["text"].strip().endswith(",")]
    assert all(processor._count_lines(c["text"]) <= processor.max_lines
               for c in cards)


def test_a_card_is_a_sentence_or_a_clause_of_one():
    """Never more sentences than cards, and never a card built from two."""
    for name, words in _timelines():
        groups = SubtitleProcessor().group_words(words)
        declared = len({w.get("segment_id") for w in words})
        assert len(groups) >= declared, (
            f"{name}: {len(groups)} cards from {declared} sentences")


def test_the_word_count_is_no_longer_the_primary_rule():
    """An ordinary nine-word sentence must not be cut because nine is more
    than eight."""
    assert SubtitleProcessor().max_words >= 30
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.15,
              "segment_id": 0, "segment_end": i == 8}
             for i, w in enumerate(
                 "Hoy vamos a aprender el phrasal verb show up.".split())]
    groups = SubtitleProcessor().group_words(words)
    assert len(groups) == 1, [g["text"] for g in groups]


def test_an_english_phrase_no_longer_splits_its_sentence():
    """"Empezamos con one," / "que significa uno." came out of ONE sentence
    because the English branch peeled the English word into its own group."""
    words = []
    for i, (w, en) in enumerate([
            ("Empezamos", False), ("con", False), ("one,", True),
            ("que", False), ("significa", False), ("uno.", False)]):
        words.append({"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25,
                      "is_english": en, "segment_id": 0,
                      "segment_end": i == 5})
    groups = SubtitleProcessor().group_words(words)
    assert len(groups) == 1, [g["text"] for g in groups]
    assert groups[0]["english"] is True, "the hero card must still fire"


def test_a_forced_split_lands_on_a_clause_boundary():
    """The ceiling is a last resort, and when it fires the fragment still
    reads as language — never a cut mid-clause."""
    processor = SubtitleProcessor(max_words_per_group=6)
    text = "Por ejemplo, si tienes cinco manzanas, dirías algo muy simple."
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.15,
              "segment_id": 0, "segment_end": i == len(text.split()) - 1}
             for i, w in enumerate(text.split())]
    for group in processor.group_words(words):
        assert not group["text"].strip().endswith(
            ("si", "y", "o", "que", "muy")), group["text"]


def test_a_run_with_no_clause_boundary_is_left_whole_and_reported(caplog):
    """A mid-clause cut is worse than a full card, so the run survives and
    the log says so."""
    import logging

    processor = SubtitleProcessor(max_words_per_group=4)
    words = [{"word": f"palabra{i}", "start": i * 0.2, "end": i * 0.2 + 0.15,
              "segment_id": 0, "segment_end": i == 9} for i in range(10)]
    with caplog.at_level(logging.WARNING):
        groups = processor.group_words(words)
    assert len(groups) == 1
    assert "no clause boundary" in caplog.text


def test_legacy_timelines_keep_the_old_behaviour():
    """Sidecars with no segment_id — 23 of 51 — must not have sentence
    boundaries invented for them."""
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.15}
             for i, w in enumerate(["palabra"] * 20)]
    assert len(SubtitleProcessor().group_words(words)) >= 1


# ═════════════════════════ the two halves together ═════════════════════════

def test_the_longest_real_sentence_fits_and_clears_the_mark():
    """The frame that closes this: a whole sentence from the corpus, grouped
    as one card, drawn clear of the watermark."""
    longest, source = "", ""
    for name, words in _timelines():
        for _, run in itertools.groupby(words, key=lambda w: w.get("segment_id")):
            text = " ".join(w["word"] for w in run).strip()
            if len(text.split()) > len(longest.split()):
                longest, source = text, name
    assert longest, "no sentence found"
    floor = watermark_top()
    for item in _draw_group(longest):
        assert item["bottom"] <= floor, (
            f"{source}: {len(longest.split())}-word sentence reaches "
            f"{item['bottom']}, watermark starts {floor}")


# ═════════════════ the ceiling is LINES, measured at full size ═════════════════
#
# The word ceiling could not see the real problem. The card holds ten lines at
# 90px, so every sentence up to ten rendered at full size and never appeared in
# a font distribution: 78 declared sentences — 19% of the corpus — were six
# lines or more and shipped untouched, of which only six ever had to shrink.
# And the 40-word ceiling was unreachable, the longest declared sentence being
# 36 words, so _clause_split was built, tested and never executed.

def test_the_ceiling_is_lines_not_words():
    processor = SubtitleProcessor()
    assert processor.max_lines == 4
    # Words and lines do not track each other, which is the whole argument.
    # Measured at this card width: eight short words are one line, and eight
    # long ones are three — a word ceiling cannot tell them apart.
    short = processor._count_lines("uno dos tres y sin fin de mar")
    long_ = processor._count_lines(
        "otorrinolaringologia desafortunadamente extraordinariamente "
        "incomprensiblemente")
    assert long_ > short


def test_lines_are_counted_at_full_size_not_after_the_fit():
    """THE TRAP. A long sentence that shrinks to 80px fits more lines into
    the same card, so measuring after the fit would loosen the ceiling
    exactly where the text is longest — the gate would relax on the
    sentences it exists to catch."""
    import inspect

    source = _code_only(inspect.getsource(SubtitleProcessor._count_lines))
    assert "SIZE_MAIN_SPANISH" in source
    assert "fit_text_font" not in source


def test_no_card_exceeds_the_line_ceiling_unless_it_cannot_be_split():
    """Every over-budget card must be one with no clause boundary at all —
    never one the splitter simply gave up on."""
    processor = SubtitleProcessor()
    unsplittable = 0
    for _, words in _timelines():
        for group in processor.group_words(words):
            text = group["text"].strip()
            if not text or processor._count_lines(text) <= processor.max_lines:
                continue
            cut, _ = processor._best_split([{"word": w} for w in text.split()])
            assert cut is None, (
                f"card of {processor._count_lines(text)} lines was left "
                f"over budget while a boundary existed: {text[:60]!r}")
            unsplittable += 1
    assert unsplittable < 40, unsplittable


def test_no_card_ends_on_a_comma_anywhere_in_the_corpus():
    """Garcia: "hay una coma cerrando una oración, eso debería ser un
    punto". Includes the cards whose DECLARED sentence ends on a comma —
    a card is a card whether the break was ours or the segmenter's."""
    offenders = []
    for name, words in _timelines():
        for group in SubtitleProcessor().group_words(words):
            if group["text"].strip().endswith((",", ";", ":")):
                offenders.append(f"{name}: {group['text'][-40:]!r}")
    assert not offenders, chr(10).join(offenders[:10])


def test_a_conjunction_is_preferred_over_a_later_comma():
    """Scanning for the first boundary of either kind put 50 of 136 cards
    on a comma. A card ending on a whole word before "y" reads as a
    continuation; one ending on a comma reads as a cut."""
    processor = SubtitleProcessor()
    words = [{"word": w} for w in
             "uno, dos, tres cuatro cinco seis y siete ocho".split()]
    index, kind = processor._best_split(words)
    assert kind == "before"
    assert words[index]["word"] == "y"


def test_the_split_head_fits_the_budget_when_a_boundary_allows_it():
    """_clause_split takes the LAST boundary, which makes the head as long
    as possible — and a head can be over budget while the tail is under it.
    That left 45 cards above four lines, because the loop re-checked the
    tail it kept and never the head it had emitted."""
    processor = SubtitleProcessor()
    long_sentence = ("Ahora, en un contexto mucho más informal y relajado, "
                     "puedes usar expresiones y frases hechas que suenan "
                     "naturales, porque el registro cambia mucho.")
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.15,
              "segment_id": 0} for i, w in enumerate(long_sentence.split())]
    for run in processor._split_to_line_budget(words):
        text = " ".join(w["word"] for w in run)
        assert processor._count_lines(text) <= processor.max_lines, text


def test_a_long_sentence_becomes_several_cards_not_one_and_a_remainder():
    processor = SubtitleProcessor()
    text = " ".join(["palabra, y otra"] * 12)
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.15,
              "segment_id": 0} for i, w in enumerate(text.split())]
    runs = processor._split_to_line_budget(words)
    assert len(runs) >= 3
    assert sum(len(r) for r in runs) == len(words), "words lost in the split"

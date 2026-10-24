#!/usr/bin/env python3
"""Nothing the pronunciation renderer draws overlaps anything else on screen.

    python3 -m pytest tests/test_pronunciation_stack.py

THE DEFECT. The layout was ten hardcoded Y constants, and the slot they left
the word was smaller than one line of the font it was built for:

    PRON_TITLE_Y = 250, PRON_TRANSLATION_Y = 430   ->  a 180px slot
    _word_font_size buckets on len(word):
        160px (<=8 chars)   ONE line = 194px   ->  250..444   INVADES
        120px (9-12)        ONE line = 146px   ->  250..396   clear
         88px (>=13)        ONE line = 108px   ->  250..358   clear

Not a long word and not a wrapped one: ONE line at the largest bucket
overflowed the slot by exactly 14px, always. That bucket holds 25 of the 56
words in content/topics/pronunciation.json — knight, beach, sheet, think —
the short ones the type exists for. Eight more in the 88px bucket collide by
wrapping. 33 of 56, and the WORST CASE IS THE SHORTEST WORD, which is the
reverse of what a broken frame suggests.

WHY THE TEST DRIVES ALL 56 WORDS. The defect is content-dependent: 23 of the
56 pass today. A single fixture would have been chosen from the passing side
as easily as the failing one.

WHAT IS DELIBERATELY NOT ASSERTED. The four phase windows were traced before
counting, and the mistake block and the phonetic never share the screen at
the same Y — the phonetic sits low while the mistake is up and only moves
after the mistake's alpha reaches zero. An earlier pass reported a 74px
collision between them; that was a false positive from ignoring the phases.
So overlap is asserted WITHIN a phase, never across.
"""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from studio.renderer_presentation import resolve_presentation  # noqa: E402
from video.brand import watermark_top  # noqa: E402
from video.utils import font_line_height  # noqa: E402
import video.pronunciation as pron  # noqa: E402
import video.utils as vutils  # noqa: E402

TOPICS = ROOT / "content/topics/pronunciation.json"
DURATION = 50.0

#: One instant inside each phase, from pronunciation.py's own boundaries:
#: word 0.25, mistake 0.50, phonetic 0.80.
PHASES = {"A": 0.10, "B": 0.35, "C": 0.65, "D": 0.92}


def _words():
    if not TOPICS.exists():
        pytest.skip(f"topic file not present: {TOPICS}")
    return json.loads(TOPICS.read_text())


#: The topic file carries word/phonetic/common_mistake/tip and NO
#: translation — the translation is produced by the generator, and every real
#: pronunciation script on disk has one (measured: 48 characters on the most
#: recent). Building render data straight from the topic file therefore draws
#: no translation at all and hides the very collision under test: the first
#: version of this harness caught 7 overlaps instead of 33 for exactly that
#: reason. A fixed synthetic translation of representative length stands in,
#: and it is stated rather than borrowed from a topic field it does not
#: belong to.
_SYNTHETIC_TRANSLATION = "traducción de ejemplo para medir"


def _data(topic):
    return {
        "type": "pronunciation",
        "word": topic.get("word", ""),
        "phonetic": topic.get("phonetic", ""),
        "common_mistake": topic.get("common_mistake", ""),
        "tip": topic.get("tip", ""),
        "translation": topic.get("translation") or _SYNTHETIC_TRANSLATION,
        "words": [], "segments": [], "duration": DURATION,
    }


def _blocks(topic, t):
    """Every visible block on screen at `t`, as (top, bottom, text, size).

    Captured from draw_text_solid — the real canvas call — and regrouped:
    draw_text_centered emits one call per line at line_height intervals, so
    consecutive calls sharing a font and spaced by exactly that advance are
    one block. Anything alpha<=0 is not on screen and is not recorded.
    """
    drawn = []
    # Patched on utils, not on the pronunciation module: the renderer calls
    # draw_text_centered, which issues the real canvas call from utils' own
    # global. This is still the line that reached the canvas.
    original = vutils.draw_text_solid

    def spy(draw, text, x, y, f, color, alpha, *args, **kwargs):
        if alpha > 0:
            drawn.append({"text": text, "y": y, "font": f, "size": f.size})
        return original(draw, text, x, y, f, color, alpha, *args, **kwargs)

    # The background generator and finalize_frame cost ~0.5s a call and draw
    # nothing this test measures; 56 words x 4 phases of them is minutes of
    # gradient. Stubbed so the LAYOUT code under test runs untouched.
    base, fin = pron.create_base_frame, pron.finalize_frame

    def cheap_base(_t):
        image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        return image, ImageDraw.Draw(image, "RGBA")

    vutils.draw_text_solid = spy
    pron.create_base_frame = cheap_base
    pron.finalize_frame = lambda frame, draw, t, duration, words=None: None
    try:
        pron.create_frame_pronunciation(
            t, _data(topic), DURATION,
            presentation=resolve_presentation("es"),
        )
    finally:
        vutils.draw_text_solid = original
        pron.create_base_frame, pron.finalize_frame = base, fin

    blocks = []
    for item in sorted(drawn, key=lambda i: i["y"]):
        line_h = font_line_height(item["font"])
        if (blocks and blocks[-1]["size"] == item["size"]
                and abs(item["y"] - blocks[-1]["bottom"]) <= 2):
            blocks[-1]["bottom"] = item["y"] + line_h
            blocks[-1]["text"] += " " + item["text"]
        else:
            blocks.append({"top": item["y"], "bottom": item["y"] + line_h,
                           "text": item["text"], "size": item["size"]})
    return blocks


# ─────────────────────── the measurement, not the intent ───────────────────────

def test_no_two_visible_blocks_overlap_in_any_phase():
    """THE PIN. Against the constant layout this fails on 33 of 56 words —
    25 of them in the 160px bucket, every one by exactly 14px."""
    failures = []
    for topic in _words():
        for name, fraction in PHASES.items():
            blocks = _blocks(topic, DURATION * fraction)
            for upper, lower in zip(blocks, blocks[1:]):
                if lower["top"] < upper["bottom"]:
                    failures.append(
                        f"{topic['word']!r} phase {name}: "
                        f"{upper['text'][:22]!r} ends {upper['bottom']} but "
                        f"{lower['text'][:22]!r} starts {lower['top']} "
                        f"(overlap {upper['bottom'] - lower['top']}px)")
    assert not failures, f"{len(failures)} overlaps\n" + "\n".join(failures[:12])


def test_the_shortest_words_are_the_worst_case():
    """Pinned because it is counter-intuitive and a future 'optimisation'
    that buckets on length again would reintroduce exactly this. A one-line
    word at the largest size must fit whatever slot it is given."""
    for topic in _words():
        if len(topic.get("word", "")) <= 8:
            blocks = _blocks(topic, DURATION * PHASES["A"])
            assert blocks, topic["word"]
            word_block = blocks[0]
            assert word_block["bottom"] <= blocks[1]["top"], topic["word"]


def test_nothing_crosses_the_watermark():
    """The floor is watermark_top(), not SAFE_AREA_BOTTOM. It does not fire
    on today's content; it is the guard for the day a phonetic runs three
    lines."""
    floor = watermark_top()
    for topic in _words():
        for name, fraction in PHASES.items():
            for block in _blocks(topic, DURATION * fraction):
                assert block["bottom"] <= floor, (
                    f"{topic['word']!r} phase {name}: {block['text'][:30]!r} "
                    f"ends {block['bottom']}, watermark starts {floor}")


def test_every_phase_draws_something():
    """A layout that fits by drawing nothing is not a fix."""
    for topic in _words()[:8]:
        for name, fraction in PHASES.items():
            assert _blocks(topic, DURATION * fraction), (topic["word"], name)


def test_the_word_is_always_the_topmost_block():
    for topic in _words():
        blocks = _blocks(topic, DURATION * PHASES["A"])
        assert topic["word"].split()[0][:6].lower() in blocks[0]["text"].lower()


# ────────────────────── one element, one position (item 4) ──────────────────────

def test_the_phonetic_has_no_second_hardcoded_position():
    """It had two Y pairs for the same block — 1000/1080 in phase C and
    650/750 in phase D. Under a stack its position follows from what is
    above it and visible, so the two constants collapse into one rule."""
    import inspect

    source = inspect.getsource(pron.create_frame_pronunciation)
    for name in ("PRON_CORRECT_LABEL_Y", "PRON_CORRECT_TEXT_Y",
                 "PRON_CORRECT_FINAL_LABEL_Y", "PRON_CORRECT_FINAL_TEXT_Y",
                 "PRON_TRANSLATION_Y", "PRON_QUESTION_Y",
                 "PRON_INCORRECT_LABEL_Y", "PRON_INCORRECT_TEXT_Y",
                 "PRON_TIP_Y"):
        assert name not in source, f"{name} still places an element directly"


def test_the_word_size_is_fitted_not_bucketed():
    """_word_font_size guessed from len(word), which cannot know the
    rendered height — that is what put 194px in a 180px slot."""
    import inspect

    source = inspect.getsource(pron)
    assert "fit_text_font" in source
    assert "def _word_font_size" not in source


def test_the_stack_floor_is_the_watermark():
    import inspect

    assert "watermark_top" in inspect.getsource(pron)


def test_no_drawn_line_is_wider_than_the_text_column():
    """WIDTH, not just height. fit_text_font's guard tests advance_height
    only and leaves width to line_break, which cannot break a single word
    longer than the column: 'advertisement' at 160px is one unbreakable
    1240px line that passes the height check and is drawn clipped at both
    edges of the frame. Caught in a rendered frame, not by the type checker,
    so it is pinned on drawn pixels."""
    from PIL import Image, ImageDraw
    from video.constants import TEXT_AREA_WIDTH

    max_w = TEXT_AREA_WIDTH - 80
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    offenders = []
    for topic in _words():
        for name, fraction in PHASES.items():
            for block in _blocks(topic, DURATION * fraction):
                pass
    # measured per LINE, so a wrapped block is judged line by line
    original = vutils.draw_text_solid
    seen = []

    def spy(draw, text, x, y, f, color, alpha, *args, **kwargs):
        if alpha > 0:
            seen.append((text, probe.textbbox((0, 0), text, font=f)[2], f.size))
        return original(draw, text, x, y, f, color, alpha, *args, **kwargs)

    for topic in _words():
        seen.clear()
        vutils.draw_text_solid = spy
        base, fin = pron.create_base_frame, pron.finalize_frame
        pron.create_base_frame = lambda _t: (
            lambda im: (im, ImageDraw.Draw(im, "RGBA")))(
                Image.new("RGBA", (1080, 1920), (0, 0, 0, 255)))
        pron.finalize_frame = lambda frame, draw, t, duration, words=None: None
        try:
            for fraction in PHASES.values():
                pron.create_frame_pronunciation(
                    DURATION * fraction, _data(topic), DURATION,
                    presentation=resolve_presentation("es"))
        finally:
            vutils.draw_text_solid = original
            pron.create_base_frame, pron.finalize_frame = base, fin
        for text, width, size in seen:
            if width > max_w:
                offenders.append(
                    f"{topic['word']!r}: {text[:24]!r} at {size}px is "
                    f"{width}px in a {max_w}px column (+{width - max_w})")
    assert not offenders, f"{len(offenders)} too wide" + chr(10) + chr(10).join(offenders[:8])

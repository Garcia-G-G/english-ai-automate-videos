#!/usr/bin/env python3
"""Han text needs a font that has it and a breaker that can break it.

    python3 -m pytest tests/test_cjk_text.py

The Bilibili workspace produces Simplified Chinese copy, and the renderer
stack was built for Spanish. Three separate layers assume Latin, and two of
them are fixed here:

  THE FONT.  assets/fonts/Inter-Bold.ttf has no Han glyphs, so every Chinese
  character resolves to .notdef and renders to a byte-identical blank box.
  That is worse than a missing frame: a wall of identical boxes looks like a
  deliberate style, not a missing font, so it survives review.

  THE BREAKER.  line_break packed by text.split(), and Chinese has no
  spaces. A 28-character sentence came back as ONE line measuring 1680px
  against an 800px box — it would have been drawn straight off both edges of
  a 1080px frame.

The third layer is NOT fixed here and has no test pretending otherwise:
word timing (subtitle_processor, tts_openai) also splits on whitespace, so
Chinese narration still yields one "word" per line. Educational karaoke
therefore remains Spanish-only.

The Spanish path must come through all of this untouched. Paso 6a measured
the layout against line_break's exact output, so the oracle test below
re-implements the ORIGINAL algorithm and asserts the new one still agrees
with it character for character.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.utils import (  # noqa: E402
    MissingCJKFont, cjk_font, font, font_for_text, has_cjk, line_break,
)


def _draw():
    return ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def _width(text, f):
    bbox = _draw().textbbox((0, 0), text, font=f)
    return bbox[2] - bbox[0]


def _bitmap(ch, f):
    mask = f.getmask(ch)
    return (mask.size, bytes(mask))


@pytest.fixture
def han():
    try:
        return cjk_font(60)
    except MissingCJKFont:                                   # pragma: no cover
        pytest.skip("no Han-capable font installed on this machine")


# ─────────────────────────── detection ───────────────────────────

@pytest.mark.parametrize("text", [
    "怎么发音？", "英语微课堂", "这个短语 hang in there 的意思",
    "问题 1", "。", "答案：A",
])
def test_han_text_is_detected(text):
    assert has_cjk(text) is True


@pytest.mark.parametrize("text", [
    "¿Cómo se pronuncia?", "MINI CLASE DE INGLÉS", "hang in there",
    "VERDADERO", "Pregunta 1", "", "1234 !?",
])
def test_latin_text_is_not_mistaken_for_han(text):
    assert has_cjk(text) is False


# ─────────────────────────── the font ───────────────────────────

def test_inter_cannot_draw_han_which_is_why_this_module_exists():
    """The defect, pinned. If Inter ever gains Han glyphs this test fails and
    the fallback can be reconsidered — until then it documents why the
    Bilibili renderer may not simply call font()."""
    inter = font(60)
    assert _bitmap("怎", inter) == _bitmap("么", inter) == _bitmap("英", inter), \
        "expected Inter to render every Han char as the same .notdef box"
    # Latin, by contrast, is genuinely distinct.
    assert _bitmap("C", inter) != _bitmap("o", inter)


def test_the_cjk_face_draws_distinct_glyphs(han):
    """The fix. Three different characters, three different bitmaps."""
    shapes = {_bitmap(ch, han) for ch in "怎么英语课"}
    assert len(shapes) == 5


def test_font_for_text_routes_by_script(han):
    assert font_for_text("¿Cómo se pronuncia?", 60).path == font(60).path
    assert font_for_text("怎么发音？", 60).path == han.path


def test_latin_keeps_inter_because_the_layout_was_measured_against_it():
    """Swapping the face globally would invalidate every Paso 6a budget."""
    assert "Inter" in str(font_for_text("VERDADERO", 48).path)


def test_a_missing_cjk_font_raises_instead_of_falling_back(monkeypatch):
    """Falling back to Inter — or to load_default(), a Latin bitmap face —
    would put the tofu back by another route. Fail closed, the way
    studio.voices does for a workspace with no voice."""
    import video.utils as U
    monkeypatch.setattr(U, "_get_cjk_font_paths", lambda: ["/nope/missing.ttf"])
    monkeypatch.setattr(U, "_cjk_font_paths", None)
    monkeypatch.setattr(U, "_cjk_fonts", {})
    with pytest.raises(MissingCJKFont):
        U.cjk_font(60)


# ─────────────────────────── line breaking ───────────────────────────

def test_han_wraps_inside_the_box(han):
    """The 1680px-on-an-800px-box defect."""
    text = "这个英语单词到底应该怎么发音才是正确的呢我们一起来学习吧"
    assert _width(text, han) > 800, "fixture no longer overflows; widen it"

    lines = line_break(text, han, 800)
    assert len(lines) > 1
    for line in lines:
        assert _width(line, han) <= 800, f"{line!r} overflows the box"
    assert "".join(lines) == text, "characters were lost or reordered"


def test_no_space_is_invented_between_han_characters(han):
    lines = line_break("这个英语单词到底应该怎么发音才是正确的", han, 400)
    assert not any(" " in line for line in lines)


def test_english_inside_chinese_is_never_split(han):
    """The product is Chinese explanation around a real English phrase; the
    English is the thing being taught and may not be broken mid-word."""
    lines = line_break("这个短语 hang in there 的意思是坚持住不要放弃继续努力",
                       han, 700)
    joined = " ".join(lines)
    assert "hang in there" in joined
    for line in lines:
        assert _width(line, han) <= 700


def test_closing_punctuation_never_starts_a_line(han):
    text = "他说这个词很难，但是我们一定可以学会的，对不对？真的没问题。"
    for line in line_break(text, han, 300):
        assert line[0] not in "。，、！？：；）」』"


def test_a_single_character_wider_than_the_box_still_returns(han):
    """Degenerate, but it must terminate rather than loop forever."""
    lines = line_break("英语课堂", han, 5)
    assert lines and "".join(lines) == "英语课堂"


# ─────────────────────── Spanish must not move ───────────────────────

def _original_line_break(text, f, max_w):
    """line_break exactly as it was before CJK support was added."""
    if not text.strip():
        return []
    draw = _draw()
    bbox = draw.textbbox((0, 0), text, font=f)
    if bbox[2] - bbox[0] <= max_w:
        return [text]
    words, lines, current = text.split(), [], []
    for word in words:
        bbox = draw.textbbox((0, 0), " ".join(current + [word]), font=f)
        if bbox[2] - bbox[0] <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


SPANISH_CORPUS = [
    "¿Cómo se pronuncia?", "MINI CLASE DE INGLÉS", "¡INGLÉS PARA PEQUES!",
    "VERDADERO", "FALSO", "Pregunta 1", "¡Piensa bien!", "Respuesta: B",
    "Hang in there significa aguanta, no te rindas todavía",
    "¿Cuál es la diferencia entre continuous y continual en inglés?",
    "Esta regla del inglés te va a volar la cabeza",
    "Incorrecto:", "Correcto:", "ESPAÑOL", "INGLÉS", "", "   ",
    "a", "una palabra muy larga supercalifragilisticoespialidoso final",
]


@pytest.mark.parametrize("text", SPANISH_CORPUS)
@pytest.mark.parametrize("max_w", [200, 480, 800, 1000])
def test_spanish_line_breaking_is_byte_identical_to_before(text, max_w):
    """The regression guard. Paso 6a measured the layout against the old
    output; if this drifts, every text box in every Spanish video moves."""
    f = font(60)
    assert line_break(text, f, max_w) == _original_line_break(text, f, max_w)

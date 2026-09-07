#!/usr/bin/env python3
"""fit_text_font checks BOTH axes, and fill_blank draws the lines it returns.

    python3 -m pytest tests/test_fit_width_axis.py

THE DEFECT IN THE SHARED FUNCTION. The fit loop tested height only:

    box = measure_block(line_break(text, f, max_width), f)
    if max_height is None or box.advance_height <= max_height:
        return box

Width was delegated entirely to line_break, which guarantees the column for
everything it can break — and a single token wider than the column is exactly
what it cannot break, because it has to emit that token whole. Nothing then
tested the result.

Not theoretical: 'advertisement' at 160px is one unbreakable 1240px line. It
cleared a 900px height budget, came back as the chosen size, and drew clipped
at both edges of the frame. That was found in a rendered pronunciation frame,
not by reading the loop.

It was fixed once inside pronunciation._word_size, which was the wrong place:
the trap belongs to the function, and there are nine call sites across six
renderers sitting on it —

    quiz.py:307, 850     true_false.py:342, 604    fill_blank.py:130, 331
    educational.py:211   vocabulary.py:158, 320

Each caller re-deriving the same guard is a habit, not a fix.
"""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.utils import (  # noqa: E402
    fit_text_font, font, font_line_height, line_break,
)


def _widest(box):
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    return max((probe.textbbox((0, 0), l, font=box.font)[2] for l in box.lines),
               default=0)


# ───────────────────────── the width axis ─────────────────────────

@pytest.mark.parametrize("token,column", [
    ("advertisement", 840),          # the real one, from the topic file
    ("Supercalifragilistic", 400),
    ("pronunciación", 300),
    ("aluminium", 200),
])
def test_a_single_token_wider_than_the_column_is_shrunk(token, column):
    """THE PIN. line_break cannot break one token, so the fit must be what
    notices. Against the previous loop this returns max_font every time."""
    box = fit_text_font(token, 160, 24, column)
    assert _widest(box) <= column, (
        f"{token!r} came back at {box.size}px, {_widest(box)}px "
        f"into a {column}px column")


def test_the_width_check_does_not_need_a_height_budget():
    """Every one of the nine call sites that passes no max_height was
    relying on line_break alone. The guard must hold with max_height=None."""
    box = fit_text_font("advertisement", 160, 24, 840, None)
    assert _widest(box) <= 840


def test_a_token_that_cannot_fit_at_any_size_returns_the_floor_and_says_why(caplog):
    """Never truncate, never shrink past min_font: return the floor, log the
    axis and the excess, and let the caller decide."""
    import logging

    with caplog.at_level(logging.WARNING):
        box = fit_text_font("Supercalifragilisticexpialidocious", 60, 40, 300)
    assert box.size == 40
    assert "too WIDE" in caplog.text
    assert "300px" in caplog.text


def test_the_log_names_the_axis_that_failed():
    """'nothing fits' was ambiguous between a block too tall and a token too
    wide, and the two have different answers — a height overflow is a budget
    question, a width overflow is usually one unbreakable word."""
    import inspect

    source = inspect.getsource(fit_text_font)
    assert "too WIDE" in source and "too TALL" in source


def test_text_that_already_fits_is_untouched():
    """The guard must not shrink anything that was fine. Nine call sites
    depend on this and their golden frames pin it."""
    for text, column in [("hola", 840), ("Buen trabajo", 400),
                         ("¿Cómo se pronuncia?", 840)]:
        assert fit_text_font(text, 56, 28, column).size == 56


def test_a_breakable_phrase_still_wraps_rather_than_shrinking():
    """Width pressure must be answered by line_break first and by the size
    only when breaking cannot help."""
    box = fit_text_font("una habilidad realmente notable", 42, 28, 400)
    assert len(box.lines) > 1
    assert _widest(box) <= 400


def test_pronunciation_no_longer_re_derives_the_guard():
    import inspect

    import video.pronunciation as pron
    source = inspect.getsource(pron._word_size)
    assert "for size in range(_WORD_MAX" not in source
    assert "fit_text_font" in source


# ──────────────── fill_blank draws the lines, not the string ────────────────

_OPT_W, _OPT_H = 860, 75
_OPT_COL = _OPT_W - 120


def _options_on_disk():
    found = set()
    for path in (list((ROOT / "output/scripts/fill_blank").glob("*.json"))
                 + list((ROOT / "output/audio/fill_blank").glob("*.json"))):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("type") != "fill_blank":
            continue
        for source in [data] + (data.get("sentences") or []):
            options = source.get("options")
            values = (options.values() if isinstance(options, dict)
                      else (options or []))
            found.update(v.strip() for v in values
                         if isinstance(v, str) and v.strip())
    return sorted(found)


def test_fill_blank_draws_the_lines_the_fit_returned():
    """The vocabulary defect, in its last remaining call site. Captured from
    the canvas, as that test is."""
    import video.fill_blank as fb

    drawn = []
    original = fb.draw_text_solid

    def spy(draw, text, x, y, f, color, alpha, *args, **kwargs):
        if alpha > 0:
            drawn.append({"text": text, "x": x, "font": f})
        return original(draw, text, x, y, f, color, alpha, *args, **kwargs)

    fb.draw_text_solid = spy
    try:
        frame = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        draw = ImageDraw.Draw(frame, "RGBA")
        long_option = "an extraordinarily lengthy option that will not fit"
        # signature: (t, draw, frame, options, correct, show_answer,
        #             options_start, answer_time, reveal_times=None)
        fb._draw_option_cards(
            99.0, draw, frame,
            ["short", long_option, "medio", "otro"],
            "short", True, 0.0, 1.0,
        )
    finally:
        fb.draw_text_solid = original

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for item in drawn:
        width = probe.textbbox((0, 0), item["text"], font=item["font"])[2]
        assert width <= _OPT_COL, (item["text"], width)


def test_the_fill_blank_call_site_passes_a_height_budget():
    """Without one the fit returns 40px for every option of any length."""
    import inspect

    import video.fill_blank as fb
    source = inspect.getsource(fb)
    assert "fit_text_font(opt, 40, 28, _OPT_W - 120, _OPT_H - 6)" in source
    assert "draw_text_solid(draw, opt," not in source, "still draws the raw string"


def test_no_real_option_changes_size_or_line_count():
    """Measured before the change and asserted after: this is a consistency
    fix, and a consistency fix that moves a frame is not one. 223 distinct
    options on disk, none of them affected."""
    options = _options_on_disk()
    if not options:
        pytest.skip("no fill_blank options on disk")
    changed = [
        o for o in options
        if (box := fit_text_font(o, 40, 28, _OPT_COL, _OPT_H - 6)).size != 40
        or len(box.lines) != 1
    ]
    assert not changed, f"{len(changed)} of {len(options)} moved: {changed[:5]}"


def test_two_lines_cannot_fit_the_option_card():
    """The card is 75px. One line at 40px is 49px; two is 98px. So a wrapped
    option is a log, never a silent overflow — stated here because it is the
    reason the budget cannot simply be made generous."""
    line_h = font_line_height(font(40))
    assert line_h <= _OPT_H - 6
    assert 2 * line_h > _OPT_H

#!/usr/bin/env python3
"""Every line the vocabulary table draws fits the column it is drawn in.

    python3 -m pytest tests/test_vocabulary_row_fit.py

THE DEFECT. _draw_vocab_rows asked how the text should be laid out, threw the
answer away, and drew the raw string:

    lf, _, _, _ = fit_text_font(es_text, _ROW_FONT, 28, left_col_w)
    draw_text_solid(draw, es_text, ..., lf, ...)      # es_text, not the lines

Two failures, chained. First, the call never shrank anything: both call sites
passed no `max_height`, and fit_text_font's guard is

    if max_height is None or box.advance_height <= max_height:

so it returned _ROW_FONT — 42px — on the first iteration for every string, of
any length. The call read like a fit and was a constant. Second, `lf, _, _, _`
discarded `box.lines`, which line_break had already cut to the column width,
and the original unwrapped string was drawn instead.

Measured on the fixture deck with Inter-Bold at 42px, against columns of
400px and 480px: 14 of 24 cells overflowed, in 9 of the 12 rows.

WHY THIS TEST CAPTURES DRAW CALLS RATHER THAN CALLING A HELPER. The defect is
a mismatch between what was measured and what was drawn, so a test that asks
the layout helper what it decided cannot see it — the helper was already
right. This monkeypatches draw_text_solid, runs the real renderer, and
measures the strings that actually reached the canvas. It fails against
e366f7f for that reason, and it would fail again if a future edit
reintroduced the raw string.

WHY A WIDTH-ONLY FIX IS NOT ENOUGH, pinned below. Shrinking to the 28px floor
on width alone still leaves four cells over: "Has demostrado una habilidad
notable" is 524px at 28px into a 400px column. The fit has to be
two-dimensional — width AND the row's own vertical budget, with wrapping
allowed. With a 78px budget every cell resolves, seven of them on two lines.
"""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.layout import (  # noqa: E402
    CARD_MARGIN_X, CARD_PADDING, CARD_WIDTH, VOCAB_DIVIDER_X, VOCAB_ROW_HEIGHT,
)
from studio.renderer_presentation import resolve_presentation  # noqa: E402
import video.vocabulary as vocab  # noqa: E402

FIXTURE = ROOT / "output/scripts/vocabulary/giving_compliments_20260904_121337.json"

CARD_X = CARD_MARGIN_X
GAP = 20
LEFT_MIN_X = vocab._text_left_edge(CARD_X)
RIGHT_MAX_X = CARD_X + CARD_WIDTH - CARD_PADDING // 2
LEFT_COL_W = VOCAB_DIVIDER_X - GAP - LEFT_MIN_X
BADGE_RIGHT = CARD_X + vocab._NUM_CENTRE_DX + vocab._NUM_RADIUS
RIGHT_COL_W = RIGHT_MAX_X - VOCAB_DIVIDER_X - GAP


def _pairs():
    if not FIXTURE.exists():
        pytest.skip(f"fixture deck not present: {FIXTURE}")
    return json.loads(FIXTURE.read_text())["pairs"]


def _capture(pairs, first_row_y=0):
    """Run the real renderer and record every string it draws, with its font.

    Returns [{text, x, y, font, size, width}] in draw order.
    """
    drawn = []
    original = vocab.draw_text_solid

    def spy(draw, text, x, y, f, color, alpha, **kwargs):
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        drawn.append({
            "text": text, "x": x, "y": y, "font": f,
            "size": getattr(f, "size", None),
            "width": probe.textbbox((0, 0), text, font=f)[2],
        })
        return original(draw, text, x, y, f, color, alpha, **kwargs)

    vocab.draw_text_solid = spy
    try:
        frame = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        draw = ImageDraw.Draw(frame, "RGBA")
        # Every row fully revealed: segment times all in the past.
        st = {f"pair_{i}": {"start": 0.0, "end": 0.1} for i in range(len(pairs))}
        vocab._draw_vocab_rows(
            t=999.0, draw=draw, frame=frame, pairs=pairs, st=st,
            card_x=CARD_X, first_row_y=first_row_y,
            card_h=VOCAB_ROW_HEIGHT * len(pairs) + 40, card_visible=1.0,
            card_top=290, presentation=resolve_presentation("es"),
        )
    finally:
        vocab.draw_text_solid = original
    return drawn


def _cells(drawn, pairs):
    """Split the captured draws into (row, column) groups.

    A cell is identified by which side of the divider it was drawn on, and
    rows by the y band. Nothing here assumes one line per cell — that is the
    thing under test.
    """
    cells = {}
    for item in drawn:
        side = "es" if item["x"] < VOCAB_DIVIDER_X else "en"
        # Rows are contiguous bands of VOCAB_ROW_HEIGHT starting at
        # first_row_y=0, and a cell's block is centred inside its own band,
        # so the band a line lands in identifies its row. (An earlier version
        # used an overlapping window and merged neighbouring rows into one
        # cell, which made a two-line row look like a mixed-size one.)
        row = int(item["y"] // VOCAB_ROW_HEIGHT)
        cells.setdefault((row, side), []).append(item)
    return cells


# ─────────────────────── the measurement, not the intent ───────────────────────

def test_every_drawn_line_fits_its_column():
    """THE PIN. Not 'the fit was asked' — the width of what reached the
    canvas. Against e366f7f this fails on 14 of 24 cells."""
    pairs = _pairs()
    failures = []
    for item in _capture(pairs):
        limit = LEFT_COL_W if item["x"] < VOCAB_DIVIDER_X else RIGHT_COL_W
        if item["width"] > limit:
            failures.append(
                f"{item['text']!r} drawn {item['width']}px at {item['size']}px "
                f"into a {limit}px column (+{item['width'] - limit})")
    assert not failures, "\n".join(failures)


def test_no_drawn_line_crosses_the_divider():
    """Right-aligned left column and left-aligned right column both start
    from the divider, so an overflowing cell does not merely look wrong — it
    lands on the other language."""
    for item in _capture(_pairs()):
        if item["x"] < VOCAB_DIVIDER_X:
            assert item["x"] + item["width"] <= VOCAB_DIVIDER_X - GAP + 1, item["text"]
            assert item["x"] >= LEFT_MIN_X - 1, item["text"]
        else:
            assert item["x"] >= VOCAB_DIVIDER_X + GAP - 1, item["text"]
            assert item["x"] + item["width"] <= RIGHT_MAX_X + 1, item["text"]


def test_each_cell_block_fits_the_row_budget():
    """Wrapping to two lines is allowed; spilling into the next row is not."""
    from video.utils import font_line_height

    pairs = _pairs()
    for (row, side), items in _cells(_capture(pairs), pairs).items():
        line_h = font_line_height(items[0]["font"])
        block_h = len(items) * line_h
        assert block_h <= VOCAB_ROW_HEIGHT, (
            f"row {row} {side}: {len(items)} lines x {line_h}px = {block_h}px "
            f"in a {VOCAB_ROW_HEIGHT}px row")


def test_the_whole_pair_is_drawn_and_nothing_is_truncated():
    """Wrapping must not lose or ellipsise a word. Every word of the source
    appears in the lines drawn for that cell."""
    pairs = _pairs()
    cells = _cells(_capture(pairs), pairs)
    for index, pair in enumerate(pairs):
        for side, key in (("es", "spanish"), ("en", "english")):
            items = cells.get((index, side))
            assert items, f"row {index} {side} drew nothing"
            joined = " ".join(i["text"] for i in items).split()
            assert joined == pair[key].split(), (pair[key], joined)
            assert "…" not in " ".join(joined) and "..." not in " ".join(joined)


def test_two_lines_share_one_font_within_a_cell():
    """A block set in two different sizes reads as two cells, not one."""
    pairs = _pairs()
    for (row, side), items in _cells(_capture(pairs), pairs).items():
        assert len({i["size"] for i in items}) == 1, f"row {row} {side}"


# ───────────────────────── alignment survives wrapping ─────────────────────────

def test_each_line_is_aligned_on_its_own_width():
    """A block right-aligned by its WIDEST line is not right-aligned. Each
    left-column line must end at the divider gap; each right-column line must
    start at it."""
    pairs = _pairs()
    for (row, side), items in _cells(_capture(pairs), pairs).items():
        if side == "es":
            right_edges = {i["x"] + i["width"] for i in items}
            assert max(right_edges) - min(right_edges) <= 2, (
                f"row {row} left column lines do not share a right edge: {right_edges}")
        else:
            left_edges = {i["x"] for i in items}
            assert len(left_edges) == 1, (
                f"row {row} right column lines do not share a left edge: {left_edges}")


def test_the_two_columns_of_a_row_are_centred_independently():
    """A one-line Spanish cell beside a two-line English cell must still read
    as one row: both blocks centred in the same band."""
    from video.utils import font_line_height

    pairs = _pairs()
    cells = _cells(_capture(pairs), pairs)
    for index in range(len(pairs)):
        es, en = cells.get((index, "es")), cells.get((index, "en"))
        if not (es and en):
            continue
        def centre(items):
            line_h = font_line_height(items[0]["font"])
            top = min(i["y"] for i in items)
            return top + len(items) * line_h / 2
        assert abs(centre(es) - centre(en)) <= 12, (
            f"row {index}: columns centred {abs(centre(es)-centre(en)):.0f}px apart")


# ────────────────── why width alone would not have been enough ──────────────────

def test_a_width_only_fit_would_still_overflow_four_cells():
    """Pinned so nobody 'simplifies' the vertical budget away later. At the
    28px floor, on width alone, four cells are still too wide."""
    from video.utils import font

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    smallest = font(28)
    still_over = [
        text for text, limit in
        [(p["spanish"], LEFT_COL_W) for p in _pairs()]
        + [(p["english"], RIGHT_COL_W) for p in _pairs()]
        if probe.textbbox((0, 0), text, font=smallest)[2] > limit
    ]
    assert len(still_over) >= 4, still_over


def test_the_row_budget_admits_two_lines_but_not_two_large_ones():
    """78px is the number: two 32px lines fit, two 42px lines do not. That is
    why a vertical BUDGET is passed rather than a line count."""
    from video.utils import font, font_line_height

    assert 2 * font_line_height(font(32)) <= vocab._ROW_TEXT_BUDGET
    assert 2 * font_line_height(font(42)) > vocab._ROW_TEXT_BUDGET
    assert vocab._ROW_TEXT_BUDGET < VOCAB_ROW_HEIGHT


# ══════════════════ the badge gutter ══════════════════
#
# THE SECOND HALF OF THE SAME DEFECT, and the same mistake in a second place.
# The left column took its origin from the card padding — `card_x +
# CARD_PADDING // 2`, 80px — while the row-number badge occupies x 72..104.
# The column therefore began 24px INSIDE the circle, and any line wider than
# 376px was drawn over the number. Seven of twelve rows were, by 8 to 19px.
#
# It stayed invisible while the cells were overflowing across the divider:
# the frame was broken in a louder way. Fixing the fit made it the visible
# defect, which is the usual shape — one measurement error hiding behind a
# bigger one.
#
# The declared column width was 400px and the usable width was 376px, and
# nothing reconciled them. So the origin is now DERIVED from the obstacle
# (_text_left_edge), the way watermark_top() derives the vertical floor, and
# these assertions exist because the fit tests above would all still pass
# with the origin back at 80.

def test_the_column_origin_clears_the_badge():
    """Derived, not written down. A gutter of at least a few px, and never
    a value that overlaps the circle."""
    assert LEFT_MIN_X >= BADGE_RIGHT, (LEFT_MIN_X, BADGE_RIGHT)
    assert vocab._NUM_GUTTER > 0
    assert LEFT_MIN_X == BADGE_RIGHT + vocab._NUM_GUTTER


def test_no_drawn_line_starts_under_the_row_number():
    """THE PIN. Measured on what reached the canvas, like the width test —
    not on the constant. Against the previous origin this fails on 7 rows."""
    offenders = []
    for item in _capture(_pairs()):
        if item["x"] < VOCAB_DIVIDER_X and item["x"] < BADGE_RIGHT:
            offenders.append(
                f"{item['text']!r} starts x={item['x']}, "
                f"under a badge ending at x={BADGE_RIGHT} "
                f"(by {BADGE_RIGHT - item['x']}px)")
    assert not offenders, chr(10).join(offenders)


def test_the_badge_and_the_text_move_together():
    """The badge is drawn from the same three constants the origin derives
    from, so a change to either radius or centre cannot walk the text back
    under the circle."""
    import inspect

    source = inspect.getsource(vocab._draw_vocab_rows)
    assert "num_r = _NUM_RADIUS" in source
    assert "card_x + _NUM_CENTRE_DX" in source
    assert "_text_left_edge(card_x)" in source


def test_a_wider_badge_pushes_the_text_rather_than_being_covered(monkeypatch):
    """The property that matters: the obstacle answers for its own extent."""
    before = vocab._text_left_edge(CARD_X)
    monkeypatch.setattr(vocab, "_NUM_RADIUS", vocab._NUM_RADIUS + 20)
    assert vocab._text_left_edge(CARD_X) == before + 20

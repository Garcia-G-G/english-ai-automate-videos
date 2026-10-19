#!/usr/bin/env python3
"""STEP 63 §1: the long lessons on the notebook page (design E). No render, no API.

Manim is not importable here (it lives in the studio's venv), so the scene's layout is
read from its source, as test_lesson_motion does; the colours are checked through theme.py.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STUDIO = REPO / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
import theme as TH  # noqa: E402

SOURCE = (STUDIO / "lesson_scene.py").read_text(encoding="utf-8")
BRAND = json.loads((REPO / "assets" / "branding" / "english-unlimited" / "brand.json").read_text(encoding="utf-8"))


def _const(name):
    """The numbers a constant line assigns, e.g. PAGE_L, PAGE_R, ... = -5.85, 5.85, ..."""
    for line in SOURCE.splitlines():
        names, _, values = line.partition("=")
        if name in [n.strip() for n in names.split(",")] and values:
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", values.split("#")[0])]
            return nums[[n.strip() for n in names.split(",")].index(name)]
    raise KeyError(name)


@pytest.mark.parametrize("name", list(TH.manim_block()["themes"]))
def test_every_theme_has_a_page_that_passes_the_contrast_rules(name):
    rows = [r for r in TH.contrast_table() if r["theme"] == name and r["bg"] == "page"]
    assert {r["fg"] for r in rows} == {"text", "blue", "green", "red"}
    assert all(r["ok"] for r in rows), rows
    p = TH.palette(name)
    assert p["page"] != p["bg"], "the page must stand off the ground"


def test_the_sticky_note_reads_ink_and_english_blue_on_yellow():
    c = BRAND["color"]
    assert TH.contrast(c["ink"], c["brand_yellow"]) >= 4.5
    assert TH.contrast(c["english_blue"], c["brand_yellow"]) >= 3.0


def test_the_note_wraps_to_two_lines_and_sits_bottom_right():
    assert _const("CAP_LINES") == 2
    assert _const("NOTE_RIGHT") > 0 and _const("NOTE_BOTTOM") < _const("PAGE_BOTTOM")
    assert "CAPTION_Y" not in SOURCE, "the full-width caption band is gone"
    assert "NOTE_YELLOW" in SOURCE and "rotate(NOTE_ROT" in SOURCE


def test_the_stage_is_inside_the_page_and_above_the_note():
    assert _const("PAGE_L") < -_const("STAGE_W") / 2 and _const("STAGE_W") / 2 < _const("PAGE_R")
    assert _const("STAGE_TOP") < _const("PAGE_TITLE_Y") < _const("PAGE_TOP") < _const("BAR_Y")
    assert _const("PAGE_BOTTOM") < _const("STAGE_BOTTOM")


def test_the_site_badge_is_small_and_above_the_page():
    assert _const("SITE_PX") <= 28
    assert _const("PAGE_TOP") < _const("SITE_Y") < _const("BAR_Y")
    assert "self.badge = self.pin(site_badge())" in SOURCE


def test_a_table_prints_every_row_and_blurs_the_meanings_until_said():
    body = SOURCE[SOURCE.index("def beat_table"):SOURCE.index("def beat_list")]
    assert "blurred(cell, bar_w=" in body, "one shared placeholder width per column"
    assert "*[FadeIn(row[0]) for row in body]" in body, "the first column is up before row 1 is said"
    assert "hl.animate" in body, "the active row is on the highlighter"


def test_a_quiz_reveal_circles_the_answer_and_strikes_the_others():
    body = SOURCE[SOURCE.index("def beat_quiz"):SOURCE.index("def beat_transform")]
    assert "hand_circle(opt[1])" in body and "strike(line)" in body
    assert "set_opacity(0.35)" not in body, "the wrong options stay readable"


def test_the_page_title_swap_costs_no_time():
    """An updater on the clock, never a play(): the cue offsets must not move."""
    body = SOURCE[SOURCE.index("def mount_page"):SOURCE.index("# ── the top bar")]
    assert "add_updater" in body and "self.play" not in body


def test_the_note_is_drawn_over_whatever_a_beat_adds_after_it():
    """The table's highlighter is added mid-beat, after the note: without a z-index it covered
    the note's top edge (first 1080p render, 2026-10-19)."""
    body = SOURCE[SOURCE.index("def mount_captions"):SOURCE.index("def _word_times")]
    assert "group.set_z_index(" in body

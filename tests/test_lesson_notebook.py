#!/usr/bin/env python3
"""STEP 63 §1: the long lessons on the notebook page (design E). No render, no API.

Manim is not importable here (it lives in the studio's venv), so the scene's layout is
read from its source, as test_lesson_motion does; the colours are checked through theme.py.
"""
import json
import math
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


FRAME_W, FRAME_H, PX = 16 / 9 * 8, 8.0, 8 / 1080


def _turned_note_box(w, h):
    """The note as mount_captions places it: the rectangle and its shadow turned NOTE_ROT
    about the rectangle's centre, then shifted so the box's right and bottom edges sit on
    NOTE_MARGIN. Returns (left, bottom, right, top)."""
    t, s = math.radians(_const("NOTE_ROT")), _const("NOTE_SHADOW")
    pts = [(x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t))
           for sx in (-1, 1) for sy in (-1, 1) for d in (0, s)
           for x, y in [(sx * w / 2 + d, sy * h / 2 - d)]]
    m = _const("NOTE_MARGIN")
    dx = FRAME_W / 2 - m - max(p[0] for p in pts)
    dy = -FRAME_H / 2 + m - min(p[1] for p in pts)
    return (min(p[0] for p in pts) + dx, min(p[1] for p in pts) + dy,
            max(p[0] for p in pts) + dx, max(p[1] for p in pts) + dy)


@pytest.mark.parametrize("lines", [1, 2])
def test_the_turned_note_and_its_shadow_stay_inside_the_frame(lines):
    """STEP 69 §1: placed from the unturned rectangle, a wide note's low corner and shadow ran
    to about -4.05 under a -4.0 frame edge. The widest note any lesson can show (a line is
    scaled to CAP_LINE_W, make-vs-do's widest included) with 1 and 2 lines keeps 0.15 to
    every edge, and its top stays under the stage."""
    pad, m = _const("NOTE_PAD"), _const("NOTE_MARGIN")
    assert m >= 0.15
    w = _const("CAP_LINE_W") + 2 * pad
    h = lines * _const("CAPTION_PX") * 1.45 * PX + (lines - 1) * 0.16 + 2 * pad   # "Hg": cap + descender
    left, bottom, right, top = _turned_note_box(w, h)
    assert left >= -FRAME_W / 2 + m and right <= FRAME_W / 2 - m + 1e-9
    assert bottom >= -FRAME_H / 2 + m - 1e-9 and top <= FRAME_H / 2 - m
    assert top <= _const("STAGE_BOTTOM"), "the note must not cover the stage's last row"


def test_the_scene_places_the_note_from_its_turned_box():
    body = SOURCE[SOURCE.index("def mount_captions"):SOURCE.index("def _word_times")]
    turn, place = body.index("group.rotate(NOTE_ROT"), body.index("group.get_right()")
    assert turn < place, "measure the box after the turn, shadow included"
    assert "group.get_bottom()" in body and "NOTE_MARGIN" in body


# ── STEP 69 §2: English in a table's first column is blue, by the script's own markup ──

import lesson as L  # noqa: E402


def _table(slug, beat_id):
    lesson = L.load(STUDIO / "lessons" / f"{slug}.json")
    return next(b for b in lesson["beats"] if b["id"] == beat_id)


def _first_column_inks(beat):
    """beat_table's rule, read back: green for emphasis, blue for marked English, else ink."""
    english, emphasis = L.english_terms(beat["narration"]), set(beat.get("emphasis", []))
    return ["green" if str(r[0]) in emphasis else "blue" if str(r[0]).casefold() in english else "ink"
            for r in beat["rows"]]


def test_make_vs_do_has_a_blue_first_column_and_do_time_keeps_its_green():
    assert _first_column_inks(_table("make-vs-do", "b18")) == ["blue"] * 5 + ["green"]


def test_a_spanish_first_column_stays_ink():
    beat = _table("can-could-pedir", "b08")
    assert [str(r[0]) for r in beat["rows"]] == ["habilidad", "posibilidad", "permiso"]
    assert _first_column_inks(beat) == ["ink"] * 3


def test_the_scene_colours_the_table_by_that_rule():
    body = SOURCE[SOURCE.index("def beat_table"):SOURCE.index("def beat_list")]
    assert 'L.english_terms(beat.get("narration", ""))' in body
    assert "GREEN if c in emphasis else BLUE if i == 0 and c.casefold() in english else TEXT" in body


@pytest.mark.parametrize("name", list(TH.manim_block()["themes"]))
def test_blue_reads_on_the_table_highlighter(name):
    p = TH.palette(name)
    assert 'hl_fill = mix(P["page"], YELLOW, 0.25) if P["dark"] else YELLOW' in SOURCE
    hl = TH.mix(p["page"], p["yellow"], 0.25) if p["dark"] else p["yellow"]
    assert TH.contrast(p["blue"], hl) >= 3.0, (name, p["blue"], hl)


# ── STEP 71 §2: the brand v3 logo on the lesson end card ──

def test_the_end_card_logo_clears_the_title_by_a_quarter_unit():
    """The logo is drawn from its inked pixels, LOGO_W wide at LOGO_Y; the title's box comes from
    Fredoka itself, scaled as text() does (cap height = px * 8/1080)."""
    from PIL import Image, ImageFont
    img = Image.open(REPO / "assets" / "branding" / "english-unlimited" / "logo_horizontal.png")
    x0, y0, x1, y1 = img.getchannel("A").getbbox()
    logo_bottom = _const("LOGO_Y") - _const("LOGO_W") * (y1 - y0) / (x1 - x0) / 2
    font = ImageFont.truetype(str(REPO / BRAND["font"]["display"]["file"]), 400)
    cap = font.getbbox("H")[3] - font.getbbox("H")[1]
    box = font.getbbox("Sigue aprendiendo")
    px = _const("TITLE_PX") * 0.9
    title_top = _const("END_TITLE_Y") + (box[3] - box[1]) / cap * px * PX / 2
    assert logo_bottom - title_top >= 0.25, (logo_bottom, title_top)
    body = SOURCE[SOURCE.index("def end_screen"):]
    assert "logo = brand_logo()" in body and 'move_to([0, END_TITLE_Y, 0])' in body


def test_the_end_screen_frames_did_not_move():
    body = SOURCE[SOURCE.index("def end_screen"):]
    assert "frame_w = 5.4" in body and ".arrange(RIGHT, buff=0.8).move_to([0, -1.75, 0])" in body

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


FRAME_W, FRAME_H, PX = 16 / 9 * 8, 8.0, 8 / 1080


def test_the_page_is_centred_82_percent_wide_inside_title_safe():
    """STEP 79 §2: even margins, about 82 % of the frame, inside the 90 % title-safe area."""
    left, right = _const("PAGE_L"), _const("PAGE_R")
    assert left == -right
    assert 0.80 <= (right - left) / FRAME_W <= 0.84 and right <= 0.45 * FRAME_W


def test_the_captions_are_a_two_line_band_under_the_page_not_a_sticky():
    """STEP 79 §2 replaces STEP 63's turned sticky note, which covered the page's corner."""
    assert _const("CAP_LINES") == 2
    assert "NOTE_ROT" not in SOURCE and "NOTE_YELLOW" not in SOURCE
    assert _const("PAGE_BOTTOM") - 0.1 > _const("BAND_TOP") > _const("BAND_BOTTOM") >= -0.45 * FRAME_H
    body = SOURCE[SOURCE.index("def mount_captions"):SOURCE.index("def _word_times")]
    assert "L.caption_chunks" in SOURCE and "BAND_TOP + BAND_BOTTOM" in body


def test_the_stage_is_inside_the_page_and_the_header_row_above_it_in_title_safe():
    assert _const("PAGE_L") < -_const("STAGE_W") / 2 and _const("STAGE_W") / 2 < _const("PAGE_R")
    assert _const("STAGE_TOP") < _const("PAGE_TITLE_Y") < _const("PAGE_TOP") < _const("BAR_Y") <= 0.45 * FRAME_H
    assert _const("PAGE_BOTTOM") < _const("STAGE_BOTTOM")


def test_the_header_row_is_aligned_to_the_page_edges():
    """Title at the page's left edge, the site badge at its right, the progress between them."""
    assert _const("SITE_PX") <= 28
    assert "SITE_Y = 24, BAR_Y" in SOURCE.replace("SITE_PX, ", "")
    assert "PAGE_R - pill.width / 2" in SOURCE and "PAGE_L + title.width / 2" in SOURCE
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


def test_the_caption_band_is_drawn_over_whatever_a_beat_adds_after_it():
    """The table's highlighter is added mid-beat, after the captions: they keep a z-index."""
    body = SOURCE[SOURCE.index("def mount_captions"):SOURCE.index("def _word_times")]
    assert "group.set_z_index(" in body


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

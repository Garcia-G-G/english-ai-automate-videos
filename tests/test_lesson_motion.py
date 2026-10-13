#!/usr/bin/env python3
"""Manim lessons, "grammar in motion": the three new beat types, their cues, the hook
before the title, the dark brand tokens and the duration fit. No Manim, no network.

The class of bug this guards: a motion beat that moves at the wrong moment. A transform
that morphs while the narration is still reading the WRONG sentence, a second timeline
event that fires with the first because both labels start with «I», a sort item cued on
the Spanish «a» of «a clasificar» — each renders without error and teaches the wrong thing.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STUDIO = REPO / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
import lesson as L  # noqa: E402
import renders as R  # noqa: E402

LESSONS = sorted((STUDIO / "lessons").glob("*.json"))


# ── transform: who glides, who falls, who drops in ─────────────────────────────

def test_an_inserted_auxiliary_is_the_cue():
    plan = L.transform_plan("Where you live?", "Where do you live?")
    assert plan["added"] == [1] and plan["removed"] == [] and plan["moved"] == []
    assert plan["to"][plan["cue"]] == "do"


def test_inversion_moves_the_verb_in_front():
    plan = L.transform_plan("You are tired.", "Are you tired?")
    assert plan["moved"] == [0] and plan["to"][plan["cue"]] == "Are"
    assert sorted(plan["pairs"], key=lambda p: p[1]) == [(1, 0), (0, 1), (2, 2)]   # case and . ? ignored


def test_a_dropped_word_falls_and_a_new_one_arrives():
    plan = L.transform_plan("He don't like it.", "He doesn't like it.")
    assert [plan["from"][i] for i in plan["removed"]] == ["don't"]
    assert [plan["to"][j] for j in plan["added"]] == ["doesn't"]


def test_the_transform_cue_waits_until_from_has_been_said():
    beat = {"type": "transform", "from": "You are tired.", "to": "Are you tired?",
            "narration": "Mira: [[You are tired. Are you tired?]] Ya es pregunta."}
    text, marks = L.marked_narration(beat)
    assert marks == {"#0": "c0"}
    assert "You are tired. <bookmark mark='c0'/>Are you tired?" in text      # not the «are» of `from`


# ── ordered cues: repeated words, English only ─────────────────────────────────

def test_two_labels_that_start_with_the_same_word_get_two_cues_in_order():
    beat = {"type": "timeline", "events": [{"label": "I used to live in Paris", "start": -8, "end": -3, "kind": "span"},
                                           {"label": "I live in Madrid", "start": -3, "end": 0, "kind": "span"}],
            "narration": "Antes, [[I used to live in Paris]]. Y hoy, [[I live in Madrid]]."}
    text, marks = L.marked_narration(beat)
    assert L.cue_keys(beat) == ["#0", "#1"] and marks == {"#0": "c0", "#1": "c1"}
    assert text.index("<bookmark mark='c0'/>I used") < text.index("<bookmark mark='c1'/>I live")


def test_a_cue_is_never_found_in_the_spanish():
    beat = {"type": "sort", "bins": ["make", "do"], "items": [["a mistake", 0]],
            "narration": "Vamos a clasificar: [[make a mistake]]."}
    text, _ = L.marked_narration(beat)
    assert "Vamos a clasificar" in text and "make <bookmark mark='c0'/>a mistake" in text


def test_an_unsaid_item_is_a_warning_with_its_word():
    lesson = {"id": "x", "title": "x", "beats": [
        {"id": "b01", "type": "sort", "bins": ["make", "do"], "items": [["coffee", 0], ["homework", 1]],
         "narration": "Mira: [[make coffee]]."}]}
    notes = L.warnings(lesson)
    assert len(notes) == 1 and "«homework»" in notes[0]


def test_the_bookmarks_strip_back_to_the_recorded_text():
    """The prerecorded service compares the marked text, bookmarks removed, with the audio's text."""
    from re import sub
    for path in LESSONS:
        for beat in L.load(path)["beats"]:
            text, _ = L.marked_narration(beat)
            assert "\x01" not in text and "\x02" not in text
            assert " ".join(sub(r"<bookmark mark='[^']+'/>", "", text).split()) == L.spoken_text(beat["narration"])


# ── validation ─────────────────────────────────────────────────────────────────

def _one(beat, extra_beats=()):
    return {"id": "x", "title": "x", "beats": [*extra_beats, {"id": "b99", "narration": "Hola [[hi]].", **beat}]}


@pytest.mark.parametrize("beat,needle", [
    ({"type": "transform", "from": "You are.", "to": "you ARE"}, "same words"),
    ({"type": "transform", "from": "x"}, "needs to"),
    ({"type": "timeline", "events": [{"label": "a", "start": -3, "end": -5, "kind": "span"}]}, "end > start"),
    ({"type": "timeline", "events": [{"label": "a", "start": -12, "kind": "point"}]}, "outside the axis"),
    ({"type": "timeline", "events": [{"label": "a", "start": 1, "kind": "arrow"}]}, "kind"),
    ({"type": "timeline", "events": [{"label": "a", "start": 1, "kind": "point"}] * 4}, "more than 3"),
    ({"type": "sort", "bins": ["a"], "items": [["x", 0]]}, "2–3 bins"),
    ({"type": "sort", "bins": ["a", "b"], "items": [["x", 2]]}, "[text, bin index]"),
    ({"type": "sort", "bins": ["a", "b"], "items": [["x", 0]] * 9}, "more than 8"),
])
def test_validate_catches_motion_beats_the_scene_cannot_draw(beat, needle):
    problems = L.validate(_one(beat))
    assert any(needle in p for p in problems), problems


def test_the_title_may_be_second_or_third_but_not_later():
    hook = [{"id": f"h{n}", "type": "tip", "text": "t", "narration": "Hola."} for n in range(3)]
    title = {"type": "title"}
    assert L.validate(_one(title, hook[:2])) == []
    assert any("title card" in p for p in L.validate(_one(title, hook)))


@pytest.mark.parametrize("path", LESSONS, ids=lambda p: p.stem)
def test_every_lesson_validates_and_has_no_warnings(path):
    lesson = L.load(path)
    assert L.validate(lesson) == [] and L.warnings(lesson) == []


def test_the_demo_exercises_every_motion_type_and_opens_on_a_hook():
    demo = L.load(STUDIO / "lessons" / "demo-motion.json")
    kinds = [b["type"] for b in demo["beats"]]
    assert {"transform", "timeline", "sort"} <= set(kinds) and kinds[0] == "transform" and kinds[1] == "title"
    assert {e["kind"] for b in demo["beats"] if b["type"] == "timeline" for e in b["events"]} >= {"span", "repeat"}


# ── poster and chapters do not assume beat 1 is the title ──────────────────────

def test_the_poster_comes_from_the_title_wherever_it_is():
    timeline = {"beats": [{"id": "b01", "type": "transform", "start": 0.0},
                          {"id": "b02", "type": "title", "start": 11.2}]}
    assert R.poster_time(timeline, 120.0) == pytest.approx(13.7)
    assert R.chapters_text(timeline) == "0:00 Introducción\n"


# ── brand: one source for the Shorts and the lessons ───────────────────────────

def test_the_dark_tokens_live_in_brand_json():
    brand = json.loads((REPO / "assets" / "branding" / "english-unlimited" / "brand.json").read_text())
    assert {k: v for k, v in brand["dark"].items() if not k.startswith("_")} == {
        "bg": "#1C1812", "text": "#FBF6EA", "yellow": "#F2D66B", "blue": "#6CB4EE",
        "green": "#7FD49B", "red": "#F28B82", "muted": "#A39B8C"}
    assert brand["color"]["english_blue"] == "#1B6FA8"          # the Shorts' tokens are untouched


def test_the_scene_reads_brand_json_and_registers_its_fonts():
    source = (STUDIO / "lesson_scene.py").read_text()
    assert 'BRAND["dark"]' in source and "manimpango.register_font" in source
    assert "DejaVu" not in source and "#FEFDFB\", INK" not in source


# ── duration: fitted on real renders ───────────────────────────────────────────

def _row(lesson, words, beats, pause, duration, bytes_=1, end=0.0):
    return {"lesson": lesson, "words": words, "beats": beats, "pause_s": pause, "duration_s": duration,
            "bytes": bytes_, "end_s": end}


def test_three_renders_fit_the_rate_only_and_duplicates_count_once():
    rows = [_row("a", 857, 31, 0.0, 425.44), _row("a", 857, 31, 0.0, 425.44),
            _row("b", 903, 28, 9.0, 423.5, 2), _row("c", 817, 32, 9.0, 357.2, 3)]
    fit = L.fit_duration(rows)
    assert fit["n"] == 3 and fit["fitted"] == "words (s/beat fixed)"
    assert fit["seconds_per_beat"] == L.SECONDS_PER_BEAT and 130 < fit["wpm"] < 145
    assert max(abs(r) for r in fit["residuals_s"]) < 35


def test_with_enough_renders_both_rates_are_fitted():
    a, k = 0.42, 1.1
    rows = [_row(f"l{n}", w, b, 9.0, a * w + k * b + 9.0 + 20.0 + L.FINAL_HOLD_S, n, end=20.0)
            for n, (w, b) in enumerate([(800, 30), (900, 28), (700, 33), (1000, 31), (850, 25), (760, 36)])]
    fit = L.fit_duration(rows)
    assert fit["fitted"] == "words+beats"
    assert fit["seconds_per_word"] == pytest.approx(a) and fit["seconds_per_beat"] == pytest.approx(k)


def test_the_estimate_includes_pauses_and_the_end_card():
    lesson = {"beats": [{"narration": "uno dos tres {{pause:3}}"}]}
    fit = {"seconds_per_word": 0.5, "seconds_per_beat": 1.0}
    assert L.estimate_seconds(lesson, fit) == pytest.approx(1.5 + 1.0 + 3.0 + L.FINAL_HOLD_S + L.END_SCREEN_S)


def test_a_render_records_what_the_fit_needs(tmp_path):
    (tmp_path / "lessons").mkdir()
    lesson = {"id": "d", "title": "D", "beats": [{"id": "b01", "type": "tip", "text": "t",
                                                  "narration": "uno dos {{pause:2}} tres"}]}
    L.save(lesson, tmp_path / "lessons" / "d.json")
    timeline = {"beats": [{"id": "end", "type": "end_screen", "start": 9.0, "seconds": 20.0}]}
    assert R.render_features("d", timeline, tmp_path) == {"words": 3, "beats": 1, "pause_s": 2.0, "end_s": 20.0}

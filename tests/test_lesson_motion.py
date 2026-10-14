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
import sfx as SFX  # noqa: E402
import theme as TH  # noqa: E402

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
    assert {"transform", "timeline", "sort", "syllables"} <= set(kinds) and kinds[0] == "transform" and kinds[1] == "title"
    assert {e["kind"] for b in demo["beats"] if b["type"] == "timeline" for e in b["events"]} >= {"span", "repeat"}


# ── poster and chapters do not assume beat 1 is the title ──────────────────────

def test_the_poster_comes_from_the_title_wherever_it_is():
    timeline = {"beats": [{"id": "b01", "type": "transform", "start": 0.0},
                          {"id": "b02", "type": "title", "start": 11.2}]}
    assert R.poster_time(timeline, 120.0) == pytest.approx(13.7)
    assert R.chapters_text(timeline) == "0:00 Introducción\n"


# ── brand: one source for the Shorts and the lessons ───────────────────────────

def test_the_themes_live_in_brand_json_and_sand_is_the_default():
    brand = json.loads((REPO / "assets" / "branding" / "english-unlimited" / "brand.json").read_text())
    block = brand["manim"]
    assert block["default_theme"] == "sand" and set(block["themes"]) == {"sand", "stone", "dark"}
    assert TH.tokens("sand") == {"bg": "#F3EEE4", "card": "#FFFFFF", "card2": "#EAE3D6", "text": "#1C1812",
                                 "muted": "#7A7164", "yellow": "#F2D66B", "blue": "#1B6FA8", "green": "#2E8B57",
                                 "red": "#C8453B"}
    assert TH.tokens("stone") == {**TH.tokens("sand"), "bg": "#E9E6E1"}
    dark = TH.tokens("dark")                                    # the Phase B stage, unchanged
    assert (dark["bg"], dark["text"], dark["blue"], dark["green"], dark["red"], dark["muted"]) == (
        "#1C1812", "#FBF6EA", "#6CB4EE", "#7FD49B", "#F28B82", "#A39B8C")
    assert brand["color"]["english_blue"] == "#1B6FA8"          # the Shorts' tokens are untouched


@pytest.mark.parametrize("row", TH.contrast_table(), ids=lambda r: f"{r['theme']}-{r['fg']}-on-{r['bg']}")
def test_contrast(row):
    """Text on the ground and on a card ≥ 4.5:1; blue / green / red on the ground ≥ 3:1."""
    assert row["ratio"] >= row["minimum"]


@pytest.mark.parametrize("name", ["sand", "stone"])
def test_yellow_is_never_text_on_paper(name):
    p = TH.palette(name)
    assert p["accent_text"] != p["yellow"] and TH.ink_on(p["yellow"], p) == p["text"]
    source = (STUDIO / "lesson_scene.py").read_text()
    assert "text(" not in "".join(line for line in source.splitlines() if "YELLOW)" in line and "text(" in line
                                  and "ink(YELLOW)" not in line)


def test_the_theme_comes_from_the_env_then_the_lesson_then_the_brand():
    assert L.theme_name({}, env={}) == "sand"
    assert L.theme_name({"theme": "dark"}, env={}) == "dark"
    assert L.theme_name({"theme": "dark"}, env={"THEME": "stone"}) == "stone"
    assert any("theme" in p for p in L.validate({"id": "x", "title": "x", "theme": "neon",
                                                  "beats": [{"id": "b1", "type": "tip", "text": "t", "narration": "Hola."}]}))


def test_the_paper_is_a_soft_vignette_with_grain_and_is_cached(tmp_path):
    import numpy as np
    from PIL import Image
    path = TH.background_png("sand", 320, 180, tmp_path)
    img = np.asarray(Image.open(path)).astype(int)
    bg = np.array(TH.rgb(TH.tokens("sand")["bg"]))
    centre, corner = img[80:100, 150:170].mean((0, 1)), img[:10, :10].mean((0, 1))
    assert np.all(centre > bg) and np.all(corner < bg)                           # lighter centre, darker edges
    assert np.abs(centre - bg).max() <= 0.03 * 255 + 1 and np.abs(corner - bg).max() <= 0.045 * 255
    assert 0 < img[80:100, 150:170, 0].std() <= 0.02 * 255                       # a faint grain, not flat
    assert TH.background_png("sand", 320, 180, tmp_path).read_bytes() == path.read_bytes()


def test_the_scene_reads_the_brand_and_registers_its_fonts():
    source = (STUDIO / "lesson_scene.py").read_text()
    assert "TH.palette(THEME)" in source and "manimpango.register_font" in source
    assert "config.background_image" in source and "MovingCameraScene" in source
    assert "DejaVu" not in source


def test_a_render_carries_the_theme_and_can_drop_the_effects():
    _, env = R.render_command("manim", "f", "demo-motion", "v", "dark", sfx=False)
    assert env["THEME"] == "dark" and env["SFX"] == "0"
    _, env = R.render_command("manim", "f", "demo-motion", "v")
    assert "THEME" not in env and "SFX" not in env
    assert R.theme_names()[1] == "sand"


# ── sound effects ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", SFX.NAMES)
def test_effects_sit_22_db_under_the_voice(name):
    x = SFX.render(name)
    assert SFX.rms_db(x) == pytest.approx(SFX.VOICE_RMS_DB - SFX.UNDER_DB - (4 if name == "tick" else 0), abs=0.01)
    assert len(x) == {"pop": 0.030, "whoosh": 0.250, "tick": 0.008}[name] * SFX.RATE // 1


# ── syllables ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("beat,needle", [
    ({"word": "comfortable", "parts": ["comfortable"], "stress": 0}, "2–6 parts"),
    ({"word": "table", "parts": ["ta", "ble"], "stress": 2}, "stress"),
    ({"word": "comfortable", "parts": ["COMF", "ta", "ble"], "stress": 0}, "respelling"),
])
def test_syllables_validation(beat, needle):
    problems = L.validate(_one({"type": "syllables", **beat}))
    assert any(needle in p for p in problems), problems


def test_syllables_spell_the_word_or_say_they_respell_it():
    ok = {"type": "syllables", "word": "to-day", "parts": ["to", "DAY"], "stress": 1, "narration": "[[today]]."}
    assert L.validate(_one(ok)) == []
    respelled = {"type": "syllables", "word": "comfortable", "parts": ["COMF", "ta", "ble"], "stress": 0,
                 "respelling": True, "narration": "Así: [[comfortable]]."}
    assert L.validate(_one(respelled)) == [] and L.marked_narration(respelled)[1] == {"#0": "c0"}


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
    lesson = {"speed": 1.0, "beats": [{"narration": "uno dos tres {{pause:3}}"}]}
    fit = {"seconds_per_word": 0.5, "seconds_per_beat": 1.0}
    assert L.estimate_seconds(lesson, fit) == pytest.approx(1.5 + 1.0 + 3.0 + L.FINAL_HOLD_S + L.END_SCREEN_S)


def test_a_slower_lesson_is_estimated_longer_from_renders_at_speed_one():
    rows = [_row("a", 900, 30, 0.0, 0.4 * 900 + L.SECONDS_PER_BEAT * 30 + L.FINAL_HOLD_S)]   # no "speed": 1.0
    fit = L.fit_duration(rows)
    assert fit["seconds_per_word"] == pytest.approx(0.4)
    lesson = {"beats": [{"narration": "uno dos tres"}]}
    base = L.SECONDS_PER_BEAT + L.FINAL_HOLD_S + L.END_SCREEN_S
    assert L.estimate_seconds(lesson, fit) == pytest.approx(0.4 * 3 / 0.92 + base)
    assert L.estimate_seconds({**lesson, "speed": 1.0}, fit) == pytest.approx(0.4 * 3 + base)
    slow = _row("b", 900, 30, 0.0, 0.4 * 900 / 0.92 + L.SECONDS_PER_BEAT * 30 + L.FINAL_HOLD_S)
    assert L.fit_duration(rows + [{**slow, "speed": 0.92}])["seconds_per_word"] == pytest.approx(0.4)


def test_a_render_records_what_the_fit_needs(tmp_path):
    (tmp_path / "lessons").mkdir()
    lesson = {"id": "d", "title": "D", "beats": [{"id": "b01", "type": "tip", "text": "t",
                                                  "narration": "uno dos {{pause:2}} tres"}]}
    L.save(lesson, tmp_path / "lessons" / "d.json")
    timeline = {"beats": [{"id": "end", "type": "end_screen", "start": 9.0, "seconds": 20.0}]}
    assert R.render_features("d", timeline, tmp_path) == {"words": 3, "beats": 1, "pause_s": 2.0, "speed": L.DEFAULT_SPEED,
                                                              "end_s": 20.0}


# ── sync: provable, not visual ─────────────────────────────────────────────────

def test_a_fast_enumeration_squeezes_each_item_to_land_before_the_next_cue():
    """The sort bug: pop 0.25 + hold 0.3 + fly 0.6 = 1.15 s against items said ~1 s apart left
    each item one behind the voice. Squeezed, item i is done before cue i+1."""
    cues = [60.44, 61.50, 62.45, 63.51, 64.62, 65.82]                 # demo-motion b06, as rendered
    phases = L.squeeze(cues, (0.25, 0.3, 0.6), floor=0.35)
    for i in range(len(cues) - 1):
        assert cues[i] + sum(phases[i]) <= cues[i + 1] - L.CUE_MARGIN + 1e-9
    assert phases[-1] == (0.25, 0.3, 0.6)                              # nothing follows: full length
    assert L.squeeze([0.0, 2.0], (0.25, 0.3, 0.6))[0] == (0.25, 0.3, 0.6)   # room enough: untouched
    assert sum(L.squeeze([0.0, 0.1], (0.25, 0.3, 0.6), floor=0.35)[0]) == pytest.approx(0.35)   # never below the floor


def _cue(start, cue=10.0, fallback=False, key="#0"):
    return {"beat": "b01", "key": key, "word": "do", "cue": cue, "start": start, "fallback": fallback}


def test_the_sync_report_flags_a_start_more_than_a_quarter_second_late():
    report = L.sync_report([_cue(10.1), _cue(10.3, key="#1"), _cue(14.0, fallback=True, key="#2")])
    assert report["cues"] == 2 and report["fallback"] == 1
    assert report["max_lag"] == pytest.approx(0.3) and [c["key"] for c in report["late"]] == ["#1"]


def test_a_late_cue_stops_the_batch_and_an_unproved_render_too():
    assert R.sync_problems({"cues": [_cue(10.2)]}) == []
    late = R.sync_problems({"cues": [_cue(10.26)]})
    assert len(late) == 1 and "+0.26 s" in late[0]
    assert R.sync_problems({}) != []                                   # no records: sync is not proved
    source = (STUDIO / "batch_run.py").read_text()
    assert "R.sync_problems(" in source and "sys.exit(" in source.split("R.sync_problems(")[1][:400]


def test_the_scene_records_every_cue_and_the_real_start():
    source = (STUDIO / "lesson_scene.py").read_text()
    assert source.count("self.at(") >= 8 and "def record(" in source
    assert 'p["rec"]["start"] = round(float(self.renderer.time), 3)' in source     # sort: the first visible frame
    assert '"cues": self.cues' in source and "OUT OF SYNC" in source


def test_a_quiz_reveals_on_the_answer_said_after_the_pause():
    beat = {"type": "quiz", "question": "___ you like coffee?", "options": ["Are", "Do", "Does"], "answer": 1,
            "narration": "¿[[Are, Do or Does]]? Piénsalo. {{pause:3}} Es [[Do]]."}
    text, marks = L.marked_narration(beat)
    assert "<bookmark mark='p0'/>Es <bookmark mark='c0'/>Do." in text and marks["Do"] == "c0"


def test_rows_cue_in_order_so_a_repeated_first_word_gets_its_own_cue():
    """hacer-preguntas b15 lists «Do…, Does…, Do…, Does…»: deduplicated, items 3 and 4 reused the
    bookmarks of 1 and 2 and drew 3.3 s late. In order, each item has its own word."""
    beat = {"type": "list", "items": ["Do you work here?", "Does it hurt?", "Do they speak Spanish?", "Does he?"],
            "narration": "[[Do you work here?]] ¿Trabajas? [[Does it hurt?]] ¿Duele? [[Do they speak Spanish?]] [[Does he?]]"}
    text, marks = L.marked_narration(beat)
    assert L.cue_keys(beat) == ["#0", "#1", "#2", "#3"] and set(marks.values()) == {"c0", "c1", "c2", "c3"}
    assert text.index("c2'/>Do they") > text.index("c1'/>Does it")


def test_a_row_cue_may_be_spanish_and_punctuation_never_hides_a_cue():
    beat = {"type": "dialogue", "lines": [{"en": "Hi! How are you?"}, {"en": "Yes, fine."}],
            "narration": "Ella dice [[Hi! How are you?]] y él [[Yes, fine.]]"}
    assert L.marked_narration(beat)[1] == {"#0": "c0", "#1": "c1"}         # «Hi!» once fell back to a guess
    recap = {"type": "recap", "items": ["El verbo va delante"], "narration": "El verbo va delante."}
    assert L.marked_narration(recap)[1] == {"#0": "c0"}
    source = (STUDIO / "lesson_scene.py").read_text()
    assert "L.cue_key(beat[\"options\"][answer]" in source and "L.cue_key(word)" in source


def test_a_caret_marks_only_a_real_gap_never_a_word():
    """«What means this word?» → «What does this word mean?»: «does» replaces «means», whose
    neighbours «What» and «this» are not adjacent — a caret between them sat on «means»."""
    assert L.insertion_gap(L.transform_plan("Where you live?", "Where do you live?")) == (0, 1)
    assert L.insertion_gap(L.transform_plan("You like coffee?", "Do you like coffee?")) == (None, 0)
    assert L.insertion_gap(L.transform_plan("I like it", "I like it a lot")) == (2, None)
    for src, dst in [("What means this word?", "What does this word mean?"), ("She did a mistake.", "She made a mistake."),
                     ("I use to wake up at seven.", "I usually wake up at seven.")]:
        assert L.insertion_gap(L.transform_plan(src, dst)) is None
    assert L.insertion_gap(L.transform_plan("You are tired.", "Are you tired?")) is None      # nothing added


def test_a_row_cues_on_its_own_phrase_not_on_a_word_of_the_row_before():
    """present-perfect-vs-past b25: item 2 «Worked at a shop…» cued on the «worked» of item 1's
    «Have you worked» — half a second early, which the lag gate cannot see."""
    beat = {"type": "list", "items": ["Have you worked: experiencia", "Worked at a shop in 2021: cerrado"],
            "narration": "[[Have]] you worked: experiencia. [[Worked]] at a shop in 2021: cerrado."}
    text, marks = L.marked_narration(beat)
    assert set(marks) == {"#0", "#1"} and "<bookmark mark='c1'/>Worked at a shop" in text


def test_a_sentence_plays_its_cues_in_spoken_order():
    """present-perfect-vs-past b06 highlights «last» and tags «have», and says «have» first: the
    highlights-then-tags order made the tag start 0.86 s after its word."""
    source = (STUDIO / "lesson_scene.py").read_text()
    assert "order = sorted(range(len(steps)), key=lambda k: (times[k], k))" in source

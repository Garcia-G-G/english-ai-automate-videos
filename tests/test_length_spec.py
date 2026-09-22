#!/usr/bin/env python3
"""Each field's length limit comes from the box that holds it.

    python3 -m pytest tests/test_length_spec.py

Six packages of layout work ended at the same sentence: the layout was right
and the text handed to it was the wrong length. duration_spec solved this
shape for time; this is the same three parts for space — a limit derived from
the geometry, a prompt instruction that aims the generator at it, and a
measurement that makes it true.

WORDS ARE THE WRONG UNIT, and the corpus settles it before any code. Measured
at SIZE_MAIN_SPANISH in the card's own width, educational sentences that FIT
four lines run up to 17 words and ones that do NOT start at 8 — the ranges
overlap, because what fills a line is character width. "Hoy aprenderemos a
count to five" and "Ahora, en un contexto mas informal" are both six words
and different widths.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import duration_spec as ds  # noqa: E402
import length_spec as ls  # noqa: E402

TYPES = ("educational", "pronunciation", "vocabulary",
         "true_false", "fill_blank", "quiz")


# ─────────────── the limit is derived, never restated ───────────────

def test_every_video_type_has_at_least_one_measured_field():
    covered = {b.video_type for b in ls.budgets().values()}
    assert covered == set(TYPES), covered


def test_no_geometry_constant_is_restated_in_this_module():
    """A number copied here would drift from the renderer the way
    VOCAB_MAX_ROWS drifted from the card it was meant to bound — and the
    copy would look authoritative while being wrong."""
    import re

    source = (ROOT / "src/length_spec.py").read_text()
    body = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    for literal in ("1080", "1920", "860", "740", "880", "368", "480"):
        assert f"= {literal}" not in body, literal
    # the boxes must come from imports
    assert "import video.vocabulary" in body
    assert "import video.fill_blank" in body


def test_each_budget_names_the_constant_it_came_from():
    for budget in ls.budgets().values():
        assert budget.source, budget.label
        assert len(budget.source) > 8


def test_the_absolute_limit_is_larger_than_the_comfortable_one():
    """comfortable_chars is what fits at the LARGEST font; max_chars is what
    fits at the smallest. Text that only fits once shrunk to the floor is
    legal and unreadable, so the generator is aimed at the former."""
    for budget in ls.budgets().values():
        assert budget.comfortable_chars <= budget.max_chars, budget.label
        assert budget.comfortable_chars > 0


def test_the_fill_blank_option_budget_matches_the_independent_measurement():
    """The clean case: the widest option that fits 740px at 40px is 34
    characters, derived separately by hand."""
    budget = ls.budget_for("fill_blank", "option")
    assert 30 <= budget.comfortable_chars <= 40, budget.comfortable_chars


# ──────────────────── the measurement, not the count ────────────────────

def test_a_field_that_fits_is_accepted():
    budget = ls.budget_for("vocabulary", "spanish")
    assert ls.measure("Buen trabajo", budget)["fits"]


def test_a_field_that_does_not_fit_is_reported_with_the_overflow():
    budget = ls.budget_for("vocabulary", "spanish")
    result = ls.measure("Eso es un gran trabajo en este proyecto enorme", budget)
    assert not result["fits"]
    assert result["over_lines"] or result["over_width"] or result["over_height"]


def test_measurement_beats_a_character_count():
    """THE ARGUMENT FOR THIS DESIGN. Two strings of the same length, one of
    which fits and one of which does not."""
    budget = ls.budget_for("vocabulary", "spanish")
    narrow = ls.measure("lililililililili lili", budget)
    wide = ls.measure("WMWMWMWMWMWMWMWM WMWM", budget)
    assert narrow["width"] < wide["width"]


def test_an_empty_field_is_not_a_violation():
    assert ls.measure("", ls.budget_for("quiz", "question"))["fits"]
    assert ls.check_script({"type": "quiz"}) == []


def test_an_unknown_type_is_not_checked():
    assert ls.check_script({"type": "banana", "question": "x" * 500}) == []


def test_check_script_finds_a_real_violation():
    script = {"type": "vocabulary",
              "pairs": [{"spanish": "Eso es un gran trabajo en este proyecto",
                         "english": "That is great work on this project"}]}
    violations = ls.check_script(script)
    assert violations
    assert violations[0]["where"].startswith("pairs[")
    assert violations[0]["max_chars"] > 0


# ─────────── the two specifications must not contradict each other ───────────

def test_the_quiz_conflict_is_resolved_by_speaking_two_items():
    """THE TRAP, RESOLVED THE WAY ITS OWN DOCSTRING PRESCRIBED.

    duration_spec used to ask quiz for a 77-word explanation because only
    ONE of three authored items was spoken, so the entire speech budget
    landed on a single explanation -- ~454 characters into a box that holds
    181. conflicts_with_duration says in its own body: "The resolution is
    upstream -- speak more items, so each explanation can be short".

    Quiz speaks two items now (20391bb), the budget is split, and each
    explanation is asked for 14 words -- about 82 characters. The conflict
    is gone because the cause was removed, not because the detector was
    loosened; the next test proves the detector still fires.
    """
    import duration_spec as ds
    ds.reload()

    assert ls.conflicts_with_duration("quiz") == []
    assert ds.per_item_budget("quiz") * ls.CHARS_PER_WORD <= \
        ls.budget_for("quiz", "explanation").max_chars


def test_the_detector_still_fires_when_a_budget_really_is_too_big():
    """The coverage the test above would otherwise have taken with it. A
    resolved conflict must not be confused with a detector that stopped
    looking."""
    import duration_spec as ds

    real = ds.per_item_budget
    ds.per_item_budget = lambda vt, target_seconds=None: 77
    try:
        conflicts = ls.conflicts_with_duration("quiz")
    finally:
        ds.per_item_budget = real

    assert conflicts, "a 77-word explanation must still be reported"
    conflict = conflicts[0]
    assert conflict["field"] == "explanation"
    assert conflict["duration_chars"] > conflict["box_max_chars"]


def test_a_conflicting_field_is_withheld_from_the_prompt():
    """A prompt carrying two contradictory numbers teaches the generator
    that neither is real -- how four brevity instructions beat the word
    budget when the duration work landed.

    Quiz no longer conflicts, so its explanation limit is now SAFE to state
    and the prompt carries it. The withholding is asserted against a
    conflict that actually exists."""
    import duration_spec as ds
    ds.reload()

    instruction = ls.prompt_instruction("quiz")
    assert "question" in instruction
    assert "explanation" in instruction, (
        "the conflict is resolved, so the limit should now be stated")

    real = ds.per_item_budget
    ds.per_item_budget = lambda vt, target_seconds=None: 77
    try:
        withheld = ls.prompt_instruction("quiz")
    finally:
        ds.per_item_budget = real

    assert "question" in withheld
    assert "explanation" not in withheld, (
        "a field whose two specs contradict must not state either number")


def test_a_type_with_no_conflict_gets_every_field():
    instruction = ls.prompt_instruction("vocabulary")
    assert "spanish" in instruction and "english" in instruction
    assert not ls.conflicts_with_duration("vocabulary")


def test_the_instruction_is_in_characters_not_words():
    instruction = ls.prompt_instruction("vocabulary")
    assert "CARACTERES" in instruction
    assert "palabras" in instruction  # only to say "not words"


def test_every_prompt_receives_the_length_rule():
    import inspect

    import script_generator as sg
    for name in ("educational", "quiz", "true_false", "fill_blank",
                 "pronunciation", "vocabulary"):
        source = inspect.getsource(getattr(sg, f"build_prompt_{name}"))
        assert "_length_rule" in source, name


def test_no_prompt_still_carries_a_brevity_instruction():
    """A budget added beside a contradiction changes nothing. Audited across
    the whole generator: the four 'explicación CORTA' rules that beat the
    word budget are gone and must not come back."""
    import re

    source = (ROOT / "src/script_generator.py").read_text()
    prompts = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#"))
    for pattern in (r"explicaci[óo]n CORTA", r"1-2 oraciones m[áa]ximo",
                    r"m[áa]ximo \d+ palabras"):
        assert not re.search(pattern, prompts, re.IGNORECASE), pattern


# ───────────────────────── the corpus today ─────────────────────────

def _scripts():
    found = []
    for path in (list((ROOT / "output/scripts").rglob("*.json"))
                 + list((ROOT / "output/artifacts").glob("*/script/script.json"))):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("type"):
            found.append(data)
    if not found:
        pytest.skip("no scripts on disk")
    return found


def test_the_validator_runs_over_the_whole_corpus_without_raising():
    """It runs on the SCRIPT, before TTS, so a violation costs nothing to
    catch — and it must never be the thing that breaks a run."""
    for script in _scripts():
        ls.check_script(script)


def test_fill_blank_options_are_the_clean_case():
    """0 of 223 options on disk overflow, which is why that fix was landed
    as a consistency change rather than an emergency."""
    offenders = [v for script in _scripts()
                 for v in ls.check_script(script)
                 if v["type"] == "fill_blank" and v["field"] == "option"]
    assert not offenders, offenders[:3]


# ═════════ §0a · the explanation card's anchor and budget ═════════
#
# The watermark fix at quiz.py was correct and could not work: it budgeted
# against the right floor from a card anchored 109px above it. exp_y derived
# from QUIZ_COUNTDOWN_ZONE_TOP — where the countdown lives, not where an
# explanation has room — leaving 53px, and one 28px line is 35px tall. The
# card had room for one line and was handed five, overflowing 122px past the
# mark and logging it on every render.

def test_the_quiz_explanation_card_has_room_for_more_than_one_line():
    from config.layout import QUIZ_OPTIONS_ZONE_BOTTOM
    from video.brand import watermark_top
    from video.utils import font, font_line_height

    budget = watermark_top() - (QUIZ_OPTIONS_ZONE_BOTTOM + 10) - 28 * 2
    assert budget >= 2 * font_line_height(font(28)), budget


def test_the_slide_no_longer_feeds_the_explanation_budget():
    """Same defect educational._card_floor() removed for its bounce: an
    animation displacement fed the layout budget, and during the 0.4s
    entrance quiz's became -7px."""
    import inspect

    import video.quiz as quiz
    import video.true_false as tf
    for module in (quiz, tf):
        source = inspect.getsource(module)
        assert "max_exp_h = watermark_top() - exp_y_base" in source, module.__name__
        assert "max_exp_h = watermark_top() - exp_y -" not in source


def test_the_explanation_card_cannot_cross_the_mark_while_sliding():
    import inspect

    import video.quiz as quiz
    import video.true_false as tf
    for module in (quiz, tf):
        source = inspect.getsource(module)
        assert "watermark_top() - exp_height" in source, module.__name__


def test_no_quiz_explanation_on_disk_overflows_after_the_fix():
    """The three from the reported script were +122 / +87 / +87 over."""
    from config.layout import CARD_WIDTH, QUIZ_OPTIONS_ZONE_BOTTOM
    from video.brand import watermark_top
    from video.utils import (fit_text_font, font_line_height,
                             strip_display_quotes)

    floor = watermark_top()
    anchor = QUIZ_OPTIONS_ZONE_BOTTOM + 10
    budget = floor - anchor - 56
    for script in _scripts():
        if script.get("type") != "quiz":
            continue
        for item in [script] + (script.get("questions") or []):
            text = item.get("explanation")
            if not text:
                continue
            box = fit_text_font(strip_display_quotes(text).strip(), 42, 28,
                                CARD_WIDTH - 56, budget)
            height = len(box.lines) * font_line_height(box.font) + 56
            # the card is placed at min(anchor + slide, floor - height)
            assert min(anchor + 60, floor - height) + height <= floor


def test_length_spec_derives_the_explanation_box_from_the_real_anchor():
    """§1 first assumed lines=4/height=None here and produced 240 chars; the
    card actually holds 111px. A budget larger than the box is worse than no
    budget."""
    budget = ls.budget_for("quiz", "explanation")
    assert budget.height and budget.height < 200
    assert "QUIZ_OPTIONS_ZONE_BOTTOM" in budget.source


# ═════════════════ §0b · the pill badge has a width ═════════════════

def test_a_pill_never_starts_off_the_frame():
    """There was no width at all: pill_w = tw + padding*2, and
    px = center_x - pill_w // 2 went negative. 9 of 69 translations on disk
    produced a pill wider than the frame, worst 1399px at x = -160."""
    from PIL import Image, ImageDraw

    from config.layout import CARD_WIDTH
    from video.constants import VIDEO_WIDTH
    from video.utils import draw_pill_badge

    long_text = "La gente está muy preocupada por los deep fakes en internet hoy"
    image = Image.new("RGBA", (VIDEO_WIDTH, 1920))
    draw = ImageDraw.Draw(image, "RGBA")
    width, _ = draw_pill_badge(image, draw, long_text, VIDEO_WIDTH // 2, 900,
                               font_size=30, padding_x=28, padding_y=12,
                               max_width=CARD_WIDTH)
    assert width <= CARD_WIDTH
    assert VIDEO_WIDTH // 2 - width // 2 >= 0


def test_every_translation_on_disk_fits_the_pill():
    from PIL import Image, ImageDraw

    from config.layout import CARD_WIDTH
    from video.constants import VIDEO_WIDTH
    from video.utils import draw_pill_badge

    seen = set()
    for script in _scripts():
        if script.get("type") != "fill_blank":
            continue
        for item in [script] + (script.get("sentences") or []):
            text = item.get("translation")
            if isinstance(text, str) and text.strip():
                seen.add(text.strip())
    if not seen:
        pytest.skip("no translations on disk")
    for text in seen:
        image = Image.new("RGBA", (VIDEO_WIDTH, 1920))
        draw = ImageDraw.Draw(image, "RGBA")
        width, _ = draw_pill_badge(image, draw, text, VIDEO_WIDTH // 2, 900,
                                   font_size=30, padding_x=28, padding_y=12,
                                   max_width=CARD_WIDTH)
        assert width <= CARD_WIDTH, text[:40]


def test_the_live_caller_passes_a_width():
    import inspect

    import video.fill_blank as fb
    assert "max_width=CARD_WIDTH" in inspect.getsource(fb)

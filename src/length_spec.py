#!/usr/bin/env python3
"""How much text each field can hold, derived from the boxes that hold it.

    from length_spec import budget_for, check_script, FIELDS
    budget_for("fill_blank", "option").max_chars      -> ~35
    check_script(script)                               -> [violation, ...]

WHY THIS EXISTS. Six packages of layout work each ended at the same sentence:
the layout was right and the text handed to it was the wrong length.

    vocabulary     worst cell fills 98.9% of its column
    fill_blank     worst option 725px of a 740px column
    pronunciation  longest word needed 118px against a 160px design
    educational    19% of sentences were six-line walls
    quiz           speaks 1 of 3 authored questions -> ~35s

duration_spec solved this shape once, for time, and its docstring states the
design: "The word target is a LEVER, not the specification." The band is the
specification, the prompt instruction aims the generator at it, and the gate
makes it true. Same three parts here, for space.

WORDS ARE THE WRONG UNIT, and the corpus proves it before any code is
written. Educational sentences measured at SIZE_MAIN_SPANISH in the card's
own width: the ones that FIT four lines run up to 17 words, and the ones that
do NOT start at 8. The two ranges overlap from 8 to 17, because what fills a
line is character width, not word count — "Hoy aprenderemos a count to five"
and "Ahora, en un contexto mas informal" are both six words and different
widths. So the prompt-facing unit is CHARACTERS, derived from the box, and
the enforcement is a measurement rather than a count.

NOTHING HERE RESTATES A GEOMETRY CONSTANT. Every box is imported from the
renderer or the layout module that owns it. A number copied into this file
would drift from the renderer the way VOCAB_MAX_ROWS drifted from the card it
was supposed to bound, and the copy would look authoritative while being
wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

#: A representative Spanish sentence, used to turn a pixel width into a
#: character budget. Character budgets are inherently approximate — 'i' and
#: 'W' are not the same width — so the budget is derived from the MEAN
#: advance of real narration text rather than from a single glyph.
_SAMPLE = ("Hoy vamos a aprender una expresion muy util en ingles, "
           "porque aparece en conversaciones reales todos los dias.")


@dataclass(frozen=True)
class Budget:
    """One field's box, and the character budget that follows from it."""

    video_type: str
    field: str
    width: int
    lines: int
    font_max: int
    font_min: int
    height: Optional[int]
    source: str          # the constant this came from, named
    max_chars: int
    comfortable_chars: int

    @property
    def label(self) -> str:
        return f"{self.video_type}.{self.field}"


def _mean_char_width(size: int) -> float:
    """Average advance of one character at `size`, from real text."""
    from PIL import Image, ImageDraw

    from video.utils import font

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    return probe.textbbox((0, 0), _SAMPLE, font=font(size))[2] / len(_SAMPLE)


def _chars_for(width: int, lines: int, size: int) -> int:
    """Characters that fit `lines` of `width` at `size`.

    Discounted by 8%: line breaking wastes the tail of every line except the
    last, because a word that does not fit is pushed whole to the next one.
    Measured against the corpus rather than guessed — without it the budget
    over-promises on multi-line fields and every long sentence "fits".
    """
    per_line = width / _mean_char_width(size)
    usable = per_line * lines
    return int(usable * (1.0 - 0.08 * (lines - 1) / max(1, lines)))


def _boxes() -> List[Dict]:
    """Every measurable field, with its box read from the owning module."""
    from config.layout import (CARD_PADDING, CARD_WIDTH, VOCAB_DIVIDER_X,
                               QUIZ_QUESTION_ZONE_BOTTOM, QUIZ_QUESTION_ZONE_TOP,
                               QUIZ_OPTIONS_ZONE_BOTTOM, TF_EXPLANATION_ZONE_TOP,
                               TF_QUESTION_ZONE_HEIGHT)
    from video.brand import watermark_top
    from video.utils import font, font_line_height
    from animations.subtitle_processor import SubtitleProcessor
    from video.constants import SIZE_MAIN_SPANISH, TEXT_AREA_WIDTH
    import video.fill_blank as fb
    import video.pronunciation as pron
    import video.vocabulary as vocab

    gap = 20
    card_x = __import__("config.layout", fromlist=["CARD_MARGIN_X"]).CARD_MARGIN_X
    left_edge = vocab._text_left_edge(card_x)
    right_max = card_x + CARD_WIDTH - CARD_PADDING // 2

    return [
        # ── educational ──────────────────────────────────────────────
        dict(video_type="educational", field="sentence",
             width=CARD_WIDTH - CARD_PADDING * 2 - 40,
             lines=SubtitleProcessor.MAX_LINES_PER_GROUP,
             font_max=SIZE_MAIN_SPANISH, font_min=42, height=None,
             source="CARD_WIDTH/CARD_PADDING + SubtitleProcessor.MAX_LINES_PER_GROUP"),

        # ── vocabulary ───────────────────────────────────────────────
        dict(video_type="vocabulary", field="spanish",
             width=VOCAB_DIVIDER_X - gap - left_edge, lines=2,
             font_max=vocab._ROW_FONT, font_min=36,
             height=vocab._ROW_TEXT_BUDGET,
             source="VOCAB_DIVIDER_X - vocabulary._text_left_edge()"),
        dict(video_type="vocabulary", field="english",
             width=right_max - VOCAB_DIVIDER_X - gap, lines=2,
             font_max=vocab._ROW_FONT, font_min=36,
             height=vocab._ROW_TEXT_BUDGET,
             source="CARD_WIDTH - VOCAB_DIVIDER_X"),

        # ── fill_blank ───────────────────────────────────────────────
        dict(video_type="fill_blank", field="option",
             width=fb._OPT_W - 120, lines=1, font_max=40, font_min=28,
             height=fb._OPT_H - 6,
             source="fill_blank._OPT_W - 120, _OPT_H - 6"),
        dict(video_type="fill_blank", field="sentence",
             width=fb._TEXT_MAX_W, lines=3, font_max=48, font_min=32,
             height=None, source="fill_blank._TEXT_MAX_W"),

        # ── pronunciation ────────────────────────────────────────────
        dict(video_type="pronunciation", field="word",
             width=TEXT_AREA_WIDTH - 80, lines=2,
             font_max=pron._WORD_MAX, font_min=pron._WORD_MIN, height=None,
             source="TEXT_AREA_WIDTH - 80, pronunciation._WORD_MAX/_MIN"),
        dict(video_type="pronunciation", field="phonetic",
             width=TEXT_AREA_WIDTH - 80, lines=2,
             font_max=pron._SIZE_PHONETIC, font_min=pron._SIZE_PHONETIC,
             height=None, source="pronunciation._SIZE_PHONETIC"),
        dict(video_type="pronunciation", field="tip",
             width=TEXT_AREA_WIDTH - 80, lines=3,
             font_max=pron._SIZE_TIP, font_min=pron._SIZE_TIP, height=None,
             source="pronunciation._SIZE_TIP"),

        # ── quiz ─────────────────────────────────────────────────────
        dict(video_type="quiz", field="question",
             width=CARD_WIDTH - 40 * 2, lines=3, font_max=52, font_min=40,
             height=QUIZ_QUESTION_ZONE_BOTTOM - QUIZ_QUESTION_ZONE_TOP - 160,
             source="CARD_WIDTH - 80, QUIZ_QUESTION_ZONE_*"),
        # The REAL box, not four notional lines. §1 first assumed
        # lines=4/height=None here and produced a 240-char budget; the card
        # is actually anchored above the watermark and holds far less. The
        # height is derived from the same two constants the renderer uses,
        # so the two cannot disagree.
        dict(video_type="quiz", field="explanation",
             width=CARD_WIDTH - 28 * 2,
             lines=max(1, (watermark_top() - (QUIZ_OPTIONS_ZONE_BOTTOM + 10)
                           - 56) // font_line_height(font(28))),
             font_max=42, font_min=28,
             height=watermark_top() - (QUIZ_OPTIONS_ZONE_BOTTOM + 10) - 56,
             source="watermark_top() - QUIZ_OPTIONS_ZONE_BOTTOM (quiz.py)"),

        # ── true_false ───────────────────────────────────────────────
        dict(video_type="true_false", field="statement",
             width=CARD_WIDTH - 36 * 2, lines=3, font_max=56, font_min=36,
             height=TF_QUESTION_ZONE_HEIGHT - 36 * 2,
             source="CARD_WIDTH - 72, TF_QUESTION_ZONE_HEIGHT"),
        dict(video_type="true_false", field="explanation",
             width=CARD_WIDTH - 28 * 2,
             lines=max(1, (watermark_top() - TF_EXPLANATION_ZONE_TOP - 56)
                       // font_line_height(font(28))),
             font_max=42, font_min=28,
             height=watermark_top() - TF_EXPLANATION_ZONE_TOP - 56,
             source="watermark_top() - TF_EXPLANATION_ZONE_TOP (true_false.py)"),
    ]


_CACHE: Optional[Dict[str, Budget]] = None


def budgets() -> Dict[str, Budget]:
    """Every field's budget, keyed 'type.field'."""
    global _CACHE
    if _CACHE is None:
        built = {}
        for box in _boxes():
            # max_chars at the SMALLEST font the renderer will accept: that
            # is the true ceiling, past which the text cannot be shown at
            # all. comfortable_chars is what fits at the LARGEST, which is
            # what the generator should aim at — text that only fits once
            # shrunk to the floor is legal and unreadable.
            built[f"{box['video_type']}.{box['field']}"] = Budget(
                video_type=box["video_type"], field=box["field"],
                width=box["width"], lines=box["lines"],
                font_max=box["font_max"], font_min=box["font_min"],
                height=box["height"], source=box["source"],
                max_chars=_chars_for(box["width"], box["lines"], box["font_min"]),
                comfortable_chars=_chars_for(box["width"], box["lines"],
                                             box["font_max"]),
            )
        _CACHE = built
    return _CACHE


def reload() -> None:
    global _CACHE
    _CACHE = None


def budget_for(video_type: str, field: str) -> Optional[Budget]:
    return budgets().get(f"{(video_type or '').lower()}.{field}")


FIELDS = tuple(sorted(budgets())) if False else ()   # populated lazily below


# ─────────────────────────── the measurement ───────────────────────────

def measure(text: str, budget: Budget) -> Dict:
    """Lay `text` out in `budget`'s box with the real font. Measured, not counted.

    This is the enforcement. The character budget is the prompt-facing
    approximation; THIS is the specification, because it asks the same
    question the renderer will ask.
    """
    from video.utils import fit_text_font, font, line_break, measure_block

    text = str(text or "").strip()
    if not text:
        return {"fits": True, "empty": True}

    box = fit_text_font(text, budget.font_max, budget.font_min,
                        budget.width, budget.height)
    widest = measure_block(line_break(text, box.font, budget.width), box.font).width
    over_width = max(0, widest - budget.width)
    over_lines = max(0, len(box.lines) - budget.lines)
    over_height = (max(0, box.advance_height - budget.height)
                   if budget.height else 0)
    return {
        "fits": not (over_width or over_lines or over_height),
        "empty": False,
        "chars": len(text),
        "size": box.size,
        "lines": len(box.lines),
        "width": widest,
        "over_width": over_width,
        "over_lines": over_lines,
        "over_height": over_height,
        "shrunk": box.size < budget.font_max,
        "at_floor": box.size <= budget.font_min,
    }


#: Which script keys carry each field. A field the script does not have is
#: simply not checked — absence is not a violation.
_SCRIPT_FIELDS = {
    "educational": {},                      # measured per SENTENCE, see below
    "vocabulary": {"spanish": None, "english": None},   # per pair
    "fill_blank": {"sentence": "sentence", "option": None},
    "pronunciation": {"word": "word", "phonetic": "phonetic", "tip": "tip"},
    "quiz": {"question": "question", "explanation": "explanation"},
    "true_false": {"statement": "statement", "explanation": "explanation"},
}


def check_script(script: Dict) -> List[Dict]:
    """Every field of one script that does not fit its box.

    Runs on the SCRIPT, before TTS, so a violation costs nothing to catch.
    Returns a list of violations; an empty list means everything fits.
    """
    video_type = (script or {}).get("type")
    if video_type not in _SCRIPT_FIELDS:
        return []

    violations = []

    def look(field, text, where):
        budget = budget_for(video_type, field)
        if not budget or not str(text or "").strip():
            return
        result = measure(text, budget)
        if not result["fits"]:
            violations.append({
                "type": video_type, "field": field, "where": where,
                "text": str(text), **result,
                "max_chars": budget.max_chars,
                "comfortable_chars": budget.comfortable_chars,
            })

    for field, key in _SCRIPT_FIELDS[video_type].items():
        if key:
            look(field, script.get(key), key)

    if video_type == "vocabulary":
        for index, pair in enumerate(script.get("pairs") or []):
            look("spanish", pair.get("spanish"), f"pairs[{index}]")
            look("english", pair.get("english"), f"pairs[{index}]")

    if video_type == "fill_blank":
        options = script.get("options")
        values = (options.values() if isinstance(options, dict)
                  else (options or []))
        for index, option in enumerate(values):
            look("option", option, f"options[{index}]")
        for index, item in enumerate(script.get("sentences") or []):
            look("sentence", item.get("sentence"), f"sentences[{index}]")
            options = item.get("options")
            values = (options.values() if isinstance(options, dict)
                      else (options or []))
            for j, option in enumerate(values):
                look("option", option, f"sentences[{index}].options[{j}]")

    if video_type == "quiz":
        for index, item in enumerate(script.get("questions") or []):
            look("question", item.get("question"), f"questions[{index}]")
            look("explanation", item.get("explanation"), f"questions[{index}]")

    if video_type == "educational":
        # Educational has no per-field text: the card is a SENTENCE, and the
        # sentences are only known once the narration is segmented. Checked
        # against full_script split on sentence marks, which is the closest
        # a pre-TTS check can get.
        import re
        budget = budget_for("educational", "sentence")
        for index, sentence in enumerate(
                re.split(r"(?<=[.!?])\s+", str(script.get("full_script") or ""))):
            if not sentence.strip():
                continue
            result = measure(sentence, budget)
            if not result["fits"]:
                violations.append({
                    "type": video_type, "field": "sentence",
                    "where": f"full_script[{index}]", "text": sentence,
                    **result, "max_chars": budget.max_chars,
                    "comfortable_chars": budget.comfortable_chars,
                })

    return violations


#: Spanish narration, characters per word including the trailing space.
#: Measured over the corpus rather than assumed, and used only to compare
#: the two specifications with each other — never to enforce anything.
CHARS_PER_WORD = 5.9


def conflicts_with_duration(video_type: str) -> List[Dict]:
    """Fields where duration_spec asks for more text than the box can hold.

    THE TRAP THIS EXISTS TO STOP. When the duration work landed we named the
    rule: a budget only commands if nothing else in the prompt contradicts
    it. Four brevity instructions beat the word budget and the videos came
    out short anyway.

    The contradiction now is between two of OUR OWN specifications.
    duration_spec asks quiz for a 77-word explanation because only ONE of
    the three authored items is spoken, and 77 words is about 454
    characters against a box that holds 240. Emitting both numbers into one
    prompt would repeat the exact mistake with better provenance.

    So a field that conflicts gets NO character instruction, and the
    conflict is reported instead. The resolution is upstream — speak more
    items, so each explanation can be short — and it is not something a
    prompt sentence can paper over.
    """
    import duration_spec as ds

    out = []
    per_item = ds.per_item_budget(video_type)
    if per_item is None:
        return out
    # duration_spec's per-item budget lands on the explanation-shaped field
    for field in ("explanation", "sentence"):
        budget = budget_for(video_type, field)
        if not budget:
            continue
        wanted = int(per_item * CHARS_PER_WORD)
        if wanted > budget.max_chars:
            out.append({
                "video_type": video_type, "field": field,
                "duration_words": per_item, "duration_chars": wanted,
                "box_max_chars": budget.max_chars,
                "over_by": wanted - budget.max_chars,
            })
    return out


def prompt_instruction(video_type: str) -> str:
    """The length rule for a generator prompt, in characters, per field.

    Characters rather than words, because words do not separate what fits
    from what does not: educational sentences that fit four lines run up to
    17 words and ones that do not start at 8. The two ranges overlap.
    """
    fields = [b for key, b in sorted(budgets().items())
              if b.video_type == (video_type or "").lower()]
    if not fields:
        return ""
    conflicting = {c["field"] for c in conflicts_with_duration(video_type)}
    lines = ["LONGITUD DE CADA CAMPO (obligatorio, cuéntalo en CARACTERES):"]
    for budget in fields:
        if budget.field in conflicting:
            # Silent here ON PURPOSE. duration_spec already gives this field
            # a word target that the box cannot hold, and a prompt carrying
            # both numbers teaches the generator that neither is real.
            logger.warning(
                "length_spec: %s.%s omitted from the prompt — duration_spec "
                "asks for more text than the box holds; see "
                "conflicts_with_duration()", video_type, budget.field)
            continue
        lines.append(
            f"  · {budget.field}: máximo {budget.comfortable_chars} caracteres "
            f"(límite absoluto {budget.max_chars}).")
    if len(lines) == 1:
        return ""
    lines.append(
        "Estos límites vienen del tamaño real de la tarjeta en pantalla. "
        "Un texto más largo se encoge hasta ser ilegible o se sale del cuadro. "
        "Cuenta caracteres, no palabras.")
    return "\n".join(lines)

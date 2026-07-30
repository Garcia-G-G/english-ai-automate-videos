#!/usr/bin/env python3
"""Pin that renderer timing fallbacks use the duration they are PASSED.

    python3 -m pytest tests/test_render_timing_params.py

The bug class: a resolver takes `duration` as a parameter, and a downstream
function re-derives it from `data` with a bad default. The correct value is
already in scope and is ignored in favour of a lookup — the same class as the
offset_x shadowing at educational.py:522, and unrelated to the missing-key
defaults deleted in the same commit. This is parameter shadowing, not a
default bug: it is provable by inspection plus these tests, with no
measurement, tuning or judgement.

The render duration is measured from the rendered mp3 at
video/__init__.py:110 (`get_audio_duration(audio_path)`). `data['duration']`
is a *different* number written by the TTS stage (the sum of its concat
segments, rounded to 3dp). They usually agree; nothing guarantees it.

Swept all four resolve/fallback pairs. Only true_false shadowed:

    quiz.py:519        resolve_quiz_timestamps  -> parse_quiz_timestamps(words)   CLEAN
    true_false.py:112  resolve_true_false_timestamps -> parse_true_false_timestamps  SHADOWED
    fill_blank.py:354  legacy `elif not st:` branch, inline                       CLEAN
    vocabulary.py:86   _build_fallback_times(pairs, duration)                     CLEAN
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.quiz import resolve_quiz_timestamps                    # noqa: E402
from video.true_false import (                                    # noqa: E402
    parse_true_false_timestamps,
    resolve_true_false_timestamps,
)
from video.vocabulary import _build_fallback_times                # noqa: E402

# The fallback backstops in parse_true_false_timestamps, as multiples of
# duration. These fire only when the keyword scan finds nothing.
OPTIONS_AT = 0.15
ANSWER_AT = 0.40

# A real duration, deliberately far from the old default of 10.
REAL_DURATION = 45.0

# Words that match none of the keywords the parser scans for
# ('verdadero', 'falso', 'piensa', 'tres', 'dos', 'uno', 'respuesta'),
# so every backstop below is forced to fire.
NO_KEYWORD_WORDS = [
    {"word": "hola", "start": 0.0, "end": 0.5},
    {"word": "mundo", "start": 0.5, "end": 1.0},
]


def _fallback_data(**extra):
    """A true_false payload with no segment_times, so the fallback fires."""
    return dict({"words": list(NO_KEYWORD_WORDS)}, **extra)


# ── true_false: the confirmed shadow ─────────────────────────────────

def test_true_false_fallback_uses_the_passed_duration():
    """The regression pin. Before the fix this read data.get('duration', 10)
    and produced 1.5 / 4.0 on a 45s video."""
    ts = parse_true_false_timestamps(_fallback_data(), REAL_DURATION)

    assert ts["options_start"] == REAL_DURATION * OPTIONS_AT == 6.75
    assert ts["answer_start"] == REAL_DURATION * ANSWER_AT == 18.0


def test_true_false_fallback_ignores_a_conflicting_duration_in_data():
    """`data['duration']` is TTS-written and may disagree with the measured
    audio duration. The parameter wins."""
    ts = parse_true_false_timestamps(
        _fallback_data(duration=10), REAL_DURATION
    )

    assert ts["options_start"] == REAL_DURATION * OPTIONS_AT
    assert ts["answer_start"] == REAL_DURATION * ANSWER_AT


def test_true_false_parse_requires_duration_rather_than_defaulting():
    """No default means a caller cannot silently get the old 10 back."""
    try:
        parse_true_false_timestamps(_fallback_data())
    except TypeError:
        pass
    else:
        raise AssertionError(
            "parse_true_false_timestamps still accepts a single argument; "
            "duration must be required, not defaulted"
        )


def test_true_false_resolver_threads_duration_into_segment_times():
    """End to end through the public resolver, which is what
    video/__init__.py:327 actually calls."""
    data = resolve_true_false_timestamps(_fallback_data(), REAL_DURATION)
    st = data["segment_times"]

    assert st["options"]["start"] == REAL_DURATION * OPTIONS_AT
    assert st["answer"]["start"] == REAL_DURATION * ANSWER_AT


def test_true_false_resolver_prefers_exact_segment_times():
    """The fallback is only for payloads without them — 10 of 14 real
    true_false TTS outputs carry segment_times and skip this path."""
    exact = {"options": {"start": 1.0, "end": 2.0, "duration": 1.0},
             "answer": {"start": 3.0, "end": 4.0, "duration": 1.0}}
    data = resolve_true_false_timestamps(
        _fallback_data(segment_times=dict(exact)), REAL_DURATION
    )

    assert data["segment_times"] == exact


# ── the three that did not shadow: regression guards ─────────────────

def test_vocabulary_fallback_scales_with_the_passed_duration():
    """_build_fallback_times takes duration as a parameter and never looks
    it up. Pin that it stays that way."""
    pairs = [{"spanish": "hola", "english": "hello"},
             {"spanish": "adiós", "english": "goodbye"}]

    short = _build_fallback_times(pairs, 10.0)
    long = _build_fallback_times(pairs, REAL_DURATION)

    assert short["title"]["end"] < long["title"]["end"]
    assert long["pair_1"]["end"] > short["pair_1"]["end"]
    assert long["pair_1"]["end"] <= REAL_DURATION


def test_quiz_fallback_is_independent_of_duration_in_data():
    """resolve_quiz_timestamps derives everything from `words` via
    parse_quiz_timestamps(words), which has no access to `data` at all."""
    words = list(NO_KEYWORD_WORDS)

    a = resolve_quiz_timestamps({"words": list(words)}, REAL_DURATION)
    b = resolve_quiz_timestamps({"words": list(words), "duration": 10}, REAL_DURATION)

    assert a["segment_times"] == b["segment_times"]


# ── the class-wide guard, which also covers fill_blank ───────────────

def test_no_renderer_reads_duration_out_of_data():
    """The whole bug class in one assertion.

    Every renderer receives `duration` as a parameter. Reading it back out of
    `data` re-introduces the shadow, and the fill_blank legacy branch at
    :354-362 is only correct because it uses the parameter inline — which a
    behavioural test cannot reach without rendering a frame.
    """
    def reads_duration_from_data(node):
        # data.get('duration', ...)
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "data"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "duration"):
            return True
        # data['duration']
        return (isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "data"
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "duration")

    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in sorted((ROOT / "src" / "video").rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if reads_duration_from_data(node)
    ]

    assert not offenders, (
        "renderer reads duration out of `data` instead of using the passed "
        "parameter:\n  " + "\n  ".join(offenders)
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
"""A quiz renders every item it carries, not just the first.

    python3 -m pytest tests/test_quiz_multi_item.py

THE DEFECT THIS PINS. `QuizScript.questions` is a List[QuizItem] that
script_schema labels DEAD PAYLOAD in its own comment: the prompt demands
three, GPT writes three, and quiz.py had no loop, no `items[`, no
`item_index`. Setting items_spoken: 3 produced audio for three questions and
video for one.

WHY IT MATTERS BEYOND THE WASTE. quiz, true_false and fill_blank cannot
reach the 50s floor with one item. Every narrated field at its absolute
maximum — the size at which fit_text_font is already at its floor and the
card is on the watermark — comes to 59 spoken words against a 67-word floor.
All 14 quiz scripts in the queue are blocked on this, and no rewrite moves
them, because the ceiling is a layout fact rather than a style choice.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video import quiz  # noqa: E402


def _seg(start, end=None):
    end = start + 0.5 if end is None else end
    return {"start": start, "end": end, "duration": end - start}


def _item(n):
    return {"question": f"Q{n}?",
            "options": {"A": f"a{n}", "B": f"b{n}", "C": f"c{n}", "D": f"d{n}"},
            "correct": "B",
            "explanation": f"E{n}"}


def _three_item_script():
    data = dict(_item(1))
    data["type"] = "quiz"
    data["questions"] = [_item(1), _item(2), _item(3)]
    data["segment_times"] = {
        "question": _seg(0.0), "option_a": _seg(2.0), "answer": _seg(8.0),
        "explanation": _seg(9.0),
        "i2_question": _seg(20.0), "i2_option_a": _seg(22.0),
        "i2_answer": _seg(28.0), "i2_explanation": _seg(29.0),
        "i3_question": _seg(40.0), "i3_option_a": _seg(42.0),
        "i3_answer": _seg(48.0), "i3_explanation": _seg(49.0),
    }
    return data


# ── the projection ───────────────────────────────────────────────────

def test_three_authored_items_become_three_views():
    views = quiz.quiz_item_views(_three_item_script())
    assert len(views) == 3
    assert [v["question"] for v in views] == ["Q1?", "Q2?", "Q3?"]


def test_a_view_carries_bare_segment_keys():
    """The renderer must not have to learn about prefixes — that is the
    whole reason the drawing code could be left alone."""
    views = quiz.quiz_item_views(_three_item_script())
    for view in views:
        assert "question" in view["segment_times"]
        assert not any(k.startswith("i2_") or k.startswith("i3_")
                       for k in view["segment_times"])


def test_times_inside_a_view_stay_absolute():
    """`t` is absolute, so the segments compared against it must be too."""
    views = quiz.quiz_item_views(_three_item_script())
    assert views[1]["segment_times"]["question"]["start"] == 20.0
    assert views[2]["segment_times"]["answer"]["start"] == 48.0


def test_the_root_is_item_one_and_questions_supplies_the_rest():
    """questions[0] repeats the root by the schema's own validator, so
    reading it as a separate item would render the first question twice."""
    views = quiz.quiz_item_views(_three_item_script())
    assert [v["explanation"] for v in views] == ["E1", "E2", "E3"]


# ── the dispatch ─────────────────────────────────────────────────────

@pytest.mark.parametrize("t,expected", [
    (0.0, "Q1?"), (19.9, "Q1?"),
    (20.0, "Q2?"), (39.9, "Q2?"),
    (40.0, "Q3?"), (99.0, "Q3?"),
])
def test_the_item_on_screen_is_the_one_being_spoken(t, expected):
    views = quiz.quiz_item_views(_three_item_script())
    assert quiz.quiz_item_at(views, t)["question"] == expected


def test_an_item_holds_the_screen_until_the_next_one_speaks():
    """Item 2's explanation must not vanish the instant it stops talking —
    it owns the screen until item 3 starts."""
    views = quiz.quiz_item_views(_three_item_script())
    assert quiz.quiz_item_at(views, 35.0)["explanation"] == "E2"


# ── the one-item path is untouched ───────────────────────────────────

def test_a_single_item_script_is_unchanged():
    """Every quiz on disk today is one item. It must take the old path."""
    data = dict(_item(1))
    data["segment_times"] = {"question": _seg(0.0), "option_a": _seg(2.0),
                             "answer": _seg(8.0)}
    views = quiz.quiz_item_views(data)
    assert len(views) == 1
    assert views[0]["segment_times"] == data["segment_times"]


def test_audio_for_an_item_the_script_does_not_carry_is_skipped():
    """Drawing a blank card for seconds is worse than the item's absence."""
    data = dict(_item(1))
    data["questions"] = [_item(1)]
    data["segment_times"] = {"question": _seg(0.0), "i2_question": _seg(20.0)}
    assert len(quiz.quiz_item_views(data)) == 1


# ═══════════════════════════════════════════════════════════════════════
# THE DOOR. Everything above tests the projection with segment_times typed
# by hand — which is exactly how a renderer for `iN_` ids can sit in the
# tree, fully tested, while NOTHING produces those ids and questions[1:]
# stays as dead as it was. A capability with no door is not a capability.
#
# So this one starts from a script, runs the real
# generate_quiz_audio_segmented, and feeds what it returns to the renderer's
# own projection. The TTS call and the OpenAI client are stubbed; the
# assembly is not — ffmpeg concatenates real mp3s, measure_speech_end reads
# them, and the segment boundaries come out measured, as in production.
# ═══════════════════════════════════════════════════════════════════════

#: Multi-item is governed by config.yaml's `items_spoken`, which ships at 1.
#: A test that wants three items OPENS THAT SWITCH explicitly rather than
#: assuming it — the capability and its door are separate things, and
#: saying so here is what keeps this file honest about which it is testing.
def _speak_up_to(monkeypatch, allowed):
    import duration_spec
    real = duration_spec.type_spec

    def spec(video_type):
        entry = dict(real(video_type) or {})
        entry["items_spoken"] = allowed
        return entry

    monkeypatch.setattr(duration_spec, "type_spec", spec)


def _stub_tts(monkeypatch, source_mp3: Path, provider: str):
    """Every TTS call writes a real (short) mp3 to its path.

    BOTH PROVIDERS, because elevenlabs is the default
    (pipeline.resolve_provider_name) and openai is what most of this repo's
    tooling reaches for. A door that opens on only one of them is the same
    defect one layer along.
    """
    import shutil

    calls = []

    if provider == "openai":
        import tts_openai as mod

        def fake_tts(client, path, **kwargs):
            calls.append(kwargs.get("input"))
            shutil.copy(source_mp3, path)
            return path

        monkeypatch.setattr(mod, "_tts_with_retry", fake_tts)
        monkeypatch.setattr(mod, "_get_openai_client", lambda: object())
    else:
        import tts_elevenlabs as mod

        def fake_segment(text=None, output_path=None, voice_id=None, **kwargs):
            # positional callers: generate_segment_audio(txt, path, voice)
            calls.append(text)
            shutil.copy(source_mp3, output_path)
            return output_path

        monkeypatch.setattr(mod, "generate_segment_audio", fake_segment)

    return mod, calls


@pytest.fixture
def silent_mp3(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to assemble the segments")
    path = tmp_path / "beep.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.6", "-ac", "2",
                    str(path)], capture_output=True, check=True)
    return path


@pytest.mark.parametrize("provider", ["openai", "elevenlabs"])
def test_script_to_audio_to_three_rendered_items(tmp_path, monkeypatch,
                                                 silent_mp3, provider):
    """script -> audio -> quiz_item_views -> three items, end to end.

    THE PIN FOR THE WHOLE FEATURE. If the producer ever stops emitting `iN_`
    ids, or stops passing `questions` through into the audio json, this goes
    red — and it goes red for the right reason, because every other test in
    this file would stay green with nothing in the pipeline producing a
    multi-item anything.
    """
    _speak_up_to(monkeypatch, 3)
    mod, _calls = _stub_tts(monkeypatch, silent_mp3, provider)

    script = {"type": "quiz", **_item(1),
              "questions": [_item(1), _item(2), _item(3)]}

    data = mod.generate_quiz_audio_segmented(
        script, str(tmp_path / "quiz.mp3"))

    # the producer emitted a full set of ids per item, item 1 BARE
    st = data["segment_times"]
    for name in ("question", "transition", "option_a", "option_d", "think",
                 "countdown_3", "answer", "explanation"):
        assert name in st, f"item 1 lost its bare {name!r}"
        assert f"i2_{name}" in st, f"item 2 has no {name!r}"
        assert f"i3_{name}" in st, f"item 3 has no {name!r}"
    assert not any(k.startswith("i1_") for k in st), \
        "item 1 must stay unprefixed or every stored artifact is invalidated"

    # and the renderer's own projection finds three items in it
    views = quiz.quiz_item_views(data)
    assert len(views) == 3
    assert [v["question"] for v in views] == ["Q1?", "Q2?", "Q3?"]
    assert [v["correct"] for v in views] == ["B", "B", "B"]

    # each view's segment_times is BARE, so the frame function cannot tell
    # which item it is drawing
    for view in views:
        assert "question" in view["segment_times"]
        assert not any(k.startswith("i") and k[1:2].isdigit()
                       for k in view["segment_times"])

    # the items are sequential in TIME and in order
    starts = [v["segment_times"]["question"]["start"] for v in views]
    assert starts == sorted(starts), f"items overlap or run backwards: {starts}"
    assert quiz.quiz_item_at(views, starts[1] + 0.01)["question"] == "Q2?"
    assert quiz.quiz_item_at(views, starts[2] + 0.01)["question"] == "Q3?"
    assert data["duration"] > starts[2]


@pytest.mark.parametrize("provider", ["openai", "elevenlabs"])
def test_a_one_item_script_still_produces_bare_ids_only(tmp_path, monkeypatch,
                                                        silent_mp3, provider):
    """THE COMPATIBILITY PIN. A quiz with no `questions` must come out of the
    producer looking exactly as it always did, or every audio json on disk
    and the `{'option_a','answer'}` probe in resolve_quiz_timestamps break."""
    mod, _calls = _stub_tts(monkeypatch, silent_mp3, provider)

    data = mod.generate_quiz_audio_segmented(
        {"type": "quiz", **_item(1)}, str(tmp_path / "quiz.mp3"))

    st = data["segment_times"]
    assert not any("_" in k and k.split("_")[0].startswith("i") and
                   k.split("_")[0][1:].isdigit() for k in st), \
        f"a single-item quiz grew prefixed ids: {sorted(st)}"
    assert {"option_a", "answer"} <= set(st)
    assert len(quiz.quiz_item_views(data)) == 1

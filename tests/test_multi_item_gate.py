#!/usr/bin/env python3
"""A multi-item artifact's silent countdowns are declared, not dead air.

    python3 -m pytest tests/test_multi_item_gate.py

THE DEFECT, and it rejected a real artifact. qa_gate asks whether a segment
id is one the artifact declares silent:

    SILENT_SEGMENT_PREFIXES = ("countdown_",)
    if not name.startswith(SILENT_SEGMENT_PREFIXES): ...

1af342d writes items 2..n as `i2_countdown_3`, which does not START with
"countdown_". So six of the nine countdowns in a three-item quiz were
counted as UNEXPLAINED silence and the gate rejected the artifact for
14.525 s of dead air that was intentional and declared.

The rule was right to ask. The id had simply grown a prefix the rule was
written before.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import qa_gate  # noqa: E402
from segment_ids import bare, split_item  # noqa: E402


def test_the_prefix_is_parsed_in_one_place():
    assert split_item("i2_countdown_3") == (2, "countdown_3")
    assert split_item("countdown_3") == (1, "countdown_3")
    assert bare("i12_option_a") == "option_a"
    assert bare("") == ""


def test_the_renderer_and_the_gate_agree_on_what_a_prefix_is():
    """They had separate ideas of it, which is why the gate could not see
    one. Same parser now."""
    from video import quiz

    assert quiz._split_item is split_item


def _artifact():
    st, segs = {}, []
    for item, base in ((1, 0.0), (2, 40.0), (3, 80.0)):
        prefix = "" if item == 1 else f"i{item}_"
        st[f"{prefix}question"] = {"start": base, "end": base + 3}
        segs.append({"id": f"{prefix}question", "text": "¿Pregunta?"})
        for n, off in (("3", 10.0), ("2", 11.5), ("1", 13.0)):
            st[f"{prefix}countdown_{n}"] = {"start": base + off,
                                            "end": base + off + 1.5}
            segs.append({"id": f"{prefix}countdown_{n}", "text": f"[{n}]"})
    return {"segment_times": st, "segments": segs}


def test_every_items_countdown_counts_as_declared_silence():
    """THE PIN. Six of nine were invisible, which is 14.5s of 'dead air' on
    a correct artifact."""
    silent = qa_gate._silent_segment_ids(_artifact())

    for item in (1, 2, 3):
        prefix = "" if item == 1 else f"i{item}_"
        for n in ("3", "2", "1"):
            assert f"{prefix}countdown_{n}" in silent, (
                f"item {item}'s countdown_{n} is not recognised as silent")


def test_a_spoken_countdown_is_still_not_declared_silence():
    """The prefix fix must not weaken the rule it rides on: a countdown the
    artifact says is SPOKEN ('Tres.') is not a silence declaration, prefixed
    or not."""
    data = {"segment_times": {"i2_countdown_3": {"start": 1.0, "end": 2.5}},
            "segments": [{"id": "i2_countdown_3", "text": "Tres."}]}

    assert "i2_countdown_3" not in qa_gate._silent_segment_ids(data)


def test_the_gaps_between_prefixed_segments_are_explained():
    """The envelope is built from every declared bound, so the silence
    between item 1's explanation and item 2's question is intended."""
    spans = qa_gate._declared_silence_envelope(_artifact())
    assert spans, "no declared silence at all"
    # item 1's last countdown ends at 14.5, item 2's question starts at 40:
    # the stretch between them is a gap between consecutive declared bounds
    between = 20.0
    assert any(s <= between <= e for s, e in spans), (
        "the stretch between one item and the next is not explained")

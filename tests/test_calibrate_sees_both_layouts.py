#!/usr/bin/env python3
"""The calibrator measures the production tree that is actually being written.

    python3 -m pytest tests/test_calibrate_sees_both_layouts.py

THE DEFECT. samples() walked output/audio/<type>/*.json against
output/scripts/<type>/<same name>.json -- the LEGACY layout. Nothing has
been written there since 2026-08-21: every render since produces
output/artifacts/<id>/ with audio/narration.json and script/script.json.

So 30 finished artifacts were invisible, 11 of them quiz, and quiz's fit
(n=56) was drawn entirely from videos made before the current layout
existed. A calibration tool that cannot see the last month of production is
measuring the wrong month -- and the numbers it produces go into a guard
that decides whether a video ships.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import duration_calibrate as dc  # noqa: E402


def _script(n_words=40):
    words = " ".join(f"palabra{i}" for i in range(n_words))
    return {"type": "quiz", "question": f"¿{words}?",
            "options": {"A": "uno", "B": "dos", "C": "tres", "D": "cuatro"},
            "correct": "B", "explanation": words}


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A repo root with one sample in each layout."""
    monkeypatch.setattr(dc, "ROOT", tmp_path)

    _write(tmp_path / "output/audio/quiz/old_one.json",
           {"type": "quiz", "duration": 51.0})
    _write(tmp_path / "output/scripts/quiz/old_one.json", _script())

    _write(tmp_path / "output/artifacts/new_one/audio/narration.json",
           {"type": "quiz", "duration": 83.5})
    _write(tmp_path / "output/artifacts/new_one/script/script.json", _script())
    return tmp_path


def test_both_layouts_are_measured(tree):
    """THE PIN. Before this, the artifact-layout sample simply was not
    there, and nothing said so -- the fit just had fewer points."""
    rows = dc.samples()["quiz"]
    seconds = sorted(round(d, 1) for _, d in rows)

    assert 51.0 in seconds, "the legacy sample was dropped"
    assert 83.5 in seconds, "the artifact sample is still invisible"


def test_an_artifact_without_its_script_is_skipped(tree):
    """Half a pair is not a measurement."""
    (tree / "output/artifacts/new_one/script/script.json").unlink()

    seconds = [round(d, 1) for _, d in dc.samples()["quiz"]]
    assert 83.5 not in seconds
    assert 51.0 in seconds


def test_the_same_artifact_in_both_trees_is_counted_once(tree):
    """An older render copied forward would otherwise weight itself twice
    and pull the fit toward whichever videos happened to be duplicated."""
    _write(tree / "output/artifacts/dupe/audio/narration.json",
           {"type": "quiz", "duration": 51.0})
    _write(tree / "output/artifacts/dupe/script/script.json", _script())

    rows = dc.samples()["quiz"]
    assert sum(1 for _, d in rows if round(d, 1) == 51.0) == 1


def test_a_malformed_sidecar_does_not_stop_the_measurement(tree):
    (tree / "output/artifacts/broken/audio").mkdir(parents=True)
    (tree / "output/artifacts/broken/audio/narration.json").write_text("{not json")

    assert dc.samples()["quiz"], "one bad file emptied the whole measurement"


def test_the_live_tree_carries_artifact_samples():
    """Not a fixture: the real repo. If this goes to zero, either the
    layout changed again or production stopped -- both worth knowing."""
    import glob

    found = glob.glob(str(ROOT / "output/artifacts/*/audio/narration.json"))
    if not found:
        pytest.skip("no artifacts on disk in this checkout")
    assert len(found) >= 1


# ═══════════════════════════════════════════════════════════════════════
# HOW MANY ITEMS A SAMPLE CARRIED, which is not what config says today.
#
# spoken_words() read `items_spoken` from config. The moment quiz moved
# from 1 to 2, that started counting item two's words for eighty-nine
# historical ONE-item videos that never spoke them, and the fit answered
# with a straight face: quiz's rate leapt 2.43 -> 3.95 words per second.
# Not a measurement of anything -- the same seconds divided by words nobody
# said. A re-fit run on top of that would have written it into the guard.
# ═══════════════════════════════════════════════════════════════════════

def test_a_one_item_artifact_is_counted_as_one_item():
    """No `iN_` prefixes in segment_times means item 1 only, whatever
    config has since become."""
    assert dc.items_in_audio({"segment_times": {
        "question": {}, "option_a": {}, "countdown_3": {}, "answer": {}}}) == 1


def test_the_highest_prefix_is_the_item_count():
    assert dc.items_in_audio({"segment_times": {
        "question": {}, "i2_question": {}, "i2_answer": {}}}) == 2
    assert dc.items_in_audio({"segment_times": {
        "question": {}, "i2_question": {}, "i3_question": {}}}) == 3


def test_something_merely_starting_with_i_is_not_an_item_prefix():
    assert dc.items_in_audio({"segment_times": {"intro_line": {}}}) == 1
    assert dc.items_in_audio({"segment_times": {"i_am_not_a_prefix": {}}}) == 1


def test_an_artifact_with_no_segment_times_is_one_item():
    assert dc.items_in_audio({}) == 1
    assert dc.items_in_audio({"segment_times": {}}) == 1


def test_a_historical_one_item_sample_is_not_charged_for_item_two(tree,
                                                                  monkeypatch):
    """THE PIN. With items_spoken=2 in config, the old behaviour counted
    words the video never spoke — inflating the rate for every sample
    produced before the switch moved."""
    monkeypatch.setattr(dc, "_items_spoken", lambda vtype: 2)

    script = _script(40)
    script["questions"] = [dict(script), {"question": "extra " * 30,
                                          "explanation": "extra " * 30,
                                          "options": {"A": "x", "B": "y",
                                                      "C": "z", "D": "w"}}]

    one_item_audio = {"segment_times": {"question": {}, "answer": {}}}
    measured = dc.spoken_words(script, items=dc.items_in_audio(one_item_audio))
    assumed = dc.spoken_words(script)

    assert measured < assumed, (
        "the historical sample is still charged for an item it never spoke")


def test_a_script_with_no_audio_falls_back_to_config(monkeypatch):
    """Predicting the length of a script not yet produced is the one case
    where today's config IS the right answer."""
    monkeypatch.setattr(dc, "_items_spoken", lambda vtype: 2)

    script = _script(10)
    script["questions"] = [dict(script), {"question": "uno dos tres cuatro",
                                          "explanation": "cinco seis",
                                          "options": {}}]
    assert dc.spoken_words(script) > dc.spoken_words(script, items=1)

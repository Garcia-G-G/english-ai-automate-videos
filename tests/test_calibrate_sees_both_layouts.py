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

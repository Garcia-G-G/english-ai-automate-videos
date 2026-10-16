#!/usr/bin/env python3
"""The duration model's per-item silence matches what the generator splices.

    python3 -m pytest tests/test_per_item_silence.py

WHY THIS CAN ONLY BE MEASURED. PER_ITEM_SILENCE was 8.0, arrived at by
listing the pauses that looked per-item. It was wrong by 5.2 s because the
option block — transition gap, four letter-to-word gaps, three
between-option gaps — was classed as per-video, and after 1af342d the whole
block repeats per ITEM. A number derived by reading the code was wrong; the
number from running it is right, so this test runs it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


def _item(n):
    return {"question": f"¿Pregunta numero {n}?",
            "options": {"A": "apple", "B": "bread", "C": "cheese", "D": "dates"},
            "correct": "B",
            "explanation": f"Explicacion numero {n} con algo de texto."}


@pytest.fixture
def beep(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to assemble the segments")
    path = tmp_path / "beep.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.5", "-ac", "2", str(path)],
                   capture_output=True, check=True)
    return path


def _silence_for(el, monkeypatch, beep, tmp_path, n_items):
    """Total spliced silence for an n-item quiz.

    config.yaml's `items_spoken` ships at 1, so the cap is lifted here: this
    measures what an item COSTS, which the duration model needs whatever the
    switch is currently set to.
    """
    import duration_spec
    _real_spec = duration_spec.type_spec
    monkeypatch.setattr(duration_spec, "type_spec",
                        lambda vt: {**(_real_spec(vt) or {}),
                                    "items_spoken": n_items})
    monkeypatch.setattr(
        el, "generate_segment_audio",
        lambda text=None, output_path=None, voice_id=None, **k: (
            shutil.copy(beep, output_path), output_path)[1])

    total = {"s": 0.0}
    real = el.generate_silence

    def spy(duration, path, *args, **kwargs):
        total["s"] += duration
        return real(duration, path, *args, **kwargs)

    monkeypatch.setattr(el, "generate_silence", spy)

    script = {"type": "quiz", **_item(1),
              "questions": [_item(i) for i in range(1, n_items + 1)],
              "full_script": "Un guion de prueba suficientemente largo."}
    el.generate_quiz_audio_segmented(script, str(tmp_path / f"q{n_items}.mp3"))
    return total["s"]


def test_an_extra_item_costs_what_the_model_thinks_it_costs(tmp_path,
                                                            monkeypatch, beep):
    """THE PIN. Every pause the generator splices per item is in the
    constant, so a three-item prediction is not short by ten seconds."""
    import tts_elevenlabs as el
    from duration_calibrate import PER_ITEM_SILENCE

    one = _silence_for(el, monkeypatch, beep, tmp_path, 1)
    two = _silence_for(el, monkeypatch, beep, tmp_path, 2)
    three = _silence_for(el, monkeypatch, beep, tmp_path, 3)

    assert two - one == pytest.approx(three - two, abs=0.01), (
        "items are not uniform, so one constant cannot describe them")
    assert two - one == pytest.approx(PER_ITEM_SILENCE, abs=0.1), (
        f"the generator splices {two - one:.2f}s per extra item, the duration "
        f"model assumes {PER_ITEM_SILENCE}s — a 3-item quiz is predicted "
        f"{2 * (two - one - PER_ITEM_SILENCE):+.1f}s off")


def test_the_prediction_grows_with_items(tmp_path):
    from duration_calibrate import predict

    one = predict("quiz", 60, 2.6, 20.0, items=1)
    three = predict("quiz", 180, 2.6, 20.0, items=3)
    assert three > one
    # three items of the same size, not one item of triple length
    assert three - one == pytest.approx(120 / 2.6 + 2 * 13.2, abs=0.1)

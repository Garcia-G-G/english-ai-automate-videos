#!/usr/bin/env python3
"""The generator speaks as many items as config says, and no more.

    python3 -m pytest tests/test_items_spoken_switch.py

config.yaml's `items_spoken` is the declared switch -- "how many of the
authored items are actually synthesised". duration_spec divides the word
budget by it and tools/duration_calibrate measures against it, so the
duration band a video is judged by follows it automatically.

1af342d taught the generator to speak every authored item and walked past
that switch. Measured consequence, not a worry: config declared 1, the
audio carried 3, and the artifact came out at 123.9 s against a band sized
for one item -- rejected 43.9 s over the ceiling.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import items_to_speak  # noqa: E402


def _item(n):
    return {"question": f"¿Pregunta numero {n}?",
            "options": {"A": "apple", "B": "bread", "C": "cheese", "D": "dates"},
            "correct": "B", "explanation": f"Explicacion {n}."}


def _script(n_authored):
    return {"type": "quiz", **_item(1),
            "questions": [_item(i) for i in range(1, n_authored + 1)],
            "full_script": "Un guion de prueba suficientemente largo."}


@pytest.mark.parametrize("allowed,authored,spoken", [
    (1, 3, 1),          # today's config: the capability is built, door shut
    (2, 3, 2),
    (3, 3, 3),
    (3, 1, 1),          # a ceiling, not a quota — nothing is padded
    (0, 3, 1),          # a nonsense value still speaks the root item
])
def test_the_config_decides_how_many_items_are_spoken(monkeypatch, allowed,
                                                      authored, spoken):
    import duration_spec

    monkeypatch.setattr(duration_spec, "type_spec",
                        lambda vt: {"items_spoken": allowed, "fixed_words": 36})
    assert len(items_to_speak(_script(authored), "quiz")) == spoken


def test_an_unreadable_config_speaks_one_item():
    """Fails CLOSED. Speaking every authored item when the switch cannot be
    read is how a 124s video reached a gate expecting 80."""
    import duration_spec

    def boom(video_type):
        raise RuntimeError("config.yaml is unreadable")

    original = duration_spec.type_spec
    duration_spec.type_spec = boom
    try:
        assert len(items_to_speak(_script(3), "quiz")) == 1
    finally:
        duration_spec.type_spec = original


def test_the_live_config_is_what_the_generator_obeys():
    """No monkeypatch: whatever config.yaml says today is what ships."""
    import duration_spec

    allowed = int(duration_spec.type_spec("quiz")["items_spoken"])
    assert len(items_to_speak(_script(3), "quiz")) == min(3, max(1, allowed))


# ── end to end, through the real generator ───────────────────────────

@pytest.fixture
def beep(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to assemble the segments")
    path = tmp_path / "beep.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.4", "-ac", "2", str(path)],
                   capture_output=True, check=True)
    return path


def test_the_audio_carries_exactly_the_configured_items(tmp_path, monkeypatch,
                                                        beep):
    """THE PIN. Not the helper in isolation — the segment_times that come
    out of the generator, which is what the band and the gate both read."""
    import duration_spec
    import tts_elevenlabs as el

    monkeypatch.setattr(duration_spec, "type_spec",
                        lambda vt: {"items_spoken": 2, "fixed_words": 36})
    monkeypatch.setattr(
        el, "generate_segment_audio",
        lambda text=None, output_path=None, voice_id=None, **k: (
            shutil.copy(beep, output_path), output_path)[1])

    data = el.generate_quiz_audio_segmented(_script(3), str(tmp_path / "q.mp3"))
    st = data["segment_times"]

    assert "question" in st and "i2_question" in st
    assert "i3_question" not in st, (
        "a third item was synthesised though config allows two — paid for "
        "and pushing the artifact past its duration band")

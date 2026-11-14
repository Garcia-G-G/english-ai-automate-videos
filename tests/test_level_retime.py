#!/usr/bin/env python3
"""STEP 60 §4: a level narration gets today's thinks with its words untouched. No API, no render."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import level_retime as R  # noqa: E402


def _meta():
    """say_it_level, two rows: a short sentence (3 s today) and a long one (5 s), both rendered at 3 s."""
    times = {"intro": (0.0, 1.0), "think_1": (1.5, 4.5), "answer_1": (4.5, 5.5),
             "think_2": (5.9, 8.9), "answer_2": (8.9, 10.0), "outro": (10.5, 11.0)}
    st = {k: {"start": a, "end": b, "duration": round(b - a, 3)} for k, (a, b) in times.items()}
    return {"type": "say_it_level", "duration": 11.0, "segment_times": st,
            "segments": [{"id": k, "text": "x", **v} for k, v in st.items()],
            "items": [{"spanish": "Hola.", "english": "Hi."},
                      {"spanish": "¿Me trae la cuenta, por favor?", "english": "The check, please."}]}


def test_only_the_long_sentence_gets_more_silence_and_the_words_keep_their_samples():
    samples = (np.arange(int(11.0 * R.RATE)) % 30000).astype(np.int16)    # every sample tells its time
    out, new = R.retime(_meta(), samples)
    st = out["segment_times"]
    assert st["think_1"]["duration"] == pytest.approx(3.0)
    assert st["think_2"]["duration"] == pytest.approx(5.0)
    assert st["answer_2"]["start"] == pytest.approx(10.9) and st["outro"]["end"] == pytest.approx(13.0)
    assert out["duration"] == pytest.approx(13.0, abs=1e-3) and len(new) == len(samples) + 2 * R.RATE
    # the second answer is the very same audio, two seconds later; the gap is digital silence
    a, b = int(8.9 * R.RATE), int(10.9 * R.RATE)
    assert np.array_equal(new[b:b + R.RATE], samples[a:a + R.RATE])
    assert not new[a:b].any()
    assert [s["start"] for s in out["segments"]] == [st[s["id"]]["start"] for s in out["segments"]]


def test_a_think_that_would_shrink_is_refused():
    meta = _meta()
    meta["segment_times"]["think_1"]["end"] = meta["segment_times"]["answer_1"]["start"] = 6.0
    with pytest.raises(ValueError, match="think_1 would shrink"):
        R.retime(meta, np.zeros(int(11.0 * R.RATE), dtype=np.int16))

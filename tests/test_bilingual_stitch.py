"""STEP 76 §2: the Shorts' bilingual path stitches like the lessons — next_text only at a
switch, an onset gate with retakes, trimmed clips with punctuation gaps, one level."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import loudness  # noqa: E402
import stitch  # noqa: E402
import tts_bilingual as TB  # noqa: E402

SETTINGS = {"voice_id": "v", "model_id": "eleven_turbo_v2_5", "narration_lang": "es", "english_lang": "en",
            "native_language": "es", "stability": 0.5, "similarity": 0.8, "style": 0.05, "speed": 1.0,
            "english_speed_factor": 0.92}
SCRIPT = {"type": "educational",
          "full_script": "Hola a todos, hoy aprendemos algo. [[I have a car.]] Y yo tengo uno, claro que sí."}
LEAD, SPEECH, TAIL = 0.5, 1.0, 0.8


def _fake_clip(path, db):
    t = np.arange(int(SPEECH * loudness.RATE)) / loudness.RATE
    tone = np.sin(2 * np.pi * 220 * t) * 10 ** (db / 20) * np.sqrt(2)
    x = np.concatenate([np.zeros(int(LEAD * loudness.RATE)), tone, np.zeros(int(TAIL * loudness.RATE))])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(loudness.RATE), "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-q:a", "2", str(path)], input=x.astype("<f8").tobytes(), check=True, timeout=30)


@pytest.fixture
def fake_tts(monkeypatch):
    sent = []

    def synth(call, out_path, settings, take=0):
        sent.append(dict(call))
        _fake_clip(out_path, -18.0 if call["is_english"] else -24.0)
        return {"duration": LEAD + SPEECH + TAIL,
                "words": [{"word": "w", "start": LEAD, "end": LEAD + SPEECH}]}
    monkeypatch.setattr(TB, "_synthesize_segment", synth)
    onsets = iter([{"start_db": -2.0, "fragment": None, "doubled_onset": "fragment"}])   # first take: dirty
    clean = {"start_db": -40.0, "fragment": None, "doubled_onset": None}
    monkeypatch.setattr(stitch, "onset_values", lambda path: next(onsets, clean))
    return sent


def test_only_next_text_is_sent_at_a_language_switch():
    calls = TB.plan_calls(SCRIPT, SETTINGS)
    assert [c["is_english"] for c in calls] == [False, True, False]
    assert all(c["previous_text"] is None for c in calls)
    assert calls[0]["next_text"] == calls[1]["text"] and calls[1]["next_text"] == calls[2]["text"]
    assert calls[0]["pause_after"] == stitch.GAP_AFTER["."]


def test_a_dirty_onset_is_re_asked_and_clips_are_trimmed_gapped_and_levelled(tmp_path, fake_tts):
    out = tmp_path / "n.mp3"
    result = TB.generate_bilingual_narration(SCRIPT, str(out), settings=SETTINGS, dry_run=False)
    calls = result["tts_calls"]
    assert len(fake_tts) == 4 and calls[0]["takes"] == 2 and calls[0]["onset"]["clean"]
    assert all(c["takes"] == 1 for c in calls[1:])
    # trimmed: ~0.5 s of lead silence gone, so each word starts near its clip's start
    assert all(c["trim_start"] == pytest.approx(LEAD - 0.08, abs=0.03) for c in calls)
    words = result["words"]
    assert words[0]["start"] == pytest.approx(0.08, abs=0.03)
    # the gap from one clip's speech to the next is the trim pads plus the full stop's 0.30 s
    gap = words[1]["start"] - words[0]["end"]
    assert gap == pytest.approx(0.08 + stitch.GAP_AFTER["."] + 0.08, abs=0.06)
    # levelled to the median (the Spanish clips): the English clip 6 dB louder comes down
    assert calls[0]["gain_db"] == pytest.approx(0, abs=0.3) and calls[1]["gain_db"] == pytest.approx(-6, abs=0.5)
    levels = loudness.segment_levels(loudness.decode(out), [
        {"id": str(i), "text": "x", "start": w["start"], "end": w["end"]} for i, w in enumerate(words)])
    assert loudness.spread(levels) <= 1.5
    assert result["duration"] == pytest.approx(words[-1]["end"] + 0.08, abs=0.1)


def test_levelled_clips_fade_at_their_edges_and_leave_headroom(tmp_path):
    loud = tmp_path / "loud.mp3"
    t = np.arange(int(0.5 * loudness.RATE)) / loudness.RATE
    x = np.sin(2 * np.pi * 220 * t) * 0.9                         # ends on a loud sample
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(loudness.RATE), "-ac", "1", "-i", "-",
                    str(loud)], input=x.astype("<f8").tobytes(), check=True, timeout=30)
    quiet = tmp_path / "quiet.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(loudness.RATE), "-ac", "1", "-i", "-",
                    str(quiet)], input=(x * 0.1).astype("<f8").tobytes(), check=True, timeout=30)
    out = loudness.level_clips([quiet, loud, quiet], tmp_path)
    y = loudness.decode(out[1]["path"])
    assert abs(y[-1]) < 0.01 and abs(y[0]) < 0.01                  # faded in and out
    assert np.max(np.abs(loudness.decode(out[0]["path"]))) <= loudness.CLIP_CEILING + 1e-3

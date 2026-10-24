"""STEP 76 §6: one PCM timeline for every generator."""
import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_common import Timeline  # noqa: E402


def _tone(path, seconds, rate=44100, lead=0.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*330*t)*gte(t,{lead})':s={rate}:d={seconds}", "-ac", "1",
                    str(path)], check=True, timeout=30)
    return path


def _decode(path, rate=44100):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
                         capture_output=True, check=True, timeout=30).stdout
    return np.frombuffer(raw, "<f4")


def _onsets(x, rate=44100, frame=0.005):
    n = int(rate * frame)
    db = 20 * np.log10(np.sqrt((x[: x.size // n * n].reshape(-1, n) ** 2).mean(1)) + 1e-9)
    loud = db > -30
    return [i * frame for i in range(1, loud.size) if loud[i] and not loud[i - 1]] + ([0.0] if loud[0] else [])


def test_the_contract_and_the_clock(tmp_path):
    tl = Timeline(tmp_path)
    a = _tone(tmp_path / "a.mp3", 1.0)
    start, end, dur, speech_end = tl.add_audio(str(a))
    assert start == 0.0 and end == pytest.approx(dur) and 0 < speech_end <= end + 0.01
    assert tl.add_silence(0.5) == (pytest.approx(end), pytest.approx(end + 0.5))
    assert tl.time == pytest.approx(end + 0.5)


def test_each_piece_lands_on_its_declared_sample(tmp_path):
    a = _tone(tmp_path / "a.mp3", 1.0)
    b = _tone(tmp_path / "b.mp3", 0.8)
    tl = Timeline(tmp_path)
    tl.add_audio(str(a), duration=0.7)                 # declared shorter than the file: cut at 0.7
    tl.add_silence(0.6)
    s_b, _, _, _ = tl.add_audio(str(b))
    out = tmp_path / "n.mp3"
    assert tl.finalize(str(out)) == pytest.approx(tl.time, abs=0.001)
    x = _decode(out)
    on = sorted(_onsets(x))
    assert on[0] == pytest.approx(0.0, abs=0.01) and on[1] == pytest.approx(s_b, abs=0.01) and s_b == pytest.approx(1.3)
    gap = x[int(0.75 * 44100):int(1.25 * 44100)]
    assert 1e-6 < np.sqrt(np.mean(gap ** 2)) < 10 ** (-50 / 20)       # room tone, not digital zero, not loud


def test_room_tone_is_reproducible(tmp_path):
    outs = []
    for n in (1, 2):
        tl = Timeline(tmp_path / f"t{n}")
        (tmp_path / f"t{n}").mkdir()
        tl.add_silence(0.8)
        tl.finalize(str(tmp_path / f"s{n}.mp3"))
        outs.append(_decode(tmp_path / f"s{n}.mp3"))
    assert np.array_equal(*outs)


def test_the_output_keeps_the_timelines_rate(tmp_path):
    tl = Timeline(tmp_path, sample_rate=24000)
    tl.add_audio(str(_tone(tmp_path / "a.mp3", 0.5, rate=24000)))
    tl.finalize(str(tmp_path / "o.mp3"))
    rate = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate", "-of", "json",
                                      str(tmp_path / "o.mp3")], capture_output=True, text=True, check=True).stdout)
    assert rate["streams"][0]["sample_rate"] == "24000"


@pytest.mark.parametrize("rel", ["src/tts_elevenlabs.py", "src/tts_openai.py", "src/tts_google.py", "src/tts_bilingual.py"])
def test_no_generator_keeps_its_own_closures_or_concat(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(text)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("add_audio", "add_silence")]
    assert "audio_files" not in text and "'-f', 'concat'" not in text and '"-f", "concat"' not in text
    assert "Timeline(" in text

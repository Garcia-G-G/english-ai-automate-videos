"""STEP 75 §5: segments levelled to their median (±6 dB), −14 LUFS / ≤ −1.5 dBTP, same length."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import loudness as L  # noqa: E402


def _speechlike(seconds, db, seed):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * L.RATE)) / L.RATE
    voice = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) / k for k, f in enumerate((180, 360, 720, 1440), 1))
    voice *= 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t) ** 2          # syllables
    return voice / np.sqrt(np.mean(voice ** 2)) * 10 ** (db / 20)


def _narration(tmp_path, levels=(-30.0, -20.0)):
    parts, segments, t = [], [], 0.0
    for i, db in enumerate(levels):
        x = _speechlike(3.0, db, i)
        parts += [x, np.zeros(int(1.0 * L.RATE))]
        segments += [{"id": f"s{i}", "text": "hola", "start": t, "end": t + 3.0},
                     {"id": f"think{i}", "text": "[silence]", "start": t + 3.0, "end": t + 4.0}]
        t += 4.0
    audio = tmp_path / "n.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(L.RATE), "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-q:a", "2", str(audio)],
                   input=np.concatenate(parts).astype("<f8").tobytes(), check=True, timeout=60)
    data = tmp_path / "n.json"
    data.write_text(json.dumps({"segments": segments}))
    return audio, data, segments


def test_segments_are_levelled_then_normalised_and_nothing_moves(tmp_path):
    audio, data, segments = _narration(tmp_path)
    before = audio.read_bytes()
    info = L.prepare_narration(audio, data, tmp_path / "out.wav")
    assert info["spread_before"] == pytest.approx(10.0, abs=0.7)
    assert info["spread_after"] <= 1.0
    assert info["gains"]["s0"] == pytest.approx(5.0, abs=0.7) and info["gains"]["s1"] == pytest.approx(-5.0, abs=0.7)
    assert info["loudnorm"]["normalization_type"] == "linear"
    assert info["samples"][0] == info["samples"][1]
    m = L.measure(tmp_path / "out.wav")
    assert abs(m["I"] - L.TARGET_I) <= 0.5 and m["TP"] <= -1.5
    assert audio.read_bytes() == before                     # the cached narration is never rewritten
    assert not (tmp_path / "out.leveled.wav").exists()


def test_a_gain_is_clamped_to_six_db(tmp_path):
    audio, data, _ = _narration(tmp_path, levels=(-40.0, -20.0, -20.0))
    info = L.prepare_narration(audio, data, tmp_path / "out.wav")
    assert info["gains"]["s0"] == pytest.approx(6.0)


def test_the_gate_flags_loud_peaky_or_uneven_audio(tmp_path):
    audio, data, segments = _narration(tmp_path)
    g = L.gate(audio, segments)
    assert any(f.startswith("segment_spread:") for f in g["flags"])
    assert any(f.startswith("loudness:") for f in g["flags"])
    L.prepare_narration(audio, data, tmp_path / "out.wav")
    assert L.gate(tmp_path / "out.wav", segments)["flags"] == []


def test_silence_is_copied_not_normalised(tmp_path):
    src = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2",
                    str(src)], check=True, timeout=30)
    assert "silence" in L.loudnorm_two_pass(src, tmp_path / "d.wav")["normalization_type"]


def test_the_render_muxes_the_normalised_copy_and_removes_it():
    src = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    body = src[src.index("def render_video("):src.index("def finalize_video(")]
    assert "loudness.prepare_narration(audio_path, data_path, narration)" in body
    assert '"-a", str(narration.resolve()),' in body and "narration.unlink(missing_ok=True)" in body

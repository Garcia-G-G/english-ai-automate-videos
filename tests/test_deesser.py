"""STEP 80 §00: one split-band de-esser on every narration, measured."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import deesser as D  # noqa: E402

RATE = 44100


def _write(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def _voice_with_esses(seconds=6.0):
    """A voiced tone (180 Hz with harmonics) with «s» bursts of 6–9 kHz noise every second."""
    rng = np.random.default_rng(5)
    t = np.arange(int(seconds * RATE)) / RATE
    tone = sum(0.12 / k * np.sin(2 * np.pi * 180 * k * t) for k in range(1, 12))
    noise = rng.standard_normal(t.size)
    spec = np.fft.rfft(noise)
    f = np.fft.rfftfreq(t.size, 1 / RATE)
    spec[(f < 6000) | (f > 9000)] = 0
    hiss = np.fft.irfft(spec, t.size)
    hiss = hiss / np.abs(hiss).max() * 0.5
    gate = ((t % 1.0) > 0.55) & ((t % 1.0) < 0.75)          # 200 ms «s» each second
    tone_part = tone * ~gate
    return tone_part + hiss * gate, tone_part, gate


def _band_db(x, lo, hi):
    spec = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(x.size, 1 / RATE)
    return 10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-20)


@pytest.fixture(scope="module")
def processed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("deess")
    x, tone, gate = _voice_with_esses()
    _write(tmp / "in.wav", x)
    measure = D.deess(tmp / "in.wav", tmp / "out.wav", dict(D.DEFAULTS))
    y = D._decode(tmp / "out.wav")[:x.size]
    return x, y, gate, measure


def test_the_esses_drop_at_least_5_db(processed):
    x, y, gate, _m = processed
    assert _band_db(x[gate], 6000, 9000) - _band_db(y[:gate.size][gate], 6000, 9000) >= 5.0


def test_the_voiced_tone_is_unchanged_within_0_3_db(processed):
    x, y, gate, _m = processed
    assert abs(_band_db(x[~gate], 100, 4000) - _band_db(y[:gate.size][~gate], 100, 4000)) <= 0.3


def test_the_measure_passes_the_gate_band(processed):
    *_x, m = processed
    assert m["enabled"] and m["sibilant_frames"] > 0
    assert D.SIB_MIN_DB <= m["sibilant_hf_db"] <= D.SIB_MAX_DB, m
    assert m["other_hf_db"] <= D.NONSIB_MAX_DB and abs(m["body_db"]) <= D.BODY_MAX_DB, m
    assert D.flags(m) == []


def test_the_threshold_follows_the_narrations_loudness(tmp_path):
    x, _t, _g = _voice_with_esses(3.0)
    _write(tmp_path / "a.wav", x)
    _write(tmp_path / "b.wav", x * 0.25)                     # 12 dB quieter
    a = D.deess(tmp_path / "a.wav", tmp_path / "a_o.wav", dict(D.DEFAULTS))
    b = D.deess(tmp_path / "b.wav", tmp_path / "b_o.wav", dict(D.DEFAULTS))
    assert abs((a["input_lufs"] - a["threshold_db"]) - 12) < 0.11
    assert abs(a["sibilant_hf_db"] - b["sibilant_hf_db"]) < 1.0      # level-independent


def test_the_gate_refuses_too_little_too_much_and_a_dulled_voice():
    assert D.flags({"enabled": True, "sibilant_hf_db": 3.0, "other_hf_db": 0.2, "body_db": 0.0})
    assert D.flags({"enabled": True, "sibilant_hf_db": 14.0, "other_hf_db": 0.2, "body_db": 0.0})
    assert D.flags({"enabled": True, "sibilant_hf_db": 8.0, "other_hf_db": 1.5, "body_db": 0.0})
    assert D.flags({"enabled": True, "sibilant_hf_db": 8.0, "other_hf_db": 0.2, "body_db": 0.85})
    assert D.flags({"enabled": False}) == [] and D.flags(None) == []


def test_the_config_block_is_read_without_yaml():
    cfg = D.settings()
    assert cfg == {"enabled": True, "split_hz": 5500.0, "below_lufs_db": 12.0, "ratio": 4.0}
    assert "acrossover=split=5500:order=4th" in D.chain(-28.0, cfg) and "ratio=4" in D.chain(-28.0, cfg)


def test_combine_weighs_each_clip_by_its_frames():
    c = D.combine([{"enabled": True, "sibilant_hf_db": 8.0, "other_hf_db": 0.2, "body_db": 0.0,
                    "sibilant_frames": 30, "voiced_frames": 100},
                   {"enabled": True, "sibilant_hf_db": 6.0, "other_hf_db": 0.6, "body_db": 0.1,
                    "sibilant_frames": 10, "voiced_frames": 300}])
    assert c["sibilant_hf_db"] == 7.5 and c["clips"] == 2 and c["voiced_frames"] == 400


# ── every path calls the same function ───────────────────────────────

def test_shorts_and_series_de_ess_inside_prepare_narration():
    src = (ROOT / "src" / "loudness.py").read_text(encoding="utf-8")
    body = src[src.index("def prepare_narration"):src.index("def gate(")]
    assert "deesser.deess(audio_path" in body and body.index("deesser.deess") < body.index("loudnorm_two_pass")
    assert "loudness.prepare_narration" in (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert "loudness.prepare_narration" in (ROOT / "src" / "video" / "series" / "render.py").read_text(encoding="utf-8")


def test_lessons_de_ess_each_beat_with_the_same_function():
    voices = (ROOT / "experiments" / "manim_voiceover_poc" / "voices.py").read_text(encoding="utf-8")
    assert "_deesser().deess(" in voices and "import deesser" in voices


def test_every_gate_reads_the_measure():
    assert "deesser_flags(de)" in (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert "deesser.flags(info.get(\"deesser\"))" in (ROOT / "src" / "video" / "series" / "gate.py").read_text(encoding="utf-8")
    assert "deesser.flags(de)" in (ROOT / "experiments" / "manim_voiceover_poc" / "renders.py").read_text(encoding="utf-8")


def test_prepare_narration_leaves_the_measure_for_the_gate(tmp_path):
    import loudness
    x, _t, _g = _voice_with_esses(4.0)
    _write(tmp_path / "v.wav", x)
    (tmp_path / "d.json").write_text(json.dumps({"segments": [{"start": 0.0, "end": 4.0, "text": "x"}]}))
    info = loudness.prepare_narration(tmp_path / "v.wav", tmp_path / "d.json", tmp_path / "n.wav")
    saved = json.loads(loudness.deesser_path(tmp_path / "n.wav").read_text())
    assert info["deesser"] == saved and saved["enabled"] and saved["sibilant_hf_db"] >= 5.0
    assert not (tmp_path / "n.deessed.wav").exists()

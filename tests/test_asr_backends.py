"""asr_timings: OpenRouter (Scribe v2) first, local mlx-whisper second; no paid call outside a panel job."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import asr_timings as A  # noqa: E402

WORDS = [{"word": "spill", "start": 0.1, "end": 0.3}]


def test_openrouter_answers_first(tmp_path, monkeypatch):
    f = tmp_path / "a.mp3"; f.write_bytes(b"x")
    monkeypatch.setattr(A, "_words_from_openrouter", lambda p, l: WORDS)
    monkeypatch.setattr(A, "_words_from_local", lambda p, l: (_ for _ in ()).throw(AssertionError("local ran")))
    assert A.transcribe_words(f)[0]["word"] == "spill" and A.backend_name().startswith("openrouter:")


def test_local_answers_when_openrouter_does_not(tmp_path, monkeypatch):
    f = tmp_path / "a.mp3"; f.write_bytes(b"x")
    monkeypatch.setattr(A, "_words_from_openrouter", lambda p, l: None)
    monkeypatch.setattr(A, "_words_from_local", lambda p, l: WORDS)
    assert A.transcribe_words(f) and A.backend_name().startswith("local:")


def test_no_paid_transcription_outside_a_panel_job(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    f = tmp_path / "a.mp3"; f.write_bytes(b"x")
    assert A._words_from_openrouter(f, None) is None          # pytest is never granted (voice_lock)

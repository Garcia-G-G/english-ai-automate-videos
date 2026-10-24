"""STEP 76 §5: costs that are true — once per 2xx, one price table, retries only where they
can help, a per-video budget, no hidden paid transcriber, no v3 respellings."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "manim_voiceover_poc"))

import cost_tracker as CT  # noqa: E402
import tts_elevenlabs as TE  # noqa: E402

KW = dict(voice_id="v", text="spoon.", model_id="eleven_v3", output_format="mp3_44100_128")


class Err(Exception):
    def __init__(self, status, headers=None):
        super().__init__(f"HTTP {status}")
        self.status_code, self.headers = status, headers or {}


class Flaky:
    """convert() fails with the given errors in order, then streams bytes."""

    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0
        self.text_to_speech = self

    def convert(self, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return iter([b"ID3fake-audio"])


@pytest.fixture(autouse=True)
def _fake_client_may_be_asked(monkeypatch):
    """Every client in this file is a fake that never reaches ElevenLabs, so the STEP 79 §00
    lock (which refuses before any request) is opened for it here, and only here."""
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)


@pytest.fixture
def tracker(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    t = CT.reset_tracker("costs-test")
    t.sleeps = sleeps
    return t


def _tts_rows(t):
    return [e for e in t.entries if e["api_type"] == "elevenlabs_tts"]


def test_one_price_table_for_shorts_and_lessons():
    import gen_audio
    import manim_studio
    for model in ("eleven_v3", "eleven_v4", "eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5"):
        assert model in CT.PRICING
    assert gen_audio.PRICE_PER_1K_CHARS == CT.tts_price_per_1k(gen_audio.ONE_REQUEST_MODEL)
    assert manim_studio.PRICE_PER_1K_CHARS == CT.tts_price_per_1k(manim_studio.TTS_MODELS[0])


def test_a_retried_5xx_is_logged_once_after_the_success(tmp_path, tracker):
    client = Flaky(Err(503), Err(429, {"retry-after": "1.5"}))
    TE._elevenlabs_with_retry(client, str(tmp_path / "a.mp3"), **KW)
    assert client.calls == 3 and len(_tts_rows(tracker)) == 1
    assert tracker.sleeps == [1.0, 1.5]                              # backoff, then Retry-After


def test_a_client_error_is_not_retried_and_not_billed(tmp_path, tracker):
    client = Flaky(Err(401))
    with pytest.raises(Err):
        TE._elevenlabs_with_retry(client, str(tmp_path / "a.mp3"), **KW)
    assert client.calls == 1 and _tts_rows(tracker) == [] and tracker.sleeps == []


def test_the_budget_stops_the_job_before_the_next_call(tmp_path, tracker, monkeypatch):
    monkeypatch.setattr(CT, "per_video_tts_usd", lambda: 0.25)
    tracker.log_elevenlabs_tts(characters=1100, model="eleven_v3")   # $0.242 already spent
    client = Flaky()
    with pytest.raises(CT.TTSBudgetExceeded, match="Presupuesto de voz superado") as caught:
        TE._elevenlabs_with_retry(client, str(tmp_path / "a.mp3"), **{**KW, "text": "x" * 100})
    assert client.calls == 0 and "per_video_tts_usd" in str(caught.value)
    TE._elevenlabs_with_retry(client, str(tmp_path / "b.mp3"), **{**KW, "text": "x" * 20})   # $0.0044 fits
    assert client.calls == 1


def test_the_budget_reads_config():
    assert CT.per_video_tts_usd() == 0.30          # Garcia's per-Short budget (STEP 77 §0)


def test_a_failed_bilingual_run_is_the_jobs_failure_not_a_paid_fallback(tmp_path, monkeypatch):
    import pipeline
    import tts_bilingual
    from tts_providers.elevenlabs_provider import ElevenLabsTTSProvider
    monkeypatch.setattr(tts_bilingual, "generate_bilingual_narration",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(TE, "generate_segment_audio", lambda *a, **k: pytest.fail("fell back to the single call"))
    with pytest.raises(pipeline.TTSError, match="boom"):
        ElevenLabsTTSProvider(voice_id="v").generate_from_script(
            {"type": "educational", "full_script": "Hola mundo, esto es una prueba."}, str(tmp_path / "a.mp3"))
    src = (ROOT / "src" / "tts_providers" / "elevenlabs_provider.py").read_text(encoding="utf-8")
    assert "extract_timestamps_whisper" not in src and "transcribe_words" in src


def test_v3_gets_no_respellings_the_older_models_keep_them():
    text = "Mi schedule pasa through el día."
    words = {"schedule", "through"}
    assert TE.enhance_bilingual_text(text, words, "eleven_v3") == text
    assert TE.enhance_bilingual_text(text, words, "eleven_multilingual_v2") != text

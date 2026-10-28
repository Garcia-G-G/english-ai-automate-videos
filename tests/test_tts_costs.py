"""STEP 76 §5: costs that are true — one price table, a per-video budget, no hidden paid
transcriber, no v3 respellings. (The direct ElevenLabs retry/billing path is gone, 2026-10-27;
OpenRouter's retries and caps are in test_openrouter_tts.)"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "manim_voiceover_poc"))

import cost_tracker as CT  # noqa: E402
import tts_elevenlabs as TE  # noqa: E402

KW = dict(voice_id="v", text="spoon.", model_id="eleven_v3", output_format="mp3_44100_128")


@pytest.fixture(autouse=True)
def _fake_client_may_be_asked(monkeypatch):
    """Nothing in this file reaches the network, so the STEP 79 §00 lock (which refuses
    before any request) is opened here, and only here."""
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)


def test_one_price_table_for_shorts_and_lessons():
    import gen_audio
    import manim_studio
    for model in ("eleven_v3", "eleven_v4", "eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5"):
        assert model in CT.PRICING
    assert gen_audio.PRICE_PER_1K_CHARS == CT.tts_price_per_1k(gen_audio.ONE_REQUEST_MODEL)
    assert manim_studio.PRICE_PER_1K_CHARS == CT.tts_price_per_1k(manim_studio.TTS_MODELS[0])


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

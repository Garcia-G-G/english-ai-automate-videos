"""STEP 76 §4: every TTS call is cached by content; a second run of a script asks nothing."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts_cache  # noqa: E402

SETTINGS = {"voice_id": "v", "model_id": "eleven_turbo_v2_5", "narration_lang": "es", "english_lang": "en",
            "native_language": "es", "stability": 0.5, "similarity": 0.8, "style": 0.05, "speed": 1.0,
            "english_speed_factor": 0.92}
SCRIPT = {"type": "educational",
          "full_script": "Hola a todos, hoy aprendemos algo. [[I have a car.]] Y yo tengo uno, claro que sí."}


@pytest.fixture(autouse=True)
def _fake_client_may_be_asked(monkeypatch):
    """Every client in this file is a fake that never reaches ElevenLabs, so the STEP 79 §00
    lock (which refuses before any request) is opened for it here, and only here."""
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)


def _mp3_bytes(tmp_path, seconds=1.2):
    path = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='0.3*sin(2*PI*220*t)*between(t,0.3,{seconds - 0.3})':s=44100:d={seconds}",
                    "-ac", "1", str(path)], check=True, timeout=30)
    return path.read_bytes()


class FakeTTS:
    """tts_openrouter.speak, counting HTTP calls (the only voice request there is)."""

    def __init__(self, audio):
        self.audio, self.calls = audio, 0

    def __call__(self, kwargs, out_path, **k):
        self.calls += 1
        Path(out_path).write_bytes(self.audio)


def test_a_second_run_of_the_same_script_makes_no_http_call(tmp_path, monkeypatch):
    import stitch
    import tts_bilingual as TB
    import tts_openrouter
    fake = FakeTTS(_mp3_bytes(tmp_path))
    monkeypatch.setattr(tts_openrouter, "speak", fake)
    monkeypatch.setattr(TB, "_local_words", lambda *a: None)    # no transcriber: the words are estimated
    monkeypatch.setattr(stitch, "onset_values", lambda p: {"start_db": -40.0, "fragment": None,
                                                           "doubled_onset": None, "first_dbfs": -90.0})
    first = TB.generate_bilingual_narration(SCRIPT, str(tmp_path / "a.mp3"), settings=SETTINGS, dry_run=False)
    asked = fake.calls
    assert asked == 3
    second = TB.generate_bilingual_narration(SCRIPT, str(tmp_path / "b.mp3"), settings=SETTINGS, dry_run=False)
    assert fake.calls == asked                                   # zero HTTP calls the second time
    assert [w["start"] for w in second["words"]] == [w["start"] for w in first["words"]]
    assert tts_cache.STATS["hits"] == 3
    import loudness
    import numpy as np
    assert np.array_equal(loudness.decode(tmp_path / "a.mp3"), loudness.decode(tmp_path / "b.mp3"))   # seeded room tone


def test_the_key_covers_what_changes_the_audio_and_the_take():
    base = {"voice_id": "v", "model_id": "m", "text": "hola", "language_code": "es",
            "output_format": "mp3_44100_128", "voice_settings": {"stability": 0.5}}
    k = tts_cache.key(base)
    for change in ({"text": "hola."}, {"voice_id": "w"}, {"model_id": "n"}, {"language_code": "en"},
                   {"previous_text": "x"}, {"next_text": "y"}, {"voice_settings": {"stability": 0.6}},
                   {"output_format": "pcm_44100"}):
        assert tts_cache.key({**base, **change}) != k, change
    assert tts_cache.key(base, take=1) != k                      # a retake is not the cached take 0
    assert tts_cache.key(dict(reversed(list(base.items())))) == k


def test_the_level_path_convert_is_cached_per_take(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    import tts_openrouter
    fake = FakeTTS(_mp3_bytes(tmp_path))
    monkeypatch.setattr(tts_openrouter, "speak", fake)
    kw = dict(voice_id="v", text="spoon.", model_id="eleven_v3", output_format="mp3_44100_128")
    TE._elevenlabs_with_retry(str(tmp_path / "0.mp3"), take=0, **kw)
    TE._elevenlabs_with_retry(str(tmp_path / "1.mp3"), take=1, **kw)
    TE._elevenlabs_with_retry(str(tmp_path / "0b.mp3"), take=0, **kw)
    assert fake.calls == 2 and (tmp_path / "0b.mp3").read_bytes() == (tmp_path / "0.mp3").read_bytes()


def test_the_cache_is_never_the_real_one_under_tests():
    assert "_output" in str(tts_cache.CACHE_DIR)

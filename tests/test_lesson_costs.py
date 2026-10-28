"""STEP 79 §1: the lesson studio logs every ElevenLabs request in output/costs/, as the Shorts do:
characters, lesson, beat, reason. No voice spend goes unlogged."""
import base64
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "manim_voiceover_poc"))

import cost_tracker  # noqa: E402
import gen_audio  # noqa: E402
import voice_lock  # noqa: E402


class _Answer(io.BytesIO):
    headers = {"request-id": "r1"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def costs(tmp_path, monkeypatch):
    """A fake ElevenLabs (never the network) and a scratch costs folder."""
    monkeypatch.setattr(cost_tracker, "COSTS_DIR", tmp_path)
    monkeypatch.setattr(voice_lock, "locked", lambda: False)     # the fake answers; nothing is sent
    body = {"audio_base64": base64.b64encode(b"mp3").decode(),
            "alignment": {"characters": list("Hola"), "character_start_times_seconds": [0, .1, .2, .3],
                          "character_end_times_seconds": [.1, .2, .3, .4]}}
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Answer(json.dumps(body).encode()))
    monkeypatch.setattr(gen_audio, "COST_CONTEXT", {"lesson": None, "beat": None, "reason": "probe"})
    return tmp_path


def _rows(folder):
    return [json.loads(line) for f in sorted(folder.glob("costs_*.jsonl")) for line in f.read_text().splitlines()]


def test_every_answered_request_is_one_row_with_lesson_beat_and_reason(costs):
    gen_audio.COST_CONTEXT.update(lesson="make-vs-do", beat="b07", reason="beat")
    gen_audio.eleven_segment("k" * 20, "v", "Hola, ¿qué tal?", "es", "eleven_v4", {})
    gen_audio.COST_CONTEXT["reason"] = "onset_retake"
    gen_audio.eleven_segment("k" * 20, "v", "Hola, ¿qué tal?", "es", "eleven_v4", {})
    rows = _rows(costs)
    assert [(r["lesson"], r["beat"], r["reason"], r["characters"]) for r in rows] == [
        ("make-vs-do", "b07", "beat", 15), ("make-vs-do", "b07", "onset_retake", 15)]
    assert all(r["api_type"] == "elevenlabs_tts" and r["video_id"] == "lesson_make-vs-do" and r["cost_usd"] > 0
               for r in rows)


def test_a_probe_calling_the_segment_directly_is_logged_as_one(costs):
    gen_audio.eleven_segment("k" * 20, "v", "Hi", "en", "eleven_v4", {})
    assert [(r["reason"], r["video_id"]) for r in _rows(costs)] == [("probe", "lesson_probe")]


def test_a_refused_request_is_not_billed_and_not_logged(costs, monkeypatch):
    def refuse(*a, **k):
        raise urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b"quota_exceeded"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(urllib.error.HTTPError):
        gen_audio.eleven_segment("k" * 20, "v", "Hola", "es", "eleven_v4", {})
    assert _rows(costs) == []


def test_the_main_loop_names_the_lesson_and_beat_before_asking():
    src = (ROOT / "experiments" / "manim_voiceover_poc" / "gen_audio.py").read_text(encoding="utf-8")
    assert 'COST_CONTEXT.update(beat=beat["id"], reason="beat")' in src
    assert 'COST_CONTEXT["reason"] = "beat" if attempt == 0 else "onset_retake"' in src

"""Garcia (STEP 80): «the cut when the voice changes from Spanish to English is very noticeable».
With v4 through OpenRouter, the series says a mixed sentence in one request (the lessons' choice
by ear, STEP 55): no seam inside a sentence."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import tts_bilingual as B  # noqa: E402


def _settings(**extra):
    return {**B.resolve_settings(), "model_id": "eleven_v3", **extra}


def _series_data():
    from video.series import beats
    s = json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / "hc_c010.json").read_text(encoding="utf-8"))
    return {"type": "hecho_con_claude", "full_script": beats.full_script(s)}


def test_a_mixed_sentence_is_one_request_with_the_english_inside():
    split = B.plan_calls(_series_data(), _settings(one_request=False))
    merged = B.plan_calls(_series_data(), _settings(one_request=True))
    assert len(merged) < len(split)
    first = merged[0]
    assert first["lang"] == B.resolve_settings()["narration_lang"]
    assert "¿Cómo dirías" in first["text"] and "I carry two hours waiting" in first["text"]
    assert "¿ " not in first["text"] and " ?" not in first["text"]
    assert " ".join(c["text"] for c in merged).count("two hours") == " ".join(c["text"] for c in split).count("two hours")


def test_an_english_sentence_alone_keeps_its_own_request_and_speed():
    merged = B.plan_calls(_series_data(), _settings(one_request=True))
    alone = [c for c in merged if c["is_english"]]
    assert alone and all(c["text"].rstrip().endswith((".", "?", "!")) for c in alone)


def test_only_the_series_through_openrouter_merges(monkeypatch):
    import tts_openrouter
    monkeypatch.setattr(tts_openrouter, "active", lambda: True)
    assert B.one_request("hecho_con_claude", _settings())
    assert not B.one_request("how_do_you_say", _settings())          # its timeline needs each piece
    monkeypatch.setattr(tts_openrouter, "active", lambda: False)
    assert not B.one_request("hecho_con_claude", _settings())        # ElevenLabs direct: as before


def test_a_type_that_teaches_by_repetition_is_never_merged(monkeypatch):
    import duration_spec
    monkeypatch.setattr(duration_spec, "takes", lambda vtype: 3)
    data = {**_series_data(), "type": "hecho_con_claude"}
    split = B.plan_calls(data, _settings(one_request=False))
    assert len(B.plan_calls(data, _settings(one_request=True))) == len(split)

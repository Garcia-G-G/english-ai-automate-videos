"""STEP 80 §1: ElevenLabs voice through OpenRouter. No real request: the HTTP layer, the Keychain
and the settings are mocked."""
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cost_tracker  # noqa: E402
import secret_store  # noqa: E402
import tts_openrouter as T  # noqa: E402
import voice_lock  # noqa: E402

SETTINGS = {"provider": "openrouter", "voice_name": None, "voice_category": "premade", "humanize": True,
            "model": T.MODEL, "per_short_usd": 0.25, "monthly_usd": 15.0}


@pytest.fixture(autouse=True)
def _no_voice_override(monkeypatch):
    monkeypatch.delenv("OPENROUTER_VOICE_ID", raising=False)


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def router(tmp_path, monkeypatch):
    """A fake OpenRouter that records what it was sent; the lock opened as for a panel click."""
    sent = []

    def opener(request, timeout=None):
        sent.append({"url": request.full_url, "headers": dict(request.headers), "body": json.loads(request.data)})
        return _Answer(b"ID3fake-mp3")
    monkeypatch.setattr(T, "_settings", lambda: dict(SETTINGS))
    monkeypatch.setattr(voice_lock, "locked", lambda: False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(cost_tracker, "COSTS_DIR", tmp_path / "costs")
    (tmp_path / "costs").mkdir()
    cost_tracker.reset_tracker("test-video")
    return sent, opener, tmp_path


KW = {"voice_id": "voice123", "text": "[cheerful] Hola, ¿qué tal? [curious]", "model_id": "eleven_v3",
      "language_code": "es", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": 0.95},
      "previous_text": "Antes", "next_text": "Después", "output_format": "mp3_44100_128"}


# ── the request ──────────────────────────────────────────────────────

def test_the_body_is_openroutes_speech_api_with_elevenlabs_options():
    body = T.request_body(KW)
    assert body["input"] == "[cheerfully] Hola, ¿qué tal? [curious]"
    assert body["model"] == "elevenlabs/eleven-v4" and body["voice"] == "voice123"
    assert body["response_format"] == "mp3"
    opts = body["provider"]["options"]["elevenlabs"]
    assert opts["language_code"] == "es" and opts["previous_text"] == "Antes" and opts["next_text"] == "Después"
    assert "speed" not in opts["voice_settings"] and "speed" not in body, "v4 refuses speed"


def test_v3_tags_v4_names_differently_are_mapped():
    assert T.v4_text("[cheerful] hi [whispers] [curious]") == "[cheerfully] hi [whispering] [curious]"


@pytest.mark.parametrize("text, want", [
    ("¿Sabes cómo se dice? Se dice apple.", "¿Sabes cómo se dice? [short pause] Se dice apple."),
    ("Jajaja, fácil.", "[laughs], fácil."),
    ("Mira esto 😂 increíble", "Mira esto [laughs] increíble"),
    ("Eso es... raro.", "Eso es [short pause] raro."),
    ("Hola [name], ¿listo?", "Hola, ¿listo?"),                          # a placeholder, not a tag
    ("[cheerful] Vamos.", "[cheerfully] Vamos."),
    ("Se dice apple.", "Se dice apple."),                                  # nothing to add: nothing added
])
def test_the_v4_humanizer_takes_its_cues_from_the_script(text, want):
    assert T.humanize(text) == want


def test_the_request_is_humanized_unless_config_turns_it_off():
    assert "[short pause]" in T.request_body({**KW, "text": "¿Qué? Nada."})["input"]
    assert "[short pause]" not in T.request_body({**KW, "text": "¿Qué? Nada.", "_humanize": False})["input"]


def test_the_chosen_voice_replaces_the_channels(monkeypatch):
    monkeypatch.setenv("OPENROUTER_VOICE_ID", "matilda-id")
    assert T.request_body(KW)["voice"] == "matilda-id"


def test_a_named_voice_without_its_id_is_refused(monkeypatch):
    with pytest.raises(T.OpenRouterRefused, match="OPENROUTER_VOICE_ID"):   # names what is missing
        T.check_voice({**SETTINGS, "voice_name": "Matilda", "voice_category": "premade"})
    monkeypatch.setenv("OPENROUTER_VOICE_ID", "matilda-id")
    T.check_voice({**SETTINGS, "voice_name": "Matilda", "voice_category": "premade"})


def test_speak_writes_the_audio_and_logs_one_openrouter_row(router):
    sent, opener, tmp = router
    out = tmp / "seg.mp3"
    T.speak(dict(KW), out, opener=opener)
    assert out.read_bytes() == b"ID3fake-mp3"
    assert sent[0]["url"] == T.URL and sent[0]["headers"]["Authorization"] == "Bearer sk-or-v1-test"
    rows = cost_tracker.get_tracker().entries
    assert [(r["api_type"], r["model"], r["provider"]) for r in rows] == [("openrouter_tts", T.MODEL, "openrouter")]
    assert rows[0]["cost_usd"] == pytest.approx(len(KW["text"]) * 80 / 1e6)
    assert cost_tracker.provider_of("openrouter_tts") == "openrouter"


# ── what stops a request before it is sent ───────────────────────────

def test_the_voice_lock_stops_it_before_the_network(router, monkeypatch):
    sent, opener, tmp = router
    monkeypatch.setattr(voice_lock, "locked", lambda: True)
    with pytest.raises(voice_lock.VoiceLocked):
        T.speak(dict(KW), tmp / "x.mp3", opener=opener)
    assert sent == []


@pytest.mark.parametrize("category", [None, "cloned", "generated"])
def test_a_voice_openrouter_cannot_use_without_byok_is_refused(router, monkeypatch, category):
    sent, opener, tmp = router
    monkeypatch.setattr(T, "_settings", lambda: {**SETTINGS, "voice_category": category})
    with pytest.raises(T.OpenRouterRefused, match="no está confirmada"):
        T.speak(dict(KW), tmp / "x.mp3", opener=opener)
    assert sent == []


def test_the_per_short_cap_refuses_in_spanish(router, monkeypatch):
    sent, opener, tmp = router
    monkeypatch.setattr(T, "_settings", lambda: {**SETTINGS, "per_short_usd": 0.001})
    with pytest.raises(T.OpenRouterRefused, match="Tope de OpenRouter por vídeo"):
        T.speak(dict(KW), tmp / "x.mp3", opener=opener)
    assert sent == []


def test_the_monthly_cap_counts_the_logs(router, monkeypatch):
    sent, opener, tmp = router
    from datetime import date
    log = tmp / "costs" / f"costs_{date.today():%Y-%m}-01.jsonl"
    log.write_text(json.dumps({"api_type": "openrouter_tts", "cost_usd": 14.999}) + "\n"
                   + json.dumps({"api_type": "elevenlabs_tts", "cost_usd": 5.0}) + "\n")
    assert T.month_spend() == pytest.approx(14.999)
    with pytest.raises(T.OpenRouterRefused, match="Tope mensual"):
        T.speak(dict(KW), tmp / "x.mp3", opener=opener)
    assert sent == []


def test_no_key_is_refused_before_the_network(router, monkeypatch):
    sent, opener, tmp = router
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(T.OpenRouterRefused, match="No hay clave"):
        T.speak(dict(KW), tmp / "x.mp3", opener=opener)
    assert sent == []


# ── routing and the cache ────────────────────────────────────────────

def test_the_elevenlabs_path_routes_to_openrouter_and_caches_it(router, monkeypatch):
    import tts_cache
    import tts_elevenlabs as E
    sent, opener, tmp = router
    monkeypatch.setattr(tts_cache, "CACHE_DIR", tmp / "cache")
    calls = []
    monkeypatch.setattr(T, "speak", lambda kw, out, **k: (calls.append(kw["text"]), Path(out).write_bytes(b"ID3x")))
    kw = {k: v for k, v in KW.items()}
    E._elevenlabs_with_retry(str(tmp / "a.mp3"), **kw)
    E._elevenlabs_with_retry(str(tmp / "b.mp3"), **kw)              # the second one is a cache hit
    assert calls == [KW["text"]] and (tmp / "b.mp3").read_bytes() == b"ID3x"


def test_audio_already_cached_from_elevenlabs_is_used_and_nothing_is_asked(router, monkeypatch):
    import tts_cache
    import tts_elevenlabs as E
    sent, opener, tmp = router
    monkeypatch.setattr(tts_cache, "CACHE_DIR", tmp / "cache")
    src = tmp / "old.mp3"
    src.write_bytes(b"ID3old")
    tts_cache.store(tts_cache.key({**KW, "endpoint": "convert"}, 0), src, {**KW, "endpoint": "convert"})
    monkeypatch.setattr(T, "speak", lambda *a, **k: pytest.fail("a cached segment was asked again"))
    E._elevenlabs_with_retry(str(tmp / "c.mp3"), **KW)
    assert (tmp / "c.mp3").read_bytes() == b"ID3old"


def test_a_refusal_is_the_jobs_failure_with_no_direct_elevenlabs_call(router, monkeypatch):
    import tts_cache
    import tts_elevenlabs as E
    sent, opener, tmp = router
    monkeypatch.setattr(tts_cache, "CACHE_DIR", tmp / "cache")

    def refuse(*a, **k):
        raise T.OpenRouterRefused("Tope mensual de OpenRouter")
    monkeypatch.setattr(T, "speak", refuse)
    with pytest.raises(T.OpenRouterRefused, match="Tope mensual"):
        E._elevenlabs_with_retry(str(tmp / "d.mp3"), **KW)
    assert not (tmp / "d.mp3").exists()
    source = (ROOT / "src" / "tts_elevenlabs.py").read_text(encoding="utf-8")
    assert "from elevenlabs" not in source and "text_to_speech.convert" not in source


def test_the_bilingual_path_goes_through_the_same_routing():
    source = (ROOT / "src" / "tts_bilingual.py").read_text(encoding="utf-8")
    body = source[source.index("def _synthesize_segment"):source.index("def _local_words")]
    assert "_elevenlabs_with_retry(out_path" in body and "_local_words(out_path" in body
    assert "get_client" not in source and "elevenlabs.types" not in source


# ── the key, the panel, the price table ──────────────────────────────

def test_the_key_comes_from_the_environment_then_the_keychain(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert secret_store.get("OPENROUTER_API_KEY") is None                  # pytest never reads the Keychain
    assert secret_store.get("OPENROUTER_API_KEY", reader=lambda n: "sk-or-v1-k") == "sk-or-v1-k"
    assert secret_store.where("OPENROUTER_API_KEY", reader=lambda n: "sk-or-v1-k") == "Llavero"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-env")
    assert secret_store.get("OPENROUTER_API_KEY", reader=lambda n: pytest.fail("env first")) == "sk-or-v1-env"


def test_the_price_table_has_the_two_openrouter_models():
    assert cost_tracker.PRICING["elevenlabs/eleven-v4"]["per_1m_chars"] == 80.0
    assert cost_tracker.PRICING["elevenlabs/eleven-v4-turbo"]["per_1m_chars"] == 40.0


def test_the_panel_header_shows_openrouters_balance_without_latex():
    import voice_credits as V
    assert V.header_lines(2.5, 15.0) == ["OpenRouter: &#36;2.50 de &#36;15 este mes"]
    assert V.header_lines(None, 15.0) == ["OpenRouter: sin datos"]


def test_the_panel_refuses_a_render_past_the_monthly_cap(monkeypatch):
    import voice_credits as V
    monkeypatch.setattr(T, "_settings", lambda: dict(SETTINGS))
    assert V.openrouter_refusal(1000, spent=1.0, cap=15.0) is None
    assert "Tope mensual" in V.openrouter_refusal(1000, spent=14.99, cap=15.0)


def test_per_video_costs_reads_openrouter_rows(tmp_path):
    """An openrouter_* row in output/costs broke admin's import (KeyError 'openrouter_usd')."""
    import json
    import cost_tracker
    (tmp_path / "costs_2026-10-27-a.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"video_id": "v1", "api_type": "openrouter_tts", "cost_usd": 0.004, "timestamp": "2026-10-27T09:18:06"},
        {"video_id": "v1", "api_type": "openrouter_image", "cost_usd": 0.01, "timestamp": "2026-10-27T09:18:07"},
        {"video_id": "v1", "api_type": "openai_gpt", "cost_usd": 0.001, "timestamp": "2026-10-27T09:18:08"}]))
    rows = {r["video_id"]: r for r in cost_tracker.per_video_costs(tmp_path)}
    assert rows["v1"]["openrouter_usd"] == pytest.approx(0.014) and rows["v1"]["total_usd"] == pytest.approx(0.015)

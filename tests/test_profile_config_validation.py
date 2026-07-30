#!/usr/bin/env python3
"""Pin config validation for audience profiles.

    python3 -m pytest tests/test_profile_config_validation.py

Two silent-lie bugs, both in config.yaml's `profiles:` block:

  a) voice_id: "KIDS_VOICE_ID_PENDIENTE" was validated by nothing. It
     resolved through apply_profile_env and was sent to the ElevenLabs API
     verbatim, failing mid-run — after the script had been generated and
     paid for — instead of at config load.

  b) The profile declares model: eleven_v3, but the bilingual TTS path
     resolves eleven_turbo_v2_5. The BEHAVIOUR is correct (eleven_v3 does not
     accept language_code, which the bilingual path requires); the config was
     silently lying about it. That warns; it must not fail the run.

The voice-id rule is NOT re-implemented here or in profiles.py. It comes from
config/secrets.py, which already carried a per-key format regex and was
imported by nothing — these tests pin that it stays the single source.
"""

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import profiles  # noqa: E402
from config.secrets import is_valid_voice_id, voice_id_pattern  # noqa: E402

VALID_VOICE = "ZOgeDYxfyev5qgOXq2lN"          # the real default voice id
PLACEHOLDER = "KIDS_VOICE_ID_PENDIENTE"        # what config.yaml shipped


@pytest.fixture(autouse=True)
def _restore_env():
    """apply_profile_env writes os.environ; do not leak between tests."""
    keys = ("ELEVENLABS_VOICE_ID", "VIDEO_PROFILE_VOICE_ID",
            "ELEVENLABS_MODEL", "VIDEO_PROFILE_TTS_MODEL")
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── (a) voice_id format ──────────────────────────────────────────────

def test_placeholder_voice_id_is_rejected():
    """22 characters, so a bare length check passes it. The underscores are
    what make it invalid."""
    assert len(PLACEHOLDER) > 20
    assert not is_valid_voice_id(PLACEHOLDER)


@pytest.mark.parametrize("value", [VALID_VOICE, "a" * 20, "AbC123" * 4])
def test_well_formed_voice_ids_are_accepted(value):
    assert is_valid_voice_id(value)


@pytest.mark.parametrize("value", [
    "", None, "short", "ab-cd-ef-gh-ij-kl-mn", "KIDS_VOICE_ID_PENDIENTE",
])
def test_malformed_voice_ids_are_rejected(value):
    assert not is_valid_voice_id(value)


def test_invalid_voice_id_fails_at_config_load_not_at_api_call():
    """The whole point: raise before the run starts."""
    with pytest.raises(ValueError, match="voice_id"):
        profiles.apply_profile_env(
            {"name": "kids", "audio": {"voice_id": PLACEHOLDER}}
        )


def test_valid_voice_id_is_exported_to_both_env_names():
    profiles.apply_profile_env(
        {"name": "t", "audio": {"voice_id": VALID_VOICE}}
    )

    assert os.environ["ELEVENLABS_VOICE_ID"] == VALID_VOICE
    assert os.environ["VIDEO_PROFILE_VOICE_ID"] == VALID_VOICE


def test_the_rule_comes_from_secrets_not_a_second_copy():
    """profiles.py must not grow its own regex. If secrets.py is the source,
    changing nothing here should still describe the same rule."""
    assert voice_id_pattern() == r"^[a-zA-Z0-9]{20,}$"

    src = (ROOT / "src" / "profiles.py").read_text(encoding="utf-8")
    assert "is_valid_voice_id" in src
    assert "[a-zA-Z0-9]{20,}" not in src, (
        "profiles.py re-implemented the voice-id regex instead of importing it"
    )


# ── (b) the model override ───────────────────────────────────────────

def test_overridden_model_warns_and_does_not_fail(caplog):
    """eleven_v3 is dropped by the bilingual path. Warn loudly; keep running."""
    with caplog.at_level(logging.WARNING, logger="profiles"):
        profiles.apply_profile_env(
            {"name": "kids", "audio": {"voice_id": VALID_VOICE,
                                       "model": "eleven_v3"}}
        )

    warnings = [r.getMessage() for r in caplog.records
                if r.levelno >= logging.WARNING]
    assert warnings, "the silent override must warn"
    msg = warnings[0]
    assert "eleven_v3" in msg
    assert "eleven_turbo_v2_5" in msg
    assert "language_code" in msg, "the warning must say WHY it is overridden"

    # and the run continues
    assert os.environ["VIDEO_PROFILE_TTS_MODEL"] == "eleven_v3"


def test_language_code_capable_model_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="profiles"):
        profiles.apply_profile_env(
            {"name": "t", "audio": {"voice_id": VALID_VOICE,
                                    "model": "eleven_turbo_v2_5"}}
        )

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_bilingual_default_constant_matches_the_real_resolver():
    """profiles._BILINGUAL_DEFAULT_MODEL is a copy of tts_bilingual's
    fallback. Pin them together so the warning cannot start lying itself."""
    src = (ROOT / "src" / "tts_bilingual.py").read_text(encoding="utf-8")

    assert f'or "{profiles._BILINGUAL_DEFAULT_MODEL}")' in src, (
        "tts_bilingual's fallback model changed; update "
        "profiles._BILINGUAL_DEFAULT_MODEL to match"
    )


def test_every_language_code_model_is_accepted_without_warning(caplog):
    for model in sorted(profiles._LANGUAGE_CODE_MODELS):
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="profiles"):
            profiles.apply_profile_env(
                {"name": "t", "audio": {"voice_id": VALID_VOICE, "model": model}}
            )
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING], model


# ── the shipped config ───────────────────────────────────────────────

def test_shipped_kids_profile_is_still_flagged():
    """Documents reality rather than asserting a fix: config.yaml still holds
    the placeholder, and loading that profile must now fail loudly. Delete
    this test when a real kids voice id is set."""
    kids = profiles.get_active_profile("kids")
    voice = (kids.get("audio") or {}).get("voice_id")

    if voice == PLACEHOLDER:
        with pytest.raises(ValueError, match="voice_id"):
            profiles.apply_profile_env(kids)
    else:
        assert is_valid_voice_id(voice), (
            f"kids voice_id was changed to {voice!r}, which is still invalid"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""Audience profiles (adults / kids) — voice, background and content overrides.

Profiles live in config.yaml under `profiles:`; the active one is chosen by
(in priority order): explicit name > env VIDEO_PROFILE > config `profile:` > "adults".
Each profile deep-merges its overrides on top of the base audio/video/content
sections, so an empty profile behaves exactly like the base config.
"""

import copy
import logging
import os
from pathlib import Path

import yaml

from config.secrets import is_valid_voice_id, voice_id_pattern

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# Sections a profile can override
_MERGEABLE_SECTIONS = ("audio", "video", "content")

#: ElevenLabs models that accept `language_code`. The bilingual TTS path sends
#: an explicit per-segment language_code so the model cannot guess the accent,
#: so it can only use a model from this set — see tts_bilingual.py:14-19.
_LANGUAGE_CODE_MODELS = frozenset({"eleven_turbo_v2_5", "eleven_flash_v2_5"})

#: What tts_bilingual.resolve_settings falls back to. Kept in sync by
#: tests/test_profile_config_validation.py rather than by hope.
_BILINGUAL_DEFAULT_MODEL = "eleven_turbo_v2_5"


def _load_config() -> dict:
    """Load config.yaml as a dict."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_profiles() -> dict:
    """Read the `profiles:` section (and `profile:` default) from config.yaml."""
    config = _load_config()
    return {
        "default": config.get("profile", "adults"),
        "profiles": config.get("profiles", {}) or {},
    }


def get_active_profile(name: str = None) -> dict:
    """Resolve the active profile and return it merged over the base config.

    Priority: name arg > env VIDEO_PROFILE > config `profile:` > "adults".
    Returns a dict with at least the audio/video/content sections plus `name`.
    """
    config = _load_config()
    profiles = config.get("profiles", {}) or {}

    resolved = name or os.getenv("VIDEO_PROFILE") or config.get("profile") or "adults"

    overrides = profiles.get(resolved)
    if overrides is None and resolved != "adults":
        logger.warning("Profile '%s' not found in config.yaml, using base config", resolved)
    overrides = overrides or {}

    base = {section: config.get(section, {}) or {} for section in _MERGEABLE_SECTIONS}
    merged = _deep_merge(base, {k: v for k, v in overrides.items() if k in _MERGEABLE_SECTIONS})
    merged["name"] = resolved
    return merged


def apply_profile_env(profile: dict):
    """Export the profile's audio overrides to env vars the TTS providers read.

    tts_elevenlabs.py calls load_dotenv(override=True) at import time, so the
    plain ELEVENLABS_* names would be clobbered by .env; the VIDEO_PROFILE_*
    variants take precedence there and survive the dotenv reload.
    """
    audio = profile.get("audio", {}) or {}

    voice_id = audio.get("voice_id")
    if voice_id and voice_id != "default":
        # Validate the FORMAT at config load, not at API call time.
        #
        # config.yaml carried voice_id: "KIDS_VOICE_ID_PENDIENTE" for the kids
        # profile. Nothing checked it, so it resolved through here and was sent
        # to the ElevenLabs API verbatim — failing mid-run, after the script had
        # been generated and paid for, instead of before the run started.
        #
        # The rule comes from config/secrets.py, which already had a per-key
        # format regex for ELEVENLABS_VOICE_ID and was imported by nothing. It
        # is reused rather than re-implemented so the two cannot drift.
        if not is_valid_voice_id(str(voice_id)):
            raise ValueError(
                f"Profile '{profile.get('name', '?')}' has an invalid "
                f"ElevenLabs voice_id: {voice_id!r}. Expected "
                f"{voice_id_pattern()} (20+ alphanumerics, no underscores or "
                f"hyphens). Set a real voice id in config.yaml before using "
                f"this profile."
            )
        os.environ["ELEVENLABS_VOICE_ID"] = str(voice_id)
        os.environ["VIDEO_PROFILE_VOICE_ID"] = str(voice_id)

    model = audio.get("model")
    if model:
        # A profile's `model` is honoured by the single-call ElevenLabs path,
        # but the BILINGUAL path overrides it: tts_bilingual.resolve_settings
        # reads ELEVENLABS_SEGMENT_MODEL / audio.segment_model and defaults to
        # eleven_turbo_v2_5, because eleven_v3 does not accept language_code
        # and the bilingual path requires per-segment language_code to stop
        # the model guessing the accent.
        #
        # The behaviour is correct. The config was silently lying about it,
        # which is what this warns on. Deliberately NOT an error — the run is
        # fine, the declaration is merely not what gets used.
        if str(model) not in _LANGUAGE_CODE_MODELS:
            logger.warning(
                "Profile '%s' declares model=%s, but the bilingual TTS path "
                "will OVERRIDE it with %s. %s does not accept language_code, "
                "and the bilingual path needs per-segment language_code to "
                "control the accent. The declared value is still used by the "
                "single-call path. Set audio.segment_model to change what the "
                "bilingual path uses.",
                profile.get("name", "?"), model, _BILINGUAL_DEFAULT_MODEL, model,
            )
        os.environ["ELEVENLABS_MODEL"] = str(model)
        os.environ["VIDEO_PROFILE_TTS_MODEL"] = str(model)

    for key, env_name in (
        ("stability", "VIDEO_PROFILE_TTS_STABILITY"),
        ("style", "VIDEO_PROFILE_TTS_STYLE"),
        ("global_speed", "VIDEO_PROFILE_TTS_SPEED"),
    ):
        if audio.get(key) is not None:
            os.environ[env_name] = str(audio[key])

    logger.info("Profile '%s' applied (voice=%s, model=%s)",
                profile.get("name", "?"),
                voice_id or "default", model or "default")

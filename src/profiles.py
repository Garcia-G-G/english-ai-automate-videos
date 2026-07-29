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

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# Sections a profile can override
_MERGEABLE_SECTIONS = ("audio", "video", "content")


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
        os.environ["ELEVENLABS_VOICE_ID"] = str(voice_id)
        os.environ["VIDEO_PROFILE_VOICE_ID"] = str(voice_id)

    model = audio.get("model")
    if model:
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

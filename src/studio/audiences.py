"""Strict, workspace-independent audience profile resolution."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Union

import yaml

from config.secrets import is_valid_voice_id

from .models import Audience


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
_MERGEABLE_SECTIONS = ("audio", "video", "content", "metadata", "editorial")
_CHILDREN_VOICE_ENV = "CHILDREN_ELEVENLABS_VOICE_ID"

_AUDIENCE_DEFAULTS = {
    Audience.ADULTS: {
        "metadata": {
            "hashtag_seed": ["LearnEnglish", "EnglishTips", "AdultLearning"],
        },
        "editorial": {
            "tone": "natural conversational instruction",
            "pacing": "direct",
            "interaction_style": "adult contexts with restrained humor",
            "child_safety": False,
        },
    },
    Audience.CHILDREN: {
        "metadata": {
            "hashtag_seed": ["LearnEnglishForKids", "KidsEnglish", "EnglishPractice"],
        },
        "editorial": {
            "tone": "age-appropriate without exaggerated infantilization",
            "pacing": "clear with purposeful repetition",
            "interaction_style": "restrained rewards",
            "child_safety": True,
        },
    },
}


class InvalidAudienceProfile(ValueError):
    """Audience identity or profile configuration is invalid."""


def normalize_audience(value: Union[str, Audience]) -> Audience:
    """Return the canonical audience, accepting ``kids`` only as legacy input."""
    if isinstance(value, Audience):
        return value
    if not isinstance(value, str) or not value.strip():
        raise InvalidAudienceProfile("invalid audience: expected adults or children")
    normalized = value.strip()
    if normalized == "kids":
        normalized = Audience.CHILDREN.value
    try:
        return Audience(normalized)
    except ValueError as exc:
        raise InvalidAudienceProfile(
            f"invalid audience {value!r}: expected adults or children"
        ) from exc


def _load_config(config_path: Path) -> dict:
    try:
        with Path(config_path).open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidAudienceProfile(f"invalid config at {config_path}") from exc
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise InvalidAudienceProfile("invalid config: expected a mapping")
    return config


def _mapping(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidAudienceProfile(f"invalid {field}: expected a mapping")
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validated_voice(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidAudienceProfile("invalid voice_id: expected a string")
    voice = value.strip()
    upper = voice.upper()
    if (
        not voice
        or voice.lower() == "default"
        or "PENDIENTE" in upper
        or "PLACEHOLDER" in upper
        or not is_valid_voice_id(voice)
    ):
        raise InvalidAudienceProfile("invalid voice_id for children audience")
    return voice


def resolve_audience_profile(
    name: Union[str, Audience],
    config_path: Path = CONFIG_PATH,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    """Resolve a deterministic audience snapshot without mutating its inputs."""
    audience = normalize_audience(name)
    config = _load_config(Path(config_path))
    profiles = _mapping(config.get("profiles"), "profiles")
    if audience.value not in profiles:
        raise InvalidAudienceProfile(f"missing profile for audience {audience.value}")
    override = _mapping(profiles[audience.value], "profile")

    merged = copy.deepcopy(_AUDIENCE_DEFAULTS[audience])
    for section in _MERGEABLE_SECTIONS:
        base_section = _mapping(config.get(section, {}), section)
        override_section = _mapping(override.get(section, {}), section)
        merged[section] = _deep_merge(
            _deep_merge(merged.get(section, {}), base_section),
            override_section,
        )

    if audience is Audience.CHILDREN:
        environment = os.environ if environ is None else environ
        if _CHILDREN_VOICE_ENV in environment:
            voice = _validated_voice(environment[_CHILDREN_VOICE_ENV])
        else:
            voice = _validated_voice(merged["audio"].get("voice_id"))
        merged["audio"]["voice_id"] = voice

    merged["profile_schema_version"] = 1
    merged["audience"] = audience.value
    merged["name"] = audience.value
    return copy.deepcopy(merged)

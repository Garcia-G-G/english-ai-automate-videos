"""Strict workspace-by-audience voice profile resolution."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

import yaml

from config.secrets import is_valid_voice_id

from .models import Audience, CreationRequest, LearningLanguage, Market, NativeLanguage


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"

_WORKSPACE_KEYS = MappingProxyType({
    (Market.YOUTUBE, NativeLanguage.SPANISH, LearningLanguage.ENGLISH): "youtube_es_en",
    (
        Market.BILIBILI,
        NativeLanguage.SIMPLIFIED_MANDARIN,
        LearningLanguage.ENGLISH,
    ): "bilibili_zh_hans_en",
})
_WORKSPACE_LOCALES = MappingProxyType({
    "youtube_es_en": "es",
    "bilibili_zh_hans_en": "zh-Hans",
})
_CELL_ENVIRONMENT = MappingProxyType({
    ("youtube_es_en", Audience.ADULTS): "YOUTUBE_ADULTS_ELEVENLABS_VOICE_ID",
    ("youtube_es_en", Audience.CHILDREN): "YOUTUBE_CHILDREN_ELEVENLABS_VOICE_ID",
    ("bilibili_zh_hans_en", Audience.ADULTS): "BILIBILI_ADULTS_ELEVENLABS_VOICE_ID",
    ("bilibili_zh_hans_en", Audience.CHILDREN): "BILIBILI_CHILDREN_ELEVENLABS_VOICE_ID",
})
_LEGACY_YOUTUBE = MappingProxyType({
    Audience.ADULTS: ("ELEVENLABS_VOICE_ID", "legacy_youtube_adult"),
    Audience.CHILDREN: (
        "CHILDREN_ELEVENLABS_VOICE_ID",
        "legacy_youtube_children",
    ),
})
_VOICE_FIELDS = frozenset(("locale", "provider", "voice_id", "traits"))
_AUDIENCES = frozenset((Audience.ADULTS.value, Audience.CHILDREN.value))
_REQUIRED_TRAITS = MappingProxyType({
    Audience.ADULTS.value: frozenset(("female", "natural", "warm", "confident")),
    Audience.CHILDREN.value: frozenset(
        ("female", "natural", "clear", "expressive", "not_infantilized")
    ),
})


class InvalidVoiceProfile(ValueError):
    """Voice matrix configuration does not satisfy its strict contract."""


def _load_config(config_path: Path) -> dict:
    try:
        with Path(config_path).open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidVoiceProfile(f"invalid config at {config_path}") from exc
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise InvalidVoiceProfile("invalid config: expected a mapping")
    return config


def _mapping(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidVoiceProfile(f"invalid {field}: expected a mapping")
    return value


def _exact_fields(value: dict, expected: frozenset, context: str) -> None:
    unknown = set(value) - expected
    if unknown:
        raise InvalidVoiceProfile(f"unknown field {sorted(unknown)[0]} in {context}")
    missing = expected - set(value)
    if missing:
        raise InvalidVoiceProfile(f"missing field {sorted(missing)[0]} in {context}")


def _valid_voice_id(value: Any, cell: str) -> str:
    if not isinstance(value, str):
        raise InvalidVoiceProfile(f"invalid voice_id for {cell}")
    normalized = value.strip()
    upper = normalized.upper()
    if (
        not normalized
        or upper == "DEFAULT"
        or "PENDIENTE" in upper
        or "PLACEHOLDER" in upper
        or not is_valid_voice_id(normalized)
    ):
        raise InvalidVoiceProfile(f"invalid voice_id for {cell}")
    return normalized


def _validate_matrix(matrix: dict) -> None:
    expected_workspaces = frozenset(_WORKSPACE_LOCALES)
    unknown = set(matrix) - expected_workspaces
    if unknown:
        raise InvalidVoiceProfile(f"unknown workspace cell {sorted(unknown)[0]}")
    missing = expected_workspaces - set(matrix)
    if missing:
        raise InvalidVoiceProfile(f"missing workspace cell {sorted(missing)[0]}")

    for workspace_id, locale in _WORKSPACE_LOCALES.items():
        audiences = _mapping(matrix[workspace_id], workspace_id)
        unknown_audiences = set(audiences) - _AUDIENCES
        if unknown_audiences:
            raise InvalidVoiceProfile(
                f"unknown audience cell {workspace_id}/{sorted(unknown_audiences)[0]}"
            )
        missing_audiences = _AUDIENCES - set(audiences)
        if missing_audiences:
            raise InvalidVoiceProfile(
                f"missing audience cell {workspace_id}/{sorted(missing_audiences)[0]}"
            )
        for audience in sorted(_AUDIENCES):
            cell_name = f"{workspace_id}/{audience}"
            cell = _mapping(audiences[audience], cell_name)
            _exact_fields(cell, _VOICE_FIELDS, cell_name)
            if cell["provider"] != "elevenlabs":
                raise InvalidVoiceProfile(f"invalid provider for {cell_name}")
            if cell["locale"] != locale:
                raise InvalidVoiceProfile(f"invalid locale for {cell_name}")
            if not isinstance(cell["voice_id"], str):
                raise InvalidVoiceProfile(f"invalid voice_id for {cell_name}")
            if cell["voice_id"].strip().lower() != "default":
                _valid_voice_id(cell["voice_id"], cell_name)
            traits = cell["traits"]
            if not isinstance(traits, list) or not traits:
                raise InvalidVoiceProfile(f"invalid traits for {cell_name}")
            if any(not isinstance(trait, str) or not trait.strip() for trait in traits):
                raise InvalidVoiceProfile(f"invalid traits for {cell_name}")
            if len(set(traits)) != len(traits):
                raise InvalidVoiceProfile(f"duplicate traits for {cell_name}")
            if set(traits) != _REQUIRED_TRAITS[audience]:
                raise InvalidVoiceProfile(f"invalid traits for {cell_name}")


def resolve_voice_profile(
    request: CreationRequest,
    config_path: Path = CONFIG_PATH,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    """Return a validated, independent voice snapshot for a creation request."""
    dimensions = (request.market, request.native_language, request.learning_language)
    workspace_id = _WORKSPACE_KEYS.get(dimensions)
    if workspace_id is None:
        values = tuple(getattr(value, "value", value) for value in dimensions)
        raise InvalidVoiceProfile(
            f"unsupported voice workspace: {values[0]} + {values[1]} + {values[2]}"
        )

    config = _load_config(Path(config_path))
    voices = _mapping(config.get("voices"), "voices")
    _exact_fields(voices, frozenset(("profile_schema_version", "matrix")), "voices")
    if voices["profile_schema_version"] != 1:
        raise InvalidVoiceProfile("invalid profile_schema_version for voices: expected 1")
    matrix = _mapping(voices["matrix"], "matrix")
    _validate_matrix(matrix)

    audience = request.audience
    cell_name = f"{workspace_id}/{audience.value}"
    cell = matrix[workspace_id][audience.value]
    environment = os.environ if environ is None else environ
    cell_key = _CELL_ENVIRONMENT[(workspace_id, audience)]

    if cell_key in environment:
        voice_id = _valid_voice_id(environment[cell_key], cell_name)
        source = "cell_environment"
    elif cell["voice_id"].strip().lower() != "default":
        voice_id = _valid_voice_id(cell["voice_id"], cell_name)
        source = "configured_cell"
    elif workspace_id == "youtube_es_en":
        legacy_key, source = _LEGACY_YOUTUBE[audience]
        if legacy_key not in environment:
            raise InvalidVoiceProfile(f"missing voice_id for {cell_name}")
        voice_id = _valid_voice_id(environment[legacy_key], cell_name)
    else:
        raise InvalidVoiceProfile(f"missing voice_id for {cell_name}")

    return copy.deepcopy({
        "profile_schema_version": 1,
        "workspace_id": workspace_id,
        "audience": audience.value,
        "locale": cell["locale"],
        "provider": cell["provider"],
        "voice_id": voice_id,
        "traits": cell["traits"],
        "source": source,
    })

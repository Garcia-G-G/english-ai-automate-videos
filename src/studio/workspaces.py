"""Strict resolution of multilingual editorial workspace policy."""

from __future__ import annotations

import copy
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .models import CreationRequest, LearningLanguage, Market, NativeLanguage


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"

_WORKSPACE_KEYS = MappingProxyType({
    (
        Market.YOUTUBE,
        NativeLanguage.SPANISH,
        LearningLanguage.ENGLISH,
    ): "youtube_es_en",
    (
        Market.BILIBILI,
        NativeLanguage.SIMPLIFIED_MANDARIN,
        LearningLanguage.ENGLISH,
    ): "bilibili_zh_hans_en",
})

_IDENTITY_FIELDS = (
    "profile_schema_version",
    "workspace_id",
    "market",
    "native_language",
    "learning_language",
)
_POLICY_SECTIONS = ("audio", "subtitles", "metadata", "editorial", "publication")
_ALLOWED_FIELDS = frozenset((*_IDENTITY_FIELDS, *_POLICY_SECTIONS))


class InvalidWorkspaceProfile(ValueError):
    """Workspace configuration does not satisfy its typed contract."""


def _load_config(config_path: Path) -> dict:
    try:
        with Path(config_path).open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidWorkspaceProfile(f"invalid config at {config_path}") from exc
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise InvalidWorkspaceProfile("invalid config: expected a mapping")
    return config


def _mapping(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidWorkspaceProfile(f"invalid {field}: expected a mapping")
    return value


def _dimensions(request: CreationRequest) -> tuple:
    return (request.market, request.native_language, request.learning_language)


def resolve_workspace_profile(
    request: CreationRequest,
    config_path: Path = CONFIG_PATH,
) -> dict:
    """Return an independent, validated snapshot for a creation workspace."""
    dimensions = _dimensions(request)
    workspace_id = _WORKSPACE_KEYS.get(dimensions)
    if workspace_id is None:
        values = tuple(getattr(value, "value", value) for value in dimensions)
        raise InvalidWorkspaceProfile(
            f"unsupported workspace dimensions: {values[0]} + {values[1]} + {values[2]}"
        )

    config = _load_config(Path(config_path))
    workspaces = _mapping(config.get("workspaces"), "workspaces")
    if workspace_id not in workspaces:
        raise InvalidWorkspaceProfile(f"missing workspace key {workspace_id}")
    entry = _mapping(workspaces[workspace_id], workspace_id)

    unknown = set(entry) - _ALLOWED_FIELDS
    if unknown:
        field = sorted(unknown)[0]
        raise InvalidWorkspaceProfile(
            f"unknown field {field} in workspace {workspace_id}"
        )
    missing = _ALLOWED_FIELDS - set(entry)
    if missing:
        field = sorted(missing)[0]
        raise InvalidWorkspaceProfile(
            f"missing field {field} in workspace {workspace_id}"
        )

    if entry["profile_schema_version"] != 1:
        raise InvalidWorkspaceProfile(
            f"invalid profile_schema_version for {workspace_id}: expected 1"
        )

    expected_identity = {
        "workspace_id": workspace_id,
        "market": request.market.value,
        "native_language": request.native_language.value,
        "learning_language": request.learning_language.value,
    }
    for field, expected in expected_identity.items():
        if entry[field] != expected:
            raise InvalidWorkspaceProfile(
                f"invalid {field} for {workspace_id}: expected {expected!r}"
            )

    for section in _POLICY_SECTIONS:
        _mapping(entry[section], section)

    return copy.deepcopy(entry)

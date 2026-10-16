"""Pure composition of resolved Editorial Studio profile snapshots."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Mapping, Optional

from .audiences import CONFIG_PATH, resolve_audience_profile
from .models import Audience, CreationRequest, LearningLanguage, Market, NativeLanguage
from .voices import resolve_voice_profile
from .workspaces import resolve_workspace_profile


class InvalidProfileBundle(ValueError):
    """Resolved profile snapshots disagree with the creation request."""


def _require(field: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise InvalidProfileBundle(field)


def resolve_profile_bundle(
    request: CreationRequest,
    config_path: Path = CONFIG_PATH,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    """Resolve, cross-check, and return independent profile snapshots."""
    environment = dict(os.environ if environ is None else environ)

    voice = resolve_voice_profile(request, config_path, environ=environment)
    workspace = resolve_workspace_profile(request, config_path)

    audience_environment = environment.copy()
    if request.audience is Audience.CHILDREN:
        audience_environment["CHILDREN_ELEVENLABS_VOICE_ID"] = voice["voice_id"]
    audience = resolve_audience_profile(
        request.audience,
        config_path,
        environ=audience_environment,
    )

    audience = copy.deepcopy(audience)
    workspace = copy.deepcopy(workspace)
    voice = copy.deepcopy(voice)

    for name, snapshot in (
        ("audience", audience),
        ("workspace", workspace),
        ("voice", voice),
    ):
        _require(f"{name}.profile_schema_version", snapshot.get("profile_schema_version"), 1)

    _require("audience.audience", audience.get("audience"), request.audience.value)
    _require("audience.name", audience.get("name"), request.audience.value)
    _require("workspace.market", workspace.get("market"), request.market.value)
    _require(
        "workspace.native_language",
        workspace.get("native_language"),
        request.native_language.value,
    )
    _require(
        "workspace.learning_language",
        workspace.get("learning_language"),
        request.learning_language.value,
    )
    _require("voice.audience", voice.get("audience"), request.audience.value)
    _require("voice.workspace_id", voice.get("workspace_id"), workspace.get("workspace_id"))

    expected_locales = {
        (Market.YOUTUBE, NativeLanguage.SPANISH, LearningLanguage.ENGLISH): "es",
        (
            Market.BILIBILI,
            NativeLanguage.SIMPLIFIED_MANDARIN,
            LearningLanguage.ENGLISH,
        ): "zh-Hans",
    }
    expected_locale = expected_locales.get(
        (request.market, request.native_language, request.learning_language)
    )
    _require("voice.locale", voice.get("locale"), expected_locale)

    return {
        "profile_schema_version": 1,
        "audience": audience,
        "workspace": workspace,
        "voice": voice,
    }

import copy
from pathlib import Path

import pytest
import yaml

from studio.models import (
    CreationRequest,
    LearningLanguage,
    Market,
    NativeLanguage,
)
from studio.workspaces import InvalidWorkspaceProfile, resolve_workspace_profile


EXPECTED_KEYS = {
    "profile_schema_version",
    "workspace_id",
    "market",
    "native_language",
    "learning_language",
    "audio",
    "subtitles",
    "metadata",
    "editorial",
    "publication",
}


def request(*, bilibili=False, audience="adults"):
    return CreationRequest(
        market="bilibili" if bilibili else "youtube",
        native_language="zh-Hans" if bilibili else "es",
        learning_language="en",
        audience=audience,
        mode="auto",
        idea="actually",
    )


def shipped_workspaces():
    config = Path(__file__).parents[2] / "config.yaml"
    return yaml.safe_load(config.read_text(encoding="utf-8"))["workspaces"]


def write_config(path, workspaces=None):
    path.write_text(
        yaml.safe_dump(
            {"workspaces": shipped_workspaces() if workspaces is None else workspaces},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("bilibili", "workspace_id"),
    [(False, "youtube_es_en"), (True, "bilibili_zh_hans_en")],
)
def test_valid_triples_select_exact_workspace_key(tmp_path, bilibili, workspace_id):
    profile = resolve_workspace_profile(
        request(bilibili=bilibili),
        write_config(tmp_path / "config.yaml"),
    )

    assert profile["workspace_id"] == workspace_id


@pytest.mark.parametrize("bilibili", [False, True])
def test_audience_does_not_affect_workspace_snapshot(tmp_path, bilibili):
    config = write_config(tmp_path / "config.yaml")

    adult = resolve_workspace_profile(request(bilibili=bilibili), config)
    child = resolve_workspace_profile(
        request(bilibili=bilibili, audience="children"), config
    )

    assert adult == child


@pytest.mark.parametrize("bilibili", [False, True])
def test_snapshot_has_exact_versioned_identity_and_policy_sections(tmp_path, bilibili):
    profile = resolve_workspace_profile(
        request(bilibili=bilibili),
        write_config(tmp_path / "config.yaml"),
    )

    assert set(profile) == EXPECTED_KEYS
    assert profile["profile_schema_version"] == 1
    for section in ("audio", "subtitles", "metadata", "editorial", "publication"):
        assert isinstance(profile[section], dict)


def test_youtube_spanish_workspace_policy(tmp_path):
    profile = resolve_workspace_profile(
        request(), write_config(tmp_path / "config.yaml")
    )

    assert (profile["market"], profile["native_language"], profile["learning_language"]) == (
        "youtube", "es", "en"
    )
    assert profile["audio"] == {
        "narration_lang": "es",
        "learning_lang": "en",
        "english_accent": "en-US",
        "segment_model": "eleven_turbo_v2_5",
        "voice_preference": "female",
    }
    assert profile["subtitles"] == {
        "bilingual": True,
        "primary_language": "es",
        "learning_language": "en",
        "script": "latin",
    }
    assert profile["metadata"]["title_language"] == "es"
    assert profile["metadata"]["cover_language"] == "es"
    assert profile["metadata"]["hashtag_seed"] == [
        "AprendeIngles", "EnglishTips", "InglesReal"
    ]
    assert profile["editorial"] == {
        "explanation_language": "es",
        "adaptation": "spanish_locale",
        "translation_policy": "never_literal",
    }
    assert profile["publication"] == {
        "manual": True,
        "automatic_publishing": False,
        "initial_visibility": "private",
    }


def test_bilibili_mandarin_workspace_policy(tmp_path):
    profile = resolve_workspace_profile(
        request(bilibili=True), write_config(tmp_path / "config.yaml")
    )

    assert (profile["market"], profile["native_language"], profile["learning_language"]) == (
        "bilibili", "zh-Hans", "en"
    )
    assert profile["audio"] == {
        "narration_lang": "zh",
        "learning_lang": "en",
        "english_accent": "en-US",
        "segment_model": "eleven_turbo_v2_5",
        "voice_preference": "female",
    }
    assert profile["subtitles"] == {
        "bilingual": True,
        "primary_language": "zh-Hans",
        "learning_language": "en",
        "script": "simplified_chinese",
    }
    assert profile["metadata"]["title_language"] == "zh-Hans"
    assert profile["metadata"]["cover_language"] == "zh-Hans"
    assert profile["metadata"]["hashtag_seed"] == ["英语学习", "实用英语", "英语表达"]
    assert profile["editorial"] == {
        "explanation_language": "zh-Hans",
        "adaptation": "mandarin_cultural",
        "translation_policy": "never_mechanical_spanish_translation",
    }
    assert profile["publication"] == {
        "manual": True,
        "automatic_publishing": False,
        "initial_status": "draft",
    }


def nested_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from nested_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from nested_keys(nested)


@pytest.mark.parametrize("bilibili", [False, True])
def test_snapshot_contains_no_audience_voice_or_secret_identity(tmp_path, bilibili):
    profile = resolve_workspace_profile(
        request(bilibili=bilibili), write_config(tmp_path / "config.yaml")
    )
    keys = set(nested_keys(profile))

    assert "audience" not in keys
    assert "voice_id" not in keys
    assert not any(
        forbidden in key
        for key in keys
        for forbidden in ("secret", "credential", "api_token", "environment", "env_var")
    )


def test_resolution_is_deterministic_independent_and_does_not_mutate_yaml(tmp_path, monkeypatch):
    config_path = write_config(tmp_path / "config.yaml")
    import studio.workspaces as workspaces

    loaded = workspaces._load_config(config_path)
    original = copy.deepcopy(loaded)
    monkeypatch.setattr(workspaces, "_load_config", lambda _path: loaded)

    first = resolve_workspace_profile(request(), config_path)
    second = resolve_workspace_profile(request(), config_path)

    assert first == second
    assert first is not second
    assert first["audio"] is not second["audio"]
    first["audio"]["narration_lang"] = "changed"
    assert second["audio"]["narration_lang"] == "es"
    assert loaded == original


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda data: data.pop("workspaces"), "workspaces"),
        (lambda data: data.__setitem__("workspaces", []), "workspaces"),
        (lambda data: data["workspaces"].pop("youtube_es_en"), "youtube_es_en"),
        (lambda data: data["workspaces"].__setitem__("youtube_es_en", []), "youtube_es_en"),
        (lambda data: data["workspaces"]["youtube_es_en"].pop("audio"), "audio"),
        (lambda data: data["workspaces"]["youtube_es_en"].__setitem__("audio", []), "audio"),
        (lambda data: data["workspaces"]["youtube_es_en"].__setitem__("profile_schema_version", 2), "profile_schema_version"),
        (lambda data: data["workspaces"]["youtube_es_en"].__setitem__("market", "bilibili"), "market"),
        (lambda data: data["workspaces"]["youtube_es_en"].__setitem__("unexpected", True), "unexpected"),
    ],
)
def test_malformed_workspace_config_fails_with_field_or_key(tmp_path, mutation, field):
    data = {"workspaces": copy.deepcopy(shipped_workspaces())}
    mutation(data)
    config = write_config(tmp_path / "config.yaml", data.get("workspaces"))
    if "workspaces" not in data:
        config.write_text("{}\n", encoding="utf-8")

    with pytest.raises(InvalidWorkspaceProfile, match=field):
        resolve_workspace_profile(request(), config)


def test_unsupported_request_dimensions_are_wrapped(tmp_path):
    unsupported = CreationRequest.model_construct(
        market=Market.BILIBILI,
        native_language=NativeLanguage.SPANISH,
        learning_language=LearningLanguage.ENGLISH,
        audience="adults",
        mode="auto",
        idea="actually",
    )

    with pytest.raises(InvalidWorkspaceProfile, match="bilibili.*es.*en"):
        resolve_workspace_profile(unsupported, write_config(tmp_path / "config.yaml"))

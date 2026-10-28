import copy
from pathlib import Path

import pytest
import yaml

from studio.models import CreationRequest
from studio.voices import InvalidVoiceProfile, resolve_voice_profile


VALID = {
    "youtube_es_en": {
        "adults": "YoutubeAdultsVoice1234",
        "children": "YoutubeChildrenVoice12",
    },
    "bilibili_zh_hans_en": {
        "adults": "BilibiliAdultsVoice12",
        "children": "BilibiliChildrenVoice",
    },
}
CELL_ENV = {
    ("youtube_es_en", "adults"): "YOUTUBE_ADULTS_ELEVENLABS_VOICE_ID",
    ("youtube_es_en", "children"): "YOUTUBE_CHILDREN_ELEVENLABS_VOICE_ID",
    ("bilibili_zh_hans_en", "adults"): "BILIBILI_ADULTS_ELEVENLABS_VOICE_ID",
    ("bilibili_zh_hans_en", "children"): "BILIBILI_CHILDREN_ELEVENLABS_VOICE_ID",
}


def request(workspace_id="youtube_es_en", audience="adults"):
    bilibili = workspace_id == "bilibili_zh_hans_en"
    return CreationRequest(
        market="bilibili" if bilibili else "youtube",
        native_language="zh-Hans" if bilibili else "es",
        learning_language="en",
        audience=audience,
        mode="auto",
        idea="actually",
    )


def shipped_voices():
    path = Path(__file__).parents[2] / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["voices"]


def write_config(path, voices=None):
    path.write_text(
        yaml.safe_dump(
            {"voices": shipped_voices() if voices is None else voices},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("workspace_id", "audience", "locale", "traits"),
    [
        ("youtube_es_en", "adults", "es", ["female", "natural", "warm", "confident"]),
        ("youtube_es_en", "children", "es", ["female", "natural", "clear", "expressive", "not_infantilized"]),
        ("bilibili_zh_hans_en", "adults", "zh-Hans", ["female", "natural", "warm", "confident"]),
        ("bilibili_zh_hans_en", "children", "zh-Hans", ["female", "natural", "clear", "expressive", "not_infantilized"]),
    ],
)
def test_all_four_cells_resolve_exact_snapshot(tmp_path, workspace_id, audience, locale, traits):
    env_name = CELL_ENV[(workspace_id, audience)]
    profile = resolve_voice_profile(
        request(workspace_id, audience),
        write_config(tmp_path / "config.yaml"),
        environ={env_name: VALID[workspace_id][audience]},
    )

    assert profile == {
        "profile_schema_version": 1,
        "workspace_id": workspace_id,
        "audience": audience,
        "locale": locale,
        "provider": "elevenlabs",
        "voice_id": VALID[workspace_id][audience],
        "traits": traits,
        "source": "cell_environment",
    }


@pytest.mark.parametrize("workspace_id,audience", CELL_ENV)
def test_cell_environment_override_wins(tmp_path, workspace_id, audience):
    voices = copy.deepcopy(shipped_voices())
    voices["matrix"][workspace_id][audience]["voice_id"] = "ConfiguredVoice1234567"
    env_name = CELL_ENV[(workspace_id, audience)]

    profile = resolve_voice_profile(
        request(workspace_id, audience),
        write_config(tmp_path / "config.yaml", voices),
        environ={env_name: VALID[workspace_id][audience]},
    )

    assert profile["voice_id"] == VALID[workspace_id][audience]
    assert profile["source"] == "cell_environment"


@pytest.mark.parametrize("workspace_id,audience", CELL_ENV)
def test_configured_non_default_voice_is_second_precedence(tmp_path, workspace_id, audience):
    voices = copy.deepcopy(shipped_voices())
    voices["matrix"][workspace_id][audience]["voice_id"] = VALID[workspace_id][audience]

    profile = resolve_voice_profile(
        request(workspace_id, audience),
        write_config(tmp_path / "config.yaml", voices),
        environ={},
    )

    assert profile["voice_id"] == VALID[workspace_id][audience]
    assert profile["source"] == "configured_cell"


@pytest.mark.parametrize(
    ("audience", "legacy_key", "source"),
    [
        ("adults", "ELEVENLABS_VOICE_ID", "legacy_youtube_adult"),
        ("children", "CHILDREN_ELEVENLABS_VOICE_ID", "legacy_youtube_children"),
    ],
)
def test_youtube_uses_only_respective_legacy_fallback(tmp_path, audience, legacy_key, source):
    profile = resolve_voice_profile(
        request(audience=audience),
        write_config(tmp_path / "config.yaml"),
        environ={legacy_key: VALID["youtube_es_en"][audience]},
    )

    assert profile["source"] == source


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_bilibili_cannot_use_legacy_youtube_variables(tmp_path, audience):
    environ = {
        "ELEVENLABS_VOICE_ID": VALID["youtube_es_en"]["adults"],
        "CHILDREN_ELEVENLABS_VOICE_ID": VALID["youtube_es_en"]["children"],
    }
    with pytest.raises(InvalidVoiceProfile, match="voice_id.*bilibili"):
        resolve_voice_profile(
            request("bilibili_zh_hans_en", audience),
            write_config(tmp_path / "config.yaml"),
            environ=environ,
        )


@pytest.mark.parametrize("bad", ["", "   ", "default", "VOICE_PENDING_PLACEHOLDER", "short"])
def test_present_invalid_cell_override_fails_without_fallback(tmp_path, bad):
    env_name = CELL_ENV[("youtube_es_en", "adults")]
    environ = {env_name: bad, "ELEVENLABS_VOICE_ID": VALID["youtube_es_en"]["adults"]}
    with pytest.raises(InvalidVoiceProfile, match="voice_id.*youtube_es_en.*adults"):
        resolve_voice_profile(request(), write_config(tmp_path / "config.yaml"), environ=environ)


def test_malformed_configured_voice_fails_without_legacy_fallback(tmp_path):
    voices = copy.deepcopy(shipped_voices())
    voices["matrix"]["youtube_es_en"]["adults"]["voice_id"] = "malformed"
    with pytest.raises(InvalidVoiceProfile, match="voice_id"):
        resolve_voice_profile(
            request(),
            write_config(tmp_path / "config.yaml", voices),
            environ={"ELEVENLABS_VOICE_ID": VALID["youtube_es_en"]["adults"]},
        )


def test_existing_secret_validator_is_used(tmp_path, monkeypatch):
    import studio.voices as voices_module

    seen = []
    monkeypatch.setattr(voices_module, "is_valid_voice_id", lambda value: seen.append(value) or True)
    value = "AnyValueAcceptedByPatchedValidator"
    resolve_voice_profile(
        request(),
        write_config(tmp_path / "config.yaml"),
        environ={CELL_ENV[("youtube_es_en", "adults")]: value},
    )
    assert seen == [value]


def test_resolution_is_pure_and_returns_independent_data(tmp_path, monkeypatch):
    import studio.voices as voices_module

    config = write_config(tmp_path / "config.yaml")
    loaded = voices_module._load_config(config)
    original = copy.deepcopy(loaded)
    environ = {CELL_ENV[("youtube_es_en", "adults")]: VALID["youtube_es_en"]["adults"]}
    original_environ = copy.deepcopy(environ)
    monkeypatch.setattr(voices_module, "_load_config", lambda _path: loaded)

    first = resolve_voice_profile(request(), config, environ=environ)
    second = resolve_voice_profile(request(), config, environ=environ)
    first["traits"].append("changed")

    assert "changed" not in second["traits"]
    assert loaded == original
    assert environ == original_environ
    assert not any("environment" in key or "credential" in key for key in first)


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda data: data.pop("voices"), "voices"),
        (lambda data: data.__setitem__("voices", []), "voices"),
        (lambda data: data["voices"].__setitem__("profile_schema_version", 2), "profile_schema_version"),
        (lambda data: data["voices"].__setitem__("unexpected", True), "unexpected"),
        (lambda data: data["voices"].__setitem__("matrix", []), "matrix"),
        (lambda data: data["voices"]["matrix"].pop("youtube_es_en"), "youtube_es_en"),
        (lambda data: data["voices"]["matrix"].__setitem__("unknown", {}), "unknown"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"].pop("adults"), "adults"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"].__setitem__("teens", {}), "teens"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"].__setitem__("adults", []), "adults"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].pop("provider"), "provider"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("extra", True), "extra"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("provider", "other"), "provider"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("locale", "zh-Hans"), "locale"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("traits", {}), "traits"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("traits", []), "traits"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("traits", ["female", "female"]), "traits"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("traits", ["female", 1]), "traits"),
        (lambda data: data["voices"]["matrix"]["youtube_es_en"]["adults"].__setitem__("traits", ["natural", "warm", "confident"]), "traits"),
        (lambda data: data["voices"]["matrix"]["bilibili_zh_hans_en"]["children"].__setitem__("voice_id", "PLACEHOLDER_VOICE_VALUE"), "voice_id"),
    ],
)
def test_invalid_matrix_structure_fails_with_field_and_cell(tmp_path, mutation, field):
    data = {"voices": copy.deepcopy(shipped_voices())}
    mutation(data)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(InvalidVoiceProfile, match=field):
        resolve_voice_profile(
            request(),
            path,
            environ={CELL_ENV[("youtube_es_en", "adults")]: VALID["youtube_es_en"]["adults"]},
        )


def test_shipped_config_and_env_example_define_placeholders_only():
    voices = shipped_voices()
    for cells in voices["matrix"].values():
        for cell in cells.values():
            assert cell["voice_id"] == "default"

    env_text = (Path(__file__).parents[2] / ".env.example").read_text(encoding="utf-8")
    for variable in CELL_ENV.values():
        assert f"{variable}=\n" in env_text

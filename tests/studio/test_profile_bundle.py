import copy
import os
from pathlib import Path

import pytest
import yaml

from studio.audiences import InvalidAudienceProfile
from studio.models import CreationRequest
from studio.profile_bundle import InvalidProfileBundle, resolve_profile_bundle
from studio.voices import InvalidVoiceProfile
from studio.workspaces import InvalidWorkspaceProfile


VOICE_IDS = {
    ("youtube", "adults"): "YoutubeAdultsVoice1234",
    ("youtube", "children"): "YoutubeChildrenVoice12",
    ("bilibili", "adults"): "BilibiliAdultsVoice12",
    ("bilibili", "children"): "BilibiliChildrenVoice",
}
CELL_ENV = {
    ("youtube", "adults"): "YOUTUBE_ADULTS_ELEVENLABS_VOICE_ID",
    ("youtube", "children"): "YOUTUBE_CHILDREN_ELEVENLABS_VOICE_ID",
    ("bilibili", "adults"): "BILIBILI_ADULTS_ELEVENLABS_VOICE_ID",
    ("bilibili", "children"): "BILIBILI_CHILDREN_ELEVENLABS_VOICE_ID",
}
WORKSPACE_IDS = {
    "youtube": "youtube_es_en",
    "bilibili": "bilibili_zh_hans_en",
}
LOCALES = {"youtube": "es", "bilibili": "zh-Hans"}


def request(market="youtube", audience="adults"):
    return CreationRequest(
        market=market,
        native_language="es" if market == "youtube" else "zh-Hans",
        learning_language="en",
        audience=audience,
        mode="auto",
        idea="actually",
    )


def config_document():
    adult_traits = ["female", "natural", "warm", "confident"]
    child_traits = [
        "female",
        "natural",
        "clear",
        "expressive",
        "not_infantilized",
    ]
    return {
        "audio": {"voice_id": "default", "model": "eleven_v3"},
        "video": {"background_mode": "random"},
        "content": {"default_type": "educational"},
        "profiles": {
            "adults": {"content": {"categories": ["adult_phrases"]}},
            "children": {
                "audio": {"voice_id": "default", "style": 0.3},
                "content": {"categories": ["kids_colors"]},
            },
        },
        "workspaces": {
            "youtube_es_en": workspace_snapshot("youtube"),
            "bilibili_zh_hans_en": workspace_snapshot("bilibili"),
        },
        "voices": {
            "profile_schema_version": 1,
            "matrix": {
                "youtube_es_en": {
                    "adults": voice_cell("youtube", adult_traits),
                    "children": voice_cell("youtube", child_traits),
                },
                "bilibili_zh_hans_en": {
                    "adults": voice_cell("bilibili", adult_traits),
                    "children": voice_cell("bilibili", child_traits),
                },
            },
        },
    }


def workspace_snapshot(market):
    bilibili = market == "bilibili"
    native = "zh-Hans" if bilibili else "es"
    workspace_id = WORKSPACE_IDS[market]
    return {
        "profile_schema_version": 1,
        "workspace_id": workspace_id,
        "market": market,
        "native_language": native,
        "learning_language": "en",
        "audio": {
            "narration_lang": "zh" if bilibili else "es",
            "learning_lang": "en",
            "voice_preference": "female",
        },
        "subtitles": {
            "bilingual": True,
            "primary_language": native,
        },
        "metadata": {"title_language": native, "hashtag_seed": ["英语"] if bilibili else ["Ingles"]},
        "editorial": {"explanation_language": native},
        "publication": {"manual": True},
    }


def voice_cell(market, traits):
    return {
        "locale": LOCALES[market],
        "provider": "elevenlabs",
        "voice_id": "default",
        "traits": traits,
    }


def write_config(path):
    path.write_text(
        yaml.safe_dump(config_document(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def expected_audience(audience, voice_id):
    snapshot = {
        "metadata": {
            "hashtag_seed": [
                "LearnEnglish",
                "EnglishTips",
                "AdultLearning",
            ]
        },
        "editorial": {
            "tone": "natural conversational instruction",
            "pacing": "direct",
            "interaction_style": "adult contexts with restrained humor",
            "child_safety": False,
        },
        "audio": {"voice_id": "default", "model": "eleven_v3"},
        "video": {"background_mode": "random"},
        "content": {
            "default_type": "educational",
            "categories": ["adult_phrases"],
        },
        "profile_schema_version": 1,
        "audience": "adults",
        "name": "adults",
    }
    if audience == "children":
        snapshot.update(
            metadata={
                "hashtag_seed": [
                    "LearnEnglishForKids",
                    "KidsEnglish",
                    "EnglishPractice",
                ]
            },
            editorial={
                "tone": "age-appropriate without exaggerated infantilization",
                "pacing": "clear with purposeful repetition",
                "interaction_style": "restrained rewards",
                "child_safety": True,
            },
            audio={"voice_id": voice_id, "model": "eleven_v3", "style": 0.3},
            content={"default_type": "educational", "categories": ["kids_colors"]},
            audience="children",
            name="children",
        )
    return snapshot


def expected_voice(market, audience, voice_id, source="cell_environment"):
    traits = (
        ["female", "natural", "warm", "confident"]
        if audience == "adults"
        else ["female", "natural", "clear", "expressive", "not_infantilized"]
    )
    return {
        "profile_schema_version": 1,
        "workspace_id": WORKSPACE_IDS[market],
        "audience": audience,
        "locale": LOCALES[market],
        "provider": "elevenlabs",
        "voice_id": voice_id,
        "traits": traits,
        "source": source,
    }


@pytest.mark.parametrize("market", ["youtube", "bilibili"])
@pytest.mark.parametrize("audience", ["adults", "children"])
def test_all_four_cells_return_exact_complete_snapshots(tmp_path, market, audience):
    config = write_config(tmp_path / "config.yaml")
    voice_id = VOICE_IDS[(market, audience)]

    bundle = resolve_profile_bundle(
        request(market, audience),
        config,
        environ={CELL_ENV[(market, audience)]: voice_id},
    )

    assert bundle == {
        "profile_schema_version": 1,
        "audience": expected_audience(audience, voice_id),
        "workspace": workspace_snapshot(market),
        "voice": expected_voice(market, audience, voice_id),
    }
    assert set(bundle) == {
        "profile_schema_version",
        "audience",
        "workspace",
        "voice",
    }


def test_voice_resolves_before_workspace_and_audience(monkeypatch):
    import studio.profile_bundle as module

    calls = []
    monkeypatch.setattr(module, "resolve_voice_profile", lambda *a, **k: calls.append("voice") or valid_voice())
    monkeypatch.setattr(module, "resolve_workspace_profile", lambda *a, **k: calls.append("workspace") or valid_workspace())
    monkeypatch.setattr(module, "resolve_audience_profile", lambda *a, **k: calls.append("audience") or valid_audience())

    module.resolve_profile_bundle(request(), Path("config.yaml"), environ={})

    assert calls == ["voice", "workspace", "audience"]


@pytest.mark.parametrize("market", ["youtube", "bilibili"])
def test_children_bridge_uses_selected_matrix_voice_with_only_cell_variable(tmp_path, market):
    config = write_config(tmp_path / "config.yaml")
    voice_id = VOICE_IDS[(market, "children")]
    environment = {CELL_ENV[(market, "children")]: voice_id}

    bundle = resolve_profile_bundle(
        request(market, "children"), config, environ=environment
    )

    assert bundle["audience"]["audio"]["voice_id"] == voice_id
    assert bundle["voice"]["voice_id"] == voice_id
    assert "CHILDREN_ELEVENLABS_VOICE_ID" not in environment


def test_adults_receive_no_children_compatibility_override(monkeypatch):
    import studio.profile_bundle as module

    received = {}
    monkeypatch.setattr(module, "resolve_voice_profile", lambda *a, **k: valid_voice())
    monkeypatch.setattr(module, "resolve_workspace_profile", lambda *a, **k: valid_workspace())

    def audience_resolver(*args, **kwargs):
        received.update(kwargs["environ"])
        return valid_audience()

    monkeypatch.setattr(module, "resolve_audience_profile", audience_resolver)
    source = {"UNCHANGED": "yes"}

    module.resolve_profile_bundle(request(), Path("config.yaml"), environ=source)

    assert received == source
    assert "CHILDREN_ELEVENLABS_VOICE_ID" not in received


@pytest.mark.parametrize(
    ("source_kind", "source_label"),
    [
        ("cell", "cell_environment"),
        ("configured", "configured_cell"),
        ("legacy_adult", "legacy_youtube_adult"),
        ("legacy_child", "legacy_youtube_children"),
    ],
)
def test_voice_source_labels_survive_composition(tmp_path, source_kind, source_label):
    data = config_document()
    audience = "children" if source_kind == "legacy_child" else "adults"
    voice_id = VOICE_IDS[("youtube", audience)]
    environment = {}
    if source_kind == "cell":
        environment[CELL_ENV[("youtube", audience)]] = voice_id
    elif source_kind == "configured":
        data["voices"]["matrix"]["youtube_es_en"][audience]["voice_id"] = voice_id
    elif source_kind == "legacy_child":
        environment["CHILDREN_ELEVENLABS_VOICE_ID"] = voice_id
    else:
        environment["ELEVENLABS_VOICE_ID"] = voice_id
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    bundle = resolve_profile_bundle(
        request("youtube", audience), config, environ=environment
    )

    assert bundle["voice"]["source"] == source_label


def test_supplied_mapping_and_os_environ_are_not_mutated_and_no_dotenv_is_loaded(
    tmp_path, monkeypatch
):
    config = write_config(tmp_path / "config.yaml")
    supplied = {
        CELL_ENV[("bilibili", "children")]: VOICE_IDS[("bilibili", "children")],
        "UNRELATED": "kept",
    }
    original_supplied = copy.deepcopy(supplied)
    original_os = dict(os.environ)
    monkeypatch.setitem(os.environ, "DOTENV_SENTINEL", "unchanged")
    before_call = dict(os.environ)

    resolve_profile_bundle(
        request("bilibili", "children"), config, environ=supplied
    )

    assert supplied == original_supplied
    assert dict(os.environ) == before_call
    monkeypatch.undo()
    assert dict(os.environ) == original_os


def test_none_environment_reads_os_environ_without_mutating_it(tmp_path, monkeypatch):
    config = write_config(tmp_path / "config.yaml")
    key = CELL_ENV[("youtube", "children")]
    monkeypatch.setenv(key, VOICE_IDS[("youtube", "children")])
    before = dict(os.environ)

    resolve_profile_bundle(request("youtube", "children"), config)

    assert dict(os.environ) == before


def test_repeated_calls_return_independent_nested_mappings_and_lists(tmp_path):
    config = write_config(tmp_path / "config.yaml")
    environment = {
        CELL_ENV[("youtube", "children")]: VOICE_IDS[("youtube", "children")]
    }

    first = resolve_profile_bundle(
        request("youtube", "children"), config, environ=environment
    )
    prior = copy.deepcopy(first)
    second = resolve_profile_bundle(
        request("youtube", "children"), config, environ=environment
    )
    first["audience"]["content"]["categories"].append("changed")
    first["workspace"]["metadata"]["hashtag_seed"].append("changed")
    first["voice"]["traits"].append("changed")

    assert second == prior


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_resolvers_receive_same_request_path_and_isolated_environments(
    monkeypatch, audience
):
    import studio.profile_bundle as module

    creation_request = request("youtube", audience)
    config_path = Path("chosen-config.yaml")
    source = {"ORIGINAL": "value"}
    received = {}

    def voice_resolver(got_request, got_path, *, environ):
        received["voice"] = (got_request, got_path, environ)
        return valid_voice(audience=audience)

    def workspace_resolver(got_request, got_path):
        received["workspace"] = (got_request, got_path)
        return valid_workspace()

    def audience_resolver(got_request, got_path, *, environ):
        received["audience"] = (got_request, got_path, environ)
        return valid_audience(audience=audience)

    monkeypatch.setattr(module, "resolve_voice_profile", voice_resolver)
    monkeypatch.setattr(module, "resolve_workspace_profile", workspace_resolver)
    monkeypatch.setattr(module, "resolve_audience_profile", audience_resolver)

    module.resolve_profile_bundle(creation_request, config_path, environ=source)

    assert received["voice"][:2] == received["workspace"] == (
        creation_request,
        config_path,
    )
    assert received["audience"][:2] == (creation_request.audience, config_path)
    voice_environment = received["voice"][2]
    audience_environment = received["audience"][2]
    assert voice_environment is not source
    assert audience_environment is not source
    assert voice_environment is not audience_environment
    assert voice_environment == source
    expected_audience_environment = copy.deepcopy(source)
    if audience == "children":
        expected_audience_environment["CHILDREN_ELEVENLABS_VOICE_ID"] = valid_voice(
            audience="children"
        )["voice_id"]
    assert audience_environment == expected_audience_environment


@pytest.mark.parametrize(
    ("resolver_name", "error"),
    [
        ("resolve_voice_profile", InvalidVoiceProfile("voice_id")),
        ("resolve_workspace_profile", InvalidWorkspaceProfile("workspace_id")),
        ("resolve_audience_profile", InvalidAudienceProfile("audience")),
    ],
)
def test_underlying_resolver_exception_propagates_unchanged(
    monkeypatch, resolver_name, error
):
    import studio.profile_bundle as module

    monkeypatch.setattr(module, "resolve_voice_profile", lambda *a, **k: valid_voice())
    monkeypatch.setattr(module, "resolve_workspace_profile", lambda *a, **k: valid_workspace())
    monkeypatch.setattr(module, "resolve_audience_profile", lambda *a, **k: valid_audience())

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, resolver_name, fail)

    with pytest.raises(type(error)) as caught:
        module.resolve_profile_bundle(request(), Path("config.yaml"), environ={})

    assert caught.value is error
    assert not isinstance(caught.value, InvalidProfileBundle)


def valid_audience(audience="adults"):
    return {
        "profile_schema_version": 1,
        "audience": audience,
        "name": audience,
        "audio": {"voice_id": VOICE_IDS[("youtube", audience)]},
        "nested": {"values": ["complete"]},
    }


def valid_workspace():
    return {
        "profile_schema_version": 1,
        "workspace_id": "youtube_es_en",
        "market": "youtube",
        "native_language": "es",
        "learning_language": "en",
        "nested": {"values": ["complete"]},
    }


def valid_voice(audience="adults"):
    return {
        "profile_schema_version": 1,
        "workspace_id": "youtube_es_en",
        "audience": audience,
        "locale": "es",
        "voice_id": VOICE_IDS[("youtube", audience)],
        "nested": {"values": ["complete"]},
    }


INVARIANT_MUTATIONS = [
    ("audience.profile_schema_version", lambda a, w, v: a.__setitem__("profile_schema_version", 2)),
    ("workspace.profile_schema_version", lambda a, w, v: w.__setitem__("profile_schema_version", 2)),
    ("voice.profile_schema_version", lambda a, w, v: v.__setitem__("profile_schema_version", 2)),
    ("audience.audience", lambda a, w, v: a.__setitem__("audience", "children")),
    ("audience.name", lambda a, w, v: a.__setitem__("name", "children")),
    ("workspace.market", lambda a, w, v: w.__setitem__("market", "bilibili")),
    ("workspace.native_language", lambda a, w, v: w.__setitem__("native_language", "zh-Hans")),
    ("workspace.learning_language", lambda a, w, v: w.__setitem__("learning_language", "fr")),
    ("voice.audience", lambda a, w, v: v.__setitem__("audience", "children")),
    ("voice.workspace_id", lambda a, w, v: v.__setitem__("workspace_id", "other")),
    ("voice.locale", lambda a, w, v: v.__setitem__("locale", "zh-Hans")),
]


@pytest.mark.parametrize(("field", "mutate"), INVARIANT_MUTATIONS)
def test_every_cross_profile_mismatch_names_its_field(monkeypatch, field, mutate):
    import studio.profile_bundle as module

    audience = valid_audience()
    workspace = valid_workspace()
    voice = valid_voice()
    mutate(audience, workspace, voice)
    monkeypatch.setattr(module, "resolve_voice_profile", lambda *a, **k: voice)
    monkeypatch.setattr(module, "resolve_workspace_profile", lambda *a, **k: workspace)
    monkeypatch.setattr(module, "resolve_audience_profile", lambda *a, **k: audience)

    with pytest.raises(InvalidProfileBundle, match=field.replace(".", r"\.")):
        module.resolve_profile_bundle(request(), Path("config.yaml"), environ={})


def test_composition_creates_no_files_and_does_not_mutate_configuration(tmp_path):
    config = write_config(tmp_path / "config.yaml")
    original = config.read_bytes()
    environment = {
        CELL_ENV[("youtube", "adults")]: VOICE_IDS[("youtube", "adults")]
    }
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    resolve_profile_bundle(request(), config, environ=environment)

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before
    assert Path("config.yaml") in before
    assert config.read_bytes() == original

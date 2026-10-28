import copy
from pathlib import Path

import pytest

from studio.audiences import (
    InvalidAudienceProfile,
    normalize_audience,
    resolve_audience_profile,
)
from studio.models import Audience


VALID_VOICE = "AbC123def456GHI789jk"


def write_config(path: Path, *, children_voice="default") -> Path:
    path.write_text(
        f"""
profile: adults
audio:
  voice_id: default
  model: eleven_v3
  stability: 0.5
video:
  background_mode: random
content:
  default_type: educational
profiles:
  adults:
    audio:
      style: 0.05
  children:
    audio:
      voice_id: {children_voice!r}
      style: 0.3
    video:
      clips_dir: assets/clips/kids
    content:
      categories: [kids_colors]
""",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("adults", Audience.ADULTS),
        ("children", Audience.CHILDREN),
        ("kids", Audience.CHILDREN),
        (Audience.ADULTS, Audience.ADULTS),
        (Audience.CHILDREN, Audience.CHILDREN),
    ],
)
def test_normalize_audience_accepts_canonical_values_and_legacy_kids(value, expected):
    assert normalize_audience(value) is expected


@pytest.mark.parametrize("value", ["", "   ", "teens", "Adults", None])
def test_normalize_audience_rejects_unknown_or_blank_values(value):
    with pytest.raises(InvalidAudienceProfile, match="audience"):
        normalize_audience(value)


def test_resolved_snapshots_are_canonical_complete_and_independent(tmp_path):
    config = write_config(tmp_path / "config.yaml", children_voice=VALID_VOICE)

    adult = resolve_audience_profile("adults", config, environ={})
    child = resolve_audience_profile("children", config, environ={})

    for snapshot, audience in ((adult, "adults"), (child, "children")):
        assert snapshot["profile_schema_version"] == 1
        assert snapshot["audience"] == snapshot["name"] == audience
        assert set(("audio", "video", "content", "metadata", "editorial")) <= snapshot.keys()
        assert snapshot["metadata"]["hashtag_seed"]
        assert snapshot["editorial"]

    assert adult["audio"]["stability"] == child["audio"]["stability"] == 0.5
    assert adult["editorial"]["pacing"] == "direct"
    assert child["editorial"]["child_safety"] is True
    assert child["content"]["categories"] == ["kids_colors"]
    child["audio"]["stability"] = 99
    assert adult["audio"]["stability"] == 0.5


def test_resolution_does_not_mutate_environment_or_loaded_yaml(tmp_path, monkeypatch):
    config = write_config(tmp_path / "config.yaml")
    environ = {"CHILDREN_ELEVENLABS_VOICE_ID": VALID_VOICE, "market": "bilibili"}
    original_environ = copy.deepcopy(environ)

    import studio.audiences as audiences

    loaded = audiences._load_config(config)
    original_loaded = copy.deepcopy(loaded)
    monkeypatch.setattr(audiences, "_load_config", lambda _path: loaded)

    snapshot = resolve_audience_profile("children", config, environ=environ)

    assert environ == original_environ
    assert loaded == original_loaded
    assert "market" not in snapshot
    assert "native_language" not in snapshot
    assert "learning_language" not in snapshot


def test_children_environment_voice_has_highest_precedence(tmp_path):
    configured = "ConfiguredVoice1234567"
    override = "EnvironmentVoice123456"
    config = write_config(tmp_path / "config.yaml", children_voice=configured)

    profile = resolve_audience_profile(
        "children",
        config,
        environ={"CHILDREN_ELEVENLABS_VOICE_ID": override},
    )

    assert profile["audio"]["voice_id"] == override


def test_children_accepts_valid_configured_voice_without_override(tmp_path):
    config = write_config(tmp_path / "config.yaml", children_voice=VALID_VOICE)

    profile = resolve_audience_profile("children", config, environ={})

    assert profile["audio"]["voice_id"] == VALID_VOICE


@pytest.mark.parametrize(
    "voice",
    ["default", "", "short", "bad-voice-id-with-hyphen", "VOICE_PENDIENTE_VALUE", "voicePLACEHOLDERvalue123"],
)
def test_children_rejects_missing_placeholder_or_malformed_voice(tmp_path, voice):
    config = write_config(tmp_path / "config.yaml", children_voice=voice)

    with pytest.raises(InvalidAudienceProfile, match="voice_id"):
        resolve_audience_profile("children", config, environ={})


def test_children_rejects_empty_environment_override(tmp_path):
    config = write_config(tmp_path / "config.yaml", children_voice=VALID_VOICE)

    with pytest.raises(InvalidAudienceProfile, match="voice_id"):
        resolve_audience_profile(
            "children",
            config,
            environ={"CHILDREN_ELEVENLABS_VOICE_ID": "   "},
        )


def test_voice_validation_uses_config_secrets_rule(tmp_path, monkeypatch):
    config = write_config(tmp_path / "config.yaml", children_voice=VALID_VOICE)
    seen = []

    monkeypatch.setattr(
        "studio.audiences.is_valid_voice_id",
        lambda value: seen.append(value) or True,
    )

    resolve_audience_profile("children", config, environ={})
    assert seen == [VALID_VOICE]


@pytest.mark.parametrize(
    ("document", "field"),
    [
        ("[]", "config"),
        ("profiles: []", "profiles"),
        ("profiles: {adults: []}", "profile"),
        ("profiles: {adults: {audio: []}}", "audio"),
        ("profiles: {adults: {metadata: []}}", "metadata"),
        ("profiles: {adults: {editorial: []}}", "editorial"),
    ],
)
def test_missing_or_non_mapping_profile_data_fails_with_field_name(tmp_path, document, field):
    config = tmp_path / "config.yaml"
    config.write_text(document, encoding="utf-8")

    with pytest.raises(InvalidAudienceProfile, match=field):
        resolve_audience_profile("adults", config, environ={})


def test_public_module_does_not_encode_workspace_policy():
    source = (Path(__file__).parents[2] / "src/studio/audiences.py").read_text(encoding="utf-8")

    for forbidden in ("bilibili", "youtube", "zh-Hans", "native_language", "learning_language"):
        assert forbidden not in source

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from studio.models import (
    ArtifactLineage,
    ArtifactRelation,
    Audience,
    CreationMode,
    CreationRequest,
    LearningLanguage,
    Market,
    NativeLanguage,
    VideoArtifact,
)


def test_creation_request_supports_auto_and_directed_modes():
    auto = CreationRequest(audience="adults", mode="auto", idea="actually")
    directed = CreationRequest(
        audience="children", mode="directed", idea="colors",
        learning_objective="Identify three primary colors", video_type="vocabulary",
    )
    assert auto.audience is Audience.ADULTS
    assert directed.mode is CreationMode.DIRECTED


def test_creation_request_rejects_unknown_audience():
    with pytest.raises(ValidationError, match="audience"):
        CreationRequest(audience="teens", mode="auto", idea="slang")


def test_creation_request_strips_idea_and_rejects_blank_value():
    request = CreationRequest(audience="adults", mode="auto", idea="  actually  ")
    assert request.idea == "actually"

    with pytest.raises(ValidationError, match="idea"):
        CreationRequest(audience="adults", mode="auto", idea="   ")


def test_legacy_request_defaults_to_youtube_spanish_workspace():
    request = CreationRequest(audience="adults", mode="auto", idea="actually")

    assert (
        request.market,
        request.native_language,
        request.learning_language,
    ) == (Market.YOUTUBE, NativeLanguage.SPANISH, LearningLanguage.ENGLISH)
    dumped = request.model_dump()
    assert dumped["market"] is Market.YOUTUBE
    assert dumped["native_language"] is NativeLanguage.SPANISH
    assert dumped["learning_language"] is LearningLanguage.ENGLISH


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_bilibili_simplified_mandarin_workspace_is_valid_for_each_audience(audience):
    request = CreationRequest(
        market="bilibili",
        native_language="zh-Hans",
        learning_language="en",
        audience=audience,
        mode="directed",
        idea="colors",
    )

    assert request.market is Market.BILIBILI
    assert request.native_language is NativeLanguage.SIMPLIFIED_MANDARIN
    assert request.learning_language is LearningLanguage.ENGLISH


@pytest.mark.parametrize(
    ("market", "native_language"),
    [("bilibili", "es"), ("youtube", "zh-Hans")],
)
def test_invalid_workspace_combination_is_rejected(market, native_language):
    with pytest.raises(ValidationError, match="workspace"):
        CreationRequest(
            market=market,
            native_language=native_language,
            learning_language="en",
            audience="adults",
            mode="auto",
            idea="actually",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market", "vimeo"),
        ("native_language", "fr"),
        ("learning_language", "de"),
    ],
)
def test_unknown_workspace_enum_values_are_rejected(field, value):
    values = {
        "market": "youtube",
        "native_language": "es",
        "learning_language": "en",
        "audience": "adults",
        "mode": "auto",
        "idea": "actually",
        field: value,
    }

    with pytest.raises(ValidationError, match=field):
        CreationRequest(**values)


def test_creation_request_rejects_reversed_duration_range_and_unknown_fields():
    with pytest.raises(ValidationError, match="duration_min_seconds"):
        CreationRequest(
            audience="adults",
            mode="auto",
            idea="actually",
            duration_min_seconds=60,
            duration_max_seconds=30,
        )

    with pytest.raises(ValidationError, match="extra_forbidden"):
        CreationRequest(
            audience="adults",
            mode="auto",
            idea="actually",
            is_chinese=True,
        )


def test_direct_artifact_has_no_lineage_and_uses_generic_snapshots():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    artifact = VideoArtifact.new(
        CreationRequest(audience="adults", mode="auto", idea="actually"),
        "art_01",
        now,
    )

    assert artifact.lineage is None
    assert artifact.schema_version == 2
    assert artifact.performance_snapshots == []
    assert "youtube_snapshots" not in artifact.model_dump()


def test_adaptation_has_distinct_typed_lineage():
    lineage = ArtifactLineage(
        source_artifact_id="  art_yt_01  ",
        relation="adaptation",
        preserved_learning_objective="  Use actually naturally in a correction  ",
    )
    artifact = VideoArtifact.new(
        CreationRequest(
            market="bilibili",
            native_language="zh-Hans",
            learning_language="en",
            audience="adults",
            mode="auto",
            idea="actually",
        ),
        "art_bili_01",
        datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
        lineage=lineage,
    )

    assert artifact.lineage == ArtifactLineage(
        source_artifact_id="art_yt_01",
        relation=ArtifactRelation.ADAPTATION,
        preserved_learning_objective="Use actually naturally in a correction",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_artifact_id", "   "),
        ("preserved_learning_objective", "   "),
    ],
)
def test_lineage_rejects_empty_text_fields(field, value):
    values = {
        "source_artifact_id": "art_yt_01",
        "relation": "adaptation",
        "preserved_learning_objective": "Use actually naturally",
        field: value,
    }

    with pytest.raises(ValidationError, match=field):
        ArtifactLineage(**values)


def test_new_artifact_rejects_self_lineage():
    with pytest.raises(ValidationError, match="source_artifact_id.*artifact_id"):
        VideoArtifact.new(
            CreationRequest(audience="adults", mode="auto", idea="actually"),
            "art_01",
            datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
            lineage=ArtifactLineage(
                source_artifact_id="art_01",
                relation="adaptation",
                preserved_learning_objective="Use actually naturally",
            ),
        )


def test_new_artifact_starts_with_draft_event():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    request = CreationRequest(audience="adults", mode="auto", idea="actually")
    artifact = VideoArtifact.new(request, "art_01", now)
    assert artifact.state.value == "draft"
    assert artifact.created_at == artifact.updated_at == now
    assert [(e.previous_state, e.next_state) for e in artifact.events] == [(None, "draft")]


def test_direct_and_adapted_artifacts_have_independent_empty_production_metadata():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    request = CreationRequest(audience="adults", mode="auto", idea="actually")
    direct = VideoArtifact.new(request, "art_direct", now)
    adapted = VideoArtifact.new(
        request,
        "art_adapted",
        now,
        lineage=ArtifactLineage(
            source_artifact_id="art_source",
            relation="adaptation",
            preserved_learning_objective="Use actually naturally",
        ),
    )

    assert direct.production == adapted.production == {}
    direct.production["stage"] = "rendered"
    assert adapted.production == {}


def test_explicit_nested_production_metadata_survives_strict_validation():
    artifact = VideoArtifact.new(
        CreationRequest(audience="children", mode="directed", idea="颜色练习"),
        "art_zh_01",
        datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
    )
    payload = artifact.model_dump()
    payload["production"] = {
        "background": {"selection_reason": "适合颜色课程", "recently_used": False},
        "scrim": {"opacity": 0.28},
        "versions": {"renderer": "render-v2", "tts": "eleven_turbo_v2_5"},
        "stages": {"tts": "complete", "render": "pending"},
    }

    validated = VideoArtifact.model_validate(payload)

    assert validated.production == payload["production"]


def test_unknown_outer_artifact_field_remains_forbidden():
    artifact = VideoArtifact.new(
        CreationRequest(audience="adults", mode="auto", idea="actually"),
        "art_01",
        datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
    )
    payload = artifact.model_dump()
    payload["production_metadata"] = {}

    with pytest.raises(ValidationError, match="extra_forbidden"):
        VideoArtifact.model_validate(payload)

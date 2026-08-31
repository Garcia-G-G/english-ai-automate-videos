from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from studio.models import Audience, CreationMode, CreationRequest, VideoArtifact


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


def test_new_artifact_starts_with_draft_event():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    request = CreationRequest(audience="adults", mode="auto", idea="actually")
    artifact = VideoArtifact.new(request, "art_01", now)
    assert artifact.state.value == "draft"
    assert artifact.schema_version == 1
    assert [(e.previous_state, e.next_state) for e in artifact.events] == [(None, "draft")]

from datetime import datetime, timedelta, timezone

import pytest

from studio.lifecycle import InvalidTransition, transition
from studio.models import (
    ArtifactLineage,
    ArtifactState,
    CreationRequest,
    VideoArtifact,
)


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=1)

VALID_EDGES = [
    ("draft", "writing"),
    ("draft", "archived"),
    ("writing", "ready_for_production"),
    ("writing", "blocked_editorial"),
    ("blocked_editorial", "writing"),
    ("blocked_editorial", "rejected"),
    ("blocked_editorial", "archived"),
    ("ready_for_production", "producing"),
    ("ready_for_production", "archived"),
    ("producing", "ready_for_review"),
    ("producing", "blocked_production"),
    ("blocked_production", "producing"),
    ("blocked_production", "rejected"),
    ("blocked_production", "archived"),
    ("ready_for_review", "approved"),
    ("ready_for_review", "rejected"),
    ("ready_for_review", "writing"),
    ("ready_for_review", "archived"),
    ("approved", "publishing"),
    ("approved", "rejected"),
    ("approved", "archived"),
    ("rejected", "writing"),
    ("rejected", "archived"),
    ("publishing", "published"),
    ("publishing", "partially_published"),
    ("publishing", "approved"),
    ("partially_published", "publishing"),
    ("partially_published", "published"),
    ("partially_published", "archived"),
    ("published", "archived"),
]

OWNER_GATED_EDGES = [
    ("draft", "archived"),
    ("blocked_editorial", "rejected"),
    ("blocked_editorial", "archived"),
    ("ready_for_production", "archived"),
    ("blocked_production", "rejected"),
    ("blocked_production", "archived"),
    ("ready_for_review", "approved"),
    ("ready_for_review", "rejected"),
    ("ready_for_review", "writing"),
    ("ready_for_review", "archived"),
    ("approved", "publishing"),
    ("approved", "rejected"),
    ("approved", "archived"),
    ("rejected", "archived"),
    ("partially_published", "publishing"),
    ("partially_published", "archived"),
    ("published", "archived"),
]


def artifact_in_state(state="draft", *, adapted=False):
    request = CreationRequest(
        market="bilibili" if adapted else "youtube",
        native_language="zh-Hans" if adapted else "es",
        learning_language="en",
        audience="children" if adapted else "adults",
        mode="auto",
        idea="actually",
    )
    lineage = None
    artifact_id = "art_01"
    if adapted:
        artifact_id = "art_bili_01"
        lineage = ArtifactLineage(
            source_artifact_id="art_yt_01",
            relation="adaptation",
            preserved_learning_objective="Use actually naturally",
        )
    artifact = VideoArtifact.new(request, artifact_id, NOW, lineage=lineage)
    return artifact.model_copy(update={"state": ArtifactState(state)})


def actor_for(source, destination):
    if (source, destination) in OWNER_GATED_EDGES:
        return "owner"
    return "system"


@pytest.mark.parametrize(("source", "destination"), VALID_EDGES)
def test_every_listed_graph_edge_succeeds(source, destination):
    changed = transition(
        artifact_in_state(source),
        destination,
        actor=actor_for(source, destination),
        reason="approved transition",
        now=LATER,
    )

    assert changed.state is ArtifactState(destination)


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("draft", "published"),
        ("writing", "producing"),
        ("ready_for_production", "ready_for_review"),
        ("approved", "published"),
    ],
)
def test_representative_unlisted_edges_are_rejected(source, destination):
    artifact = artifact_in_state(source)
    before = artifact.model_dump()

    with pytest.raises(InvalidTransition, match=f"{source}.*{destination}"):
        transition(artifact, destination, actor="owner", reason="shortcut", now=LATER)

    assert artifact.model_dump() == before


@pytest.mark.parametrize("state", [state.value for state in ArtifactState])
def test_every_same_state_transition_is_rejected(state):
    with pytest.raises(InvalidTransition, match=f"{state}.*{state}"):
        transition(
            artifact_in_state(state),
            state,
            actor="owner",
            reason="no change",
            now=LATER,
        )


@pytest.mark.parametrize("destination", [state.value for state in ArtifactState])
def test_archived_has_no_outgoing_transitions(destination):
    with pytest.raises(InvalidTransition, match=f"archived.*{destination}"):
        transition(
            artifact_in_state("archived"),
            destination,
            actor="owner",
            reason="restore",
            now=LATER,
        )


def test_enum_destination_works_and_unknown_string_is_wrapped():
    changed = transition(
        artifact_in_state(),
        ArtifactState.WRITING,
        actor="system",
        reason="start",
        now=LATER,
    )
    assert changed.state is ArtifactState.WRITING

    with pytest.raises(InvalidTransition, match="draft.*unknown"):
        transition(
            artifact_in_state(),
            "unknown",
            actor="system",
            reason="start",
            now=LATER,
        )


def test_success_returns_copy_and_changes_only_state_time_and_events():
    original = artifact_in_state()
    original_dump = original.model_dump()
    original_events = original.events

    changed = transition(
        original,
        "writing",
        actor="system",
        reason="start",
        now=LATER,
    )

    expected = original_dump | {
        "state": ArtifactState.WRITING,
        "updated_at": LATER,
        "events": changed.model_dump()["events"],
    }
    assert changed is not original
    assert changed.model_dump() == expected
    assert original.model_dump() == original_dump
    assert original.events is original_events
    assert changed.events is not original.events


def test_success_appends_exactly_one_normalized_event():
    original = artifact_in_state()
    changed = transition(
        original,
        "writing",
        actor="  system  ",
        reason="  generation started  ",
        now=LATER,
    )

    assert len(changed.events) == len(original.events) + 1
    event = changed.events[-1]
    assert event.timestamp == LATER
    assert event.previous_state is ArtifactState.DRAFT
    assert event.next_state is ArtifactState.WRITING
    assert event.actor == "system"
    assert event.reason == "generation started"


@pytest.mark.parametrize(
    ("actor", "reason", "message"),
    [("   ", "start", "actor"), ("system", "   ", "reason")],
)
def test_blank_actor_or_reason_fails_without_mutation(actor, reason, message):
    artifact = artifact_in_state()
    before = artifact.model_dump()

    with pytest.raises(InvalidTransition, match=message):
        transition(artifact, "writing", actor=actor, reason=reason, now=LATER)

    assert artifact.model_dump() == before


@pytest.mark.parametrize(
    ("now", "message"),
    [(datetime(2026, 8, 31, 12, 1), "timezone"), (NOW - timedelta(seconds=1), "updated_at")],
)
def test_invalid_transition_time_fails_without_mutation(now, message):
    artifact = artifact_in_state()
    before = artifact.model_dump()

    with pytest.raises(InvalidTransition, match=message):
        transition(artifact, "writing", actor="system", reason="start", now=now)

    assert artifact.model_dump() == before


def test_equal_timezone_aware_timestamp_is_accepted():
    changed = transition(
        artifact_in_state(),
        "writing",
        actor="system",
        reason="start",
        now=NOW,
    )

    assert changed.updated_at == NOW


@pytest.mark.parametrize(("source", "destination"), OWNER_GATED_EDGES)
def test_system_cannot_perform_owner_gated_edges(source, destination):
    artifact = artifact_in_state(source)
    before = artifact.model_dump()

    with pytest.raises(InvalidTransition, match="owner"):
        transition(
            artifact,
            destination,
            actor="system",
            reason="automatic action",
            now=LATER,
        )

    assert artifact.model_dump() == before


@pytest.mark.parametrize(("source", "destination"), OWNER_GATED_EDGES)
def test_owner_can_perform_every_owner_gated_edge(source, destination):
    changed = transition(
        artifact_in_state(source),
        destination,
        actor="  owner  ",
        reason="owner decision",
        now=LATER,
    )

    assert changed.state is ArtifactState(destination)
    assert changed.events[-1].actor == "owner"


def test_system_can_recover_publishing_to_approved():
    changed = transition(
        artifact_in_state("publishing"),
        "approved",
        actor="system",
        reason="all publication attempts failed",
        now=LATER,
    )

    assert changed.state is ArtifactState.APPROVED


def test_schema_workspace_and_lineage_survive_transition():
    original = artifact_in_state(adapted=True)
    changed = transition(
        original,
        "writing",
        actor="system",
        reason="start adaptation",
        now=LATER,
    )

    assert changed.schema_version == 2
    assert changed.request == original.request
    assert changed.lineage == original.lineage


def test_transition_preserves_production_metadata_unchanged():
    original = artifact_in_state().model_copy(
        update={
            "production": {
                "background": {"selection_reason": "least_recently_used"},
                "scrim": {"opacity": 0.25},
                "stages": {"tts": "complete"},
            }
        }
    )

    changed = transition(
        original,
        "writing",
        actor="system",
        reason="start",
        now=LATER,
    )

    assert changed.production == original.production
    assert changed.model_dump()["production"] == original.model_dump()["production"]
    assert len(changed.events) == len(original.events) + 1

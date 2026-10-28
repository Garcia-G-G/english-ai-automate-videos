"""Canonical lifecycle transitions for video artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Set, Union

from .models import ArtifactEvent, ArtifactState, VideoArtifact


class InvalidTransition(ValueError):
    """A requested artifact lifecycle operation is not allowed."""


_ALLOWED_TRANSITIONS: Dict[ArtifactState, Set[ArtifactState]] = {
    ArtifactState.DRAFT: {
        ArtifactState.WRITING,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.WRITING: {
        ArtifactState.READY_FOR_PRODUCTION,
        ArtifactState.BLOCKED_EDITORIAL,
    },
    ArtifactState.BLOCKED_EDITORIAL: {
        ArtifactState.WRITING,
        ArtifactState.REJECTED,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.READY_FOR_PRODUCTION: {
        ArtifactState.PRODUCING,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.PRODUCING: {
        ArtifactState.READY_FOR_REVIEW,
        ArtifactState.BLOCKED_PRODUCTION,
    },
    ArtifactState.BLOCKED_PRODUCTION: {
        ArtifactState.PRODUCING,
        ArtifactState.REJECTED,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.READY_FOR_REVIEW: {
        ArtifactState.APPROVED,
        ArtifactState.REJECTED,
        ArtifactState.WRITING,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.APPROVED: {
        ArtifactState.PUBLISHING,
        ArtifactState.REJECTED,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.REJECTED: {
        ArtifactState.WRITING,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.PUBLISHING: {
        ArtifactState.PUBLISHED,
        ArtifactState.PARTIALLY_PUBLISHED,
        ArtifactState.APPROVED,
    },
    ArtifactState.PARTIALLY_PUBLISHED: {
        ArtifactState.PUBLISHING,
        ArtifactState.PUBLISHED,
        ArtifactState.ARCHIVED,
    },
    ArtifactState.PUBLISHED: {
        ArtifactState.ARCHIVED,
    },
    ArtifactState.ARCHIVED: set(),
}

_OWNER_DESTINATIONS = {
    ArtifactState.APPROVED,
    ArtifactState.REJECTED,
    ArtifactState.PUBLISHING,
    ArtifactState.ARCHIVED,
}


def transition(
    artifact: VideoArtifact,
    next_state: Union[ArtifactState, str],
    *,
    actor: str,
    reason: str,
    now: datetime,
) -> VideoArtifact:
    """Return an artifact copy after one valid, event-backed transition."""
    source = artifact.state
    requested = next_state.value if isinstance(next_state, ArtifactState) else str(next_state)
    try:
        destination = ArtifactState(next_state)
    except (TypeError, ValueError) as exc:
        raise InvalidTransition(
            f"invalid transition from {source.value} to {requested}"
        ) from exc

    if destination not in _ALLOWED_TRANSITIONS[source]:
        raise InvalidTransition(
            f"invalid transition from {source.value} to {destination.value}"
        )

    if not isinstance(actor, str) or not actor.strip():
        raise InvalidTransition("actor must be non-empty")
    normalized_actor = actor.strip()

    if not isinstance(reason, str) or not reason.strip():
        raise InvalidTransition("reason must be non-empty")
    normalized_reason = reason.strip()

    if now.tzinfo is None or now.utcoffset() is None:
        raise InvalidTransition("now must be timezone-aware")
    try:
        time_regressed = now < artifact.updated_at
    except TypeError as exc:
        raise InvalidTransition("now must be comparable to artifact.updated_at") from exc
    if time_regressed:
        raise InvalidTransition("now must be greater than or equal to artifact.updated_at")

    recovery_to_approved = (
        source is ArtifactState.PUBLISHING
        and destination is ArtifactState.APPROVED
    )
    owner_revision = (
        source is ArtifactState.READY_FOR_REVIEW
        and destination is ArtifactState.WRITING
    )
    if (
        (destination in _OWNER_DESTINATIONS and not recovery_to_approved)
        or owner_revision
    ) and normalized_actor != "owner":
        raise InvalidTransition(
            f"transition from {source.value} to {destination.value} requires owner actor"
        )

    event = ArtifactEvent(
        timestamp=now,
        previous_state=source,
        next_state=destination,
        actor=normalized_actor,
        reason=normalized_reason,
    )
    return artifact.model_copy(
        update={
            "state": destination,
            "updated_at": now,
            "events": [*artifact.events, event],
        }
    )

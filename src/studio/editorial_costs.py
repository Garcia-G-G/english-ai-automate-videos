"""Shared conversion and attribution for legacy API cost entries."""

from __future__ import annotations

import copy
from typing import Callable, Tuple, TypeVar

from .creation import AuthorFailure
from .models import ArtifactCost


T = TypeVar("T")


def artifact_cost(entry: dict) -> ArtifactCost:
    if not isinstance(entry, dict) or "cost_usd" not in entry:
        raise ValueError("cost tracker returned invalid entry")
    details = {
        key: copy.deepcopy(value)
        for key, value in entry.items()
        if key not in {"api_type", "cost_usd", "timestamp"}
    }
    return ArtifactCost(
        category=str(entry.get("api_type", "unknown")),
        amount=entry["cost_usd"],
        details=details,
    )


def cost_delta(tracker, start: int) -> list[ArtifactCost]:
    return [artifact_cost(entry) for entry in tracker.entries[start:]]


def invoke_with_costs(tracker, invocation: Callable[[], T]) -> Tuple[T, list[ArtifactCost]]:
    """Run one author invocation and attach only its new cost entries."""
    start = len(tracker.entries)
    try:
        value = invocation()
    except Exception as exc:
        raise AuthorFailure(exc, costs=cost_delta(tracker, start)) from exc
    return value, cost_delta(tracker, start)

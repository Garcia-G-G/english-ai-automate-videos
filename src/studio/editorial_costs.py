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


#: Where spend incurred before a production failure is parked on the
#: exception carrying that failure.
#:
#: WHY NOT A WRAPPER EXCEPTION, as the editorial half uses. The production
#: gateway's contract is that the ORIGINAL exception object reaches the
#: caller — tests/studio/test_legacy_pipeline.py asserts `raised.value is
#: error` for every delegated stage, so a broken renderer cannot be
#: disguised as a pipeline error. Replacing the exception to carry money
#: would trade a real diagnostic guarantee for a bookkeeping convenience.
#: The object is annotated instead and re-raised unchanged.
_COSTS_ATTRIBUTE = "studio_costs"


def attach_costs(exc: BaseException, tracker, start: int) -> BaseException:
    """Record on `exc` what was spent since `start`, and return it.

    Best effort by design: an exception type that refuses attributes
    (__slots__, some C extensions) must not turn a render failure into an
    attribute error on top of it. The ledger write in the gateway's finally
    is the authoritative record; this is the copy the artifact shows.
    """
    try:
        setattr(exc, _COSTS_ATTRIBUTE, cost_delta(tracker, start))
    except Exception:                                          # noqa: BLE001
        pass
    return exc


def costs_of(exc: BaseException) -> list[ArtifactCost]:
    """The spend attached to a failure, or an empty list if none was."""
    attached = getattr(exc, _COSTS_ATTRIBUTE, None)
    return list(attached) if isinstance(attached, list) else []

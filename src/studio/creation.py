"""Checkpointed application service for canonical video creation."""

from __future__ import annotations

import copy
import re
import secrets
from datetime import datetime, timezone
from typing import Callable, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .artifacts import ArtifactRepository
from .lifecycle import transition
from .models import (
    ArtifactCost,
    ArtifactLineage,
    ArtifactPaths,
    CreationRequest,
    VideoArtifact,
)
from .profile_bundle import resolve_profile_bundle


ProgressCallback = Callable[[str, int], None]
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{8}$")
_COMPATIBILITY_GATE = {
    "kind": "compatibility",
    "status": "not_run",
    "version": 1,
}


@runtime_checkable
class ScriptAuthor(Protocol):
    def generate(self, request: CreationRequest, profile: dict) -> "AuthorResult":
        """Generate one script for a resolved creation request."""


@runtime_checkable
class ProductionGateway(Protocol):
    def produce(
        self,
        artifact: VideoArtifact,
        script: dict,
        profile: dict,
        progress: ProgressCallback,
    ) -> "ProductionResult":
        """Produce canonical media metadata for an artifact."""


class ProductionResult(BaseModel):
    """Strict value returned by an injected production gateway."""

    model_config = ConfigDict(extra="forbid")

    paths: ArtifactPaths = Field(default_factory=ArtifactPaths)
    costs: List[ArtifactCost] = Field(default_factory=list)
    production: dict = Field(default_factory=dict)
    gates: List[dict[str, JsonValue]] = Field(default_factory=list)


class AuthorResult(BaseModel):
    """Strict script and invocation costs returned by a script author."""

    model_config = ConfigDict(extra="forbid")

    script: dict
    costs: List[ArtifactCost] = Field(default_factory=list)


class AuthorFailure(Exception):
    """An author failure carrying costs incurred before its original cause."""

    def __init__(self, cause: Exception, *, costs: Optional[List[ArtifactCost]] = None):
        self.cause = cause
        self.costs = [cost.model_copy(deep=True) for cost in (costs or [])]
        super().__init__(str(cause))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return secrets.token_hex(4)


def _no_progress(step: str, percent: int) -> None:
    return None


class CreationService:
    """Own deterministic creation orchestration above injected collaborators."""

    def __init__(
        self,
        repository: ArtifactRepository,
        author: ScriptAuthor,
        producer: ProductionGateway,
        profile_resolver: Callable[[CreationRequest], dict] = resolve_profile_bundle,
        clock: Callable[[], datetime] = _utc_now,
        token_factory: Callable[[], str] = _token,
    ):
        self.repository = repository
        self.author = author
        self.producer = producer
        self.profile_resolver = profile_resolver
        self.clock = clock
        self.token_factory = token_factory

    def create(
        self,
        request: CreationRequest,
        *,
        artifact_id: Optional[str] = None,
        lineage: Optional[ArtifactLineage] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> VideoArtifact:
        creation_time = self._clock_utc()
        chosen_artifact_id = (
            artifact_id
            if artifact_id is not None
            else self._generated_id(creation_time)
        )

        artifact = VideoArtifact.new(
            request,
            chosen_artifact_id,
            creation_time,
            lineage=lineage,
        )
        self.repository.create(artifact)

        artifact = self._transition(
            artifact,
            "writing",
            reason="creation_started",
        )
        self.repository.save(artifact)

        try:
            resolved = self.profile_resolver(copy.deepcopy(request))
            if type(resolved) is not dict:
                raise TypeError("profile_resolver must return dict")
        except Exception as exc:
            return self._editorial_failure(artifact, exc)

        profile = copy.deepcopy(resolved)
        artifact = artifact.model_copy(
            update={"resolved_profile": copy.deepcopy(profile)}
        )
        self.repository.save(artifact)

        try:
            generated = self.author.generate(
                copy.deepcopy(request),
                copy.deepcopy(profile),
            )
            if not isinstance(generated, AuthorResult):
                raise TypeError("author.generate must return AuthorResult")
        except AuthorFailure as failure:
            if failure.costs:
                artifact = artifact.model_copy(
                    update={
                        "costs": [
                            *artifact.costs,
                            *(cost.model_copy(deep=True) for cost in failure.costs),
                        ]
                    }
                )
                self.repository.save(artifact)
            return self._editorial_failure(artifact, failure.cause)
        except Exception as exc:
            return self._editorial_failure(artifact, exc)

        script = copy.deepcopy(generated.script)
        artifact = artifact.model_copy(
            update={
                "scripts": [*artifact.scripts, copy.deepcopy(script)],
                "costs": [
                    *artifact.costs,
                    *(cost.model_copy(deep=True) for cost in generated.costs),
                ],
            }
        )
        self.repository.save(artifact)

        artifact = artifact.model_copy(
            update={"gates": [*artifact.gates, copy.deepcopy(_COMPATIBILITY_GATE)]}
        )
        self.repository.save(artifact)

        artifact = self._transition(
            artifact,
            "ready_for_production",
            reason="editorial_compatibility_ready",
        )
        self.repository.save(artifact)

        artifact = self._transition(
            artifact,
            "producing",
            reason="production_started",
        )
        self.repository.save(artifact)

        progress_callback = _no_progress if progress is None else progress
        try:
            produced = self.producer.produce(
                artifact.model_copy(deep=True),
                copy.deepcopy(script),
                copy.deepcopy(profile),
                progress_callback,
            )
            if not isinstance(produced, ProductionResult):
                raise TypeError("producer.produce must return ProductionResult")
            produced = ProductionResult.model_validate(
                produced.model_dump(warnings=False)
            )
        except Exception as exc:
            return self._production_failure(artifact, exc)

        artifact = artifact.model_copy(
            update={
                "paths": produced.paths.model_copy(deep=True),
                "costs": [
                    *artifact.costs,
                    *(cost.model_copy(deep=True) for cost in produced.costs),
                ],
                "production": copy.deepcopy(produced.production),
                "gates": [
                    *artifact.gates,
                    *(copy.deepcopy(gate) for gate in produced.gates),
                ],
                "error": None,
            }
        )
        self.repository.save(artifact)

        artifact = self._transition(
            artifact,
            "ready_for_review",
            reason="production_completed",
        )
        self.repository.save(artifact)
        return artifact

    def _generated_id(self, creation_time: datetime) -> str:
        token = self.token_factory()
        if not isinstance(token, str) or not _TOKEN_PATTERN.fullmatch(token):
            raise ValueError("token_factory must return eight lowercase hexadecimal characters")
        return f"art_{creation_time:%Y%m%d_%H%M%S}_{token}"

    def _clock_utc(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _transition(
        self,
        artifact: VideoArtifact,
        next_state: str,
        *,
        reason: str,
    ) -> VideoArtifact:
        return transition(
            artifact,
            next_state,
            actor="system",
            reason=reason,
            now=self._clock_utc(),
        )

    @staticmethod
    def _error(exc: Exception) -> str:
        return f"{exc.__class__.__name__}: {exc}"

    def _editorial_failure(
        self,
        artifact: VideoArtifact,
        exc: Exception,
    ) -> VideoArtifact:
        error = self._error(exc)
        failed = artifact.model_copy(update={"error": error})
        failed = self._transition(
            failed,
            "blocked_editorial",
            reason=f"editorial_failed: {error}",
        )
        self.repository.save(failed)
        return failed

    def _production_failure(
        self,
        artifact: VideoArtifact,
        exc: Exception,
    ) -> VideoArtifact:
        error = self._error(exc)
        failed = artifact.model_copy(update={"error": error})
        failed = self._transition(
            failed,
            "blocked_production",
            reason=f"production_failed: {error}",
        )
        self.repository.save(failed)
        return failed

"""Strict persisted contracts for Editorial Studio creation and artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Audience(str, Enum):
    ADULTS = "adults"
    CHILDREN = "children"


class CreationMode(str, Enum):
    AUTO = "auto"
    DIRECTED = "directed"


class ArtifactState(str, Enum):
    DRAFT = "draft"
    WRITING = "writing"
    BLOCKED_EDITORIAL = "blocked_editorial"
    READY_FOR_PRODUCTION = "ready_for_production"
    PRODUCING = "producing"
    BLOCKED_PRODUCTION = "blocked_production"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIALLY_PUBLISHED = "partially_published"
    ARCHIVED = "archived"


class PersistedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreationRequest(PersistedModel):
    audience: Audience
    mode: CreationMode
    idea: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    category: Optional[str] = None
    topic: Optional[str] = None
    learning_objective: Optional[str] = None
    learner_level: Optional[str] = None
    video_type: Optional[str] = None
    duration_min_seconds: Optional[int] = None
    duration_max_seconds: Optional[int] = None
    tone: Optional[str] = None
    voice_id: Optional[str] = None
    background: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_duration_range(self):
        if (
            self.duration_min_seconds is not None
            and self.duration_max_seconds is not None
            and self.duration_min_seconds > self.duration_max_seconds
        ):
            raise ValueError(
                "duration_min_seconds must be less than or equal to "
                "duration_max_seconds"
            )
        return self


class ArtifactEvent(PersistedModel):
    timestamp: datetime
    previous_state: Optional[ArtifactState]
    next_state: ArtifactState
    actor: str
    reason: str


class ArtifactPaths(PersistedModel):
    script: Optional[str] = None
    audio: Optional[str] = None
    video: Optional[str] = None
    background: Optional[str] = None


class ArtifactCost(PersistedModel):
    category: str
    amount: float
    currency: str = "USD"
    details: Dict[str, Any] = Field(default_factory=dict)


class VideoArtifact(PersistedModel):
    schema_version: int
    artifact_id: str
    created_at: datetime
    updated_at: datetime
    state: ArtifactState
    request: CreationRequest
    resolved_profile: Dict[str, Any] = Field(default_factory=dict)
    scripts: List[Dict[str, Any]] = Field(default_factory=list)
    gates: List[Dict[str, Any]] = Field(default_factory=list)
    paths: ArtifactPaths = Field(default_factory=ArtifactPaths)
    costs: List[ArtifactCost] = Field(default_factory=list)
    events: List[ArtifactEvent] = Field(default_factory=list)
    owner_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    publications: List[Dict[str, Any]] = Field(default_factory=list)
    youtube_snapshots: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None

    @classmethod
    def new(
        cls,
        request: CreationRequest,
        artifact_id: str,
        now: datetime,
    ) -> "VideoArtifact":
        return cls(
            schema_version=1,
            artifact_id=artifact_id,
            created_at=now,
            updated_at=now,
            state=ArtifactState.DRAFT,
            request=request,
            events=[
                ArtifactEvent(
                    timestamp=now,
                    previous_state=None,
                    next_state=ArtifactState.DRAFT,
                    actor="system",
                    reason="artifact_created",
                )
            ],
        )

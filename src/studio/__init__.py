"""Canonical application contracts for the Editorial Studio."""

from .artifacts import (
    ArtifactAlreadyExists,
    ArtifactCorrupt,
    ArtifactNotFound,
    ArtifactRepository,
    ArtifactRepositoryError,
    ArtifactWriteError,
    InvalidArtifactId,
)
from .audiences import (
    InvalidAudienceProfile,
    normalize_audience,
    resolve_audience_profile,
)
from .creation import (
    CreationService,
    ProductionGateway,
    ProductionResult,
    ScriptAuthor,
)
from .lifecycle import InvalidTransition, transition
from .legacy_pipeline import LegacyProductionGateway, TopicScriptAuthor
from .models import (
    ArtifactCost,
    ArtifactEvent,
    ArtifactLineage,
    ArtifactPaths,
    ArtifactRelation,
    ArtifactState,
    Audience,
    CreationMode,
    CreationRequest,
    LearningLanguage,
    Market,
    NativeLanguage,
    VideoArtifact,
)
from .profile_bundle import InvalidProfileBundle, resolve_profile_bundle
from .workspaces import InvalidWorkspaceProfile, resolve_workspace_profile
from .voices import InvalidVoiceProfile, resolve_voice_profile

__all__ = [
    "ArtifactCost",
    "ArtifactAlreadyExists",
    "ArtifactCorrupt",
    "ArtifactEvent",
    "ArtifactLineage",
    "ArtifactPaths",
    "ArtifactRelation",
    "ArtifactRepository",
    "ArtifactRepositoryError",
    "ArtifactState",
    "ArtifactNotFound",
    "ArtifactWriteError",
    "Audience",
    "CreationMode",
    "CreationRequest",
    "CreationService",
    "InvalidTransition",
    "InvalidAudienceProfile",
    "InvalidArtifactId",
    "InvalidProfileBundle",
    "InvalidWorkspaceProfile",
    "InvalidVoiceProfile",
    "LearningLanguage",
    "LegacyProductionGateway",
    "Market",
    "NativeLanguage",
    "ProductionGateway",
    "ProductionResult",
    "ScriptAuthor",
    "TopicScriptAuthor",
    "VideoArtifact",
    "normalize_audience",
    "resolve_audience_profile",
    "resolve_profile_bundle",
    "resolve_workspace_profile",
    "resolve_voice_profile",
    "transition",
]

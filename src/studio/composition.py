"""Workspace-routed composition root for canonical creation."""

from __future__ import annotations

from pathlib import Path

from .artifacts import ArtifactRepository
from .bilibili import BilibiliScriptAuthor
from .bilibili_production import BilibiliProductionGateway
from .creation import CreationService
from .legacy_pipeline import LegacyProductionGateway, TopicScriptAuthor
from .models import LearningLanguage, Market, NativeLanguage
from .profile_bundle import resolve_profile_bundle


_YOUTUBE = (Market.YOUTUBE, NativeLanguage.SPANISH, LearningLanguage.ENGLISH)
_BILIBILI = (
    Market.BILIBILI,
    NativeLanguage.SIMPLIFIED_MANDARIN,
    LearningLanguage.ENGLISH,
)


def _workspace(request):
    dimensions = (request.market, request.native_language, request.learning_language)
    if dimensions == _YOUTUBE:
        return Market.YOUTUBE
    if dimensions == _BILIBILI:
        return Market.BILIBILI
    values = tuple(getattr(value, "value", value) for value in dimensions)
    raise ValueError(f"unsupported workspace: {' + '.join(values)}")


class WorkspaceScriptAuthor:
    def __init__(self, youtube, bilibili):
        self.youtube = youtube
        self.bilibili = bilibili

    def generate(self, request, profile):
        selected = self.youtube if _workspace(request) is Market.YOUTUBE else self.bilibili
        return selected.generate(request, profile)


class WorkspaceProductionGateway:
    def __init__(self, youtube, bilibili):
        self.youtube = youtube
        self.bilibili = bilibili

    def produce(self, artifact, script, profile, progress):
        selected = (
            self.youtube
            if _workspace(artifact.request) is Market.YOUTUBE
            else self.bilibili
        )
        return selected.produce(artifact, script, profile, progress)


def build_creation_service(
    root: Path,
    *,
    repository=None,
    youtube_author=None,
    bilibili_author=None,
    youtube_producer=None,
    bilibili_producer=None,
    profile_resolver=resolve_profile_bundle,
    clock=None,
    token_factory=None,
) -> CreationService:
    """Build one service whose only routing dimension is the typed workspace."""
    root = Path(root)
    repository = repository or ArtifactRepository(root)
    author = WorkspaceScriptAuthor(
        youtube_author or TopicScriptAuthor(),
        bilibili_author or BilibiliScriptAuthor(),
    )
    producer = WorkspaceProductionGateway(
        youtube_producer or LegacyProductionGateway(root),
        bilibili_producer or BilibiliProductionGateway(root),
    )
    kwargs = {"profile_resolver": profile_resolver}
    if clock is not None:
        kwargs["clock"] = clock
    if token_factory is not None:
        kwargs["token_factory"] = token_factory
    return CreationService(repository, author, producer, **kwargs)

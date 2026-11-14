from datetime import datetime, timezone

import pytest

from studio.artifacts import ArtifactRepository
from studio.creation import AuthorFailure, AuthorResult, ProductionResult
from studio.models import ArtifactCost, ArtifactPaths, CreationRequest


def request(market, audience):
    return CreationRequest(
        market=market,
        native_language="es" if market == "youtube" else "zh-Hans",
        learning_language="en", audience=audience, mode="auto", idea="lesson",
    )


def profile(req):
    workspace_id = "youtube_es_en" if req.market.value == "youtube" else "bilibili_zh_hans_en"
    locale = "es" if req.market.value == "youtube" else "zh-Hans"
    return {
        "profile_schema_version": 1,
        "workspace": {"workspace_id": workspace_id, "market": req.market.value,
                      "native_language": req.native_language.value,
                      "learning_language": "en"},
        "audience": {"audience": req.audience.value, "name": req.audience.value},
        "voice": {"workspace_id": workspace_id, "audience": req.audience.value,
                  "locale": locale, "voice_id": "Voice123456789"},
    }


class Author:
    def __init__(self, label, calls):
        self.label, self.calls = label, calls

    def generate(self, req, resolved):
        self.calls.append(("author", self.label, req.market.value, req.audience.value))
        return AuthorResult(
            script={"type": "educational", "full_script": f"{self.label} lesson"},
            costs=[ArtifactCost(category="author", amount=0.01)],
        )


class Producer:
    def __init__(self, label, calls):
        self.label, self.calls = label, calls

    def produce(self, artifact, script, resolved, progress):
        self.calls.append(("producer", self.label, artifact.request.market.value,
                           artifact.request.audience.value))
        return ProductionResult(
            paths=ArtifactPaths(video="video/final.mp4"),
            costs=[ArtifactCost(category="production", amount=0.02)],
            production={"workspace": self.label, "text": "中文"},
        )


@pytest.mark.parametrize("market", ["youtube", "bilibili"])
@pytest.mark.parametrize("audience", ["adults", "children"])
def test_all_four_cells_share_creation_service_and_route_by_workspace(tmp_path, market, audience):
    calls = []
    from studio.composition import build_creation_service

    service = build_creation_service(
        tmp_path,
        youtube_author=Author("youtube", calls), bilibili_author=Author("bilibili", calls),
        youtube_producer=Producer("youtube", calls), bilibili_producer=Producer("bilibili", calls),
        profile_resolver=profile,
        clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    result = service.create(request(market, audience), artifact_id=f"{market}_{audience}")

    assert result.state.value == "ready_for_review"
    assert calls == [("author", market, market, audience),
                     ("producer", market, market, audience)]
    assert [event.next_state.value for event in result.events] == [
        "draft", "writing", "ready_for_production", "producing", "ready_for_review"
    ]
    assert [cost.amount for cost in result.costs] == [0.01, 0.02]
    assert result.production == {"workspace": market, "text": "中文"}
    assert result.publications == []
    assert ArtifactRepository(tmp_path).load(result.artifact_id) == result


def test_router_rejects_dimension_mismatch_before_collaborators():
    from studio.composition import WorkspaceScriptAuthor
    calls = []
    author = WorkspaceScriptAuthor(Author("youtube", calls), Author("bilibili", calls))
    req = request("youtube", "adults").model_copy(update={"native_language": "zh-Hans"})
    with pytest.raises(ValueError, match="unsupported workspace"):
        author.generate(req, {})
    assert calls == []


@pytest.mark.parametrize(("failure", "state"), [
    ("profile", "blocked_editorial"), ("author", "blocked_editorial"),
    ("producer", "blocked_production"),
])
def test_composed_service_preserves_failure_state(tmp_path, failure, state):
    from studio.composition import build_creation_service
    calls = []

    class BrokenAuthor(Author):
        def generate(self, req, resolved):
            if failure == "author":
                raise AuthorFailure(RuntimeError("author failed"))
            return super().generate(req, resolved)

    class BrokenProducer(Producer):
        def produce(self, *args):
            if failure == "producer":
                raise RuntimeError("producer failed")
            return super().produce(*args)

    def resolver(req):
        if failure == "profile":
            raise RuntimeError("profile failed")
        return profile(req)

    service = build_creation_service(
        tmp_path, youtube_author=BrokenAuthor("youtube", calls),
        bilibili_author=Author("bilibili", calls),
        youtube_producer=BrokenProducer("youtube", calls),
        bilibili_producer=Producer("bilibili", calls), profile_resolver=resolver,
        clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    result = service.create(request("youtube", "adults"), artifact_id=f"fail_{failure}")
    assert result.state.value == state
    assert "failed" in result.error

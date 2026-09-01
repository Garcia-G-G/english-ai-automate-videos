import builtins
import copy
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from studio.artifacts import (
    ArtifactAlreadyExists,
    ArtifactRepository,
    ArtifactWriteError,
    InvalidArtifactId,
)
from studio.creation import (
    CreationService,
    ProductionGateway,
    ProductionResult,
    ScriptAuthor,
)
from studio.lifecycle import InvalidTransition
from studio.models import (
    ArtifactCost,
    ArtifactLineage,
    ArtifactPaths,
    CreationRequest,
    VideoArtifact,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 31, 12, 34, 56, tzinfo=UTC)


def youtube_request(audience="adults"):
    return CreationRequest(
        market="youtube",
        native_language="es",
        learning_language="en",
        audience=audience,
        mode="auto",
        idea="actually",
    )


def bilibili_request(audience="children"):
    return CreationRequest(
        market="bilibili",
        native_language="zh-Hans",
        learning_language="en",
        audience=audience,
        mode="directed",
        idea="颜色练习",
        learning_objective="自然地说出三种颜色",
    )


def profile_for(request):
    workspace_id = (
        "youtube_es_en" if request.market.value == "youtube" else "bilibili_zh_hans_en"
    )
    return {
        "profile_schema_version": 1,
        "audience": {"name": request.audience.value, "lessons": ["complete"]},
        "workspace": {
            "workspace_id": workspace_id,
            "market": request.market.value,
            "native_language": request.native_language.value,
            "learning_language": request.learning_language.value,
        },
        "voice": {"voice_id": "ExampleVoice123456789", "traits": ["natural"]},
    }


class SequenceClock:
    def __init__(self, start=NOW):
        self.values = [start + timedelta(seconds=index) for index in range(20)]
        self.calls = 0

    def __call__(self):
        value = self.values[self.calls]
        self.calls += 1
        return value


class RecordingRepository(ArtifactRepository):
    def __init__(self, root, *, fail_create=None, fail_save_number=None, failure=None):
        super().__init__(root)
        self.snapshots = []
        self.operations = []
        self.save_calls = 0
        self.fail_create = fail_create
        self.fail_save_number = fail_save_number
        self.failure = failure or ArtifactWriteError("recording failure")

    def create(self, artifact):
        self.operations.append("create")
        if self.fail_create:
            raise self.failure
        super().create(artifact)
        self.snapshots.append(artifact.model_copy(deep=True))

    def save(self, artifact):
        self.save_calls += 1
        self.operations.append("save")
        if self.save_calls == self.fail_save_number:
            raise self.failure
        super().save(artifact)
        self.snapshots.append(artifact.model_copy(deep=True))


class RecordingAuthor:
    def __init__(self, *, result=None, error=None, mutate=False, log=None):
        self.result = result or {
            "type": "educational",
            "full_script": "A valid generated lesson",
            "examples": ["That is actually useful."],
        }
        self.error = error
        self.mutate = mutate
        self.log = log
        self.calls = []

    def generate(self, request, profile):
        if self.log is not None:
            self.log.append("author")
        self.calls.append((copy.deepcopy(request), copy.deepcopy(profile)))
        if self.mutate:
            request.idea = "mutated by author"
            profile["audience"]["lessons"].append("mutated by author")
        if self.error:
            raise self.error
        return self.result


class RecordingProducer:
    def __init__(self, *, result=None, error=None, mutate=False, log=None):
        self.result = result or ProductionResult(
            paths={"video": "video/final.mp4", "audio": "audio/narration.mp3"},
            costs=[{"category": "tts", "amount": 0.25, "details": {"segments": 3}}],
            production={
                "background": {"selection_reason": "适合颜色课程"},
                "stages": ["tts", "render"],
            },
        )
        self.error = error
        self.mutate = mutate
        self.log = log
        self.calls = []

    def produce(self, artifact, script, profile, progress):
        if self.log is not None:
            self.log.append("producer")
        self.calls.append(
            (
                artifact.model_copy(deep=True),
                copy.deepcopy(script),
                copy.deepcopy(profile),
                progress,
            )
        )
        if self.mutate:
            artifact.scripts[0]["examples"].append("mutated by producer")
            script["examples"].append("mutated by producer")
            profile["voice"]["traits"].append("mutated by producer")
        if self.error:
            raise self.error
        return self.result


def make_service(tmp_path, *, repository=None, author=None, producer=None, resolver=None, clock=None):
    repository = repository or RecordingRepository(tmp_path)
    author = author or RecordingAuthor()
    producer = producer or RecordingProducer()
    service = CreationService(
        repository=repository,
        author=author,
        producer=producer,
        profile_resolver=resolver or profile_for,
        clock=clock or SequenceClock(),
        token_factory=lambda: "1a2b3c4d",
    )
    return service, repository, author, producer


def test_public_protocols_and_successful_orchestration(tmp_path):
    order = []
    repository = RecordingRepository(tmp_path)
    author = RecordingAuthor(log=order)
    producer = RecordingProducer(log=order)

    def resolver(request):
        order.append("profile")
        return profile_for(request)

    service, _, _, _ = make_service(
        tmp_path,
        repository=repository,
        author=author,
        producer=producer,
        resolver=resolver,
    )

    result = service.create(youtube_request(), artifact_id="safe_explicit_id")

    assert isinstance(author, ScriptAuthor)
    assert isinstance(producer, ProductionGateway)
    assert order == ["profile", "author", "producer"]
    assert result.state.value == "ready_for_review"
    assert result == repository.load("safe_explicit_id")
    assert result.artifact_id == "safe_explicit_id"


def test_every_success_checkpoint_is_a_distinct_persisted_snapshot(tmp_path):
    clock = SequenceClock()
    service, repository, _, _ = make_service(tmp_path, clock=clock)

    result = service.create(youtube_request(), artifact_id="art_checkpoints")

    snapshots = repository.snapshots
    assert len(snapshots) == 9
    assert [snapshot.state.value for snapshot in snapshots] == [
        "draft",
        "writing",
        "writing",
        "writing",
        "writing",
        "ready_for_production",
        "producing",
        "producing",
        "ready_for_review",
    ]
    assert [
        (bool(s.resolved_profile), len(s.scripts), len(s.gates), bool(s.paths.video))
        for s in snapshots
    ] == [
        (False, 0, 0, False),
        (False, 0, 0, False),
        (True, 0, 0, False),
        (True, 1, 0, False),
        (True, 1, 1, False),
        (True, 1, 1, False),
        (True, 1, 1, False),
        (True, 1, 1, True),
        (True, 1, 1, True),
    ]
    assert len({id(snapshot) for snapshot in snapshots}) == 9
    assert [len(snapshot.events) for snapshot in snapshots] == [1, 2, 2, 2, 2, 3, 4, 4, 5]
    assert [event.reason for event in result.events] == [
        "artifact_created",
        "creation_started",
        "editorial_compatibility_ready",
        "production_started",
        "production_completed",
    ]
    timestamps = [event.timestamp for event in result.events]
    assert timestamps == sorted(timestamps)
    assert all(value.tzinfo == UTC for value in timestamps)


def test_generated_identity_uses_normalized_utc_time_and_exact_token(tmp_path):
    local_time = datetime(2026, 8, 31, 8, 34, 56, tzinfo=timezone(timedelta(hours=-4)))
    clock = SequenceClock(local_time)
    service, repository, _, _ = make_service(tmp_path, clock=clock)

    result = service.create(youtube_request())

    assert result.artifact_id == "art_20260831_123456_1a2b3c4d"
    assert result.created_at == NOW
    assert result.created_at.tzinfo == UTC
    assert repository.load(result.artifact_id) == result


@pytest.mark.parametrize("token", ["ABCDEF12", "abcdef1", "abcdef123", "abcd-123", "１２３４５６７８"])
def test_invalid_generated_token_fails_before_repository_creation(tmp_path, token):
    repository = RecordingRepository(tmp_path)
    service = CreationService(
        repository,
        RecordingAuthor(),
        RecordingProducer(),
        profile_resolver=profile_for,
        clock=SequenceClock(),
        token_factory=lambda: token,
    )

    with pytest.raises(ValueError, match="token_factory"):
        service.create(youtube_request())

    assert repository.operations == []
    assert not (tmp_path / "art_20260831_123456_1a2b3c4d").exists()


def test_naive_initial_clock_fails_before_repository_creation(tmp_path):
    repository = RecordingRepository(tmp_path)
    service, _, _, _ = make_service(
        tmp_path,
        repository=repository,
        clock=lambda: datetime(2026, 8, 31, 12, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        service.create(youtube_request(), artifact_id="art_naive")

    assert repository.operations == []


@pytest.mark.parametrize("artifact_id", ["", " unsafe ", "../escape"])
def test_unsafe_explicit_identity_propagates_without_normalization(tmp_path, artifact_id):
    service, repository, _, _ = make_service(tmp_path)

    with pytest.raises(InvalidArtifactId):
        service.create(youtube_request(), artifact_id=artifact_id)

    assert repository.operations == ["create"]


def test_identity_collision_propagates_without_retry_or_overwrite(tmp_path):
    service, repository, author, _ = make_service(tmp_path)
    first = service.create(youtube_request(), artifact_id="art_collision")
    before = (tmp_path / "art_collision" / "artifact.json").read_bytes()

    with pytest.raises(ArtifactAlreadyExists):
        service.create(youtube_request(), artifact_id="art_collision")

    assert repository.load("art_collision") == first
    assert (tmp_path / "art_collision" / "artifact.json").read_bytes() == before
    assert len(author.calls) == 1


def test_self_lineage_model_failure_propagates_before_repository_creation(tmp_path):
    lineage = ArtifactLineage(
        source_artifact_id="art_same",
        relation="adaptation",
        preserved_learning_objective="Preserve the lesson",
    )
    service, repository, _, _ = make_service(tmp_path)

    with pytest.raises(ValidationError, match="source_artifact_id"):
        service.create(youtube_request(), artifact_id="art_same", lineage=lineage)

    assert repository.operations == []


@pytest.mark.parametrize(
    ("creation_request", "artifact_id", "lineage"),
    [
        (youtube_request(), "art_youtube", None),
        (bilibili_request(), "art_bilibili", None),
        (
            bilibili_request(),
            "art_adapted",
            ArtifactLineage(
                source_artifact_id="art_youtube_source",
                relation="adaptation",
                preserved_learning_objective="Use colors naturally",
            ),
        ),
    ],
)
def test_direct_and_adapted_requests_preserve_request_profile_and_lineage(
    tmp_path, creation_request, artifact_id, lineage
):
    service, repository, _, _ = make_service(tmp_path)

    result = service.create(creation_request, artifact_id=artifact_id, lineage=lineage)

    assert result.request == creation_request
    assert result.resolved_profile == profile_for(creation_request)
    assert result.lineage == lineage
    assert repository.load(artifact_id) == result


def test_collaborators_receive_value_equal_isolated_inputs_and_exact_progress(tmp_path):
    creation_request = bilibili_request()
    original_request = creation_request.model_copy(deep=True)
    resolved_profile = profile_for(creation_request)
    original_profile = copy.deepcopy(resolved_profile)
    script = {"full_script": "颜色 lesson", "examples": ["red"]}
    original_script = copy.deepcopy(script)
    author = RecordingAuthor(result=script, mutate=True)
    producer = RecordingProducer(mutate=True)
    progress = lambda step, percent: None
    service, repository, _, _ = make_service(
        tmp_path,
        author=author,
        producer=producer,
        resolver=lambda request: resolved_profile,
    )

    result = service.create(creation_request, artifact_id="art_isolated", progress=progress)

    author_request, author_profile = author.calls[0]
    producer_artifact, producer_script, producer_profile, received_progress = producer.calls[0]
    assert author_request == original_request
    assert author_profile == original_profile
    assert producer_artifact.state.value == "producing"
    assert producer_artifact.scripts == [original_script]
    assert producer_script == original_script
    assert producer_profile == original_profile
    assert received_progress is progress
    assert creation_request == original_request
    assert resolved_profile == original_profile
    assert script == original_script
    assert result.scripts == [original_script]
    assert result.resolved_profile == original_profile
    assert repository.load("art_isolated") == result


def test_none_progress_passes_callable_noop_without_emitting_progress(tmp_path):
    producer = RecordingProducer()
    service, _, _, _ = make_service(tmp_path, producer=producer)

    service.create(youtube_request(), artifact_id="art_noop")

    callback = producer.calls[0][3]
    assert callable(callback)
    assert callback("ignored", 50) is None


def test_production_result_is_strict_coerces_nested_values_and_has_independent_defaults():
    result = ProductionResult(
        paths={"video": "video/final.mp4"},
        costs=[{"category": "render", "amount": "0.5"}],
        production={"stages": ["render"]},
    )
    empty_one = ProductionResult()
    empty_two = ProductionResult()

    assert result.paths == ArtifactPaths(video="video/final.mp4")
    assert result.costs == [ArtifactCost(category="render", amount=0.5)]
    assert isinstance(result.paths, ArtifactPaths)
    assert isinstance(result.costs[0], ArtifactCost)
    empty_one.paths.video = "changed.mp4"
    empty_one.costs.append(ArtifactCost(category="tts", amount=1))
    empty_one.production["changed"] = True
    assert empty_two == ProductionResult()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ProductionResult(unexpected=True)


def test_result_values_unicode_and_accumulated_costs_persist_independently(tmp_path):
    producer_result = ProductionResult(
        paths={"video": "视频/最终.mp4", "background": "背景/城市.jpg"},
        costs=[
            {"category": "tts", "amount": 0.4, "details": {"语言": "中文"}},
            {"category": "render", "amount": 0.2},
        ],
        production={"背景": {"原因": "适合颜色课程"}, "阶段": ["配音", "渲染"]},
    )
    producer = RecordingProducer(result=producer_result)
    service, repository, _, _ = make_service(tmp_path, producer=producer)

    result = service.create(bilibili_request(), artifact_id="art_unicode")
    producer_result.production["阶段"].append("mutated later")
    producer_result.costs[0].details["语言"] = "mutated later"

    loaded = repository.load("art_unicode")
    assert result.paths == ArtifactPaths(video="视频/最终.mp4", background="背景/城市.jpg")
    assert [cost.category for cost in result.costs] == ["tts", "render"]
    assert loaded.production == {"背景": {"原因": "适合颜色课程"}, "阶段": ["配音", "渲染"]}
    assert loaded.costs[0].details == {"语言": "中文"}


def test_compatibility_gate_is_exact_visible_once_and_never_passed(tmp_path):
    service, repository, _, _ = make_service(tmp_path)

    result = service.create(youtube_request(), artifact_id="art_gate")

    assert result.gates == [{"kind": "compatibility", "status": "not_run", "version": 1}]
    assert all(gate.get("status") != "passed" for gate in result.gates)
    assert repository.load("art_gate").gates == result.gates


EDITORIAL_FAILURES = [
    ("profile_exception", RuntimeError("profile unavailable"), "RuntimeError: profile unavailable"),
    ("profile_non_dict", ["not", "dict"], "TypeError: profile_resolver must return dict"),
    ("author_exception", RuntimeError("author unavailable"), "RuntimeError: author unavailable"),
    ("author_non_dict", ["not", "dict"], "TypeError: author.generate must return dict"),
]


@pytest.mark.parametrize(("case", "failure", "expected_error"), EDITORIAL_FAILURES)
def test_editorial_failures_return_exact_blocked_artifact(
    tmp_path, case, failure, expected_error
):
    author = RecordingAuthor()
    producer = RecordingProducer()
    resolver = profile_for
    if case == "profile_exception":
        resolver = lambda request: (_ for _ in ()).throw(failure)
    elif case == "profile_non_dict":
        resolver = lambda request: failure
    elif case == "author_exception":
        author = RecordingAuthor(error=failure)
    else:
        author = RecordingAuthor(result=failure)
    service, repository, _, _ = make_service(
        tmp_path,
        author=author,
        producer=producer,
        resolver=resolver,
    )

    result = service.create(youtube_request(), artifact_id=f"art_{case}")

    assert result.state.value == "blocked_editorial"
    assert result.error == expected_error
    assert result.events[-1].reason == f"editorial_failed: {expected_error}"
    assert result.gates == []
    assert producer.calls == []
    if case.startswith("profile"):
        assert author.calls == []
        assert len(repository.snapshots) == 3
        assert result.resolved_profile == {}
    else:
        assert len(author.calls) == 1
        assert len(repository.snapshots) == 4
        assert result.resolved_profile == profile_for(youtube_request())
    assert repository.load(f"art_{case}") == result


PRODUCTION_FAILURES = [
    ("exception", RuntimeError("renderer unavailable"), "RuntimeError: renderer unavailable"),
    ("non_result", {"paths": {}}, "TypeError: producer.produce must return ProductionResult"),
]


@pytest.mark.parametrize(("case", "failure", "expected_error"), PRODUCTION_FAILURES)
def test_production_failures_return_exact_blocked_artifact(
    tmp_path, case, failure, expected_error
):
    producer = (
        RecordingProducer(error=failure)
        if case == "exception"
        else RecordingProducer(result=failure)
    )
    service, repository, _, _ = make_service(tmp_path, producer=producer)

    result = service.create(youtube_request(), artifact_id=f"art_production_{case}")

    assert result.state.value == "blocked_production"
    assert result.error == expected_error
    assert result.events[-1].reason == f"production_failed: {expected_error}"
    assert result.resolved_profile == profile_for(youtube_request())
    assert len(result.scripts) == 1
    assert result.gates == [{"kind": "compatibility", "status": "not_run", "version": 1}]
    assert result.paths == ArtifactPaths()
    assert result.costs == []
    assert result.production == {}
    assert len(producer.calls) == 1
    assert len(repository.snapshots) == 8
    assert repository.load(f"art_production_{case}") == result


def test_callback_exception_follows_production_failure_path(tmp_path):
    class CallbackProducer(RecordingProducer):
        def produce(self, artifact, script, profile, progress):
            self.calls.append((artifact, script, profile, progress))
            progress("render", 50)
            return self.result

    callback_error = LookupError("progress consumer unavailable")

    def broken_progress(step, percent):
        raise callback_error

    producer = CallbackProducer()
    service, repository, _, _ = make_service(tmp_path, producer=producer)

    result = service.create(
        youtube_request(), artifact_id="art_callback", progress=broken_progress
    )

    assert result.state.value == "blocked_production"
    assert result.error == "LookupError: progress consumer unavailable"
    assert result.events[-1].reason == (
        "production_failed: LookupError: progress consumer unavailable"
    )
    assert repository.load("art_callback") == result


def test_repository_create_failure_propagates_same_instance(tmp_path):
    failure = ArtifactWriteError("create failed")
    repository = RecordingRepository(tmp_path, fail_create=True, failure=failure)
    service, _, author, producer = make_service(tmp_path, repository=repository)

    with pytest.raises(ArtifactWriteError) as caught:
        service.create(youtube_request(), artifact_id="art_create_failure")

    assert caught.value is failure
    assert author.calls == []
    assert producer.calls == []


@pytest.mark.parametrize("save_number", range(1, 9))
def test_every_repository_save_failure_propagates_and_preserves_last_bytes(
    tmp_path, save_number
):
    failure = ArtifactWriteError(f"save {save_number} failed")
    repository = RecordingRepository(
        tmp_path,
        fail_save_number=save_number,
        failure=failure,
    )
    service, _, _, _ = make_service(tmp_path, repository=repository)

    with pytest.raises(ArtifactWriteError) as caught:
        service.create(youtube_request(), artifact_id=f"art_save_{save_number}")

    assert caught.value is failure
    durable = repository.load(f"art_save_{save_number}")
    assert durable == repository.snapshots[-1]
    assert durable.state.value not in {"blocked_editorial", "blocked_production"}
    canonical = tmp_path / f"art_save_{save_number}" / "artifact.json"
    assert canonical.read_text(encoding="utf-8").endswith("\n")


def test_naive_later_clock_propagates_without_blocked_fallback(tmp_path):
    values = iter([NOW, NOW, datetime(2026, 8, 31, 12, 0)])
    repository = RecordingRepository(tmp_path)
    service, _, _, _ = make_service(
        tmp_path,
        repository=repository,
        clock=lambda: next(values),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        service.create(youtube_request(), artifact_id="art_later_naive")

    durable = repository.load("art_later_naive")
    assert durable.state.value == "writing"
    assert durable.resolved_profile == profile_for(youtube_request())


def test_lifecycle_failure_propagates_without_illegal_fallback(tmp_path, monkeypatch):
    import studio.creation as module

    failure = InvalidTransition("lifecycle failed")

    def broken_transition(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "transition", broken_transition)
    service, repository, _, _ = make_service(tmp_path)

    with pytest.raises(InvalidTransition) as caught:
        service.create(youtube_request(), artifact_id="art_lifecycle")

    assert caught.value is failure
    assert repository.load("art_lifecycle").state.value == "draft"


@pytest.mark.parametrize("stage", ["author", "producer"])
def test_mutating_failure_fakes_cannot_change_canonical_history(tmp_path, stage):
    author = RecordingAuthor(
        mutate=True,
        error=RuntimeError("author mutation failure") if stage == "author" else None,
    )
    producer = RecordingProducer(
        mutate=True,
        error=RuntimeError("producer mutation failure") if stage == "producer" else None,
    )
    service, repository, _, _ = make_service(
        tmp_path,
        author=author,
        producer=producer,
    )
    creation_request = youtube_request()
    before = creation_request.model_copy(deep=True)

    result = service.create(creation_request, artifact_id=f"art_mutating_{stage}")

    assert creation_request == before
    assert result.request == before
    assert "mutated by author" not in result.resolved_profile["audience"]["lessons"]
    if result.scripts:
        assert "mutated by producer" not in result.scripts[0]["examples"]
    assert repository.load(f"art_mutating_{stage}") == result


def test_importing_service_does_not_import_legacy_or_provider_modules(monkeypatch):
    import studio.creation as module

    forbidden = (
        "pipeline",
        "main",
        "admin",
        "uploader",
        "elevenlabs",
        "openai",
        "requests",
        "httpx",
    )
    real_import = builtins.__import__
    attempted = []

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in forbidden:
            attempted.append(name)
            raise AssertionError(f"forbidden service import: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    importlib.reload(module)

    assert attempted == []

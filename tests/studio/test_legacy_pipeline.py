import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from studio.creation import ProductionGateway, ScriptAuthor
from studio.models import CreationRequest, VideoArtifact


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def request(*, market="youtube", audience="adults", mode="auto", **values):
    base = {
        "market": market,
        "native_language": "es" if market == "youtube" else "zh-Hans",
        "learning_language": "en",
        "audience": audience,
        "mode": mode,
        "idea": "actually" if market == "youtube" else "颜色",
    }
    base.update(values)
    return CreationRequest(**base)


def bundle(audience="adults"):
    return {
        "profile_schema_version": 1,
        "audience": {
            "name": audience,
            "audience": audience,
            "content": {
                "categories": ["false_friends", "travel"],
                "default_type": "educational",
            },
            "video": {"background_mode": "random"},
        },
        "workspace": {
            "workspace_id": "youtube_es_en",
            "market": "youtube",
            "native_language": "es",
            "learning_language": "en",
        },
        "voice": {"voice_id": "SpanishVoice123456789", "locale": "es"},
    }


def artifact(artifact_id="art_01", **request_values):
    return VideoArtifact.new(request(**request_values), artifact_id, NOW)


def test_auto_author_delegates_selection_and_generation_once():
    calls = []
    topic = {"english": "actually", "gloss": "en realidad"}

    def select(*, allowed_categories):
        calls.append(("select", allowed_categories))
        return "false_friends", topic

    def generate(category, selected, video_type):
        calls.append(("generate", category, selected, video_type))
        return {"type": video_type, "full_script": "¡Úsalo así!", "examples": ["你好"]}

    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(random_topic=select, generator=generate)
    result = author.generate(request(), bundle())

    assert isinstance(author, ScriptAuthor)
    assert calls == [
        ("select", ["false_friends", "travel"]),
        ("generate", "false_friends", topic, "educational"),
    ]
    assert result["full_script"] == "¡Úsalo así!"
    assert result["examples"] == ["你好"]


def test_directed_author_delegates_exact_topic_and_type_once():
    calls = []
    selected = {"topic": "airport"}

    def find(category, topic):
        calls.append(("find", category, topic))
        return selected

    def generate(category, topic, video_type):
        calls.append(("generate", category, topic, video_type))
        return {"full_script": "¿Dónde está la puerta?"}

    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(topic_finder=find, generator=generate)
    result = author.generate(
        request(mode="directed", category="travel", topic="airport", video_type="quiz"),
        bundle(),
    )

    assert calls == [
        ("find", "travel", "airport"),
        ("generate", "travel", selected, "quiz"),
    ]
    assert result == {"full_script": "¿Dónde está la puerta?"}


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_youtube_author_uses_nested_audience_profile_without_kids_leakage(audience):
    seen = {}

    def select(*, allowed_categories):
        seen["categories"] = allowed_categories
        return "travel", {"topic": "hotel"}

    def generate(*args):
        seen["args"] = args
        return {"full_script": "lesson"}

    from studio.legacy_pipeline import TopicScriptAuthor

    profile = bundle(audience)
    original = copy.deepcopy(profile)
    TopicScriptAuthor(random_topic=select, generator=generate).generate(
        request(audience=audience), profile
    )

    assert seen["categories"] == ["false_friends", "travel"]
    assert "kids" not in repr(seen)
    assert profile == original


@pytest.mark.parametrize("audience", ["adults", "children"])
def test_bilibili_author_fails_before_selection_or_generation(audience):
    calls = []
    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(
        random_topic=lambda **kwargs: calls.append("select"),
        topic_finder=lambda *args: calls.append("find"),
        generator=lambda *args: calls.append("generate"),
    )

    with pytest.raises(ValueError, match="unsupported workspace.*bilibili.*zh-Hans"):
        author.generate(request(market="bilibili", audience=audience), bundle(audience))
    assert calls == []


class Tracker:
    def __init__(self):
        self.entries = [
            {"api_type": "old", "cost_usd": 9.0, "label": "earlier", "video_id": "old"}
        ]


def gateway_fakes(tmp_path, *, background="static_midnight"):
    calls = []
    tracker = Tracker()

    def get_tracker(video_id=None):
        calls.append(("tracker", video_id))
        return tracker

    def tts(script, audio_path, script_path=None, **kwargs):
        calls.append(("tts", copy.deepcopy(script), audio_path, script_path, kwargs))
        audio_path.write_bytes(b"audio")
        metadata = audio_path.with_suffix(".json")
        metadata.write_text(
            json.dumps({"duration": 2.5, "words": [{"word": "hola"}], "segments": []}),
            encoding="utf-8",
        )
        tracker.entries.append(
            {
                "api_type": "elevenlabs_tts",
                "model": "eleven_v3",
                "cost_usd": 0.125,
                "label": "tts",
                "video_id": "art_01",
                "characters": 42,
            }
        )
        return audio_path, metadata

    def merge(script, metadata):
        calls.append(("merge", copy.deepcopy(script), metadata))

    def resolve(profile, requested, **kwargs):
        calls.append(("background", copy.deepcopy(profile), requested, kwargs))
        return background

    def render(audio, metadata, video, **kwargs):
        calls.append(("render", audio, metadata, video, kwargs))
        video.write_bytes(b"video")
        return video

    from studio.legacy_pipeline import LegacyProductionGateway

    gateway = LegacyProductionGateway(tmp_path)
    gateway._get_tracker = get_tracker
    gateway._generate_tts = tts
    gateway._merge_script_into_tts = merge
    gateway._resolve_background = resolve
    gateway._render_video = render
    return gateway, calls, tracker


def test_gateway_delegates_stages_in_order_and_forwards_monotonic_progress(tmp_path):
    artifact_dir = tmp_path / "art_01"
    artifact_dir.mkdir()
    gateway, calls, _ = gateway_fakes(tmp_path)
    progress = []

    result = gateway.produce(
        artifact(), {"type": "educational", "full_script": "¡Hola!"}, bundle(),
        lambda step, percent: progress.append((step, percent)),
    )

    assert isinstance(gateway, ProductionGateway)
    assert [call[0] for call in calls] == [
        "tracker", "tts", "merge", "background", "render"
    ]
    background_call = next(call for call in calls if call[0] == "background")
    assert background_call[3] == {}
    assert [percent for _, percent in progress] == sorted(percent for _, percent in progress)
    assert progress[-1][1] == 100
    assert result.paths.model_dump() == {
        "script": "script/script.json",
        "audio": "audio/narration.mp3",
        "video": "video/final.mp4",
        "background": None,
    }


def test_gateway_paths_costs_and_available_metadata_are_exact(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)

    result = gateway.produce(
        artifact(), {"type": "quiz", "full_script": "你好, ¡hola!"}, bundle(),
        lambda *args: None,
    )

    assert json.loads((tmp_path / "art_01/script/script.json").read_text())[
        "full_script"
    ] == "你好, ¡hola!"
    assert [cost.model_dump() for cost in result.costs] == [{
        "category": "elevenlabs_tts",
        "amount": 0.125,
        "currency": "USD",
        "details": {
            "model": "eleven_v3", "label": "tts", "video_id": "art_01",
            "characters": 42,
        },
    }]
    assert result.production == {
        "background": "static_midnight",
        "video_type": "quiz",
        "tts_metadata": "audio/narration.json",
        "duration": 2.5,
        "segments": [],
    }


def test_gateway_inputs_and_collaborator_owned_values_are_not_mutated(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    item = artifact()
    script = {"type": "educational", "full_script": "lesson", "nested": ["safe"]}
    profile = bundle()
    originals = copy.deepcopy((item, script, profile))

    result = gateway.produce(item, script, profile, lambda *args: None)
    result.production["new"] = ["caller mutation"]

    assert item == originals[0]
    assert script == originals[1]
    assert profile == originals[2]


@pytest.mark.parametrize("artifact_id", ["../escape", "/absolute", "nested/id"])
def test_gateway_rejects_artifact_directory_escape(tmp_path, artifact_id):
    from studio.legacy_pipeline import LegacyProductionGateway

    unsafe = artifact(artifact_id=artifact_id)
    with pytest.raises(ValueError, match="artifact_id"):
        LegacyProductionGateway(tmp_path).produce(unsafe, {}, bundle(), lambda *args: None)


@pytest.mark.parametrize("stage", ["tts", "merge", "background", "render"])
def test_each_delegated_stage_exception_propagates_without_false_result(tmp_path, stage):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    error = RuntimeError(f"{stage} failed")
    setattr(gateway, {
        "tts": "_generate_tts", "merge": "_merge_script_into_tts",
        "background": "_resolve_background", "render": "_render_video",
    }[stage], lambda *args, **kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(RuntimeError) as raised:
        gateway.produce(artifact(), {"type": "educational"}, bundle(), lambda *args: None)
    assert raised.value is error


@pytest.mark.parametrize("bad_output", ["missing", "outside", "absolute"])
def test_gateway_rejects_missing_or_escaped_delegated_outputs(tmp_path, bad_output):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)

    def bad_tts(script, audio_path, script_path=None, **kwargs):
        if bad_output == "missing":
            return audio_path, audio_path.with_suffix(".json")
        outside = tmp_path / "outside.mp3"
        outside.write_bytes(b"audio")
        metadata = tmp_path / "outside.json"
        metadata.write_text("{}")
        return (outside.resolve() if bad_output == "absolute" else Path("../outside.mp3")), metadata

    gateway._generate_tts = bad_tts
    with pytest.raises((ValueError, FileNotFoundError), match="output|path|missing"):
        gateway.produce(artifact(), {}, bundle(), lambda *args: None)


def test_gateway_requires_existing_artifact_directory_and_never_touches_output(tmp_path):
    from studio.legacy_pipeline import LegacyProductionGateway

    before = sorted(tmp_path.iterdir())
    with pytest.raises(FileNotFoundError, match="artifact directory"):
        LegacyProductionGateway(tmp_path).produce(artifact(), {}, bundle(), lambda *args: None)
    assert sorted(tmp_path.iterdir()) == before


def test_source_boundary_delegates_without_provider_pricing_or_renderer_implementation():
    import inspect
    import studio.legacy_pipeline as module

    source = inspect.getsource(module)
    assert "subprocess" not in source
    assert "OpenAI(" not in source
    assert "per_1m" not in source
    assert "get_tts_provider" not in source
    assert "pipeline.generate_tts" in source
    assert "pipeline.render_video" in source

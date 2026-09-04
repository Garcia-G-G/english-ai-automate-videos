import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from studio.creation import (
    AuthorFailure,
    AuthorResult,
    ProductionGateway,
    ScriptAuthor,
)
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


class Tracker:
    def __init__(self):
        self.entries = [
            {"api_type": "old", "cost_usd": 9.0, "label": "earlier", "video_id": "old"}
        ]
        self.saves = 0

    def save(self):
        """The gateway persists the ledger in a finally, on both paths."""
        self.saves += 1


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

    author = TopicScriptAuthor(
        random_topic=select, generator=generate, tracker_getter=Tracker
    )
    result = author.generate(request(), bundle())

    assert isinstance(author, ScriptAuthor)
    assert calls == [
        ("select", ["false_friends", "travel"]),
        ("generate", "false_friends", topic, "educational"),
    ]
    assert result.script["full_script"] == "¡Úsalo así!"
    assert result.script["examples"] == ["你好"]


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

    author = TopicScriptAuthor(
        topic_finder=find, generator=generate, tracker_getter=Tracker
    )
    result = author.generate(
        request(mode="directed", category="travel", topic="airport", video_type="quiz"),
        bundle(),
    )

    assert calls == [
        ("find", "travel", "airport"),
        ("generate", "travel", selected, "quiz"),
    ]
    assert result == AuthorResult(script={"full_script": "¿Dónde está la puerta?"})


def test_author_cost_delta_excludes_prior_entries_and_preserves_new_entry():
    tracker = Tracker()

    def generate(*args):
        tracker.entries.append({
            "api_type": "openai_chat",
            "model": "gpt-4o-mini",
            "cost_usd": 0.004,
            "label": "script_educational",
            "video_id": "session",
            "prompt_tokens": 10,
        })
        return {"full_script": "costed"}

    from studio.legacy_pipeline import TopicScriptAuthor

    result = TopicScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "hotel"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    ).generate(request(), bundle())

    assert [cost.model_dump() for cost in result.costs] == [{
        "category": "openai_chat",
        "amount": 0.004,
        "currency": "USD",
        "details": {
            "model": "gpt-4o-mini", "label": "script_educational",
            "video_id": "session", "prompt_tokens": 10,
        },
    }]


def test_author_failure_carries_delta_and_original_cause():
    tracker = Tracker()
    cause = ValueError("invalid generated JSON")

    def generate(*args):
        tracker.entries.append({
            "api_type": "openai_chat", "cost_usd": 0.006,
            "label": "script", "video_id": "session",
        })
        raise cause

    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "hotel"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    )
    with pytest.raises(AuthorFailure) as raised:
        author.generate(request(), bundle())

    assert raised.value.cause is cause
    assert [cost.amount for cost in raised.value.costs] == [0.006]


def test_malformed_author_cost_fails_visibly():
    tracker = Tracker()

    def generate(*args):
        tracker.entries.append({"api_type": "openai_chat"})
        return {"full_script": "not safely attributable"}

    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "hotel"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    )
    with pytest.raises(ValueError, match="cost tracker returned invalid entry"):
        author.generate(request(), bundle())


def test_repeated_author_calls_do_not_leak_costs():
    tracker = Tracker()
    amounts = iter([0.01, 0.02])

    def generate(*args):
        tracker.entries.append({
            "api_type": "openai_chat", "cost_usd": next(amounts),
            "label": "script", "video_id": "session",
        })
        return {"full_script": "lesson"}

    from studio.legacy_pipeline import TopicScriptAuthor

    author = TopicScriptAuthor(
        random_topic=lambda **kwargs: ("travel", {"topic": "hotel"}),
        generator=generate,
        tracker_getter=lambda: tracker,
    )
    first = author.generate(request(idea="first"), bundle())
    second = author.generate(request(idea="second"), bundle())

    assert [cost.amount for cost in first.costs] == [0.01]
    assert [cost.amount for cost in second.costs] == [0.02]


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
    TopicScriptAuthor(
        random_topic=select, generator=generate, tracker_getter=Tracker
    ).generate(
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
        tracker_getter=lambda: calls.append("tracker"),
    )

    with pytest.raises(ValueError, match="unsupported workspace.*bilibili.*zh-Hans"):
        author.generate(request(market="bilibili", audience=audience), bundle(audience))
    assert calls == []


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
            json.dumps({
                "duration": 2.5,
                "words": [{"word": "hola", "start": 0.0, "end": 2.5}],
                "segments": [{"text": "hola", "start": 0.0, "end": 2.5}],
            }),
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
    gateway._media_probe = lambda path: (
        {"duration": 2.5, "audio_streams": 1, "video_streams": 0}
        if Path(path).suffix == ".mp3" else
        {"duration": 2.5, "audio_streams": 1, "video_streams": 1,
         "width": 1080, "height": 1920, "frames": 75}
    )
    gateway._frame_probe = lambda path: {"nonblank": True, "changing": True}
    gateway._finalize_video = lambda video, metadata, **kwargs: {
        "video": str(video), "gate": "PASS", "outro_appended": True,
        "outro_variant": "learning_routes_a", "seam": {"delta": 0.01},
    }
    return gateway, calls, tracker


def test_youtube_zero_duration_audio_fails_before_background_and_render(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, calls, _ = gateway_fakes(tmp_path)
    gateway._media_probe = lambda path: {"duration": 0.0}
    with pytest.raises(ValueError, match="audio duration"):
        gateway.produce(artifact(), {"type": "educational", "full_script": "hola"},
                        bundle(), lambda *args: None)
    assert [call[0] for call in calls] == ["tracker", "tts", "merge"]


def test_youtube_valid_result_persists_shared_media_facts(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    result = gateway.produce(artifact(), {"type": "educational", "full_script": "hola"},
                             bundle(), lambda *args: None)
    assert result.production["media_validation"] == {
        "duration": 2.5, "audio_streams": 1, "video_streams": 1,
        "width": 1080, "height": 1920, "frames": 75,
        "nonblank": True, "changing": True,
    }


@pytest.mark.parametrize(
    ("verdict", "extra", "expected_gate"),
    [
        ("PASS", {"outro_variant": "学习路线", "seam": {"delta": 0.01}},
         {"kind": "final_qa", "version": 1, "status": "PASS",
          "blocking_flags": []}),
        ("REJECT", {"blocking_flags": ["dead_air:5.0s"]},
         {"kind": "final_qa", "version": 1, "status": "REJECT",
          "blocking_flags": ["dead_air:5.0s"]}),
        ("NO_REPORT", {"reason": "no paired audio artifact to gate"},
         {"kind": "final_qa", "version": 1, "status": "NO_REPORT",
          "blocking_flags": [], "reason": "no paired audio artifact to gate"}),
    ],
)
def test_youtube_finalizes_then_validates_definitive_video(
    tmp_path, verdict, extra, expected_gate
):
    (tmp_path / "art_01").mkdir()
    gateway, calls, _ = gateway_fakes(tmp_path)
    order = []

    def finalize(video, metadata, *, variant_seed):
        order.append(("finalize", Path(video).read_bytes(), variant_seed, metadata))
        if verdict == "PASS":
            Path(video).write_bytes(b"definitive")
        return {
            "video": str(video), "gate": verdict,
            "outro_appended": verdict == "PASS", **copy.deepcopy(extra),
        }

    gateway._finalize_video = finalize
    original_probe = gateway._media_probe

    def probe(path):
        if Path(path).suffix == ".mp4":
            order.append(("probe", Path(path).read_bytes()))
            value = original_probe(path)
            if verdict == "PASS":
                value["duration"] = 4.0
            return value
        return original_probe(path)

    gateway._media_probe = probe
    result = gateway.produce(
        artifact(), {"type": "educational", "full_script": "hola"},
        bundle(), lambda *args: None,
    )

    assert order[0][:3] == ("finalize", b"video", "art_01")
    assert order[1] == (
        "probe", b"definitive" if verdict == "PASS" else b"video"
    )
    # TWO gates now: the QA verdict and the duration verdict. Duration is
    # recorded on every artifact, pass or fail — a silent pass is what let
    # 20% of videos land in the 50-80s band unnoticed.
    assert result.gates[0] == expected_gate
    assert [g["kind"] for g in result.gates] == ["final_qa", "duration"]
    assert result.production["finalization"]["gate"] == verdict
    assert result.production["finalization"]["outro_appended"] is (verdict == "PASS")
    assert result.paths.video == "video/final.mp4"
    assert not list((tmp_path / "art_01/video").glob("*_with_outro*"))


def test_youtube_outro_must_not_make_definitive_video_shorter_than_narration(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    original_probe = gateway._media_probe
    gateway._media_probe = lambda path: (
        {**original_probe(path), "duration": 1.0}
        if Path(path).suffix == ".mp4" else original_probe(path)
    )
    with pytest.raises(ValueError, match="shorter than narration"):
        gateway.produce(artifact(), {"type": "educational"}, bundle(),
                        lambda *args: None)


@pytest.mark.parametrize(
    "finalized",
    [None, [], {"video": "video/final.mp4", "gate": "MAYBE",
                "outro_appended": False},
     {"video": "../outside.mp4", "gate": "REJECT", "outro_appended": False},
     {"video": "video/missing.mp4", "gate": "REJECT", "outro_appended": False}],
)
def test_youtube_rejects_malformed_or_unsafe_finalizer_results(tmp_path, finalized):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    gateway._finalize_video = lambda *args, **kwargs: finalized
    with pytest.raises((TypeError, ValueError, FileNotFoundError),
                       match="final|gate|video"):
        gateway.produce(artifact(), {"type": "educational"}, bundle(),
                        lambda *args: None)


def test_youtube_invalid_definitive_media_and_finalizer_exception_propagate(tmp_path):
    (tmp_path / "art_01").mkdir()
    gateway, _, _ = gateway_fakes(tmp_path)
    gateway._finalize_video = lambda video, *args, **kwargs: {
        "video": str(video), "gate": "PASS", "outro_appended": True,
    }
    original_probe = gateway._media_probe
    gateway._media_probe = lambda path: (
        {"duration": 0.0} if Path(path).suffix == ".mp4" else original_probe(path)
    )
    with pytest.raises(ValueError, match="video duration"):
        gateway.produce(artifact(), {"type": "educational"}, bundle(),
                        lambda *args: None)

    error = RuntimeError("finalizer exploded")
    gateway, _, _ = gateway_fakes(tmp_path)
    gateway._finalize_video = lambda *args, **kwargs: (_ for _ in ()).throw(error)
    with pytest.raises(RuntimeError) as caught:
        gateway.produce(artifact(), {"type": "educational"}, bundle(),
                        lambda *args: None)
    assert caught.value is error


def test_youtube_forwards_requested_engine_and_records_effective_fallback(tmp_path):
    (tmp_path / "art_01").mkdir()
    item = artifact().model_copy(deep=True)
    item.request = item.request.model_copy(
        update={"render_engine": type(item.request.render_engine)("v2")}
    )
    gateway, calls, _ = gateway_fakes(tmp_path)
    result = gateway.produce(item, {"type": "quiz", "full_script": "hola"},
                             bundle(), lambda *args: None)
    render = next(call for call in calls if call[0] == "render")
    assert render[-1]["use_v2"] is True
    assert result.production["render_engine"] == {
        "requested": "v2", "effective": "v1"
    }


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
    # THE STUDIO PATH NOW PASSES ITS TOPIC. This assertion used to be
    # `== {}`, pinning the omission recorded at legacy_pipeline.py:244 — the
    # topic tier had nowhere to write, so the Studio path was given no topic
    # and could only ever get a palette. The clip tier takes a destination
    # inside the artifact, so the objection is gone and so is the omission.
    assert background_call[3] == {
        "topic": "actually",
        "category": None,
        "dest_dir": artifact_dir / "clips",
        "duration": 2.5,
    }
    assert background_call[3]["dest_dir"].parent == artifact_dir, (
        "footage belongs to THIS artifact, not a global directory")
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
        "segments": [{"text": "hola", "start": 0.0, "end": 2.5}],
        "media_validation": {
            "duration": 2.5, "audio_streams": 1, "video_streams": 1,
            "width": 1080, "height": 1920, "frames": 75,
            "nonblank": True, "changing": True,
        },
        "render_engine": {"requested": "v1", "effective": "v1"},
        "finalization": {
            "gate": "PASS", "outro_appended": True,
            "outro_variant": "learning_routes_a", "seam": {"delta": 0.01},
        },
    }
    assert result.gates[0] == {
        "kind": "final_qa", "version": 1, "status": "PASS",
        "blocking_flags": [],
    }
    duration = result.gates[1]
    assert duration["kind"] == "duration"
    # The fake narration is 2.5s, so this MUST be recorded as out of band
    # rather than passing quietly. That is the whole point of the record.
    assert duration["status"] == "OUT_OF_BAND"
    assert duration["band"] == [50.0, 80.0]
    assert "under the 50s floor" in duration["reason"]


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

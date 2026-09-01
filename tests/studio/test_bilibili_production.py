import copy
import json
from datetime import datetime, timezone

import pytest

from studio.creation import ProductionGateway
from studio.models import CreationRequest, VideoArtifact


def _request(audience="adults"):
    return CreationRequest(
        market="bilibili", native_language="zh-Hans", learning_language="en",
        audience=audience, mode="auto", idea="机场英语", video_type="educational",
    )


def _artifact(audience="adults"):
    return VideoArtifact.new(
        _request(audience), "art_bili", datetime(2026, 9, 1, tzinfo=timezone.utc)
    )


def _profile(audience="adults"):
    return {
        "profile_schema_version": 1,
        "workspace": {
            "profile_schema_version": 1, "workspace_id": "bilibili_zh_hans_en",
            "market": "bilibili", "native_language": "zh-Hans",
            "learning_language": "en",
            "audio": {"narration_lang": "zh", "learning_lang": "en",
                      "english_accent": "en-US", "segment_model": "eleven_turbo_v2_5"},
            "subtitles": {"primary_language": "zh-Hans", "learning_language": "en"},
        },
        "audience": {"profile_schema_version": 1, "audience": audience, "name": audience,
                     "video": {"background_mode": "random"}},
        "voice": {"profile_schema_version": 1, "workspace_id": "bilibili_zh_hans_en",
                  "audience": audience, "locale": "zh-Hans", "provider": "elevenlabs",
                  "voice_id": "ChineseVoice123456789"},
    }


class Tracker:
    def __init__(self):
        self.entries = [{"api_type": "old", "cost_usd": 9.0}]


def _gateway(tmp_path, *, duration=1.25, frames=None):
    calls = []
    tracker = Tracker()

    def synthesize(script, audio_path, metadata_path, *, voice, workspace):
        calls.append(("tts", copy.deepcopy(script), voice, copy.deepcopy(workspace)))
        audio_path.write_bytes(b"audio")
        metadata = {
            "duration": duration,
            "words": [{"word": "你好", "start": 0.0, "end": 0.4, "is_english": False},
                      {"word": "hello", "start": 0.5, "end": 1.0, "is_english": True}],
            "segments": [{"start": 0.0, "end": 1.0, "text": "你好 hello"}],
            "tts_calls": [{"index": 0, "lang": "zh", "text": "你好"},
                          {"index": 1, "lang": "en", "text": "hello"}],
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        tracker.entries.append({"api_type": "elevenlabs_tts", "cost_usd": 0.04,
                                "label": "native_bilibili", "video_id": "art_bili"})
        return audio_path, metadata_path

    def render(audio, metadata, video, **kwargs):
        calls.append(("render", kwargs))
        video.write_bytes(b"video")
        return video

    def probe(path):
        if path.suffix == ".mp3":
            return {"duration": duration, "audio_streams": 1, "video_streams": 0}
        return {"duration": duration, "audio_streams": 1, "video_streams": 1,
                "width": 1080, "height": 1920, "frames": 30}

    from studio.bilibili_production import BilibiliProductionGateway
    gateway = BilibiliProductionGateway(
        tmp_path,
        synthesizer=synthesize,
        renderer=render,
        background_resolver=lambda profile, requested: "static_midnight",
        tracker_getter=lambda video_id=None: tracker,
        media_probe=probe,
        frame_probe=lambda path: frames or {"nonblank": True, "changing": True},
        font_resolver=lambda: "/System/Library/Fonts/STHeiti Medium.ttc",
    )
    return gateway, calls


def test_zero_duration_is_rejected_at_audio_boundary_before_render(tmp_path):
    (tmp_path / "art_bili").mkdir()
    gateway, calls = _gateway(tmp_path, duration=0.0)

    with pytest.raises(ValueError, match="audio duration must be positive"):
        gateway.produce(_artifact(), {"type": "educational", "full_script": "你好 hello"},
                        _profile(), lambda *args: None)

    assert [call[0] for call in calls] == ["tts"]


@pytest.mark.parametrize(
    ("probe_update", "message"),
    [
        ({"frames": 0}, "frame count"),
        ({"audio_streams": 0}, "audio stream"),
        ({"width": 1920, "height": 1080}, "portrait"),
    ],
)
def test_invalid_render_probe_cannot_return_success(tmp_path, probe_update, message):
    (tmp_path / "art_bili").mkdir()
    gateway, _ = _gateway(tmp_path)
    original = gateway._media_probe

    def probe(path):
        value = original(path)
        if path.suffix == ".mp4":
            value.update(probe_update)
        return value

    gateway._media_probe = probe
    with pytest.raises(ValueError, match=message):
        gateway.produce(_artifact(), {"type": "educational", "full_script": "你好 hello"},
                        _profile(), lambda *args: None)


@pytest.mark.parametrize("frames", [{"nonblank": False, "changing": True},
                                    {"nonblank": True, "changing": False}])
def test_blank_or_static_only_frames_are_rejected(tmp_path, frames):
    (tmp_path / "art_bili").mkdir()
    gateway, _ = _gateway(tmp_path, frames=frames)
    with pytest.raises(ValueError, match="frame"):
        gateway.produce(_artifact(), {"type": "educational", "full_script": "你好 hello"},
                        _profile(), lambda *args: None)


def test_native_gateway_uses_exact_voice_and_returns_contained_truthful_result(tmp_path):
    (tmp_path / "art_bili").mkdir()
    gateway, calls = _gateway(tmp_path)
    artifact, script, profile = _artifact(), {"type": "educational", "full_script": "你好 hello"}, _profile()
    originals = copy.deepcopy((artifact, script, profile))
    progress = []

    result = gateway.produce(artifact, script, profile,
                             lambda step, percent: progress.append((step, percent)))

    assert isinstance(gateway, ProductionGateway)
    assert calls[0][2] == "ChineseVoice123456789"
    assert calls[0][3]["audio"]["narration_lang"] == "zh"
    assert result.paths.model_dump() == {
        "script": "script/script.json", "audio": "audio/narration.mp3",
        "video": "video/final.mp4", "background": "background/selection.json",
    }
    assert [cost.amount for cost in result.costs] == [0.04]
    assert result.production["duration"] == 1.25
    assert result.production["voice_id"] == "ChineseVoice123456789"
    assert result.production["subtitle_languages"] == ["zh-Hans", "en"]
    assert result.production["media_validation"]["frames"] == 30
    render_call = next(call for call in calls if call[0] == "render")
    assert render_call[1]["native_language"] == "zh-Hans"
    assert [p for _, p in progress] == sorted(p for _, p in progress)
    assert (artifact, script, profile) == originals


def test_bilibili_forwards_v2_and_records_effective_engine(tmp_path):
    (tmp_path / "art_bili").mkdir()
    item = _artifact().model_copy(deep=True)
    item.request = item.request.model_copy(
        update={"render_engine": type(item.request.render_engine)("v2")}
    )
    gateway, calls = _gateway(tmp_path)
    result = gateway.produce(item, {"type": "educational", "full_script": "你好 hello"},
                             _profile(), lambda *args: None)
    render = next(call for call in calls if call[0] == "render")
    assert render[1]["use_v2"] is True
    assert result.production["render_engine"] == {
        "requested": "v2", "effective": "v2"
    }


def test_profile_mismatch_and_escaped_background_fail_before_tts(tmp_path):
    (tmp_path / "art_bili").mkdir()
    gateway, calls = _gateway(tmp_path)
    bad = _profile()
    bad["voice"]["locale"] = "es"
    with pytest.raises(ValueError, match="voice.locale"):
        gateway.produce(_artifact(), {}, bad, lambda *args: None)
    assert calls == []

    gateway._background_resolver = lambda *args: "photo:../../outside.png"
    with pytest.raises(ValueError, match="background"):
        gateway.produce(_artifact(), {"type": "educational", "full_script": "你好"},
                        _profile(), lambda *args: None)

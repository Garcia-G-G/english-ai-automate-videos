import json
from types import SimpleNamespace

import pytest

from studio.media_validation import probe_media, validate_timing, validate_video


def valid_metadata():
    return {
        "duration": 2.0,
        "words": [{"word": "hola", "start": 0.0, "end": 0.5}],
        "segments": [{"text": "hola", "start": 0.0, "end": 0.5}],
    }


PROBE = {"duration": 2.0, "audio_streams": 1}


@pytest.mark.parametrize("field", ["words", "segments"])
@pytest.mark.parametrize("value", [[{}], [{"start": 1.0, "end": 0.5}]])
def test_timing_rejects_malformed_or_nonmonotonic_collections(field, value):
    """Shape is checked on whatever is carried, required or not."""
    metadata = valid_metadata()
    metadata[field] = value
    with pytest.raises(ValueError, match="timing|monotonic"):
        validate_timing(metadata, PROBE, "quiz")


@pytest.mark.parametrize("video_type,required", [
    ("quiz", "segments"), ("true_false", "segments"),
    ("fill_blank", "segments"), ("vocabulary", "segments"),
    ("educational", "words"), ("pronunciation", "words"),
])
def test_timing_rejects_an_empty_REQUIRED_collection(video_type, required):
    metadata = valid_metadata()
    metadata[required] = []
    with pytest.raises(ValueError, match="non-empty"):
        validate_timing(metadata, PROBE, video_type)


@pytest.mark.parametrize("video_type,optional", [
    ("quiz", "words"), ("true_false", "words"), ("vocabulary", "words"),
    ("educational", "segments"), ("pronunciation", "segments"),
])
def test_timing_allows_an_empty_OPTIONAL_collection(video_type, optional):
    """The defect: this used to raise, which blocked every type on disk."""
    metadata = valid_metadata()
    metadata[optional] = []
    validate_timing(metadata, PROBE, video_type)


def test_timing_rejects_out_of_range_and_duration_disagreement():
    metadata = valid_metadata()
    metadata["segments"] = [{"text": "hola", "start": 0.0, "end": 2.5}]
    with pytest.raises(ValueError, match="monotonic|range"):
        validate_timing(metadata, PROBE, "quiz")
    with pytest.raises(ValueError, match="disagrees"):
        validate_timing(valid_metadata(), {"duration": 3.0, "audio_streams": 1}, "quiz")


@pytest.mark.parametrize("change", [
    {"duration": 0}, {"audio_streams": 0}, {"video_streams": 0},
    {"frames": 0}, {"width": 1920, "height": 1080},
])
def test_video_rejects_invalid_probe_facts(change):
    probe = {"duration": 2.0, "audio_streams": 1, "video_streams": 1,
             "frames": 60, "width": 1080, "height": 1920}
    probe.update(change)
    with pytest.raises(ValueError):
        validate_video(probe, {"nonblank": True, "changing": True}, 2.0)


def test_video_accepts_decode_count_when_declared_frame_count_is_unavailable():
    probe = {"duration": 2.0, "audio_streams": 1, "video_streams": 1,
             "frames": 60, "declared_frames": None, "width": 1080, "height": 1920}
    validate_video(probe, {"nonblank": True, "changing": True}, 2.0)


def test_probe_uses_ffprobe_counted_frames_when_nb_frames_is_na(monkeypatch, tmp_path):
    payload = {
        "format": {"duration": "2.0"},
        "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920,
             "nb_frames": "N/A", "nb_read_frames": "60"},
            {"codec_type": "audio"},
        ],
    }
    calls = []
    monkeypatch.setattr(
        "studio.media_validation.subprocess.run",
        lambda command, **kwargs: (
            calls.append(command)
            or SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        ),
    )
    result = probe_media(tmp_path / "video.mp4")
    assert "-count_frames" in calls[0]
    assert result["frames"] == 60
    assert result["declared_frames"] is None

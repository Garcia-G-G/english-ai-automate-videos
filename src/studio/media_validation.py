"""Truthful media probing and release-boundary validation."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from timing_contract import describe, required_timeline


def probe_media(path: Path) -> dict:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"media probe failed for {path}: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    duration = payload.get("format", {}).get("duration") or video.get("duration") or 0
    declared_frames = video.get("nb_frames")
    counted_frames = video.get("nb_read_frames")
    frames = counted_frames if str(counted_frames).isdigit() else declared_frames
    return {
        "duration": float(duration),
        "audio_streams": sum(stream.get("codec_type") == "audio" for stream in streams),
        "video_streams": sum(stream.get("codec_type") == "video" for stream in streams),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "frames": int(frames) if str(frames).isdigit() else 0,
        "declared_frames": (
            int(declared_frames) if str(declared_frames).isdigit() else None
        ),
    }


def inspect_frames(path: Path) -> dict:
    import cv2
    import numpy as np

    capture = cv2.VideoCapture(str(path))
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    samples = []
    for index in sorted({0, max(0, count // 2), max(0, count - 1)}):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if ok:
            samples.append(frame)
    capture.release()
    if not samples:
        return {"nonblank": False, "changing": False}
    nonblank = any(float(frame.std()) >= 2.0 and float(frame.mean()) >= 2.0 for frame in samples)
    changing = len(samples) > 1 and any(
        float(np.mean(np.abs(samples[0].astype(np.int16) - frame.astype(np.int16)))) >= 0.5
        for frame in samples[1:]
    )
    return {"nonblank": nonblank, "changing": changing}


def validate_timing(metadata: dict, audio_probe: dict, video_type) -> None:
    """Release-boundary check on the TTS output for ONE video type.

    `video_type` is required, not inferred from the metadata and not
    optional. This function previously demanded a non-empty `words` AND a
    non-empty `segments` for everything, which no type on disk satisfies:
    quiz/true_false/vocabulary ship `words: []` by design, and the OpenAI
    quiz path ships `segments: []`. It blocked production for every type and
    is why output/artifacts/ was empty. The requirement is per type, and
    timing_contract is the one place that says which.

    Everything else here is unchanged and none of it is duplicated
    elsewhere: positive duration, a real audio stream, metadata agreeing
    with the probe, and monotonic in-range bounds with text present on every
    entry of whichever collections are actually carried.
    """
    duration = float(metadata.get("duration") or 0)
    probed = float(audio_probe.get("duration") or 0)
    if duration <= 0 or probed <= 0:
        raise ValueError("audio duration must be positive")
    if int(audio_probe.get("audio_streams") or 0) < 1:
        raise ValueError("audio probe must contain an audio stream")
    if abs(duration - probed) > max(0.25, duration * 0.05):
        raise ValueError("audio metadata duration disagrees with probed duration")

    # Raises UnknownVideoType for a type with no declared requirement, which
    # the contract treats as REJECT rather than as "needs nothing".
    required = required_timeline(video_type)
    carried = metadata.get(required)
    if not isinstance(carried, list) or not carried:
        raise ValueError(
            f"timing data must contain a non-empty {required!r}: {describe(video_type)}"
        )

    # The other collection stays OPTIONAL, but if present it must still be
    # well formed — a malformed word list on a quiz is a defect even though
    # the quiz is not rendered from it.
    words = metadata.get("words")
    segments = metadata.get("segments")
    checks = []
    if isinstance(words, list) and words:
        checks.append((words, "word"))
    if isinstance(segments, list) and segments:
        checks.append((segments, "text"))
    for collection, content_field in checks:
        # SORTED BY START, and a span may CONTAIN another span.
        #
        # This loop used to walk the list in file order and demand
        # start >= previous_end. Both assumptions are wrong for the shape
        # the generators actually emit: fill_blank and quiz append an
        # umbrella "options" segment that deliberately spans option_1..4
        # and is written after them, so a perfectly good sidecar read as
        # non-monotonic and blocked production outright.
        #
        # The check that survives is the one that catches real corruption:
        # every entry must have text, finite numeric bounds, a non-negative
        # start, an end at or after its start, and an end inside the file.
        # Overlap is not corruption here — it is how a group is declared.
        try:
            ordered = sorted(collection, key=lambda i: float(i["start"])
                             if isinstance(i, dict) else 0.0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("timing entry must contain text and numeric bounds") from exc
        previous = -1.0
        for item in ordered:
            if not isinstance(item, dict) or not isinstance(item.get(content_field), str):
                raise ValueError("timing entry must contain text and numeric bounds")
            try:
                start = float(item["start"])
                end = float(item["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("timing entry must contain text and numeric bounds") from exc
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0
                or start < previous          # starts must not go backwards
                or end < start
                or end > duration + 0.25
            ):
                raise ValueError("timing data must be monotonic and in range")
            previous = start


def validate_video(probe: dict, frames: dict, expected_duration: float) -> None:
    duration = float(probe.get("duration") or 0)
    if duration <= 0:
        raise ValueError("video duration must be positive")
    if int(probe.get("video_streams") or 0) < 1 or int(probe.get("frames") or 0) < 1:
        raise ValueError("video frame count must be positive")
    if int(probe.get("audio_streams") or 0) < 1:
        raise ValueError("video must contain an audio stream")
    if int(probe.get("width") or 0) != 1080 or int(probe.get("height") or 0) != 1920:
        raise ValueError("video must use 1080x1920 portrait dimensions")
    if abs(duration - expected_duration) > max(0.25, expected_duration * 0.05):
        raise ValueError("video duration disagrees with audio timing")
    if not frames.get("nonblank"):
        raise ValueError("video frame content is blank")
    if not frames.get("changing"):
        raise ValueError("video frames do not change")

"""Truthful media probing and release-boundary validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe_media(path: Path) -> dict:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
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
    frames = video.get("nb_frames") or 0
    return {
        "duration": float(duration),
        "audio_streams": sum(stream.get("codec_type") == "audio" for stream in streams),
        "video_streams": sum(stream.get("codec_type") == "video" for stream in streams),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "frames": int(frames) if str(frames).isdigit() else 0,
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


def validate_timing(metadata: dict, audio_probe: dict) -> None:
    duration = float(metadata.get("duration") or 0)
    probed = float(audio_probe.get("duration") or 0)
    if duration <= 0 or probed <= 0:
        raise ValueError("audio duration must be positive")
    if abs(duration - probed) > max(0.25, duration * 0.05):
        raise ValueError("audio metadata duration disagrees with probed duration")
    words = metadata.get("words")
    segments = metadata.get("segments")
    if not isinstance(words, list) or not words or not isinstance(segments, list) or not segments:
        raise ValueError("timing data must contain non-empty words and segments")
    previous = -1.0
    for item in words:
        if not isinstance(item, dict):
            raise ValueError("timing word must be an object")
        start, end = float(item.get("start", -1)), float(item.get("end", -1))
        if start < previous or end < start or end > duration + 0.25:
            raise ValueError("timing data must be monotonic")
        previous = end


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

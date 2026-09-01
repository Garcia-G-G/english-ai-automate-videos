"""Compatibility adapters over the existing Spanish/YouTube pipeline."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Callable

from .creation import AuthorResult, ProductionResult
from .editorial_costs import cost_delta, invoke_with_costs
from .media_validation import inspect_frames, probe_media, validate_timing, validate_video
from .models import ArtifactPaths, CreationMode, Market


def _random_topic(*, allowed_categories):
    from script_generator import get_random_topic

    return get_random_topic(allowed_categories=allowed_categories)


def _find_topic(category, topic):
    from script_generator import find_topic

    return find_topic(category, topic)


def _generate_script(category, topic, video_type):
    from script_generator import generate_script

    return generate_script(category, topic, video_type)


def _get_tracker(video_id=None):
    from cost_tracker import get_tracker

    return get_tracker(video_id=video_id)


def _current_tracker():
    from cost_tracker import get_tracker

    return get_tracker()


def _generate_tts(*args, **kwargs):
    import pipeline

    return pipeline.generate_tts(*args, **kwargs)


def _merge_script_into_tts(*args, **kwargs):
    import pipeline

    return pipeline.merge_script_into_tts(*args, **kwargs)


def _resolve_background(*args, **kwargs):
    import pipeline

    return pipeline.resolve_background(*args, **kwargs)


def _render_video(*args, **kwargs):
    import pipeline

    return pipeline.render_video(*args, **kwargs)


class TopicScriptAuthor:
    """Adapt typed requests to the current Spanish lesson generator."""

    def __init__(
        self,
        *,
        random_topic: Callable = _random_topic,
        topic_finder: Callable = _find_topic,
        generator: Callable = _generate_script,
        tracker_getter: Callable = _current_tracker,
    ):
        self._random_topic = random_topic
        self._topic_finder = topic_finder
        self._generator = generator
        self._tracker_getter = tracker_getter

    def generate(self, request, profile: dict) -> AuthorResult:
        if request.market is not Market.YOUTUBE:
            raise ValueError(
                "unsupported workspace: the legacy author supports only "
                "youtube + es + en, not "
                f"{request.market.value} + {request.native_language.value} + "
                f"{request.learning_language.value}"
            )

        audience = copy.deepcopy(profile["audience"])
        video_type = (
            request.video_type
            or audience.get("content", {}).get("default_type")
            or "educational"
        )

        if request.mode is CreationMode.DIRECTED:
            if not request.category:
                raise ValueError("directed creation requires category")
            topic_name = request.topic or request.idea
            selected = self._topic_finder(request.category, topic_name)
            category = request.category
        else:
            allowed = audience.get("content", {}).get("categories")
            category, selected = self._random_topic(
                allowed_categories=copy.deepcopy(allowed)
            )

        tracker = self._tracker_getter()
        script, costs = invoke_with_costs(
            tracker,
            lambda: self._generator(
                category, copy.deepcopy(selected), video_type
            ),
        )
        return AuthorResult(script=script, costs=costs)


class LegacyProductionGateway:
    """Place canonical media paths around the existing production stages."""

    def __init__(
        self,
        root: Path,
        *,
        media_probe=probe_media,
        frame_probe=inspect_frames,
    ):
        self.root = Path(root)
        self._get_tracker = _get_tracker
        self._generate_tts = _generate_tts
        self._merge_script_into_tts = _merge_script_into_tts
        self._resolve_background = _resolve_background
        self._render_video = _render_video
        self._media_probe = media_probe
        self._frame_probe = frame_probe

    def produce(self, artifact, script: dict, profile: dict, progress) -> ProductionResult:
        artifact_dir = self._artifact_directory(artifact.artifact_id)
        if not artifact_dir.is_dir():
            raise FileNotFoundError(f"artifact directory missing: {artifact_dir}")

        script_dir = artifact_dir / "script"
        audio_dir = artifact_dir / "audio"
        video_dir = artifact_dir / "video"
        for directory in (script_dir, audio_dir, video_dir):
            directory.mkdir(exist_ok=True)

        canonical_script = copy.deepcopy(script)
        canonical_profile = copy.deepcopy(profile)
        script_path = script_dir / "script.json"
        audio_path = audio_dir / "narration.mp3"
        video_path = video_dir / "final.mp4"

        script_path.write_text(
            json.dumps(canonical_script, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        progress("script_saved", 10)

        tracker = self._get_tracker(video_id=artifact.artifact_id)
        cost_start = len(tracker.entries)

        produced_audio, metadata_path = self._generate_tts(
            copy.deepcopy(canonical_script),
            audio_path,
            script_path=script_path,
        )
        produced_audio = self._required_output(
            produced_audio, artifact_dir, "audio output"
        )
        metadata_path = self._required_output(
            metadata_path, artifact_dir, "TTS metadata output"
        )
        progress("audio_generated", 40)

        self._merge_script_into_tts(
            copy.deepcopy(canonical_script), metadata_path
        )
        tts_metadata = self._read_metadata(metadata_path)
        audio_probe = self._media_probe(produced_audio)
        validate_timing(tts_metadata, audio_probe)
        progress("timing_merged", 55)

        audience_profile = copy.deepcopy(canonical_profile["audience"])
        # The legacy topic tier writes to global output/backgrounds and has no
        # destination argument.  Omitting topic/category keeps all new media
        # inside this artifact while retaining explicit/profile resolution.
        selected_background = self._resolve_background(
            audience_profile,
            artifact.request.background,
        )
        if not isinstance(selected_background, str) or not selected_background:
            raise ValueError("background resolver returned invalid output")
        progress("background_resolved", 65)

        produced_video = self._render_video(
            produced_audio,
            metadata_path,
            video_path,
            video_type=canonical_script.get("type"),
            background=selected_background,
            native_language=canonical_profile["workspace"]["native_language"],
        )
        produced_video = self._required_output(
            produced_video, artifact_dir, "video output"
        )
        video_probe = self._media_probe(produced_video)
        frame_report = self._frame_probe(produced_video)
        validate_video(video_probe, frame_report, float(tts_metadata["duration"]))
        progress("video_rendered", 95)

        production = {
            "background": selected_background,
            "video_type": canonical_script.get("type"),
            "tts_metadata": self._relative(metadata_path, artifact_dir),
            "media_validation": {
                **copy.deepcopy(video_probe),
                **copy.deepcopy(frame_report),
            },
        }
        for field in ("duration", "segments"):
            if field in tts_metadata:
                production[field] = copy.deepcopy(tts_metadata[field])

        costs = cost_delta(tracker, cost_start)
        progress("production_complete", 100)
        return ProductionResult(
            paths=ArtifactPaths(
                script=self._relative(script_path, artifact_dir),
                audio=self._relative(produced_audio, artifact_dir),
                video=self._relative(produced_video, artifact_dir),
            ),
            costs=costs,
            production=production,
        )

    def _artifact_directory(self, artifact_id: str) -> Path:
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or Path(artifact_id).name != artifact_id
            or Path(artifact_id).is_absolute()
        ):
            raise ValueError("artifact_id must identify one safe directory")
        root = self.root.resolve()
        candidate = (root / artifact_id).resolve()
        if candidate.parent != root:
            raise ValueError("artifact_id escapes production root")
        return candidate

    @staticmethod
    def _required_output(path, artifact_dir: Path, label: str) -> Path:
        if path is None:
            raise FileNotFoundError(f"{label} missing")
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = artifact_dir / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(artifact_dir)
        except ValueError as exc:
            raise ValueError(f"{label} path escapes artifact directory") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"{label} missing: {candidate}")
        return candidate

    @staticmethod
    def _relative(path: Path, artifact_dir: Path) -> str:
        try:
            return path.resolve().relative_to(artifact_dir).as_posix()
        except ValueError as exc:
            raise ValueError("output path escapes artifact directory") from exc

    @staticmethod
    def _read_metadata(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("TTS metadata output must contain an object")
        return value

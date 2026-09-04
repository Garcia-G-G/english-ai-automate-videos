"""Native Simplified-Chinese production behind the Studio gateway contract."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

from PIL import ImageFont

from .creation import ProductionResult
from .editorial_costs import attach_costs, cost_delta
from .media_validation import inspect_frames, probe_media, validate_timing, validate_video
from .models import ArtifactPaths, Market

logger = logging.getLogger(__name__)


def _tracker(video_id=None):
    from cost_tracker import get_tracker
    return get_tracker(video_id=video_id)


def _synthesize(script, audio_path, metadata_path, *, voice, workspace):
    from tts_bilingual import generate_bilingual_narration
    from tts_segmenter import LANGUAGE_POLICIES

    audio = workspace["audio"]
    settings = {
        "voice_id": voice,
        "model_id": audio["segment_model"],
        "native_language": "zh-Hans",
        "narration_lang": audio["narration_lang"],
        "english_lang": audio["english_accent"].split("-")[0].lower(),
        "stability": 0.5, "similarity": 0.8, "style": 0.05,
        "speed": 1.0, "english_speed_factor": 0.92,
    }
    result = generate_bilingual_narration(
        script, str(audio_path), voice_id=voice, settings=settings,
        language_policy=LANGUAGE_POLICIES["zh-Hans"],
    )
    metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return audio_path, metadata_path


def _render(audio, metadata, video, **kwargs):
    import pipeline
    return pipeline.render_video(audio, metadata, video, **kwargs)


def _background(profile, requested):
    import pipeline
    return pipeline.resolve_background(profile, requested)


def resolve_cjk_font() -> str:
    candidates = (
        Path("assets/fonts/NotoSansCJKsc-Regular.otf"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            if ImageFont.truetype(str(path), 32).getmask("汉语").getbbox():
                return str(path.resolve())
        except OSError:
            continue
    raise FileNotFoundError("no CJK-capable font is available for Simplified Chinese rendering")


class BilibiliProductionGateway:
    def __init__(
        self,
        root: Path,
        *,
        synthesizer=_synthesize,
        renderer=_render,
        background_resolver=_background,
        tracker_getter=_tracker,
        media_probe=probe_media,
        frame_probe=inspect_frames,
        font_resolver=resolve_cjk_font,
    ):
        self.root = Path(root)
        self._synthesizer = synthesizer
        self._renderer = renderer
        self._background_resolver = background_resolver
        self._tracker_getter = tracker_getter
        self._media_probe = media_probe
        self._frame_probe = frame_probe
        self._font_resolver = font_resolver

    def produce(self, artifact, script: dict, profile: dict, progress):
        """Render, and record the spend either way — see
        LegacyProductionGateway.produce for why this is a finally."""
        tracker = self._tracker_getter(video_id=artifact.artifact_id)
        start = len(tracker.entries)
        try:
            return self._produce(artifact, script, profile, progress, tracker)
        except Exception as exc:                               # noqa: BLE001
            attach_costs(exc, tracker, start)
            raise
        finally:
            try:
                tracker.save()
            except Exception:                              # noqa: BLE001
                logger.exception("could not persist the cost ledger")

    def _produce(self, artifact, script: dict, profile: dict, progress, tracker) -> ProductionResult:
        self._validate_profile(artifact, profile)
        artifact_dir = (self.root.resolve() / artifact.artifact_id).resolve()
        if artifact_dir.parent != self.root.resolve() or not artifact_dir.is_dir():
            raise FileNotFoundError(f"artifact directory missing: {artifact_dir}")
        directories = {name: artifact_dir / name for name in ("script", "audio", "background", "video")}
        for directory in directories.values():
            directory.mkdir(exist_ok=True)
        script_path = directories["script"] / "script.json"
        audio_path = directories["audio"] / "narration.mp3"
        metadata_path = directories["audio"] / "narration.json"
        video_path = directories["video"] / "final.mp4"
        background_path = directories["background"] / "selection.json"
        canonical_script, canonical_profile = copy.deepcopy(script), copy.deepcopy(profile)
        script_path.write_text(json.dumps(canonical_script, ensure_ascii=False, indent=2), encoding="utf-8")
        progress("script_saved", 10)

        start = len(tracker.entries)
        produced_audio, produced_metadata = self._synthesizer(
            copy.deepcopy(canonical_script), audio_path, metadata_path,
            voice=canonical_profile["voice"]["voice_id"],
            workspace=copy.deepcopy(canonical_profile["workspace"]),
        )
        produced_audio = self._required(produced_audio, artifact_dir, "audio")
        produced_metadata = self._required(produced_metadata, artifact_dir, "timing")
        metadata = json.loads(produced_metadata.read_text(encoding="utf-8"))
        audio_probe = self._media_probe(produced_audio)
        validate_timing(metadata, audio_probe,
                        canonical_script.get("type"))
        progress("audio_validated", 45)

        selected = self._background_resolver(
            copy.deepcopy(canonical_profile["audience"]), artifact.request.background
        )
        if not isinstance(selected, str) or not selected or ".." in selected or selected.startswith("/"):
            raise ValueError("background resolver returned unsafe background")
        background_path.write_text(json.dumps({"selected": selected}, ensure_ascii=False), encoding="utf-8")
        font_path = self._font_resolver()
        progress("background_resolved", 60)

        produced_video = self._renderer(
            produced_audio, produced_metadata, video_path,
            video_type=canonical_script.get("type"), background=selected,
            font_path=font_path,
            native_language=canonical_profile["workspace"]["native_language"],
            use_v2=artifact.request.render_engine.value == "v2",
        )
        produced_video = self._required(produced_video, artifact_dir, "video")
        video_probe = self._media_probe(produced_video)
        frame_report = self._frame_probe(produced_video)
        validate_video(video_probe, frame_report, float(metadata["duration"]))
        progress("video_validated", 95)
        costs = cost_delta(tracker, start)
        progress("production_complete", 100)
        return ProductionResult(
            paths=ArtifactPaths(
                script=self._relative(script_path, artifact_dir),
                audio=self._relative(produced_audio, artifact_dir),
                video=self._relative(produced_video, artifact_dir),
                background=self._relative(background_path, artifact_dir),
            ),
            costs=costs,
            production={
                "background": selected,
                "duration": metadata["duration"],
                "timing": copy.deepcopy(metadata),
                "voice_id": canonical_profile["voice"]["voice_id"],
                "voice_locale": "zh-Hans",
                "subtitle_languages": ["zh-Hans", "en"],
                "font": font_path,
                "render_engine": {
                    "requested": artifact.request.render_engine.value,
                    "effective": artifact.request.render_engine.effective_for(
                        canonical_script.get("type")
                    ).value,
                },
                "media_validation": {**copy.deepcopy(video_probe), **copy.deepcopy(frame_report)},
            },
        )

    @staticmethod
    def _validate_profile(artifact, profile):
        request = artifact.request
        if request.market is not Market.BILIBILI:
            raise ValueError("BilibiliProductionGateway supports only bilibili")
        expected = {
            "workspace.workspace_id": "bilibili_zh_hans_en",
            "workspace.market": "bilibili", "workspace.native_language": "zh-Hans",
            "workspace.learning_language": "en", "voice.workspace_id": "bilibili_zh_hans_en",
            "voice.audience": request.audience.value, "voice.locale": "zh-Hans",
            "voice.provider": "elevenlabs", "audience.audience": request.audience.value,
        }
        for dotted, wanted in expected.items():
            value = profile
            try:
                for part in dotted.split("."):
                    value = value[part]
            except (KeyError, TypeError):
                value = None
            if value != wanted:
                raise ValueError(f"{dotted} mismatch")

    @staticmethod
    def _required(path, root, label):
        candidate = Path(path).resolve() if path is not None else None
        if candidate is None or not candidate.is_file():
            raise FileNotFoundError(f"{label} output missing")
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{label} output escapes artifact directory") from exc
        return candidate

    @staticmethod
    def _relative(path, root):
        return Path(path).resolve().relative_to(root).as_posix()

"""Compatibility adapters over the existing Spanish/YouTube pipeline."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Callable

from .creation import AuthorResult, ProductionResult
from .editorial_costs import attach_costs, cost_delta, invoke_with_costs
from .media_validation import inspect_frames, probe_media, validate_timing, validate_video
from .models import ArtifactPaths, CreationMode, Market

logger = logging.getLogger(__name__)


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


def duration_check(*args, **kwargs):
    from duration_spec import check

    return check(*args, **kwargs)


def _resolve_background(*args, **kwargs):
    import pipeline

    return pipeline.resolve_background(*args, **kwargs)


def _render_video(*args, **kwargs):
    import pipeline

    return pipeline.render_video(*args, **kwargs)


def _finalize_video(*args, **kwargs):
    import pipeline

    return pipeline.finalize_video(*args, **kwargs)


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
            # THE TYPE CONSTRAINS THE DRAW NOW.
            #
            # This used to pass the audience's category list alone, so the
            # video type and the topic category were independent draws and
            # any pairing was possible: 43 of 221 rendered artifacts (19%)
            # got a category that did not suit the type, and 0 of 20
            # pronunciation videos ever drew from the pronunciation file.
            #
            # The mapping is NOT written here — it is config, because it is
            # an editorial judgement that will be revised by whoever owns
            # the content. This only intersects the two lists and refuses
            # when they do not overlap.
            from type_categories import resolve as _eligible_categories

            allowed = _eligible_categories(
                video_type,
                audience.get("content", {}).get("categories"),
            )
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
        finalizer=_finalize_video,
    ):
        self.root = Path(root)
        self._get_tracker = _get_tracker
        self._generate_tts = _generate_tts
        self._merge_script_into_tts = _merge_script_into_tts
        self._resolve_background = _resolve_background
        self._render_video = _render_video
        self._media_probe = media_probe
        self._frame_probe = frame_probe
        self._finalize_video = finalizer

    def produce(self, artifact, script: dict, profile: dict, progress) -> ProductionResult:
        """Render one artifact, and record what it cost either way.

        THE LEDGER IS WRITTEN IN A finally. Not because failure is expected,
        but because this path never wrote it at all — `tracker.save()`
        appeared only in admin.py, so every CLI render logged its spend to
        the console and persisted none of it. The first real run of this
        path spent $0.0734 on a script and a full TTS, was blocked before
        the renderer, and left no row in output/costs/.

        Iterating on a broken pipeline is exactly when spend accumulates
        fastest and least visibly, and config.yaml carries a monthly ceiling
        that reads output/costs/. A ceiling fed only by successes
        under-counts precisely when it matters most.
        """
        tracker = self._get_tracker(video_id=artifact.artifact_id)
        start = len(tracker.entries)
        try:
            return self._produce(artifact, script, profile, progress, tracker)
        except Exception as exc:                               # noqa: BLE001
            # The ledger below is the authoritative record; this is the copy
            # the artifact shows, so it cannot say $0.0008 for a run that
            # spent $0.0734. A BARE re-raise: the delegated stage's own
            # exception must reach the caller unchanged.
            attach_costs(exc, tracker, start)
            raise
        finally:
            self._persist_costs(tracker)

    @staticmethod
    def _persist_costs(tracker) -> None:
        """save() is a no-op with no entries, and must never mask the real
        error — a failure to write the ledger is not what took the run down."""
        try:
            tracker.save()
        except Exception:                                      # noqa: BLE001
            logger.exception("could not persist the cost ledger")

    def _produce(self, artifact, script: dict, profile: dict, progress,
                 tracker) -> ProductionResult:
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
        validate_timing(tts_metadata, audio_probe,
                        canonical_script.get("type"))

        # DURATION IS A SPECIFICATION NOW, and this is where it is judged.
        #
        # AFTER the synthesis, deliberately. Language models do not hit word
        # counts precisely, so the word target the generator was given is a
        # LEVER and not the specification — the specification is the
        # duration, and the only honest way to know it is to measure the
        # narration that actually came back. Checking the script's word
        # count before synthesis would be measuring the lever.
        #
        # Recorded on the artifact whether it passes or fails: before this,
        # nothing in the pipeline aimed at a duration and 20% of videos
        # landed in band, which is exactly the kind of thing a silent pass
        # keeps invisible.
        duration_gate = duration_check(
            canonical_script.get("type"),
            float(tts_metadata.get("duration") or 0),
        )
        if duration_gate["status"] != "PASS":
            logger.warning("duration %s: %s", duration_gate["status"],
                           duration_gate.get("reason"))
        progress("timing_merged", 55)

        audience_profile = copy.deepcopy(canonical_profile["audience"])
        # TOPIC AND CATEGORY ARE PASSED NOW, and this is the change.
        #
        # They used to be omitted, with the reason recorded here: "the legacy
        # topic tier writes to global output/backgrounds and has no
        # destination argument". That objection was correct and it is now
        # obsolete — resolve_background's clip tier takes `dest_dir` and
        # writes the footage inside this artifact, so passing the topic no
        # longer leaks media into a global directory. The Studio path can
        # finally receive a real background instead of a palette.
        #
        # The image tier below it still has no destination, so it is still
        # reached only if the clip tier declines. That is deliberate: it
        # keeps the artifact self-contained on the path that runs.
        selected_background = self._resolve_background(
            audience_profile,
            artifact.request.background,
            # THE CATEGORY LIVES IN _meta, not at the top level. Reading
            # canonical_script["category"] found None on every auto-mode
            # video, the clip tier raised UnknownCategory and every batch
            # render fell through to the $0.041 image tier — the feature
            # wired but never reached. TopicScriptAuthor picks the category
            # and the generator stamps it into _meta; that is the record.
            #
            # The topic seeds WHICH footage this video gets, so the idea
            # ("batch_1" in batch mode) is the worst available choice and
            # the script's own title is the best.
            topic=(artifact.request.topic
                   or canonical_script.get("video_title")
                   or artifact.request.idea),
            category=(artifact.request.category
                      or (canonical_script.get("_meta") or {}).get("category")
                      or canonical_script.get("category")),
            dest_dir=artifact_dir / "clips",
            duration=float(tts_metadata.get("duration") or 0) or None,
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
            use_v2=artifact.request.render_engine.value == "v2",
        )
        produced_video = self._required_output(
            produced_video, artifact_dir, "video output"
        )
        finalized = self._finalize_video(
            produced_video,
            metadata_path,
            variant_seed=artifact.artifact_id,
        )
        final_video, finalization, gate = self._validated_finalization(
            finalized, produced_video, artifact_dir
        )
        video_probe = self._media_probe(final_video)
        frame_report = self._frame_probe(final_video)
        narration_duration = float(tts_metadata["duration"])
        expected_duration = narration_duration
        if finalization["outro_appended"]:
            definitive_duration = float(video_probe.get("duration") or 0)
            validate_video(video_probe, frame_report, definitive_duration)
            tolerance = max(0.25, narration_duration * 0.05)
            if definitive_duration < narration_duration - tolerance:
                raise ValueError("finalized video is shorter than narration")
        else:
            validate_video(video_probe, frame_report, expected_duration)
        progress("video_rendered", 95)

        # Re-judged against the REAL video now that it exists. The
        # projection above is what the pipeline could know before the
        # render; this is what actually shipped, and the two are kept
        # distinct in the record rather than one overwriting the other.
        duration_gate = duration_check(
            canonical_script.get("type"),
            float(tts_metadata.get("duration") or 0),
            measured_video_seconds=float(video_probe.get("duration") or 0),
        )
        if duration_gate["status"] != "PASS":
            logger.warning("duration %s: %s", duration_gate["status"],
                           duration_gate.get("reason"))

        production = {
            "background": selected_background,
            "video_type": canonical_script.get("type"),
            "tts_metadata": self._relative(metadata_path, artifact_dir),
            "media_validation": {
                **copy.deepcopy(video_probe),
                **copy.deepcopy(frame_report),
            },
            "render_engine": {
                "requested": artifact.request.render_engine.value,
                "effective": artifact.request.render_engine.effective_for(
                    canonical_script.get("type")
                ).value,
            },
            "finalization": finalization,
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
                video=self._relative(final_video, artifact_dir),
            ),
            costs=costs,
            production=production,
            gates=[gate, duration_gate],
        )

    def _validated_finalization(
        self, result, rendered_video: Path, artifact_dir: Path
    ):
        if type(result) is not dict:
            raise TypeError("finalizer must return dict")
        verdict = result.get("gate")
        if verdict not in {"PASS", "REJECT", "NO_REPORT"}:
            raise ValueError(f"finalizer returned unknown gate verdict: {verdict}")
        if type(result.get("outro_appended")) is not bool:
            raise ValueError("finalizer outro_appended must be bool")
        if verdict != "PASS" and result["outro_appended"]:
            raise ValueError("finalizer cannot append an outro without PASS")

        blocking_flags = result.get("blocking_flags", [])
        if (
            not isinstance(blocking_flags, list)
            or any(not isinstance(flag, str) for flag in blocking_flags)
        ):
            raise ValueError("finalizer blocking_flags must be a list of strings")
        reason = result.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("finalizer reason must be a string")
        variant = result.get("outro_variant")
        if variant is not None and not isinstance(variant, str):
            raise ValueError("finalizer outro_variant must be a string")

        final_video = self._required_output(
            result.get("video"), artifact_dir, "finalized video output"
        )
        if final_video != rendered_video.resolve():
            raise ValueError("finalizer must preserve the canonical video path")

        finalization = copy.deepcopy({
            key: value for key, value in result.items() if key != "video"
        })
        try:
            json.dumps(finalization, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("finalizer facts must be JSON-compatible") from exc
        gate = {
            "kind": "final_qa",
            "version": 1,
            "status": verdict,
            "blocking_flags": copy.deepcopy(blocking_flags),
        }
        if reason is not None:
            gate["reason"] = reason
        return final_video, finalization, gate

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

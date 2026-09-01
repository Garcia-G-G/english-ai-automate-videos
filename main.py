#!/usr/bin/env python3
"""
Main Pipeline Orchestrator for English AI Videos
Runs the full pipeline: GPT Script → TTS → Video

Supports video types:
- educational: Hook → Explanation → Examples → Tip → CTA
- quiz: Question → Options A/B/C/D → Timer → Answer
- true_false: Statement → ✓/✗ options → Timer → Answer
- fill_blank: Sentence with ___ → Options → Answer
- pronunciation: Word → Phonetic → Common mistake → Correct

Usage:
  python main.py --script output/scripts/embarrassed.json
  python main.py --random
  python main.py --random --type quiz
  python main.py --category false_friends --topic embarrassed --type true_false
  python main.py --batch 3 --type quiz
"""

import argparse
import fnmatch
import re
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging for the entire application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

# Paths
ROOT = Path(__file__).parent
SRC = ROOT / "src"
OUTPUT_DIR = ROOT / "output"

def get_output_paths(video_type: str, output_name: str) -> tuple:
    """Get output paths organized by video type."""
    # Create type-specific folders
    script_dir = OUTPUT_DIR / "scripts" / video_type
    audio_dir = OUTPUT_DIR / "audio" / video_type
    video_dir = OUTPUT_DIR / "video" / video_type

    script_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    return (
        script_dir / f"{output_name}.json",
        audio_dir / f"{output_name}.mp3",
        audio_dir / f"{output_name}.json",  # TTS timestamps
        video_dir / f"{output_name}.mp4"
    )

# Add src/ to PYTHONPATH so that top-level modules (script_generator, tts_openai, etc.)
# can be imported without package prefixes.  All pipeline code lives under src/.
sys.path.insert(0, str(SRC))
from script_generator import (
    get_random_topic,
    get_topic_name,
    find_topic,
    list_categories,
    load_topics,
    VIDEO_TYPES
)
from studio import CreationRequest, ProvidedScriptAuthor, build_creation_service

# Active audience profile (adults/kids), resolved in main()
ACTIVE_PROFILE = {}


def load_script(script_path: Path) -> dict:
    """Load a script JSON file."""
    with open(script_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_scripts():
    """List all available scripts organized by type."""
    scripts_dir = OUTPUT_DIR / "scripts"

    # Check both root and type subdirectories
    all_scripts = list(scripts_dir.glob("*.json")) + list(scripts_dir.glob("*/*.json"))

    if not all_scripts:
        logger.info("No scripts found in output/scripts/")
        return

    logger.info("Available Scripts:")
    logger.info("=" * 50)

    # Group by type
    by_type = {}
    for s in sorted(all_scripts):
        try:
            data = load_script(s)
            vtype = data.get('type', 'educational')
            if vtype not in by_type:
                by_type[vtype] = []
            by_type[vtype].append((s, data))
        except:
            pass

    for vtype in sorted(by_type.keys()):
        logger.info("  [%s]", vtype)
        for s, data in by_type[vtype]:
            hook = data.get('hook', data.get('question', data.get('statement', 'No preview')))[:35]
            rel_path = s.relative_to(scripts_dir)
            logger.info("    %s: %s...", rel_path, hook)


#: Characters that cannot appear in an artifact name. `/` is the one that
#: actually bit — see safe_artifact_name.
_UNSAFE_NAME_CHARS = re.compile(r"[^a-z0-9._-]+")


def safe_artifact_name(topic_name: str) -> str:
    """Turn a topic name into a name usable as a FILENAME.

    WHY. This was `topic_name.replace(' ', '_').lower()`, and 16 of the 720
    topics contain a forward slash — "Ser/Estar confusion with 'to be'",
    "doggy bag / to-go box", "swipe right / swipe left". The slash became a
    directory separator, so the pipeline tried to write
    output/scripts/fill_blank/ser/estar_confusion... into a directory that
    does not exist and died with FileNotFoundError, AFTER paying for the GPT
    call. Unattended at 2/day that is roughly one silent loss every 3 weeks.

    The name is also the ledger key and the idempotency guard's key
    (publication_log, upload_guard), so it has to be stable and collision-
    resistant, not merely legal. Measured across all 720 topics: this
    produces 704 unique names, exactly as many as the old
    `.replace(' ', '_').lower()` did, so it introduces no new collision. The
    single collision that exists ("bring vs take" / "Bring vs Take") predates
    this and comes from the .lower(), which was always there.
    """
    name = _UNSAFE_NAME_CHARS.sub("_", (topic_name or "").strip().lower())
    name = name.strip("._-")
    # A leading dot would hide the artifact; an empty name would collide with
    # every other empty one.
    return name or "untitled"


def _note_failure(entry: dict, stage: str, exc) -> None:
    """Record a stage failure in the run report, if one is being kept.

    Tolerant of entry=None so every existing caller of run_pipeline keeps
    working unchanged, and tolerant of its own errors because a reporting bug
    must never be what takes a batch down — that would be this module's own
    defect, one level up.
    """
    if entry is None:
        return
    try:
        entry.update(status="failed", stage=stage, reason=str(exc)[:1000])
    except Exception:                                      # noqa: BLE001
        logger.exception("could not record the %s failure in the report", stage)


def _note_rejection(entry: dict, video_path, fin: dict) -> None:
    """The gate refused this artifact. Its own category, not a failure.

    Nothing broke: a video was produced and judged unfit. It goes to
    output/rejected/, which already means exactly that, rather than the
    output/failed/ tree that means a stage raised.
    """
    if entry is None:
        return
    try:
        from batch_report import move_rejected, reject
        reject(entry, fin.get("blocking_flags"))
        move_rejected(video_path, entry, report=fin)
    except Exception:                                      # noqa: BLE001
        logger.exception("could not record the gate rejection")


def _report_upload(entry: dict, outcome: dict) -> None:
    if entry is None:
        return
    try:
        from batch_report import record_upload_outcome
        record_upload_outcome(entry, outcome)
    except Exception:                                      # noqa: BLE001
        logger.exception("could not fold the upload outcome into the report")


def move_uploaded_artifact(video_path: Path, outcome: dict) -> Path:
    """Move a published video (and its sidecar) to output/uploaded/<type>/.

    Mirrors admin.move_to_uploaded, which this path never had. Returns the new
    location, or the original path if nothing was moved.

    Deliberately called only when a publication was RECORDED. Moving on a bare
    upload success would take the file out of reach while the ledger still
    said nothing was published — the worst of both states.
    """
    import shutil

    uploaded_dir = OUTPUT_DIR / "uploaded" / (video_path.parent.name or "unknown")
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    dest = uploaded_dir / video_path.name

    if dest.exists():
        logger.warning("%s already exists in uploaded/; leaving %s in place",
                       dest.name, video_path)
        return video_path

    shutil.move(str(video_path), str(dest))
    sidecar = video_path.with_suffix(".json")
    if sidecar.exists():
        info = {"platforms": outcome.get("recorded", []),
                "uploaded_at": datetime.now().isoformat()}
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["upload_info"] = info
                sidecar.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            logger.warning("could not annotate %s with upload_info", sidecar)
        shutil.move(str(sidecar), str(uploaded_dir / sidecar.name))

    logger.info("moved %s -> %s", video_path.name, uploaded_dir)
    return dest


def upload_video(video_path: Path, video_type: str, script_data: dict = None,
                 platforms: list = None, artifact: str = None) -> dict:
    """Upload a video to configured social platforms, and RECORD each success.

    This is the path `--batch N --upload` runs, i.e. the one that will publish
    unattended. Two things about it were wrong.

    IT NEVER RECORDED ANYTHING. `publication_log` had zero callers outside
    admin.py, so an unattended publication left no trace this repo could join
    to the live video — the exact defect the ledger was written to fix, at the
    one place with no operator watching. It now goes through the same
    `record_upload_result` the dashboard uses.

    IT RESOLVED ITS OWN METADATA. It called generate_metadata +
    adapt_for_platform inline, a third copy of the resolver, so it could drift
    from what the dashboard publishes for the same script. It now calls
    `resolve_upload_metadata` with NO_OPERATOR_EDITS — headless, so there is
    no operator text, and it says so explicitly instead of relying on a
    default. Behaviour is unchanged: with an empty state the resolver runs the
    same generate + adapt it replaced.

    RETURNS a summary rather than None, and does NOT swallow. The old body was
    wrapped in a bare `except Exception` that logged one line and returned, so
    in batch mode an upload failure was invisible to the caller. Errors are
    now logged with a traceback and returned in `errors`. What a batch should
    DO about a failure — abort, continue, exit non-zero — is deliberately not
    decided here; the caller gets the facts to decide with.
    """
    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED,
                                 ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 PublicationRecordError, record_attempt,
                                 record_upload_result)
    from upload_guard import SKIP_DONE, SKIP_HOLD, decide
    from upload_metadata import NO_OPERATOR_EDITS, resolve_upload_metadata

    artifact = artifact or Path(video_path).stem
    outcome = {"artifact": artifact, "uploaded": [], "recorded": [],
               "unrecorded": [], "skipped": [], "skip_details": [],
               "held": [], "errors": []}

    try:
        from uploader import UploadManager, VideoMetadata, resolve_privacy
        import yaml
    except ImportError as e:
        logger.exception("upload module not available")
        outcome["errors"].append({"platform": None, "stage": "import",
                                  "error": str(e)})
        return outcome

    config_path = ROOT / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

    upload_config = config.get("upload", {})
    if platforms is None:
        platforms = upload_config.get("platforms", [])

    if not platforms:
        logger.warning("No upload platforms configured. Add platforms to config.yaml upload.platforms")
        return outcome

    category = ""
    if script_data:
        category = script_data.get("_meta", {}).get("category", "")

    platform_map = {"tiktok": "tiktok", "youtube": "youtube", "instagram": "instagram"}
    manager = UploadManager()

    for platform_name in platforms:
        platform_key = platform_map.get(platform_name.lower(), platform_name.lower())

        # IDEMPOTENCY. Ask before uploading, not after. See upload_guard.
        verdict = decide(artifact, platform_key, manager=manager)
        if verdict.action == SKIP_DONE:
            logger.info("Skipping %s: %s (id=%s)", platform_name,
                        verdict.reason, verdict.upload_id)
            outcome["skipped"].append(platform_name)
            # Carry the id the guard believes is already live, so a skip in
            # the batch report can be checked against the channel rather
            # than taken on trust.
            outcome["skip_details"].append({"platform": platform_name,
                                            "upload_id": verdict.upload_id,
                                            "reason": verdict.reason})
            if verdict.recovered:
                outcome["recorded"].append(platform_name)
            continue
        if verdict.action == SKIP_HOLD:
            logger.critical(
                "HOLDING %s -> %s: %s. NOT uploading and NOT marking failed; "
                "a human must check whether it is already live.",
                artifact, platform_name, verdict.reason)
            outcome["held"].append(platform_name)
            outcome["errors"].append({"platform": platform_name,
                                      "stage": "guard",
                                      "error": verdict.reason})
            continue

        try:
            resolved = resolve_upload_metadata(
                artifact, script_data or {}, platform_key, video_type,
                category, NO_OPERATOR_EDITS,
            )

            # No privacy= here. It used to say privacy="public" and it was
            # dead: this object is decomposed into three strings for the
            # manager.upload() call below and then discarded, so the value
            # never reached a request body. Privacy is resolved from the
            # platform inside the uploader — uploader.PLATFORM_PRIVACY.
            metadata = VideoMetadata(
                title=resolved["title"],
                description=resolved["description"],
                hashtags=[h.lstrip("#") for h in resolved["hashtags"]],
            )

            # The strings the API is actually handed. record_upload_result
            # documents that these -- not the pre-adaptation text -- are what
            # must be recorded, so they are captured from the same locals the
            # upload call reads rather than recomposed afterwards.
            sent_title = metadata.title
            sent_description = metadata.full_description
            sent_hashtags = metadata.hashtags

            logger.info("Uploading to %s (%s metadata, privacy=%s): '%s'",
                        platform_name, resolved["source"],
                        resolve_privacy(platform_key), sent_title[:60])

            # The attempt lands BEFORE a byte moves. If this process dies
            # anywhere below, the next run sees an open attempt instead of
            # "never uploaded" and reconciles rather than re-publishing.
            file_size = Path(video_path).stat().st_size
            record_attempt(artifact=artifact, platform=platform_key,
                           status=ATTEMPT_STARTED, video_path=str(video_path),
                           file_size=file_size, detail=sent_title)

            def _session(uri, size, _p=platform_key, _t=sent_title):
                """Called by the uploader the moment the resumable session
                exists and before any video bytes are sent."""
                record_attempt(artifact=artifact, platform=_p,
                               status=ATTEMPT_SESSION, video_path=str(video_path),
                               session_uri=uri, file_size=size, detail=_t)

            result = manager.upload(
                platform_key,
                str(video_path),
                title=sent_title,
                description=sent_description,
                hashtags=sent_hashtags,
                on_session=_session,
            )
        except Exception as e:                          # noqa: BLE001
            # Kept per-platform: a YouTube failure must not stop Instagram,
            # and it must not vanish either.
            logger.exception("Upload to %s raised", platform_name)
            outcome["errors"].append({"platform": platform_name,
                                      "stage": "upload", "error": str(e)})
            continue

        if isinstance(result, dict):
            success = bool(result.get("success"))
            error = result.get("error")
            ident = result.get("url") or result.get("upload_id")
            got_id = result.get("upload_id")
            session_uri = result.get("session_uri")
        else:
            success = bool(getattr(result, "success", False))
            error = getattr(result, "error", None)
            ident = getattr(result, "url", None) or getattr(result, "upload_id", None)
            got_id = getattr(result, "upload_id", None)
            session_uri = getattr(result, "session_uri", None)

        if not success:
            logger.error("Upload to %s failed: %s", platform_name, error)
            # Close the attempt ONLY when the platform said it failed. An
            # attempt left open would hold every future run; one closed on a
            # guess would let a live video be published twice.
            record_attempt(artifact=artifact, platform=platform_key,
                           status=ATTEMPT_FAILED, video_path=str(video_path),
                           session_uri=session_uri, file_size=file_size,
                           detail=str(error))
            outcome["errors"].append({"platform": platform_name,
                                      "stage": "upload", "error": str(error)})
            continue

        logger.info("Uploaded to %s: %s", platform_name, ident)
        outcome["uploaded"].append(platform_name)

        try:
            record_upload_result(
                artifact=artifact,
                video_path=str(video_path),
                video_type=video_type or "",
                platform=platform_key,
                result=result,
                sent_title=sent_title,
                sent_description=sent_description,
                sent_hashtags=sent_hashtags,
            )
            outcome["recorded"].append(platform_name)
            record_attempt(artifact=artifact, platform=platform_key,
                           status=ATTEMPT_PUBLISHED, video_path=str(video_path),
                           session_uri=session_uri, upload_id=got_id,
                           file_size=file_size, detail="recorded")
        except PublicationRecordError as exc:
            # The upload already happened. There is no operator to show a
            # banner to, so this is CRITICAL and carried in the outcome: a
            # video is live that this repo cannot name.
            logger.critical(
                "PUBLISHED BUT NOT RECORDED: %s -> %s (%s). %s",
                artifact, platform_name, ident, exc)
            # The attempt row is what saves the next run. It stays OPEN
            # (status=session) carrying the URI and now the id, so the guard
            # reconciles instead of publishing a second copy.
            record_attempt(artifact=artifact, platform=platform_key,
                           status=ATTEMPT_SESSION, video_path=str(video_path),
                           session_uri=session_uri, upload_id=got_id,
                           file_size=file_size,
                           detail=f"published but record failed: {exc}")
            outcome["unrecorded"].append(platform_name)
            outcome["errors"].append({"platform": platform_name,
                                      "stage": "record", "error": str(exc)})

    # SECOND DUPLICATE VECTOR. This path never moved the file the way
    # admin.move_to_uploaded does, so a published video stayed in the render
    # tree looking unpublished. Only moved once a publication is RECORDED --
    # moving on a bare upload success would hide the file while the ledger
    # still said nothing was published, which is the worst of both states.
    if outcome["recorded"]:
        try:
            move_uploaded_artifact(video_path, outcome)
        except Exception:                                  # noqa: BLE001
            logger.exception(
                "could not move %s out of the render tree; the ledger still "
                "records the publication", video_path)

    return outcome


def run_pipeline(script_data: dict, output_name: str, video_type: str = None, background: str = None,
                 upload: bool = False, use_v2: bool = False, dry_run: bool = False,
                 entry: dict = None) -> Path:
    """Compatibility wrapper for an owner-supplied script."""
    artifact, video = run_creation(
        workspace="youtube", audience="adults", idea=output_name,
        mode="directed", artifact_id=output_name, video_type=video_type,
        background=background, supplied_script=script_data, upload=upload,
        dry_run=dry_run,
    )
    return video


def run_from_text(text: str, name: str = None, video_type: str = "educational", background: str = None,
                  upload: bool = False, use_v2: bool = False, dry_run: bool = False) -> Path:
    """Create a canonical artifact from owner-supplied narration text."""
    if not name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"quick_{timestamp}"

    # Create a simple script structure
    script_data = {
        "type": video_type,
        "full_script": text,
        "translations": {}
    }

    return run_pipeline(script_data, name, video_type, background, upload=upload,
                        use_v2=use_v2, dry_run=dry_run)



def generate_and_run(category: str, topic: dict, topic_name: str, video_type: str = "educational",
                     background: str = None, upload: bool = False, use_v2: bool = False,
                     dry_run: bool = False, entry: dict = None) -> Path:
    """Compatibility wrapper for a directed canonical creation."""
    _, video = run_creation(
        workspace="youtube", audience="adults", idea=topic_name,
        mode="directed", category=category, topic=topic_name,
        video_type=video_type, background=background,
        artifact_id=safe_artifact_name(topic_name), upload=upload,
        dry_run=dry_run,
    )
    return video


def get_creation_service(*, root=None, **dependencies):
    return build_creation_service(Path(root or OUTPUT_DIR / "artifacts"), **dependencies)


def run_creation(*, workspace, audience, idea, mode, root=None,
                 artifact_id=None, category=None, topic=None, video_type=None,
                 background=None, notes=None, supplied_script=None,
                 upload=False, dry_run=False):
    """Construct one typed request and delegate creation to Studio."""
    if dry_run:
        print(f"Dry run: planned {workspace}/{audience} creation; no artifact or paid call was made")
        return None, None
    dimensions = {
        "youtube": ("youtube", "es", "en"),
        "bilibili": ("bilibili", "zh-Hans", "en"),
    }
    if workspace not in dimensions:
        raise ValueError(f"unsupported workspace: {workspace}")
    market, native, learning = dimensions[workspace]
    request = CreationRequest(
        market=market, native_language=native, learning_language=learning,
        audience=audience, mode=mode, idea=idea, category=category, topic=topic,
        video_type=video_type, background=background, notes=notes,
    )
    dependencies = {"root": Path(root or OUTPUT_DIR / "artifacts")}
    if supplied_script is not None:
        author = ProvidedScriptAuthor(supplied_script)
        dependencies["youtube_author"] = author
        dependencies["bilibili_author"] = author
    service = get_creation_service(**dependencies)
    create_kwargs = {}
    if artifact_id is not None:
        create_kwargs["artifact_id"] = artifact_id
    artifact = service.create(request, **create_kwargs)
    repository_root = dependencies["root"]
    video = (
        repository_root / artifact.artifact_id / artifact.paths.video
        if artifact.paths.video else None
    )
    if upload:
        print("Upload refused: owner approval is required before publication")
    return artifact, video


def main():
    parser = argparse.ArgumentParser(
        description="English AI Video Pipeline - Generate TikTok-style videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Video Types: {', '.join(VIDEO_TYPES)}

Examples:
  python main.py --list-scripts                                    # List generated scripts
  python main.py --list-topics                                     # List available topics
  python main.py --script output/scripts/test.json                # Use existing script
  python main.py --random                                          # Random educational video
  python main.py --random --type quiz                              # Random quiz video
  python main.py --random --type true_false                        # Random true/false video
  python main.py --category false_friends --topic embarrassed      # Specific educational
  python main.py -c false_friends -t embarrassed --type quiz       # Specific quiz
  python main.py --text "Tu texto con 'English' words"             # Direct text
  python main.py --batch 3 --type quiz                             # 3 random quiz videos
        """
    )

    parser.add_argument("--list-scripts", "-ls", action="store_true",
                        help="List available generated scripts")
    parser.add_argument("--list-topics", "-lt", action="store_true",
                        help="List available topics for generation")
    parser.add_argument("--script", "-s", type=str,
                        help="Path to existing script JSON file")
    parser.add_argument("--random", "-r", action="store_true",
                        help="Generate script for random topic with GPT")
    parser.add_argument("--category", "-c", type=str,
                        help="Topic category (false_friends, phrasal_verbs, common_mistakes)")
    parser.add_argument("--topic", "-t", type=str,
                        help="Specific topic name")
    parser.add_argument("--type", type=str, default="educational",
                        choices=VIDEO_TYPES,
                        help="Video type (default: educational)")
    parser.add_argument("--text", type=str,
                        help="Direct text input (Spanish with 'English' in quotes)")
    parser.add_argument("--name", "-n", type=str,
                        help="Output name (without extension)")
    parser.add_argument("--background", "--bg", type=str, default=None,
                        help="Background preset (e.g. aurora_borealis, energetic_orbs). Default: random")
    parser.add_argument("--workspace", choices=["youtube", "bilibili"], default="youtube",
                        help="Editorial workspace (YouTube Spanish or Bilibili Chinese)")
    parser.add_argument("--profile", type=str, default="adults",
                        choices=["adults", "children", "kids"],
                        help="Audience profile (voice, backgrounds, topics). Default: config.yaml profile")
    parser.add_argument("--batch", "-b", type=int,
                        help="Generate multiple videos from random topics")
    parser.add_argument("--upload", "-u", action="store_true",
                        help="Upload video to configured platforms after generation")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose/debug logging")
    parser.add_argument("--v2", action="store_true",
                        help="Use the v2 render engine (educational only; "
                             "other types fall back to v1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve and log the TTS plan (provider, model, voice, "
                             "per-segment language_code) without calling any API")

    args = parser.parse_args()

    # Configure logging
    setup_logging(verbose=args.verbose)

    # List scripts mode
    if args.list_scripts:
        list_scripts()
        return

    # List topics mode
    if args.list_topics:
        print("\nAvailable Categories and Topics:")
        print("=" * 60)
        total = 0
        for cat in sorted(list_categories()):
            topics = load_topics(cat)
            total += len(topics)
            print(f"\n  {cat} ({len(topics)} topics):")
            for t in topics[:10]:  # Show first 10
                name = get_topic_name(t)
                diff = t.get("difficulty", "")
                diff_str = f" [{diff}]" if diff else ""
                print(f"    - {name}{diff_str}")
            if len(topics) > 10:
                print(f"    ... and {len(topics) - 10} more")
        print(f"\n{'='*60}")
        print(f"Total: {total} topics across {len(list_categories())} categories")
        print(f"Video Types: {', '.join(VIDEO_TYPES)}")
        return

    audience = args.profile
    if audience == "kids":
        print("Warning: --profile kids is deprecated; using children")
        audience = "children"

    if args.dry_run:
        print(
            f"Dry run: planned {args.workspace}/{audience} {args.type} creation; "
            "no artifact or paid call was made"
        )
        return

    # Batch mode
    if args.batch:
        from batch_report import BatchReport

        print(f"\nBatch mode: Generating {args.batch} {args.type} videos")
        report = BatchReport(kind="batch")
        for i in range(args.batch):
            print(f"\n{'#'*50}")
            print(f"# VIDEO {i+1} of {args.batch} [{args.type}]")
            print(f"{'#'*50}")

            topic_name = f"batch_{i + 1}"
            entry = report.start_video(
                topic_name.replace(" ", "_").lower(), args.type, topic_name)
            try:
                artifact, video = run_creation(
                    workspace=args.workspace, audience=audience, idea=topic_name,
                    mode="auto", video_type=args.type, background=args.background,
                    upload=args.upload,
                )
                entry["artifact_id"] = artifact.artifact_id
                entry["artifact_path"] = str(video) if video else None
            except Exception as exc:                       # noqa: BLE001
                # ONE VIDEO MUST NEVER ABORT THE BATCH. Everything below
                # already returns rather than raising, so this is the backstop
                # for what nobody anticipated -- and it records rather than
                # swallows.
                logger.exception("video %d of %d raised", i + 1, args.batch)
                _note_failure(entry, entry.get("stage") or "unknown", exc)

        path = report.write()
        c = report.counts()
        print(f"\n{'#'*50}")
        print(f"# BATCH COMPLETE: {c['attempted']} attempted, "
              f"{c['rendered']} rendered, {c['gate_passed']} passed the gate")
        print(f"#   {c['published']} published, {c['skipped']} skipped, "
              f"{c['rejected']} rejected by the gate, "
              f"{c['failed']} failed, {c['needs_human']} NEED A HUMAN")
        if report.needs_human:
            print("#")
            for item in report.needs_human:
                print(f"#  !! {item['artifact']} / {item.get('platform')}: "
                      f"{item.get('why')}")
                print(f"#     {item.get('check')}")
        print(f"# report: {path}")
        print(f"{'#'*50}")
        return

    # Text mode
    if args.text:
        script = {"type": args.type, "full_script": args.text, "translations": {}}
        run_creation(
            workspace=args.workspace, audience=audience,
            idea=args.name or "supplied text", mode="directed",
            artifact_id=args.name, video_type=args.type, background=args.background,
            supplied_script=script, upload=args.upload,
        )
        return

    # Script mode (use existing script)
    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"Script not found: {script_path}")
            sys.exit(1)

        script_data = load_script(script_path)
        name = args.name or script_path.stem

        # Use script's type unless overridden
        video_type = args.type if args.type != "educational" else script_data.get('type', 'educational')
        run_creation(
            workspace=args.workspace, audience=audience, idea=name, mode="directed",
            artifact_id=name, video_type=video_type, background=args.background,
            supplied_script=script_data, upload=args.upload,
        )
        return

    # Category + Topic mode (generate with GPT)
    if args.category and args.topic:
        run_creation(
            workspace=args.workspace, audience=audience, idea=args.topic,
            mode="directed", category=args.category, topic=args.topic,
            video_type=args.type, background=args.background, upload=args.upload,
        )
        return

    # Random mode (generate with GPT)
    if args.random:
        run_creation(
            workspace=args.workspace, audience=audience, idea="automatic lesson",
            mode="auto", video_type=args.type, background=args.background,
            upload=args.upload,
        )
        return

    # No arguments - show help
    parser.print_help()


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ANSI color helpers
_BOLD = "\033[1m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def clean_output():
    """Delete generated output files with filtering options."""
    parser = argparse.ArgumentParser(
        prog="main.py clean",
        description="Delete generated output files (video, audio, scripts).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without deleting")
    parser.add_argument("--older-than", type=int, default=None, metavar="DAYS",
                        help="Only delete files older than N days")
    parser.add_argument("--pattern", type=str, default=None,
                        help='Only delete files matching glob pattern (e.g. "*.mp4")')
    parser.add_argument("--type", type=str, default="all",
                        choices=["video", "audio", "scripts", "all"],
                        help="Which subfolder to clean (default: all)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show each file being deleted")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args(sys.argv[2:])

    # Determine which subdirectories to scan
    subdirs = ["video", "audio", "scripts"] if args.type == "all" else [args.type]

    now = time.time()
    collected: list[Path] = []

    for sub in subdirs:
        target = OUTPUT_DIR / sub
        if not target.exists():
            continue
        for f in target.rglob("*"):
            if not f.is_file():
                continue
            if args.pattern and not fnmatch.fnmatch(f.name, args.pattern):
                continue
            if args.older_than is not None:
                age_days = (now - f.stat().st_mtime) / 86400
                if age_days < args.older_than:
                    continue
            collected.append(f)

    if not collected:
        print(f"{_GREEN}Nothing to delete.{_RESET}")
        return

    total_size = sum(f.stat().st_size for f in collected)

    # Summary
    print(f"\n{_BOLD}Clean Summary{_RESET}")
    print(f"  {_CYAN}Files:{_RESET}      {len(collected)}")
    print(f"  {_CYAN}Total size:{_RESET} {_human_size(total_size)}")
    print(f"  {_CYAN}Location:{_RESET}   {OUTPUT_DIR}")
    if args.pattern:
        print(f"  {_CYAN}Pattern:{_RESET}    {args.pattern}")
    if args.older_than is not None:
        print(f"  {_CYAN}Older than:{_RESET} {args.older_than} days")
    if args.type != "all":
        print(f"  {_CYAN}Type:{_RESET}       {args.type}")
    print()

    if args.dry_run:
        print(f"{_YELLOW}Dry run -- no files will be deleted.{_RESET}\n")
        for f in sorted(collected):
            sz = _human_size(f.stat().st_size)
            print(f"  {f.relative_to(OUTPUT_DIR)}  ({sz})")
        return

    # Confirmation
    if not args.yes:
        answer = input(f"{_RED}Delete {len(collected)} file(s) ({_human_size(total_size)})? [y/N] {_RESET}")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    deleted = 0
    for f in collected:
        try:
            sz = _human_size(f.stat().st_size)
            f.unlink()
            deleted += 1
            if args.verbose:
                print(f"  {_RED}deleted{_RESET} {f.relative_to(OUTPUT_DIR)}  ({sz})")
        except OSError as e:
            print(f"  {_YELLOW}error{_RESET}   {f.relative_to(OUTPUT_DIR)}: {e}")

    print(f"\n{_GREEN}Deleted {deleted} file(s).{_RESET}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["clean"]:
        clean_output()
    elif sys.argv[1:2] == ["costs"]:
        from cost_tracker import print_report
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print_report(days)
    else:
        main()

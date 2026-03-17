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
import json
import logging
import os
import subprocess
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

# Create base output directories
(OUTPUT_DIR / "scripts").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "audio").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "video").mkdir(parents=True, exist_ok=True)


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
    generate_script,
    get_random_topic,
    get_topic_name,
    find_topic,
    list_categories,
    load_topics,
    save_script,
    VIDEO_TYPES
)


def run_tts(text: str, audio_path: Path, script_data: dict = None, use_openai: bool = True, script_path: Path = None) -> tuple:
    """Run TTS to generate audio and timestamps.

    Args:
        text: Text to convert to speech
        audio_path: Output path for audio file
        script_data: Script metadata to merge into timestamps
        use_openai: Use OpenAI TTS (default: True, more reliable)
        script_path: Path to script JSON (enables automatic English detection)
    """
    from dotenv import load_dotenv
    load_dotenv()

    from tts_providers import get_tts_provider

    logger.info("=" * 50)
    logger.info("STEP 2: Generating Audio (TTS)")
    logger.info("=" * 50)
    logger.info("Output: %s", audio_path)

    # Get TTS provider from environment (default: elevenlabs)
    provider_name = os.getenv("TTS_PROVIDER", "elevenlabs").lower()

    # "openai" flag from legacy callers
    if provider_name not in ("elevenlabs", "google", "openai", "edge"):
        provider_name = "openai" if use_openai else "edge"

    logger.info("Engine: %s", provider_name)

    try:
        provider = get_tts_provider(provider_name)

        if script_data:
            # Primary path: generate from structured script data
            result = provider.generate_from_script(
                script_data, str(audio_path),
                script_path=str(script_path) if script_path else None,
            )
        else:
            # Simple text-only path
            result = provider.generate_audio(text, str(audio_path))

    except Exception as e:
        logger.error("TTS failed (%s): %s", provider_name, e)
        # Fallback to Edge TTS if primary provider fails
        if provider_name != "edge":
            logger.warning("Falling back to Edge TTS...")
            return run_tts(text, audio_path, script_data, use_openai=False)
        return None, None

    # Merge script data with TTS result for video generation
    json_path = audio_path.with_suffix('.json')
    if json_path.exists() and script_data:
        with open(json_path, 'r', encoding='utf-8') as f:
            tts_data = json.load(f)

        # Merge all script_data into TTS data
        for key, value in script_data.items():
            if key not in tts_data or key != 'words':  # Don't overwrite words from TTS
                tts_data[key] = value

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(tts_data, f, ensure_ascii=False, indent=2)

    return audio_path, json_path


def run_video(audio_path: Path, data_path: Path, video_path: Path,
              video_type: str = None, background: str = None) -> Path:
    """Run video generator."""
    cmd = [
        "python3", "-m", "video",
        "-a", str(audio_path),
        "-d", str(data_path),
        "-o", str(video_path)
    ]

    if video_type:
        cmd.extend(["-t", video_type])
    if background:
        cmd.extend(["-b", background])

    logger.info("=" * 50)
    logger.info("STEP 3: Generating Video")
    logger.info("=" * 50)
    logger.info("Type: %s", video_type or 'auto-detect')
    if background:
        logger.info("Background: %s", background)
    logger.info("Output: %s", video_path)

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SRC))

    if result.returncode != 0:
        logger.error("Video generation failed: %s", result.stderr)
        logger.debug("Stdout: %s", result.stdout)
        return None

    logger.debug(result.stdout)
    return video_path


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


def upload_video(video_path: Path, video_type: str, script_data: dict = None, platforms: list = None):
    """Upload a video to configured social platforms."""
    try:
        from uploader import UploadManager, VideoMetadata
        import yaml

        # Load config for hashtags
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
            return

        # Build metadata
        hashtags = upload_config.get("hashtags", {}).get(video_type, "#LearnEnglish #English")
        title = ""
        if script_data:
            title = (script_data.get("hook", "") or
                     script_data.get("question", "") or
                     script_data.get("statement", "") or
                     script_data.get("title", "Learn English"))

        description = f"{title}\n\n{hashtags}"

        metadata = VideoMetadata(
            title=title[:100] if title else "Learn English",
            description=description,
            hashtags=hashtags.replace("#", "").split(),
            privacy="public",
        )

        manager = UploadManager()
        results = manager.upload_all(
            str(video_path),
            title=metadata.title,
            description=metadata.description,
            hashtags=metadata.hashtags,
            platforms=platforms,
        )

        for result in results:
            if result.success:
                logger.info("Uploaded to %s: %s", result.platform, result.url or result.upload_id)
            else:
                logger.error("Upload to %s failed: %s", result.platform, result.error)

    except ImportError as e:
        logger.error("Upload module not available: %s", e)
    except Exception as e:
        logger.error("Upload failed: %s", e)


def run_pipeline(script_data: dict, output_name: str, video_type: str = None, background: str = None, upload: bool = False) -> Path:
    """Run the full pipeline from script to video."""

    # Initialize cost tracker for this video
    try:
        from cost_tracker import reset_tracker
        tracker = reset_tracker(video_id=output_name)
    except ImportError:
        tracker = None

    # Determine video type from script data if not provided
    if video_type is None:
        video_type = script_data.get('type', 'educational')

    # Get organized output paths
    script_path, audio_path, tts_json_path, video_path = get_output_paths(video_type, output_name)

    # Extract text for TTS
    full_script = script_data.get('full_script', '')
    if not full_script:
        logger.error("Script has no 'full_script' field")
        return None

    # Save script first so TTS can use automatic English detection
    with open(script_path, 'w', encoding='utf-8') as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    logger.info("Script saved: %s", script_path.relative_to(ROOT))

    # Step 2: TTS (pass script_path for automatic English detection)
    audio_result, json_path = run_tts(full_script, audio_path, script_data, script_path=script_path)
    if not audio_result or not audio_result.exists():
        logger.error("TTS failed!")
        return None

    # Step 3: Video
    video_result = run_video(audio_result, json_path, video_path, video_type, background)
    if not video_result or not video_result.exists():
        logger.error("Video generation failed!")
        return None

    logger.info("=" * 50)
    logger.info("PIPELINE COMPLETE!")
    logger.info("=" * 50)
    logger.info("Type: %s", video_type)
    logger.info("Script: %s", script_path.relative_to(ROOT))
    logger.info("Audio: %s", audio_result.relative_to(ROOT))
    logger.info("Video: %s", video_result.relative_to(ROOT))

    # Print and save cost report
    if tracker and tracker.entries:
        tracker.print_summary()
        tracker.save()

    logger.info("=" * 50)

    # Step 4: Upload (if requested)
    if upload and video_result:
        logger.info("STEP 4: Uploading to social platforms...")
        upload_video(video_result, video_type, script_data)

    return video_result


def run_from_text(text: str, name: str = None, video_type: str = "educational", background: str = None, upload: bool = False) -> Path:
    """Run pipeline directly from text input."""
    if not name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"quick_{timestamp}"

    # Create a simple script structure
    script_data = {
        "type": video_type,
        "full_script": text,
        "translations": {}
    }

    return run_pipeline(script_data, name, video_type, background, upload=upload)


def generate_and_run(category: str, topic: dict, topic_name: str, video_type: str = "educational", background: str = None, upload: bool = False) -> Path:
    """Generate a script with GPT and run the full pipeline."""

    logger.info("=" * 50)
    logger.info("STEP 1: Generating Script (GPT)")
    logger.info("=" * 50)
    logger.info("Category: %s", category)
    logger.info("Topic: %s", topic_name)
    logger.info("Video Type: %s", video_type)

    try:
        script_data = generate_script(category, topic, video_type)
    except Exception as e:
        logger.error("Script generation failed: %s", e)
        return None

    # Output name for pipeline
    output_name = topic_name.replace(' ', '_').lower()

    # Show preview based on type
    logger.info("Script Preview:")
    if video_type == "educational":
        logger.info("  Hook: %s", script_data.get('hook', 'N/A'))
    elif video_type == "quiz":
        logger.info("  Question: %s", script_data.get('question', 'N/A'))
        logger.info("  Options: %s", script_data.get('options', {}))
    elif video_type == "true_false":
        logger.info("  Statement: %s", script_data.get('statement', 'N/A'))
        logger.info("  Correct: %s", script_data.get('correct', 'N/A'))
    elif video_type == "fill_blank":
        logger.info("  Sentence: %s", script_data.get('sentence', 'N/A'))
        logger.info("  Correct: %s", script_data.get('correct', 'N/A'))
    elif video_type == "pronunciation":
        logger.info("  Word: %s", script_data.get('word', 'N/A'))
        logger.info("  Phonetic: %s", script_data.get('phonetic', 'N/A'))
    elif video_type == "vocabulary":
        logger.info("  Title: %s", script_data.get('title', 'N/A'))
        logger.info("  Difficulty: %s", script_data.get('difficulty', 'N/A'))
        logger.info("  Pairs: %d", len(script_data.get('pairs', [])))

    logger.info("  Script: %s...", script_data.get('full_script', 'N/A')[:100])

    # Run rest of pipeline
    return run_pipeline(script_data, output_name, video_type, background, upload=upload)


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
    parser.add_argument("--batch", "-b", type=int,
                        help="Generate multiple videos from random topics")
    parser.add_argument("--upload", "-u", action="store_true",
                        help="Upload video to configured platforms after generation")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose/debug logging")

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

    # Batch mode
    if args.batch:
        print(f"\nBatch mode: Generating {args.batch} {args.type} videos")
        for i in range(args.batch):
            print(f"\n{'#'*50}")
            print(f"# VIDEO {i+1} of {args.batch} [{args.type}]")
            print(f"{'#'*50}")

            category, topic = get_random_topic()
            topic_name = get_topic_name(topic)
            generate_and_run(category, topic, topic_name, args.type, args.background, upload=args.upload)
        return

    # Text mode
    if args.text:
        name = args.name or None
        run_from_text(args.text, name, args.type, args.background, upload=args.upload)
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
        run_pipeline(script_data, name, video_type, args.background, upload=args.upload)
        return

    # Category + Topic mode (generate with GPT)
    if args.category and args.topic:
        topic = find_topic(args.category, args.topic)
        generate_and_run(args.category, topic, args.topic, args.type, args.background, upload=args.upload)
        return

    # Random mode (generate with GPT)
    if args.random:
        category, topic = get_random_topic()
        topic_name = get_topic_name(topic)
        generate_and_run(category, topic, topic_name, args.type, args.background, upload=args.upload)
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
        from src.cost_tracker import print_report
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print_report(days)
    else:
        main()

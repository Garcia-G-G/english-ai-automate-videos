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
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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

# Import script generator functions
sys.path.insert(0, str(SRC))
from script_generator import (
    generate_script,
    get_random_topic,
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
    print(f"\n{'='*50}")
    print("STEP 2: Generating Audio (TTS)")
    print(f"{'='*50}")
    print(f"Output: {audio_path}")

    if use_openai:
        # Use OpenAI TTS (more reliable, better bilingual flow)
        # If we have a script path, use --script for automatic English detection
        if script_path and script_path.exists():
            cmd = [
                "python3", str(SRC / "tts_openai.py"),
                "--script", str(script_path),
                "-o", str(audio_path),
            ]
            print("Engine: OpenAI TTS + Whisper (auto English detection)")
        else:
            cmd = [
                "python3", str(SRC / "tts_openai.py"),
                text,
                "-o", str(audio_path),
            ]
            print("Engine: OpenAI TTS + Whisper")
    else:
        # Use Edge TTS (free, but can be unreliable)
        cmd = [
            "python3", str(SRC / "tts.py"),
            text,
            "-o", str(audio_path),
            "--mode", "hybrid",
            "--rate", "+15%"
        ]
        print("Engine: Edge TTS (hybrid mode)")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"TTS Error: {result.stderr}")
        # Fallback to Edge TTS if OpenAI fails
        if use_openai:
            print("Falling back to Edge TTS...")
            return run_tts(text, audio_path, script_data, use_openai=False)
        return None, None

    print(result.stdout)

    # Merge script data with TTS timestamps for video generation
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


def run_video(audio_path: Path, data_path: Path, video_path: Path, video_type: str = None) -> Path:
    """Run video generator."""
    cmd = [
        "python3", str(SRC / "video.py"),
        "-a", str(audio_path),
        "-d", str(data_path),
        "-o", str(video_path)
    ]

    if video_type:
        cmd.extend(["-t", video_type])

    print(f"\n{'='*50}")
    print("STEP 3: Generating Video")
    print(f"{'='*50}")
    print(f"Type: {video_type or 'auto-detect'}")
    print(f"Output: {video_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Video Error: {result.stderr}")
        print(f"Stdout: {result.stdout}")
        return None

    print(result.stdout)
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
        print("No scripts found in output/scripts/")
        return

    print("\nAvailable Scripts:")
    print("=" * 50)

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
        print(f"\n  [{vtype}]")
        for s, data in by_type[vtype]:
            hook = data.get('hook', data.get('question', data.get('statement', 'No preview')))[:35]
            rel_path = s.relative_to(scripts_dir)
            print(f"    {rel_path}: {hook}...")


def run_pipeline(script_data: dict, output_name: str, video_type: str = None) -> Path:
    """Run the full pipeline from script to video."""

    # Determine video type from script data if not provided
    if video_type is None:
        video_type = script_data.get('type', 'educational')

    # Get organized output paths
    script_path, audio_path, tts_json_path, video_path = get_output_paths(video_type, output_name)

    # Extract text for TTS
    full_script = script_data.get('full_script', '')
    if not full_script:
        print("Error: Script has no 'full_script' field")
        return None

    # Save script first so TTS can use automatic English detection
    with open(script_path, 'w', encoding='utf-8') as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    print(f"Script saved: {script_path.relative_to(ROOT)}")

    # Step 2: TTS (pass script_path for automatic English detection)
    audio_result, json_path = run_tts(full_script, audio_path, script_data, script_path=script_path)
    if not audio_result or not audio_result.exists():
        print("TTS failed!")
        return None

    # Step 3: Video
    video_result = run_video(audio_result, json_path, video_path, video_type)
    if not video_result or not video_result.exists():
        print("Video generation failed!")
        return None

    print(f"\n{'='*50}")
    print("PIPELINE COMPLETE!")
    print(f"{'='*50}")
    print(f"Type: {video_type}")
    print(f"Script: {script_path.relative_to(ROOT)}")
    print(f"Audio: {audio_result.relative_to(ROOT)}")
    print(f"Video: {video_result.relative_to(ROOT)}")
    print(f"{'='*50}")

    return video_result


def run_from_text(text: str, name: str = None, video_type: str = "educational") -> Path:
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

    return run_pipeline(script_data, name, video_type)


def generate_and_run(category: str, topic: dict, topic_name: str, video_type: str = "educational") -> Path:
    """Generate a script with GPT and run the full pipeline."""

    print(f"\n{'='*50}")
    print("STEP 1: Generating Script (GPT)")
    print(f"{'='*50}")
    print(f"Category: {category}")
    print(f"Topic: {topic_name}")
    print(f"Video Type: {video_type}")

    try:
        script_data = generate_script(category, topic, video_type)
    except Exception as e:
        print(f"Script generation failed: {e}")
        return None

    # Output name for pipeline
    output_name = topic_name.replace(' ', '_').lower()

    # Show preview based on type
    print(f"\nScript Preview:")
    if video_type == "educational":
        print(f"  Hook: {script_data.get('hook', 'N/A')}")
    elif video_type == "quiz":
        print(f"  Question: {script_data.get('question', 'N/A')}")
        print(f"  Options: {script_data.get('options', {})}")
    elif video_type == "true_false":
        print(f"  Statement: {script_data.get('statement', 'N/A')}")
        print(f"  Correct: {script_data.get('correct', 'N/A')}")
    elif video_type == "fill_blank":
        print(f"  Sentence: {script_data.get('sentence', 'N/A')}")
        print(f"  Correct: {script_data.get('correct', 'N/A')}")
    elif video_type == "pronunciation":
        print(f"  Word: {script_data.get('word', 'N/A')}")
        print(f"  Phonetic: {script_data.get('phonetic', 'N/A')}")

    print(f"  Script: {script_data.get('full_script', 'N/A')[:100]}...")

    # Run rest of pipeline
    return run_pipeline(script_data, output_name, video_type)


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
    parser.add_argument("--batch", "-b", type=int,
                        help="Generate multiple videos from random topics")

    args = parser.parse_args()

    # List scripts mode
    if args.list_scripts:
        list_scripts()
        return

    # List topics mode
    if args.list_topics:
        print("\nAvailable Categories and Topics:")
        print("=" * 50)
        for cat in list_categories():
            topics = load_topics(cat)
            print(f"\n{cat} ({len(topics)} topics):")
            for t in topics:
                name = t.get("english") or t.get("topic") or t.get("wrong")
                print(f"  - {name}")
        print(f"\nVideo Types: {', '.join(VIDEO_TYPES)}")
        return

    # Batch mode
    if args.batch:
        print(f"\nBatch mode: Generating {args.batch} {args.type} videos")
        for i in range(args.batch):
            print(f"\n{'#'*50}")
            print(f"# VIDEO {i+1} of {args.batch} [{args.type}]")
            print(f"{'#'*50}")

            category, topic = get_random_topic()
            topic_name = topic.get("english") or topic.get("topic") or topic.get("wrong")
            generate_and_run(category, topic, topic_name, args.type)
        return

    # Text mode
    if args.text:
        name = args.name or None
        run_from_text(args.text, name, args.type)
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
        run_pipeline(script_data, name, video_type)
        return

    # Category + Topic mode (generate with GPT)
    if args.category and args.topic:
        topic = find_topic(args.category, args.topic)
        generate_and_run(args.category, topic, args.topic, args.type)
        return

    # Random mode (generate with GPT)
    if args.random:
        category, topic = get_random_topic()
        topic_name = topic.get("english") or topic.get("topic") or topic.get("wrong")
        generate_and_run(category, topic, topic_name, args.type)
        return

    # No arguments - show help
    parser.print_help()


if __name__ == "__main__":
    main()

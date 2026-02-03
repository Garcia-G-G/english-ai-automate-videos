#!/usr/bin/env python3
"""
TTS Module for English AI Video Generator
Uses edge-tts to convert Spanish text (teaching English) to natural-sounding speech.
Optimized for Spanish speakers learning English - content is in Spanish with English words highlighted.

Example: "¿Sabías que 'embarrassed' NO significa 'embarazada'?"

Supports multiple approaches for better English pronunciation:
1. SSML mode: Add pauses and slow down English words with prosody tags
2. Multilingual voices: Use voices that handle code-switching better
3. Hybrid mode: Use Spanish voice for Spanish, English voice for English words, then merge
"""

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import tempfile
from io import BytesIO

logger = logging.getLogger(__name__)

import edge_tts

# Default voice: Mexican Spanish for Spanish content with English words
# Rate increased for more energetic, natural teacher style
DEFAULT_VOICE = "es-MX-JorgeNeural"
DEFAULT_RATE = "+15%"  # Faster = more energetic
DEFAULT_ENGLISH_VOICE = "en-US-AndrewMultilingualNeural"  # For hybrid mode - best for bilingual flow

# English voices for hybrid mode (native English pronunciation)
ENGLISH_VOICES = {
    "en-US-GuyNeural": "US English male - Clear, natural (recommended for English words)",
    "en-US-JennyNeural": "US English female - Friendly",
    "en-GB-RyanNeural": "British English male - Professional",
    "en-US-AndrewMultilingualNeural": "US English male - Multilingual (handles Spanish context)",
}

RECOMMENDED_VOICES = {
    "es-MX-JorgeNeural": "Mexican Spanish male - Main teacher voice (recommended)",
    "es-MX-DaliaNeural": "Mexican Spanish female - Alternative teacher",
    "es-ES-AlvaroNeural": "Spain Spanish male - European Spanish",
    "es-AR-TomasNeural": "Argentine Spanish male - Southern cone accent",
}

# Pause durations around English words (0 = no artificial pause, let voices switch naturally)
PAUSE_BEFORE_ENGLISH = "0ms"
PAUSE_AFTER_ENGLISH = "0ms"
ENGLISH_RATE = "slow"  # slow, x-slow, medium


async def list_voices(language_filter: str = None) -> list:
    """List all available voices, optionally filtered by language."""
    voices = await edge_tts.list_voices()
    if language_filter:
        voices = [v for v in voices if v["Locale"].startswith(language_filter)]
    return voices


def extract_english_words(text: str) -> list:
    """
    Extract English words from text. English words are marked with:
    - Single quotes: 'embarrassed'
    - Double quotes: "embarrassed"
    - Square brackets with [EN]: [EN]embarrassed[/EN]

    Returns list of tuples: (full_match, english_word, start_pos, end_pos)
    """
    patterns = [
        r"'([^']+)'",  # Single quotes
        r'"([^"]+)"',  # Double quotes
        r'\[EN\]([^\[]+)\[/EN\]',  # Explicit EN tags
    ]

    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            matches.append((
                match.group(0),  # Full match including quotes
                match.group(1),  # Just the word
                match.start(),
                match.end()
            ))

    # Sort by position
    matches.sort(key=lambda x: x[2])
    return matches


def text_to_ssml(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pause_before: str = PAUSE_BEFORE_ENGLISH,
    pause_after: str = PAUSE_AFTER_ENGLISH,
    english_rate: str = ENGLISH_RATE,
) -> str:
    """
    Convert text with English words to SSML with pauses and prosody.

    English words (in quotes) get:
    - Pause before
    - Slower rate with lang="en-US"
    - Pause after

    Example output:
    <speak>
        <voice name="es-MX-JorgeNeural">
            ¿Sabías que
            <break time="300ms"/>
            <prosody rate="slow"><lang xml:lang="en-US">embarrassed</lang></prosody>
            <break time="300ms"/>
            NO significa embarazada?
        </voice>
    </speak>
    """
    english_words = extract_english_words(text)

    if not english_words:
        # No English words, simple SSML
        return f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">
    <voice name="{voice}">
        <prosody rate="{rate}">{text}</prosody>
    </voice>
</speak>'''

    # Build SSML with English word handling
    result_parts = []
    last_end = 0

    for full_match, english_word, start, end in english_words:
        # Add Spanish text before this English word
        if start > last_end:
            spanish_part = text[last_end:start]
            result_parts.append(spanish_part)

        # Add pause before English word
        result_parts.append(f'<break time="{pause_before}"/>')

        # Add English word with slow rate and English language tag
        result_parts.append(
            f'<prosody rate="{english_rate}"><lang xml:lang="en-US">{english_word}</lang></prosody>'
        )

        # Add pause after English word
        result_parts.append(f'<break time="{pause_after}"/>')

        last_end = end

    # Add remaining Spanish text
    if last_end < len(text):
        result_parts.append(text[last_end:])

    content = ''.join(result_parts)

    return f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">
    <voice name="{voice}">
        <prosody rate="{rate}">{content}</prosody>
    </voice>
</speak>'''


def text_to_ssml_say_as(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> str:
    """
    Alternative SSML approach using say-as for English pronunciation.
    Uses IPA phonemes for better control over English pronunciation.
    """
    english_words = extract_english_words(text)

    if not english_words:
        return f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">
    <voice name="{voice}">
        <prosody rate="{rate}">{text}</prosody>
    </voice>
</speak>'''

    result_parts = []
    last_end = 0

    for full_match, english_word, start, end in english_words:
        if start > last_end:
            result_parts.append(text[last_end:start])

        # Use mstts:express-as for emphasis and lang switch
        result_parts.append(f'''<break time="400ms"/><mstts:silence type="Leading" value="200ms"/><lang xml:lang="en-US"><prosody rate="slow" pitch="-2%">{english_word}</prosody></lang><mstts:silence type="Tailing" value="200ms"/><break time="400ms"/>''')

        last_end = end

    if last_end < len(text):
        result_parts.append(text[last_end:])

    content = ''.join(result_parts)

    return f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="es-MX">
    <voice name="{voice}">
        <prosody rate="{rate}">{content}</prosody>
    </voice>
</speak>'''


def create_ssml_text_with_pauses(
    text: str,
    pause_before: str = PAUSE_BEFORE_ENGLISH,
    pause_after: str = PAUSE_AFTER_ENGLISH,
) -> str:
    """
    Create text with embedded pauses around English words.
    Uses simple ellipsis pauses since edge-tts doesn't support full SSML in text.
    """
    english_words = extract_english_words(text)

    if not english_words:
        return text

    result_parts = []
    last_end = 0

    for full_match, english_word, start, end in english_words:
        if start > last_end:
            result_parts.append(text[last_end:start])

        # Add pauses using punctuation (edge-tts responds to punctuation)
        # Triple dot creates a natural pause
        result_parts.append(f"... {english_word} ...")

        last_end = end

    if last_end < len(text):
        result_parts.append(text[last_end:])

    return ''.join(result_parts)


async def text_to_speech_ssml(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pause_before: str = PAUSE_BEFORE_ENGLISH,
    pause_after: str = PAUSE_AFTER_ENGLISH,
    english_rate: str = ENGLISH_RATE,
) -> dict:
    """
    Convert text to speech with pauses around English words.
    Uses punctuation-based pauses since edge-tts has limited SSML support.

    For the slow rate, we generate English words separately at a slower rate.
    """
    english_words = extract_english_words(text)

    if not english_words:
        return await text_to_speech(text, output_path, voice, rate)

    # For true SSML with slow English, we need to generate segments
    # edge-tts doesn't support inline prosody changes, so we use hybrid-like approach
    try:
        from pydub import AudioSegment
    except ImportError:
        # Fallback: just add pauses via punctuation
        paused_text = create_ssml_text_with_pauses(text, pause_before, pause_after)
        return await text_to_speech(paused_text, output_path, voice, rate)

    # Split into segments
    segments = []
    last_end = 0

    for full_match, english_word, start, end in english_words:
        if start > last_end:
            spanish_part = text[last_end:start].strip()
            if spanish_part:
                segments.append(("spanish", spanish_part))

        segments.append(("english", english_word))
        last_end = end

    if last_end < len(text):
        spanish_part = text[last_end:].strip()
        if spanish_part:
            segments.append(("spanish", spanish_part))

    # Generate audio for each segment
    combined = AudioSegment.silent(duration=0)
    pause_ms = int(pause_before.replace("ms", ""))

    # Rate mapping for English
    english_rate_map = {
        "x-slow": "-30%",
        "slow": "-15%",
        "medium": "+0%",
    }
    eng_rate = english_rate_map.get(english_rate, "-15%")

    for lang, segment_text in segments:
        if lang == "spanish":
            audio_bytes = await generate_audio_segment(segment_text, voice, rate)
        else:
            # Add pause before English
            combined += AudioSegment.silent(duration=pause_ms)
            # Generate English word with same Spanish voice but slower
            audio_bytes = await generate_audio_segment(segment_text, voice, eng_rate)

        audio_segment = AudioSegment.from_mp3(BytesIO(audio_bytes))
        combined += audio_segment

        if lang == "english":
            combined += AudioSegment.silent(duration=pause_ms)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    combined.export(output_path, format="mp3")

    total_duration = len(combined) / 1000.0
    timestamps = {
        "duration": round(total_duration, 3),
        "words": [],
        "mode": "ssml_with_pauses"
    }

    json_path = output_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2, ensure_ascii=False)

    return timestamps


async def generate_audio_segment(text: str, voice: str, rate: str = "+0%") -> bytes:
    """Generate audio for a text segment with specified voice."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


async def generate_audio_segment_with_timestamps(
    text: str, voice: str, rate: str = "+0%", is_english: bool = False
) -> tuple:
    """Generate audio for a text segment with word timestamps."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary='WordBoundary')
    audio_data = b""
    words = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
        elif chunk["type"] == "WordBoundary":
            start = chunk["offset"] / 10_000_000
            duration = chunk["duration"] / 10_000_000
            words.append({
                "word": chunk["text"],
                "start": start,
                "duration": duration,
                "is_english": is_english
            })

    return audio_data, words


async def text_to_speech_hybrid(
    text: str,
    output_path: str,
    spanish_voice: str = DEFAULT_VOICE,
    english_voice: str = DEFAULT_ENGLISH_VOICE,
    spanish_rate: str = DEFAULT_RATE,
    english_rate: str = "+10%",  # Match Spanish pace for seamless flow
    pause_before_ms: int = None,  # Use default if None
    pause_after_ms: int = None,   # Use default if None
) -> dict:
    """
    Hybrid approach: Use Spanish voice for Spanish, English voice for English words.
    Generates separate audio segments and merges them.

    Like a real bilingual teacher: Spanish flows naturally, brief pause,
    clear English word, brief pause, continue Spanish.

    Requires pydub for audio merging.
    """
    # Use defaults from constants if not specified
    if pause_before_ms is None:
        pause_before_ms = int(PAUSE_BEFORE_ENGLISH.replace("ms", ""))
    if pause_after_ms is None:
        pause_after_ms = int(PAUSE_AFTER_ENGLISH.replace("ms", ""))
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub required for hybrid mode. Install with: pip install pydub")

    english_words = extract_english_words(text)

    if not english_words:
        # No English words, use standard approach
        return await text_to_speech(text, output_path, spanish_voice, spanish_rate)

    # Split text into segments
    segments = []
    last_end = 0

    for full_match, english_word, start, end in english_words:
        # Spanish segment before English word
        if start > last_end:
            spanish_part = text[last_end:start].strip()
            if spanish_part:
                segments.append(("spanish", spanish_part))

        # English word
        segments.append(("english", english_word))
        last_end = end

    # Remaining Spanish text
    if last_end < len(text):
        spanish_part = text[last_end:].strip()
        if spanish_part:
            segments.append(("spanish", spanish_part))

    # Generate audio for each segment with timestamps
    combined = AudioSegment.silent(duration=0)
    all_words = []
    current_time = 0.0  # Track cumulative time in seconds

    for lang, segment_text in segments:
        is_english = (lang == "english")

        if is_english and pause_before_ms > 0:
            combined += AudioSegment.silent(duration=pause_before_ms)
            current_time += pause_before_ms / 1000.0

        # Generate audio with word timestamps
        audio_bytes, segment_words = await generate_audio_segment_with_timestamps(
            segment_text,
            english_voice if is_english else spanish_voice,
            english_rate if is_english else spanish_rate,
            is_english=is_english
        )

        # Add audio segment
        audio_segment = AudioSegment.from_mp3(BytesIO(audio_bytes))

        # Only trim English segments (Spanish segments contain intentional pauses from "...")
        if is_english:
            # Trim leading/trailing silence for seamless English word transitions
            def detect_silence_ms(sound, silence_threshold=-40.0, chunk_size=10):
                """Detect milliseconds of silence at start of audio."""
                trim_ms = 0
                while trim_ms < len(sound):
                    if sound[trim_ms:trim_ms+chunk_size].dBFS > silence_threshold:
                        break
                    trim_ms += chunk_size
                return trim_ms

            # Trim leading silence (keep just 30ms for natural breath)
            lead_silence = detect_silence_ms(audio_segment)
            if lead_silence > 50:
                audio_segment = audio_segment[lead_silence - 30:]

            # Trim trailing silence (keep just 30ms)
            reversed_seg = audio_segment.reverse()
            trail_silence = detect_silence_ms(reversed_seg)
            if trail_silence > 50:
                audio_segment = audio_segment[:-trail_silence + 30]

        # Adjust word timestamps by current offset
        for word in segment_words:
            all_words.append({
                "word": word["word"],
                "start": round(current_time + word["start"], 3),
                "end": round(current_time + word["start"] + word["duration"], 3),
                "is_english": word["is_english"]
            })

        combined += audio_segment
        current_time += len(audio_segment) / 1000.0

        if is_english and pause_after_ms > 0:
            combined += AudioSegment.silent(duration=pause_after_ms)
            current_time += pause_after_ms / 1000.0

    # Export combined audio
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    combined.export(output_path, format="mp3")

    total_duration = len(combined) / 1000.0
    timestamps = {
        "duration": round(total_duration, 3),
        "words": all_words,
        "segments": [{"lang": lang, "text": text} for lang, text in segments]
    }

    json_path = output_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2, ensure_ascii=False)

    return timestamps


async def text_to_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> dict:
    """
    Convert text to speech and generate word-level timestamps.

    Args:
        text: The text to convert (Spanish with English words)
        output_path: Path to save the MP3 file
        voice: Voice ID to use
        rate: Speech rate adjustment (e.g., "+15%", "-5%")

    Returns:
        Dictionary with duration and word timestamps
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary='WordBoundary')

    words = []
    audio_data = b""

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
        elif chunk["type"] == "WordBoundary":
            # Convert from 100-nanosecond units to seconds
            start = chunk["offset"] / 10_000_000
            duration = chunk["duration"] / 10_000_000
            end = start + duration

            words.append({
                "word": chunk["text"],
                "start": round(start, 3),
                "end": round(end, 3)
            })

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Save audio file
    with open(output_path, "wb") as f:
        f.write(audio_data)

    # Calculate total duration from last word
    total_duration = words[-1]["end"] if words else 0.0

    # Prepare timestamps data
    timestamps = {
        "duration": round(total_duration, 3),
        "words": words
    }

    # Save timestamps JSON
    json_path = output_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2, ensure_ascii=False)

    return timestamps


def read_text_from_file(file_path: str) -> str:
    """Read text content from a file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


async def main():
    parser = argparse.ArgumentParser(
        description="Convert Spanish text (teaching English) to speech with word-level timestamps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard mode (Spanish voice for everything)
  python src/tts.py "¿Sabías que 'embarrassed' NO significa 'embarazada'?" -o output.mp3

  # SSML mode - adds pauses and slows down English words
  python src/tts.py "¿Sabías que 'embarrassed' NO significa 'embarazada'?" -o output.mp3 --mode ssml

  # Multilingual voice - better code-switching
  python src/tts.py "¿Sabías que 'embarrassed' NO significa 'embarazada'?" -o output.mp3 --voice es-ES-ArabellaMultilingualNeural

  # Hybrid mode - Spanish voice for Spanish, English voice for English words
  python src/tts.py "¿Sabías que 'embarrassed' NO significa 'embarazada'?" -o output.mp3 --mode hybrid

  # Test all modes at once
  python src/tts.py "¿Sabías que 'embarrassed' NO significa 'embarazada'?" --test-all

  python src/tts.py --list-voices --language es
  python src/tts.py --recommended
        """
    )

    parser.add_argument(
        "text",
        nargs="?",
        help="Text to convert to speech (English words in 'quotes')"
    )
    parser.add_argument(
        "-o", "--output",
        default="output/audio/output.mp3",
        help="Output MP3 file path (default: output/audio/output.mp3)"
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"Voice to use (default: {DEFAULT_VOICE})"
    )
    parser.add_argument(
        "--rate",
        default=DEFAULT_RATE,
        help=f"Speech rate adjustment (default: {DEFAULT_RATE})"
    )
    parser.add_argument(
        "--mode",
        choices=["standard", "ssml", "hybrid"],
        default="standard",
        help="TTS mode: standard (default), ssml (pauses+slow English), hybrid (separate voices)"
    )
    parser.add_argument(
        "--english-voice",
        default=DEFAULT_ENGLISH_VOICE,
        help=f"English voice for hybrid mode (default: {DEFAULT_ENGLISH_VOICE})"
    )
    parser.add_argument(
        "--pause-before",
        default=PAUSE_BEFORE_ENGLISH,
        help=f"Pause before English words in SSML mode (default: {PAUSE_BEFORE_ENGLISH})"
    )
    parser.add_argument(
        "--pause-after",
        default=PAUSE_AFTER_ENGLISH,
        help=f"Pause after English words in SSML mode (default: {PAUSE_AFTER_ENGLISH})"
    )
    parser.add_argument(
        "--english-rate",
        default=ENGLISH_RATE,
        help=f"Rate for English words: slow, x-slow, medium (default: {ENGLISH_RATE})"
    )
    parser.add_argument(
        "--test-all",
        action="store_true",
        help="Generate audio with all modes for comparison"
    )
    parser.add_argument(
        "--file", "-f",
        help="Read text from file instead of command line"
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List all available voices"
    )
    parser.add_argument(
        "--language",
        help="Filter voices by language code (e.g., 'es', 'en')"
    )
    parser.add_argument(
        "--recommended",
        action="store_true",
        help="Show recommended voices for this project"
    )

    args = parser.parse_args()

    # Show recommended voices
    if args.recommended:
        print("\nRecommended voices for Spanish teaching English:\n")
        print(f"{'Voice ID':<25} {'Description':<50}")
        print("-" * 75)
        for voice_id, desc in RECOMMENDED_VOICES.items():
            print(f"{voice_id:<25} {desc:<50}")
        print()
        return

    # List voices
    if args.list_voices:
        voices = await list_voices(args.language)
        print(f"\nAvailable voices{f' (language: {args.language})' if args.language else ''}:\n")
        print(f"{'Voice ID':<30} {'Gender':<10} {'Language':<15}")
        print("-" * 55)
        for voice in voices:
            print(f"{voice['ShortName']:<30} {voice['Gender']:<10} {voice['Locale']:<15}")
        print(f"\nTotal: {len(voices)} voices")
        return

    # Get text to convert
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text = read_text_from_file(args.file)
    elif args.text:
        text = args.text
    else:
        parser.error("Either text argument or --file is required")

    if not text:
        print("Error: No text provided", file=sys.stderr)
        sys.exit(1)

    # Test all modes for comparison
    if args.test_all:
        await test_all_modes(text, args.output)
        return

    print(f"Converting text to speech...")
    print(f"  Mode: {args.mode}")
    print(f"  Voice: {args.voice}")
    print(f"  Rate: {args.rate}")
    print(f"  Output: {args.output}")

    try:
        if args.mode == "ssml":
            print(f"  Pause before English: {args.pause_before}")
            print(f"  Pause after English: {args.pause_after}")
            print(f"  English rate: {args.english_rate}")
            timestamps = await text_to_speech_ssml(
                text, args.output, args.voice, args.rate,
                args.pause_before, args.pause_after, args.english_rate
            )
        elif args.mode == "hybrid":
            print(f"  English voice: {args.english_voice}")
            print(f"  Pause before/after: {args.pause_before}/{args.pause_after}")
            pause_before_ms = int(args.pause_before.replace("ms", ""))
            pause_after_ms = int(args.pause_after.replace("ms", ""))
            timestamps = await text_to_speech_hybrid(
                text, args.output, args.voice, args.english_voice, args.rate,
                pause_before_ms=pause_before_ms, pause_after_ms=pause_after_ms
            )
        else:
            timestamps = await text_to_speech(text, args.output, args.voice, args.rate)

        json_path = args.output.rsplit(".", 1)[0] + ".json"
        print(f"\n¡Éxito!")
        print(f"  Audio: {args.output}")
        print(f"  Timestamps: {json_path}")
        print(f"  Duration: {timestamps['duration']:.2f} seconds")
        if timestamps.get('words'):
            print(f"  Words: {len(timestamps['words'])}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_all_modes(text: str, base_output: str):
    """Test all TTS modes and voices for comparison."""
    output_dir = os.path.dirname(base_output) or "output/audio"
    os.makedirs(output_dir, exist_ok=True)

    test_configs = [
        # (name, mode, voice, extra_args)
        ("1_standard_jorge", "standard", "es-MX-JorgeNeural", {}),
        ("2_ssml_jorge_pauses", "ssml", "es-MX-JorgeNeural", {}),
        ("3_ssml_jorge_xslow", "ssml", "es-MX-JorgeNeural", {"english_rate": "x-slow"}),
        ("4_hybrid_jorge_guy", "hybrid", "es-MX-JorgeNeural", {"english_voice": "en-US-GuyNeural"}),
        ("5_hybrid_jorge_andrew", "hybrid", "es-MX-JorgeNeural", {"english_voice": "en-US-AndrewMultilingualNeural"}),
        ("6_standard_alvaro", "standard", "es-ES-AlvaroNeural", {}),
        ("7_hybrid_alvaro_ryan", "hybrid", "es-ES-AlvaroNeural", {"english_voice": "en-GB-RyanNeural"}),
    ]

    print(f"\nTesting all modes with text: {text}\n")
    print("=" * 60)

    for name, mode, voice, extra in test_configs:
        output_path = os.path.join(output_dir, f"test_{name}.mp3")
        print(f"\n[{name}]")
        print(f"  Mode: {mode}, Voice: {voice}")

        try:
            if mode == "ssml":
                english_rate = extra.get("english_rate", ENGLISH_RATE)
                timestamps = await text_to_speech_ssml(
                    text, output_path, voice, DEFAULT_RATE,
                    PAUSE_BEFORE_ENGLISH, PAUSE_AFTER_ENGLISH, english_rate
                )
            elif mode == "hybrid":
                english_voice = extra.get("english_voice", DEFAULT_ENGLISH_VOICE)
                timestamps = await text_to_speech_hybrid(
                    text, output_path, voice, english_voice, DEFAULT_RATE
                )
            else:
                timestamps = await text_to_speech(text, output_path, voice, DEFAULT_RATE)

            print(f"  Output: {output_path}")
            print(f"  Duration: {timestamps['duration']:.2f}s")
            print(f"  Status: SUCCESS")

        except Exception as e:
            print(f"  Status: FAILED - {e}")

    print("\n" + "=" * 60)
    print(f"\nAll test files saved to: {output_dir}/")
    print("Listen to each file and compare English pronunciation!")
    print("\nRecommended order (best English pronunciation first):")
    print("  1. test_4_hybrid_jorge_guy.mp3 - Native English voice for 'embarrassed'")
    print("  2. test_5_hybrid_jorge_andrew.mp3 - Multilingual English voice")
    print("  3. test_3_ssml_jorge_xslow.mp3 - Same voice, slower English words")
    print("  4. test_1_standard_jorge.mp3 - Original (for comparison)")


if __name__ == "__main__":
    asyncio.run(main())

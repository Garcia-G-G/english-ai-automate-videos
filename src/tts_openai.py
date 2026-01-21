#!/usr/bin/env python3
"""
OpenAI TTS Module for English AI Video Generator
Uses OpenAI's TTS API for natural bilingual speech (Spanish + English).
Uses Whisper API for word-level timestamps.

Much better than edge-tts for bilingual content:
- Natural flow between Spanish and English
- No awkward pauses between languages
- Consistent voice throughout
- Better pronunciation of English words in Spanish context
"""

import argparse
import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path

import re

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent / ".env")

# English words that are DISTINCTLY English (not Spanish-English overlap)
ENGLISH_WORDS = {
    # Phrasal verbs with "give"
    "give", "up", "away", "back", "off",
    # Other common phrasal verbs
    "take", "get", "put", "set", "turn", "come", "make", "break",
    "run", "look", "pick", "call", "bring", "cut", "fall", "hold",
    # Common particles (excluding Spanish overlap)
    "down", "over", "through", "around", "along",
    # Quiz words
    "quiz", "time",
    # Distinctly English words (NOT in Spanish)
    "the", "is", "are", "was", "were", "be", "been",
    "to", "for", "with", "from", "at", "by", "about", "into",
    "it", "you", "he", "she", "they", "we", "this", "that",
    "what", "which", "who", "how", "when", "where", "why",
    "yes", "not", "but", "if", "then",
    "can", "could", "will", "would", "should", "may", "might",
    "do", "does", "did", "have", "has", "had",
    # Key educational words
    "embarrassed", "pregnant", "library", "bookstore",
    "actually", "sensible", "sensitive",
}

# Words that exist in both Spanish and English - DON'T auto-mark as English
SPANISH_ENGLISH_OVERLAP = {
    "no", "a", "an", "in", "on", "or", "y", "go", "and",
    "me", "mi", "sin", "son", "era", "hay",
}

# Available voices
VOICES = {
    "nova": "Warm female - great for teaching (recommended)",
    "alloy": "Neutral, balanced",
    "echo": "Male, warm",
    "fable": "British-ish, storytelling",
    "onyx": "Deep male, authoritative",
    "shimmer": "Soft female, gentle",
}

DEFAULT_VOICE = "alloy"
DEFAULT_MODEL = "tts-1"  # or "tts-1-hd" for higher quality
DEFAULT_SPEED = 0.80  # Slow for natural pacing - no rushing, let it breathe (0.25 to 4.0)


def extract_english_words_from_script(script: dict) -> set:
    """
    Automatically extract English teaching words from script metadata.
    These are the ONLY words that should be pronounced in English.
    Everything else should be Spanish.

    Strategy:
    1. Extract words in SINGLE QUOTES from full_script - these are always English
    2. From english_phrases list if provided
    3. From translations VALUES (not keys)

    Note: Options may be Spanish (for "what does X mean?" quizzes) or English
    (for "how do you say X?" quizzes). We use quotes as the primary indicator.
    """
    english_words = set()

    # Common Spanish words to filter out (even if extracted)
    # These appear frequently in Spanish quiz questions/answers
    SPANISH_FILTER = {
        # False friends - Spanish words that look like English
        'resfriado', 'estreñido', 'confundido', 'constante', 'embarazada',
        'biblioteca', 'librería', 'sensible', 'sensitivo', 'actualmente',
        'pretender', 'éxito', 'recordar', 'realizar', 'soportar',
        # Common Spanish verbs and adjectives
        'soy', 'eres', 'somos', 'son', 'estoy', 'estas', 'estamos', 'están',
        'tengo', 'tienes', 'tiene', 'tenemos', 'tienen',
        'aburrido', 'aburrida', 'cansado', 'cansada', 'emocionado', 'emocionada',
        'interesado', 'interesada', 'asustado', 'asustada',
        'hacer', 'decir', 'buscar', 'encontrar', 'ver', 'dar', 'ir', 'venir',
        # Common Spanish articles, prepositions, conjunctions
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'del', 'en', 'que', 'es', 'al', 'por', 'con', 'para', 'como',
        'más', 'pero', 'sus', 'le', 'ya', 'se', 'desde', 'porque', 'cuando',
        'muy', 'sin', 'sobre', 'ser', 'entre', 'después', 'antes', 'durante',
        'también', 'fue', 'había', 'hay', 'está', 'esto', 'eso', 'ese', 'esta',
        # Quiz-specific Spanish words
        'significa', 'respuesta', 'correcta', 'opciones', 'pregunta',
        'traducción', 'inglés', 'español', 'dice', 'cómo', 'qué', 'cuál',
        'fiesta', 'libro', 'palabra', 'frase', 'verbo',
    }

    question = script.get('question', '')
    quoted_pattern = r"'([^']+)'"

    # Determine quiz type based on question structure:
    # Type A: "¿Cómo se dice X en inglés?" → X is Spanish, correct option is English
    # Type B: "¿Qué significa X en inglés?" → X is English, options are Spanish
    is_como_se_dice = '¿cómo se dice' in question.lower() or 'como se dice' in question.lower()
    is_que_significa = '¿qué significa' in question.lower() or 'que significa' in question.lower()

    if is_como_se_dice:
        # For "how do you say X" questions, extract from the CORRECT OPTION (English)
        # NOT from the question's quoted text (which is Spanish)
        correct_letter = script.get('correct', '')
        options = script.get('options', {})
        if correct_letter in options:
            correct_option = options[correct_letter]
            clean_option = re.sub(r"['\".!?,]", '', correct_option)
            for word in clean_option.lower().split():
                if len(word) > 1 and word not in SPANISH_FILTER:
                    english_words.add(word)
    elif is_que_significa:
        # For "what does X mean" questions, X is English
        for match in re.findall(quoted_pattern, question):
            for word in match.lower().split():
                clean = re.sub(r'[^\w]', '', word)
                if clean and len(clean) > 1 and clean not in SPANISH_FILTER:
                    english_words.add(clean)
    else:
        # Fallback: extract quoted words from question (assume English)
        for match in re.findall(quoted_pattern, question):
            for word in match.lower().split():
                clean = re.sub(r'[^\w]', '', word)
                if clean and len(clean) > 1 and clean not in SPANISH_FILTER:
                    english_words.add(clean)

    # SECONDARY: From english_phrases list if explicitly provided
    for phrase in script.get('english_phrases', []):
        for word in phrase.lower().split():
            clean = re.sub(r'[^\w]', '', word)
            if clean and len(clean) > 1 and clean not in SPANISH_FILTER:
                english_words.add(clean)

    # NOTE: We don't extract from 'translations' field because its format varies
    # (sometimes values are English, sometimes Spanish depending on quiz type)

    return english_words


def prepare_bilingual_text(text: str, english_words: set) -> str:
    """
    Prepare text for bilingual TTS by ensuring proper language context.

    Strategy:
    - OpenAI TTS auto-detects language based on context
    - We ensure Spanish context is dominant for Spanish words
    - English teaching words are kept in quotes with clear context
    - Option letters (A, B, C, D) stay in Spanish context

    The text is already in Spanish with English words in quotes.
    We just need to ensure the context is clear.
    """
    # Ensure option letters are pronounced in Spanish
    # Replace "A," with "A:" to make it clearly part of Spanish enumeration
    # Actually, keeping the comma is fine, the issue is context

    # The key is that surrounding Spanish text should be clearly Spanish
    # OpenAI TTS is actually pretty good at this when the text is mostly Spanish

    # Make sure single quotes around English words are preserved
    # These signal to TTS that the word is a distinct unit

    # For numbers in countdown, ensure they're in Spanish context
    # "Tres, dos, uno" should be pronounced Spanish because context is Spanish

    # The main fix: ensure the text starts and stays in Spanish context
    # Add a Spanish language hint at the beginning if not present
    if not text.startswith('¿') and not text.startswith('¡'):
        # Text doesn't start with Spanish punctuation, add context
        pass  # Actually, most quiz scripts start with ¿ so this is fine

    return text


def preprocess_for_pauses(text: str) -> str:
    """
    Pre-process text to create natural pauses for TTS.

    OpenAI TTS doesn't respect "..." or multiple periods well.
    We use ACTUAL SPOKEN WORDS to create timing gaps:
    - Short filler phrases that take ~1 second to speak
    - Complete sentences between sections

    Target timing:
    - Question → 1 sec pause → "Escucha las opciones" → 0.5 sec → Options
    - Each option separated by ~1.5 seconds
    - Countdown: each number followed by 1 second pause
    """
    # First, normalize the ellipses
    text = text.replace("...", " ")

    # STEP 1: Add pause after questions and before options
    # "?" followed by option letter → add "Escucha las opciones" with pauses
    text = re.sub(
        r'\?\s*\.?\s*([A-D],)',
        r'? Escucha las opciones. Opción \1',
        text
    )

    # STEP 2: Add pauses between each option (A, B, C, D)
    # Pattern: after an option's content, before the next option letter
    # Add "Siguiente opción" or similar filler to create ~1.5 sec gap

    # After option A content, before B
    text = re.sub(
        r"(['\"])\.\s*\.?\s*B,",
        r"\1. Opción B,",
        text
    )
    # After option B content, before C
    text = re.sub(
        r"(['\"])\.\s*\.?\s*C,",
        r"\1. Opción C,",
        text
    )
    # After option C content, before D
    text = re.sub(
        r"(['\"])\.\s*\.?\s*D,",
        r"\1. Opción D,",
        text
    )

    # STEP 3: COUNTDOWN - Always in SPANISH
    # Convert any English countdown to Spanish: Three→Tres, Two→Dos, One→Uno
    countdown_simple = 'Tres. Dos. Uno.'

    # Convert English countdown to Spanish
    text = re.sub(r'[Tt]hree', 'Tres', text)
    text = re.sub(r'[Tt]wo', 'Dos', text)
    text = re.sub(r'[Oo]ne', 'Uno', text)

    # Replace various countdown patterns with simple version
    # Clean up any preceding punctuation/whitespace and ensure period before countdown
    text = re.sub(
        r'[\s.,]+[Tt]res[\s.,]*[Dd]os[\s.,]*[Uu]no[\s.,]*',
        '. ' + countdown_simple + ' ',
        text
    )

    # Handle "El número tres..." patterns
    text = re.sub(
        r'El número tres.*?El número uno.*?[Yy]a[.!]?',
        countdown_simple,
        text, flags=re.IGNORECASE
    )

    # Handle patterns with extra words between (from previous processing)
    text = re.sub(
        r'[\s.,]+[Tt]res[\s.,]+(?:piensa|bien|espera|y|atención|\.)*[\s.,]*[Dd]os[\s.,]+(?:piensa|bien|espera|y|atención|\.)*[\s.,]*[Uu]no[\s.,]*',
        '. ' + countdown_simple + ' ',
        text
    )

    # STEP 4: Add pause before countdown section
    # After last option, before "Piensa bien" or countdown
    text = re.sub(
        r"(['\"])\.\s*\.?\s*Piensa",
        r"\1. Ahora, piensa",
        text
    )

    # STEP 5: Clean up
    text = re.sub(r'[,]{2,}', ',', text)
    text = re.sub(r'[.]{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def text_to_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED,
    explicit_english: list = None,
) -> dict:
    """
    Convert text to speech using OpenAI TTS.
    Then extract word-level timestamps using Whisper.

    Args:
        text: The text to convert (Spanish with English words - no special marking needed)
        output_path: Path to save the MP3 file
        voice: Voice to use (nova, alloy, echo, fable, onyx, shimmer)
        model: TTS model (tts-1 or tts-1-hd)
        speed: Speech speed (0.25 to 4.0, default 0.9 for calm teaching pace)

    Returns:
        Dictionary with duration and word timestamps
    """
    client = OpenAI()

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Pre-process text for natural pauses
    processed_text = preprocess_for_pauses(text)

    # Generate speech
    print(f"Generating speech with OpenAI TTS...")
    print(f"  Voice: {voice}")
    print(f"  Model: {model}")
    print(f"  Speed: {speed}")

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=processed_text,  # Use pre-processed text with proper pauses
        speed=speed,
        response_format="mp3"
    ) as response:
        response.stream_to_file(output_path)
    print(f"  Audio saved: {output_path}")
    print(f"  Processed text: {processed_text[:100]}...")

    # Extract timestamps using Whisper
    print(f"Extracting word timestamps with Whisper...")
    timestamps = extract_timestamps_whisper(output_path, client, original_text=text,
                                            explicit_english=explicit_english)

    # Save timestamps JSON
    json_path = output_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2, ensure_ascii=False)

    print(f"  Timestamps saved: {json_path}")
    print(f"  Duration: {timestamps['duration']:.2f}s")
    print(f"  Words: {len(timestamps['words'])}")

    return timestamps


def extract_english_phrases(text: str) -> set:
    """Extract English phrases from text (words in single quotes)."""
    # Find all words in single quotes
    pattern = r"'([^']+)'"
    matches = re.findall(pattern, text)

    # Split phrases into individual words and normalize
    english_words = set()
    for phrase in matches:
        for word in phrase.lower().split():
            # Remove punctuation
            clean = re.sub(r'[^\w]', '', word)
            if clean:
                english_words.add(clean)

    return english_words


def is_english_word(word: str, english_from_script: set = None) -> bool:
    """
    Determine if a word is English based on context.

    Uses:
    1. Words extracted from single quotes in the script (highest priority)
    2. Common English word list (excluding Spanish-English overlap)
    """
    clean_word = re.sub(r'[^\w]', '', word.lower())

    # Skip empty
    if not clean_word:
        return False

    # HIGHEST PRIORITY: If it's from the script's English phrases (quoted)
    if english_from_script and clean_word in english_from_script:
        return True

    # Skip Spanish-English overlap words unless explicitly quoted
    if clean_word in SPANISH_ENGLISH_OVERLAP:
        return False

    # Check distinctly English words list
    if clean_word in ENGLISH_WORDS:
        return True

    return False


def extract_timestamps_whisper(audio_path: str, client: OpenAI = None, original_text: str = None,
                                explicit_english: list = None) -> dict:
    """
    Extract word-level timestamps from audio using OpenAI Whisper API.

    Args:
        audio_path: Path to the audio file
        client: OpenAI client instance
        original_text: Original script text (used to identify English words from quotes)
        explicit_english: Explicit list of English phrases (takes priority over quote extraction)

    Returns:
        Dictionary with duration and word timestamps
    """
    if client is None:
        client = OpenAI()

    with open(audio_path, "rb") as audio_file:
        # Use verbose_json to get word-level timestamps
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )

    # Build English word set from explicit list or extract from quotes
    if explicit_english:
        # Use explicit list - split phrases into words
        english_from_script = set()
        for phrase in explicit_english:
            for word in phrase.lower().split():
                clean = re.sub(r'[^\w]', '', word)
                if clean:
                    english_from_script.add(clean)
    else:
        # Fall back to extracting from quotes in script
        english_from_script = extract_english_phrases(original_text) if original_text else set()

    # Extract word timestamps with English detection
    words = []
    if hasattr(transcript, 'words') and transcript.words:
        for word_info in transcript.words:
            word_text = word_info.word
            words.append({
                "word": word_text,
                "start": round(word_info.start, 3),
                "end": round(word_info.end, 3),
                "is_english": is_english_word(word_text, english_from_script)
            })

    # Calculate duration
    duration = transcript.duration if hasattr(transcript, 'duration') else 0
    if not duration and words:
        duration = words[-1]["end"]

    return {
        "duration": round(duration, 3),
        "words": words,
        "text": transcript.text if hasattr(transcript, 'text') else ""
    }


def fix_countdown_timing(
    audio_path: str,
    timestamps: dict,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED,
    gap_duration: float = 1.0,
    explicit_english: list = None
) -> dict:
    """
    Fix countdown timing by generating separate clips and stitching with silence.

    Instead of manipulating existing audio (which causes glitches), we:
    1. Find countdown position in current audio
    2. Extract audio BEFORE countdown
    3. Generate fresh "Tres", "Dos", "Uno" clips separately
    4. Create silence gaps
    5. Stitch together with ffmpeg: before + Tres + gap + Dos + gap + Uno + after
    6. Re-run Whisper to get accurate timestamps

    Args:
        audio_path: Path to the original audio file
        timestamps: Dictionary with word timestamps
        voice: TTS voice to use for countdown
        model: TTS model
        speed: TTS speed
        gap_duration: Seconds of silence between countdown numbers

    Returns:
        Updated timestamps dictionary
    """
    words = timestamps.get('words', [])
    if not words:
        return timestamps

    # Find countdown position (look for "tres" or "3")
    countdown_start_idx = -1
    countdown_end_idx = -1

    for i, word_info in enumerate(words):
        word = word_info.get('word', '').lower()
        if word in ('tres', '3') and countdown_start_idx < 0:
            countdown_start_idx = i
        if word in ('uno', '1') and countdown_start_idx >= 0:
            countdown_end_idx = i
            break

    if countdown_start_idx < 0 or countdown_end_idx < 0:
        print("  No countdown found to fix")
        return timestamps

    # Get timestamps
    countdown_start_time = words[countdown_start_idx].get('start', 0)
    countdown_end_time = words[countdown_end_idx].get('end', 0)

    # Need some buffer before countdown (don't cut in middle of word)
    if countdown_start_idx > 0:
        prev_word_end = words[countdown_start_idx - 1].get('end', 0)
        cut_time = prev_word_end + 0.1  # Small gap after previous word
    else:
        cut_time = max(0, countdown_start_time - 0.1)

    print(f"  Fixing countdown timing (starts at {countdown_start_time:.2f}s)")

    # Create temp directory for working files
    temp_dir = tempfile.mkdtemp(prefix="countdown_fix_")

    try:
        client = OpenAI()

        # 1. Extract audio BEFORE countdown
        before_path = os.path.join(temp_dir, "before.mp3")
        cmd_before = [
            'ffmpeg', '-y', '-i', audio_path,
            '-t', str(cut_time),
            '-acodec', 'libmp3lame', '-q:a', '2',
            before_path
        ]
        subprocess.run(cmd_before, capture_output=True, timeout=30)

        # 2. Extract audio AFTER countdown (from after "uno" ends)
        after_start = countdown_end_time + 0.1
        after_path = os.path.join(temp_dir, "after.mp3")
        cmd_after = [
            'ffmpeg', '-y', '-i', audio_path,
            '-ss', str(after_start),
            '-acodec', 'libmp3lame', '-q:a', '2',
            after_path
        ]
        subprocess.run(cmd_after, capture_output=True, timeout=30)

        # 3. Generate countdown clips separately
        countdown_words = ["Tres.", "Dos.", "Uno."]
        countdown_paths = []

        for i, word in enumerate(countdown_words):
            clip_path = os.path.join(temp_dir, f"countdown_{i}.mp3")
            with client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=word,
                speed=speed,
                response_format="mp3"
            ) as response:
                response.stream_to_file(clip_path)
            countdown_paths.append(clip_path)

        # 4. Create silence gap
        silence_path = os.path.join(temp_dir, "silence.mp3")
        cmd_silence = [
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
            '-t', str(gap_duration),
            '-acodec', 'libmp3lame', '-q:a', '2',
            silence_path
        ]
        subprocess.run(cmd_silence, capture_output=True, timeout=30)

        # 5. Create concat file for ffmpeg
        concat_list_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_list_path, 'w') as f:
            f.write(f"file '{before_path}'\n")
            f.write(f"file '{countdown_paths[0]}'\n")  # Tres
            f.write(f"file '{silence_path}'\n")
            f.write(f"file '{countdown_paths[1]}'\n")  # Dos
            f.write(f"file '{silence_path}'\n")
            f.write(f"file '{countdown_paths[2]}'\n")  # Uno
            f.write(f"file '{after_path}'\n")

        # 6. Concatenate with ffmpeg
        output_temp = os.path.join(temp_dir, "final.mp3")
        cmd_concat = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_list_path,
            '-acodec', 'libmp3lame', '-q:a', '2',
            output_temp
        ]
        result = subprocess.run(cmd_concat, capture_output=True, timeout=60)

        if result.returncode != 0:
            print(f"  Warning: ffmpeg concat failed: {result.stderr.decode()[:200]}")
            return timestamps

        # 7. Replace original audio
        import shutil
        shutil.copy2(output_temp, audio_path)

        # 8. Re-run Whisper to get updated timestamps
        print(f"  Re-extracting timestamps after countdown fix...")
        new_timestamps = extract_timestamps_whisper(audio_path, client, explicit_english=explicit_english)

        # Preserve metadata from original
        new_timestamps['text'] = timestamps.get('text', new_timestamps.get('text', ''))

        print(f"  New duration: {new_timestamps['duration']:.2f}s (added {new_timestamps['duration'] - timestamps['duration']:.2f}s)")

        return new_timestamps

    except Exception as e:
        print(f"  Warning: Countdown fix failed: {e}")
        return timestamps

    finally:
        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def get_audio_duration(audio_path: str) -> float:
    """Get duration of an audio file using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def generate_segment_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED
) -> float:
    """
    Generate a single audio segment and return its duration.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: TTS voice
        model: TTS model
        speed: Speech speed

    Returns:
        Duration in seconds
    """
    client = OpenAI()

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
        response_format="mp3"
    ) as response:
        response.stream_to_file(output_path)

    return get_audio_duration(output_path)


def generate_silence(duration: float, output_path: str) -> None:
    """Generate a silence audio file of specified duration."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
        '-t', str(duration),
        '-acodec', 'libmp3lame', '-q:a', '2',
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


def generate_quiz_audio_segmented(
    script: dict,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Generate quiz audio using ASSEMBLY APPROACH with pre-recorded audio library.

    ARCHITECTURE:
    1. Pre-recorded standard phrases (assets/audio/standard/) - perfect quality, reused
    2. Cached English words (assets/audio/words/) - generated once, reused
    3. Fresh TTS only for: question text, explanation
    4. Assembly: [pre-recorded] + [silence] + [word/phrase] + [silence]
    5. No re-encoding during concatenation (-c:a copy)

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    import shutil
    import hashlib

    # === PATHS ===
    # Use the SPANISH library - these are the tested, approved audio files
    SPANISH_DIR = Path(__file__).parent.parent / "assets" / "audio" / "spanish"
    WORDS_DIR = Path(__file__).parent.parent / "assets" / "audio" / "words"
    WORDS_DIR.mkdir(parents=True, exist_ok=True)

    # === PAUSE DURATIONS ===
    PAUSE_AFTER_QUESTION = 0.5
    PAUSE_AFTER_TRANSITION = 0.8  # After "Escucha las opciones"
    PAUSE_BETWEEN_LETTER_AND_CONTENT = 0.4
    PAUSE_AFTER_OPTION = 0.6  # After each option A, B, C, D
    PAUSE_AFTER_THINK = 0.5  # After "Piensa bien"
    PAUSE_AFTER_COUNTDOWN = 1.0  # Between countdown numbers
    PAUSE_AFTER_LAST_COUNT = 0.6
    PAUSE_AFTER_ANSWER_PHRASE = 0.5  # After "Correcto..."
    PAUSE_AFTER_ANSWER = 0.3  # Before explanation
    PAUSE_AFTER_EXPLANATION = 0.5  # Ensure explanation has breathing room

    # === SCRIPT DATA ===
    question = script.get('question', '¿Pregunta?')
    options = script.get('options', {})
    correct = script.get('correct', 'A')
    explanation = script.get('explanation', '')

    clean_question = question.replace('¿', '').strip()
    correct_text = options.get(correct, '').strip("'\"")

    # === TEMP DIRECTORY ===
    temp_dir = tempfile.mkdtemp(prefix="quiz_assembly_")

    def get_or_generate_word(text: str) -> str:
        """Get cached word audio or generate and cache it."""
        # Create safe filename from text
        safe_name = "".join(c if c.isalnum() else "_" for c in text.lower())
        safe_name = safe_name[:50]  # Limit length
        hash_suffix = hashlib.md5(text.encode()).hexdigest()[:8]
        cache_path = WORDS_DIR / f"{safe_name}_{hash_suffix}.mp3"

        if cache_path.exists():
            print(f"      [cached] {text}")
            return str(cache_path)

        # Generate with high quality
        print(f"      [generating] {text}")
        client = OpenAI()
        with client.audio.speech.with_streaming_response.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=1.0,  # Default speed - more consistent
            response_format="mp3"
        ) as response:
            response.stream_to_file(str(cache_path))

        return str(cache_path)

    try:
        print("=" * 60)
        print("QUIZ AUDIO ASSEMBLY")
        print("=" * 60)
        print(f"  Spanish audio library: {SPANISH_DIR}")
        print(f"  Words cache: {WORDS_DIR}")
        print()

        segments = []
        audio_files = []
        running_time = 0.0

        def add_audio(path: str, duration: float = None):
            """Add audio file to sequence."""
            nonlocal running_time
            if duration is None:
                duration = get_audio_duration(path)
            audio_files.append(path)
            start = running_time
            running_time += duration
            return start, running_time, duration

        def add_silence(duration: float):
            """Add silence to sequence."""
            nonlocal running_time
            silence_path = os.path.join(temp_dir, f"silence_{len(audio_files)}.mp3")
            generate_silence(duration, silence_path)
            audio_files.append(silence_path)
            running_time += duration

        def add_segment(seg_id: str, text: str, start: float, end: float):
            """Record segment metadata."""
            segment = {
                'id': seg_id,
                'text': text,
                'start': round(start, 3),
                'end': round(end, 3),
                'duration': round(end - start, 3),
            }
            segments.append(segment)
            print(f"  [{seg_id}] {text[:50]}...")
            print(f"    {start:.2f}s - {end:.2f}s ({end-start:.2f}s)")
            return segment

        # ============================================================
        # 1. QUESTION (fresh TTS - variable content)
        # ============================================================
        print("\n[1] QUESTION")
        q_path = os.path.join(temp_dir, "question.mp3")
        client = OpenAI()
        with client.audio.speech.with_streaming_response.create(
            model="tts-1-hd",
            voice=voice,
            input=clean_question,
            speed=1.0,
            response_format="mp3"
        ) as response:
            response.stream_to_file(q_path)
        q_start, q_end, _ = add_audio(q_path)
        add_segment('question', clean_question, q_start, q_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # ============================================================
        # 2-3. TRANSITION + OPTIONS - COMBINED in ONE TTS call
        # TTS is inconsistent with short isolated words.
        # Generating ALL options together in ONE call works reliably.
        # ============================================================
        print("\n[3] OPTIONS (combined generation)")

        # Build combined text for all options
        option_lines = ["Escucha las opciones."]
        option_words = {}
        for letter in ['A', 'B', 'C', 'D']:
            word = options.get(letter, '').strip("'\"")
            option_words[letter] = word
            option_lines.append(f"Opción {letter}, {word}.")

        combined_text = "\n".join(option_lines)
        print(f"  Combined text ({len(combined_text)} chars):")
        for line in option_lines:
            print(f"    {line}")

        # Generate ALL options in ONE TTS call
        combined_path = os.path.join(temp_dir, "options_combined.mp3")
        with client.audio.speech.with_streaming_response.create(
            model="tts-1-hd",
            voice=voice,
            input=combined_text,
            speed=1.0,
            response_format="mp3"
        ) as response:
            response.stream_to_file(combined_path)

        combined_duration = get_audio_duration(combined_path)
        print(f"  Combined duration: {combined_duration:.2f}s")

        # Add the combined audio
        combined_start = running_time
        add_audio(combined_path)

        # Estimate segment times (roughly equal distribution)
        # First segment is "Escucha las opciones" (~1.5s)
        # Then 4 options share the rest
        transition_duration = 1.5
        options_duration = combined_duration - transition_duration
        per_option = options_duration / 4

        # Add transition segment
        add_segment('transition', 'Escucha las opciones.',
                   combined_start, combined_start + transition_duration)

        # Add option segments (estimated times)
        for i, letter in enumerate(['A', 'B', 'C', 'D']):
            opt_start = combined_start + transition_duration + (i * per_option)
            opt_end = opt_start + per_option
            add_segment(f'option_{letter.lower()}',
                       f"Opción {letter}, {option_words[letter]}.",
                       opt_start, opt_end)
            print(f"  Option {letter}: {opt_start:.2f}s - {opt_end:.2f}s")

        # Pause after all options
        add_silence(PAUSE_AFTER_OPTION)

        # ============================================================
        # 4. THINK (pre-recorded)
        # ============================================================
        print("\n[4] THINK")
        think_path = str(SPANISH_DIR / "piensa_bien.mp3")
        think_start, think_end, _ = add_audio(think_path)
        add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # ============================================================
        # 5. COUNTDOWN (pre-recorded)
        # ============================================================
        print("\n[5] COUNTDOWN")
        for num, name in [('3', 'tres'), ('2', 'dos'), ('1', 'uno')]:
            cd_path = str(SPANISH_DIR / f"{name}.mp3")
            cd_start, cd_end, _ = add_audio(cd_path)
            add_segment(f'countdown_{num}', f'{name.capitalize()}.', cd_start, cd_end)
            pause = PAUSE_AFTER_LAST_COUNT if num == '1' else PAUSE_AFTER_COUNTDOWN
            add_silence(pause)

        # ============================================================
        # 6. ANSWER
        # Generate FULL answer text as one sentence (like explanation and options)
        # NOT single word! Single word = TTS doesn't know it's Spanish
        # ============================================================
        print("\n[6] ANSWER")
        answer_start = running_time

        # Generate COMPLETE answer as one full Spanish sentence
        # This gives TTS full context to pronounce correctly
        full_answer_text = f"Correcto. La respuesta es {correct}, {correct_text}."
        print(f"  Answer: '{full_answer_text}'")

        ans_path = os.path.join(temp_dir, "answer.mp3")
        with client.audio.speech.with_streaming_response.create(
            model="tts-1-hd",
            voice=voice,
            input=full_answer_text,
            speed=1.0,
            response_format="mp3"
        ) as response:
            response.stream_to_file(ans_path)
        add_audio(ans_path)

        answer_end = running_time
        add_segment('answer', full_answer_text, answer_start, answer_end)
        add_silence(PAUSE_AFTER_ANSWER)

        # ============================================================
        # 7. EXPLANATION (fresh TTS - MUST COMPLETE FULLY)
        # ============================================================
        if explanation.strip():
            print("\n[7] EXPLANATION")
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            with client.audio.speech.with_streaming_response.create(
                model="tts-1-hd",
                voice=voice,
                input=explanation,
                speed=1.0,
                response_format="mp3"
            ) as response:
                response.stream_to_file(exp_path)
            exp_start, exp_end, _ = add_audio(exp_path)
            add_segment('explanation', explanation, exp_start, exp_end)
            # Add breathing room after explanation
            add_silence(PAUSE_AFTER_EXPLANATION)

        total_duration = running_time
        print(f"\n{'=' * 60}")
        print(f"Total duration: {total_duration:.2f}s")
        print(f"{'=' * 60}")

        # ============================================================
        # CONCATENATE (no re-encoding)
        # ============================================================
        print("\nConcatenating audio files...")
        concat_list_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_list_path, 'w') as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file}'\n")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_list_path,
            '-c:a', 'copy',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr.decode()[:500]}")

        print(f"Audio saved: {output_path}")

        # ============================================================
        # BUILD RESULT
        # ============================================================
        segment_times = {seg['id']: {'start': seg['start'], 'end': seg['end'], 'duration': seg['duration']} for seg in segments}

        return {
            'duration': round(total_duration, 3),
            'segments': segments,
            'segment_times': segment_times,
            'type': 'quiz',
            'question': question,
            'options': options,
            'correct': correct,
            'explanation': explanation,
            'full_script': script.get('full_script', ''),
            'translations': script.get('translations', {}),
            'hashtags': script.get('hashtags', []),
            'words': [],
        }

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def generate_true_false_audio_segmented(
    script: dict,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Generate true/false audio using SEGMENT-BASED architecture.

    Segments:
    1. statement - The statement to evaluate
    2. options - "¿Verdadero o falso?"
    3. think - "Piensa bien"
    4. countdown_3 - "Tres" + silence
    5. countdown_2 - "Dos" + silence
    6. countdown_1 - "Uno"
    7. answer - "¡Verdadero!" or "¡Falso!"
    8. explanation - The explanation
    """
    import shutil

    statement = script.get('statement', '')
    correct = script.get('correct', False)
    explanation = script.get('explanation', '')

    # Clean statement
    clean_statement = statement.replace('¿', '').replace('?', '').strip()

    # Answer text
    answer_word = "¡Verdadero!" if correct else "¡Falso!"

    segment_defs = [
        ('statement', clean_statement, 0.3),
        ('options', '¿Verdadero o falso?', 0.5),
        ('think', 'Piensa bien.', 0.5),
        ('countdown_3', 'Tres.', 1.0),
        ('countdown_2', 'Dos.', 1.0),
        ('countdown_1', 'Uno.', 0.4),
        ('answer', answer_word, 0.3),
        ('explanation', explanation, 0.0),
    ]

    temp_dir = tempfile.mkdtemp(prefix="tf_segments_")

    try:
        print("Generating true/false audio segments...")

        segments = []
        audio_files = []
        running_time = 0.0

        for seg_id, text, pause_after in segment_defs:
            if not text.strip():
                continue

            seg_path = os.path.join(temp_dir, f"{seg_id}.mp3")
            print(f"  [{seg_id}] Generating: {text[:50]}...")

            duration = generate_segment_audio(text, seg_path, voice, model, speed)

            segment = {
                'id': seg_id,
                'text': text,
                'start': round(running_time, 3),
                'end': round(running_time + duration, 3),
                'duration': round(duration, 3),
            }
            segments.append(segment)
            audio_files.append(seg_path)

            print(f"    Duration: {duration:.2f}s, Start: {running_time:.2f}s")

            running_time += duration

            if pause_after > 0:
                silence_path = os.path.join(temp_dir, f"{seg_id}_pause.mp3")
                generate_silence(pause_after, silence_path)
                audio_files.append(silence_path)
                running_time += pause_after

        total_duration = running_time
        print(f"\nTotal duration: {total_duration:.2f}s")

        # Concatenate
        concat_list_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_list_path, 'w') as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file}'\n")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        cmd_concat = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_list_path,
            '-acodec', 'libmp3lame', '-q:a', '2',
            output_path
        ]
        subprocess.run(cmd_concat, capture_output=True, timeout=120)

        print(f"Audio saved: {output_path}")

        segment_times = {}
        for seg in segments:
            segment_times[seg['id']] = {
                'start': seg['start'],
                'end': seg['end'],
                'duration': seg['duration'],
            }

        return {
            'duration': round(total_duration, 3),
            'segments': segments,
            'segment_times': segment_times,
            'type': 'true_false',
            'statement': statement,
            'correct': correct,
            'explanation': explanation,
            'full_script': script.get('full_script', ''),
            'translations': script.get('translations', {}),
            'hashtags': script.get('hashtags', []),
            'words': [],
        }

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def generate_from_script(
    script_path: str,
    output_dir: str = None,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Generate TTS audio from a script JSON file.

    Uses SEGMENT-BASED architecture for quiz and true_false videos:
    - Each segment generated separately with EXACT timestamps
    - No guessing, no estimation
    - Perfect audio-visual sync guaranteed

    Args:
        script_path: Path to the script JSON file
        output_dir: Output directory
        voice: Voice to use
        model: TTS model
        speed: Speech speed

    Returns:
        Dictionary with audio path and exact segment timestamps
    """
    # Load script
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    video_type = script.get('type', 'quiz')

    # Determine output path
    if output_dir is None:
        output_dir = f"output/audio/{video_type}"
    os.makedirs(output_dir, exist_ok=True)

    script_name = os.path.splitext(os.path.basename(script_path))[0]
    output_path = os.path.join(output_dir, f"{script_name}.mp3")

    print(f"\n{'='*60}")
    print(f"SEGMENT-BASED TTS GENERATION")
    print(f"Type: {video_type}")
    print(f"Output: {output_path}")
    print(f"{'='*60}\n")

    # Use segment-based generation based on video type
    if video_type == 'quiz':
        result = generate_quiz_audio_segmented(script, output_path, voice, model, speed)
    elif video_type == 'true_false':
        result = generate_true_false_audio_segmented(script, output_path, voice, model, speed)
    else:
        # Fallback to old method for other types
        print(f"Using legacy TTS for type: {video_type}")
        text = script.get("full_script", "")
        if not text:
            raise ValueError("Script file missing 'full_script' field")

        timestamps = text_to_speech(text, output_path, voice=voice, model=model, speed=speed)
        result = {**timestamps}
        result["type"] = video_type
        result["question"] = script.get("question", "")
        result["options"] = script.get("options", {})
        result["correct"] = script.get("correct", "")
        result["explanation"] = script.get("explanation", "")
        result["full_script"] = text
        result["translations"] = script.get("translations", {})
        result["hashtags"] = script.get("hashtags", [])

    # Save result JSON
    json_path = output_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nTimestamps saved: {json_path}")
    print(f"\nSegment timestamps:")
    for seg in result.get('segments', []):
        print(f"  {seg['id']}: {seg['start']:.2f}s - {seg['end']:.2f}s ({seg['duration']:.2f}s)")

    return result


def test_voices(text: str, output_dir: str = "output/audio/voice_tests"):
    """Test all available voices with the same text."""
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nTesting all voices with: {text[:50]}...")
    print("=" * 60)

    for voice, description in VOICES.items():
        print(f"\n[{voice}] {description}")
        output_path = os.path.join(output_dir, f"test_{voice}.mp3")

        try:
            result = text_to_speech(text, output_path, voice=voice)
            print(f"  Duration: {result['duration']:.2f}s")
            print(f"  Output: {output_path}")
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print(f"Voice test files saved to: {output_dir}/")
    print("Listen to each and pick the best for your content!")


async def main():
    parser = argparse.ArgumentParser(
        description="OpenAI TTS - Natural bilingual speech generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available voices: {', '.join(VOICES.keys())}

Examples:
  python src/tts_openai.py "Hola! Como se dice 'give up' en ingles?" -o output.mp3
  python src/tts_openai.py --script output/scripts/quiz/look_for.json -o output.mp3
  python src/tts_openai.py "Test text" -o test.mp3 --voice onyx
  python src/tts_openai.py "Test" --test-voices
  python src/tts_openai.py --list-voices
        """
    )

    parser.add_argument("text", nargs="?", help="Text to convert to speech")
    parser.add_argument("-o", "--output", default="output/audio/openai_test.mp3",
                        help="Output MP3 file path")
    parser.add_argument("--script", "-s", type=str,
                        help="Script JSON file (uses automatic English detection)")
    parser.add_argument("--voice", default=DEFAULT_VOICE, choices=list(VOICES.keys()),
                        help=f"Voice to use (default: {DEFAULT_VOICE})")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=["tts-1", "tts-1-hd"],
                        help=f"TTS model (default: {DEFAULT_MODEL})")
    parser.add_argument("--test-voices", action="store_true",
                        help="Test all voices with the provided text")
    parser.add_argument("--list-voices", action="store_true",
                        help="List available voices")

    args = parser.parse_args()

    if args.list_voices:
        print("\nAvailable OpenAI TTS Voices:")
        print("=" * 50)
        for voice, desc in VOICES.items():
            marker = " (recommended)" if voice == DEFAULT_VOICE else ""
            print(f"  {voice:<10} - {desc}{marker}")
        return

    if args.test_voices:
        if not args.text:
            args.text = "Hola! Vamos con un quiz. Como se dice 'give up' en ingles? La respuesta es 'give up', que significa rendirse."
        test_voices(args.text)
        return

    # Script mode - uses automatic English detection from script metadata
    if args.script:
        try:
            # Derive output path from script if not provided
            output_dir = os.path.dirname(args.output) if args.output != "output/audio/openai_test.mp3" else None
            result = generate_from_script(args.script, output_dir, args.voice, args.model)
            print(f"\nSuccess!")
            print(f"  Audio: {args.output}")
            print(f"  Duration: {result['duration']:.2f}s")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    if not args.text:
        parser.error("Text argument is required (or use --script or --test-voices)")

    try:
        result = text_to_speech(args.text, args.output, args.voice, args.model)
        print(f"\nSuccess!")
        print(f"  Audio: {args.output}")
        print(f"  Duration: {result['duration']:.2f}s")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

#!/usr/bin/env python3
"""
Shared helpers for all TTS modules (OpenAI, Google, ElevenLabs, Edge).

Single source of truth for:
- Audio utility functions (duration, silence, concatenation)
- English word extraction from scripts
- Spanish word filter
- Asset paths and timing constants
"""

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ============== ASSET PATHS ==============

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"
SPANISH_DIR = ASSETS_DIR / "spanish"
WORDS_DIR = ASSETS_DIR / "words"
WORDS_DIR.mkdir(parents=True, exist_ok=True)


# ============== TIMING CONSTANTS ==============
# Bug A3 fix: Increased pauses to ensure countdown completes before answer

PAUSE_AFTER_QUESTION = 0.5
PAUSE_AFTER_OPTION = 0.6
PAUSE_AFTER_THINK = 1.5      # Gap after "piensa bien" before countdown starts
PAUSE_AFTER_COUNTDOWN = 1.0  # Keep: good pacing between numbers
PAUSE_AFTER_LAST_COUNT = 1.0 # Increased: dramatic pause before answer reveal
PAUSE_AFTER_ANSWER = 0.4     # Slightly increased for breathing room
PAUSE_AFTER_EXPLANATION = 0.5


# ============== SEGMENT SPEEDS ==============
# Per-segment-type TTS speed for natural pacing.
# Slower = more deliberate; range 0.25–4.0 (OpenAI API).
# Language learners need more time to process, especially English words.
SEGMENT_SPEEDS = {
    'question':     0.88,  # Question/statement: clear, confident
    'statement':    0.88,  # True/false statements
    'sentence':     0.88,  # Fill-blank sentences
    'options':      0.82,  # Options: slower, let viewer read + listen
    'english_word': 0.78,  # Teaching words: slowest, clear pronunciation
    'answer':       0.85,  # Answer reveal: moderate
    'explanation':  0.85,  # Explanation: conversational
    'cached_phrase': 0.82, # Pre-generated words in cache
    'default':      0.85,  # Fallback
}


# ============== SPANISH FILTER ==============
# Union of all words from all TTS modules

SPANISH_FILTER = {
    # False friends - Spanish words that look like English
    'resfriado', 'estreñido', 'confundido', 'constante', 'embarazada',
    'biblioteca', 'librería', 'sensible', 'sensitivo', 'actualmente',
    'pretender', 'éxito', 'recordar', 'realizar', 'soportar',
    'avergonzado', 'desesperado',
    # Common Spanish verbs and adjectives
    'soy', 'eres', 'somos', 'son', 'estoy', 'estas', 'estamos', 'están',
    'tengo', 'tienes', 'tiene', 'tenemos', 'tienen',
    'aburrido', 'aburrida', 'cansado', 'cansada', 'emocionado', 'emocionada',
    'interesado', 'interesada', 'asustado', 'asustada',
    'hacer', 'decir', 'buscar', 'encontrar', 'ver', 'dar', 'ir', 'venir',
    'continuar', 'rendirse', 'progresar', 'crecer',
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


# ============== AUDIO UTILITIES ==============

def get_audio_duration(audio_path: str) -> float:
    """Get duration of an audio file using ffprobe."""
    import os
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError(f"ffprobe returned no duration for {audio_path}")
    return float(raw)


def generate_silence(duration: float, output_path: str,
                     sample_rate: int = 44100, channels: str = "mono") -> None:
    """Generate a silence audio file of specified duration.

    Args:
        duration: Silence duration in seconds.
        output_path: Path for the output MP3 file.
        sample_rate: Sample rate (44100 for OpenAI/ElevenLabs, 24000 for Google).
        channels: "mono" or "stereo".
    """
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'anullsrc=r={sample_rate}:cl={channels}',
        '-t', str(duration),
        '-acodec', 'libmp3lame', '-q:a', '2',
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


def concatenate_audio_files(audio_files: list, output_path: str,
                            sample_rate: int = 44100, channels: int = 1,
                            copy_codec: bool = False) -> None:
    """Concatenate multiple audio files using ffmpeg.

    Args:
        audio_files: List of audio file paths to concatenate.
        output_path: Path for the output file.
        sample_rate: Output sample rate.
        channels: Number of output channels (1=mono, 2=stereo).
        copy_codec: If True, use -c:a copy (no re-encoding). Otherwise re-encode.
    """
    import tempfile

    concat_list_path = Path(output_path).with_suffix('.txt')
    with open(concat_list_path, 'w') as f:
        for audio_file in audio_files:
            f.write(f"file '{audio_file}'\n")

    if copy_codec:
        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', str(concat_list_path),
            '-c:a', 'copy',
            output_path
        ]
    else:
        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', str(concat_list_path),
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-ar', str(sample_rate), '-ac', str(channels),
            output_path
        ]

    subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Clean up concat list
    try:
        concat_list_path.unlink()
    except OSError:
        pass


# ============== ENGLISH WORD EXTRACTION ==============

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
    # NOTE: We trust english_phrases completely - no length filter here
    # because these are explicitly marked as English teaching words
    for phrase in script.get('english_phrases', []):
        for word in phrase.lower().split():
            clean = re.sub(r'[^\w]', '', word)
            if clean:  # No length filter - include "I", "a", etc.
                english_words.add(clean)

    # TERTIARY: If no english_phrases provided, extract quoted words from full_script
    # Only as fallback - english_phrases is the canonical source
    if not english_words:
        full_script = script.get('full_script', '')
        if full_script:
            quoted_pattern = r"'([^']+)'"
            for match in re.findall(quoted_pattern, full_script):
                for word in match.lower().split():
                    clean = re.sub(r'[^\w]', '', word)
                    if clean and clean not in SPANISH_FILTER:
                        english_words.add(clean)

    return english_words


# ============== TEXT PREPROCESSING FOR TTS ==============

def clean_for_tts(text: str) -> str:
    """
    Clean text for TTS - remove visual-only elements.

    Bug A3 fix: Removes blanks, formatting characters, and other
    elements that should be displayed but not spoken.

    Examples:
        "In my opinion, we should ___ the meeting" -> "In my opinion, we should the meeting"
        "What does **important** mean?" -> "What does important mean?"
    """
    if not text:
        return text

    # Remove blanks (visual only in fill-in-the-blank)
    text = text.replace('___', '')
    text = text.replace('__', '')
    # Single underscore between words should become space
    text = re.sub(r'(?<=\w)_(?=\w)', ' ', text)

    # Remove markdown formatting
    text = text.replace('**', '')
    text = text.replace('*', '')
    text = text.replace('##', '')
    text = text.replace('#', '')
    text = text.replace('`', '')

    # Remove brackets used for display hints
    text = re.sub(r'\[.*?\]', '', text)

    # Clean up multiple spaces
    text = ' '.join(text.split())

    return text.strip()


def preprocess_text_for_tts(text: str, target_language: str = "es") -> str:
    """
    Preprocess text for optimal TTS output.

    Handles:
    - Normalizing quotes and punctuation
    - Adding natural pauses (... → SSML-like breaks)
    - Cleaning up spacing
    - Handling numbers and abbreviations
    """
    if not text:
        return text

    # 1. Normalize quotes
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace(""", '"').replace(""", '"')

    # 2. Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)

    # 3. Ensure spacing around punctuation
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'([.,!?;:])([A-Za-z])', r'\1 \2', text)

    # 4. Handle ellipsis for pauses (important for countdown timing)
    # Three dots should create a pause
    text = re.sub(r'\.{3,}', '...', text)  # Normalize to exactly 3 dots

    # 5. Clean up quotes around English words
    # Ensure space before opening quote if not at start
    text = re.sub(r"([A-Za-záéíóúñ])(')", r"\1 \2", text)
    # Ensure space after closing quote if followed by letter
    text = re.sub(r"(')([A-Za-záéíóúñ])", r"\1 \2", text)

    # 6. Handle common abbreviations for TTS
    abbreviations = {
        "Ej.": "Por ejemplo",
        "ej.": "por ejemplo",
        "vs.": "versus",
        "etc.": "etcétera",
        "WiFi": "Wai Fai",  # Phonetic for Spanish TTS
    }
    for abbr, expansion in abbreviations.items():
        text = text.replace(abbr, expansion)

    return text.strip()


def validate_script_for_tts(script: dict) -> dict:
    """
    Validate that a script is ready for TTS generation.

    Returns dict with:
    - is_valid: bool
    - errors: list of critical errors
    - warnings: list of non-critical issues
    - cleaned_script: preprocessed script text
    """
    result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "cleaned_script": ""
    }

    full_script = script.get("full_script", "")

    if not full_script:
        result["is_valid"] = False
        result["errors"].append("Missing 'full_script' field")
        return result

    # Check minimum length
    if len(full_script) < 50:
        result["warnings"].append(f"Script is very short ({len(full_script)} chars)")

    # Check for balanced quotes
    single_quotes = full_script.count("'")
    if single_quotes % 2 != 0:
        result["warnings"].append(f"Unbalanced quotes ({single_quotes} single quotes)")

    # Check for English phrases
    english_phrases = script.get("english_phrases", [])
    if not english_phrases:
        result["warnings"].append("No english_phrases defined")

    # Check that English phrases appear in script
    for phrase in english_phrases:
        if phrase.lower() not in full_script.lower():
            result["warnings"].append(f"Phrase '{phrase}' not found in script")

    # Preprocess
    result["cleaned_script"] = preprocess_text_for_tts(full_script)

    return result


def estimate_speech_duration(text: str, words_per_minute: int = 150) -> float:
    """
    Estimate how long text will take to speak.

    Args:
        text: Text to estimate
        words_per_minute: Speaking rate (150 is conversational Spanish)

    Returns:
        Estimated duration in seconds
    """
    # Count words
    words = len(text.split())

    # Add time for pauses
    pauses = text.count('...') * 0.5  # 0.5s per ellipsis
    pauses += text.count('.') * 0.2   # 0.2s per sentence end
    pauses += text.count('?') * 0.3   # 0.3s per question
    pauses += text.count('!') * 0.2   # 0.2s per exclamation

    # Calculate base duration
    base_duration = (words / words_per_minute) * 60

    return base_duration + pauses

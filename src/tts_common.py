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

# Quiz options are generated as separate clips — letter, silence, word — so
# both pauses below are SPLICED, not hoped for from the model's prosody.
#
# PAUSE_LETTER_TO_WORD exists because "Opción A, fábrica." sent as one
# utterance is heard as "Opción afábrica": the model elides a bare vowel into
# the word after it. Measured over the corpus, 38 of 42 quiz artifacts had a
# letter-to-word gap under the 250 ms the QA gate requires, and several had
# no gap at all — the letter was not a separate speech chunk.
#
# 0.30 rather than 0.25 leaves 50 ms of margin so mp3 frame quantisation and
# the gate's -45 dB edge detection cannot round a passing clip under the bar.
# PINNED BY THE 300ms FLOOR — do not lower without re-measuring.
#
# The MEASURED gap is this splice plus whatever leading/trailing silence the
# two clips happen to carry, and that contribution is not controllable and
# varies wildly: measured across two scripts it ranged 0.020s to 0.312s. At
# the worst observed edge (0.020s) a splice of 0.30 measures 0.320s — only
# 20ms of headroom over the 300ms floor and 70ms over the gate's 250ms bar.
# Any reduction here risks a gap that fails the gate on some scripts and
# passes on others, which is the worst possible failure shape.
PAUSE_LETTER_TO_WORD = 0.30

# Must stay comfortably LARGER than PAUSE_LETTER_TO_WORD. The QA gate
# separates the two by size to tell "gap inside one option" from "gap between
# two options", and a listener needs the same cue to hear four options rather
# than eight fragments. 2:1 keeps both unambiguous.
# LOWERED 0.60 -> 0.15 to claw back block duration after the R1 split.
#
# BUDGET, measured on continuous_vs_continual:
#   block = speech + clip-intrinsic silence + 4*PBO + 4*PLW
# With PLW pinned at 0.30 by the floor above, reaching the pre-R1 11.12s
# needs PBO = -0.09. It is NOT reachable; the floor at PBO=0 is ~11.6s.
#
# MEASURED RESULT: 13.958s -> 12.984s. The arithmetic says 4*0.45 = 1.80s
# should have come off; only 0.974s did.
#
# THE DOMINANT TERM IS NOT THESE CONSTANTS. Clip-intrinsic silence — the
# leading/trailing quiet inside each of the nine TTS clips — measured 1.957s
# in one run and 2.916s in another OF THE SAME SCRIPT. That ~1s of run-to-run
# variance is larger than half the savings these constants can produce, so
# block duration is only loosely controllable from here. Trimming it (the
# measure_speech_end helper already computes where each clip's speech ends)
# would remove ~2s AND make both gaps exactly what these numbers say.
#
# A predicted inversion did NOT occur, and the prediction is recorded because
# it was wrong: at 0.15 the between-option gap still MEASURES larger than the
# letter-to-word gap (0.710-0.992 vs 0.473-0.552), because the word clips
# carry 0.56-0.84s of their own trailing silence. The grouping cue survives.
PAUSE_BETWEEN_OPTIONS = 0.15
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


# ============== SPANISH FILTER (canonical) ==============
#
# THE single Spanish stoplist. It gates is_english, which drives BOTH the
# on-screen word styling and the TTS accent, so a word's presence here is the
# difference between it being spoken in a Spanish or an English accent.
#
# There used to be FIVE copies of this list, no two identical:
#
#   animations/subtitle_processor.SPANISH_COMMON   220
#   video/__init__.SPANISH_COMMON                  194      union        275
#   tts_segmenter._SPANISH_COMMON                  129      intersection  40
#   tts_common.SPANISH_FILTER                      113
#   tts_elevenlabs.SPANISH_COMMON                   99
#
# Only 40 words -- 15 per cent of the union -- were agreed on by all five, so
# the same sentence was classified differently depending on which module
# looked at it. Four formed a containment lattice, making unification a pure
# widening for them; this one was the outlier, not a subset of any other, and
# its comment claimed to be the "union of all words from all TTS modules"
# while missing 88 of the 133-word actual TTS union.
#
# Measured over the 172-script corpus, adopting the union reclassifies 371
# Spanish token-occurrences correctly and 25 English ones wrongly (6.7 per
# cent). The 25 are cross-language words, 17 of them "me" in phrases like
# "can you pick me up" -- a known, accepted cost, recorded here so that it is
# not rediscovered as a bug.
#
# ADD WORDS HERE ONLY. Do not re-fork this list.

SPANISH_FILTER = {
    'a', 'aburrida', 'aburrido', 'aceptar', 'actualmente', 'acuerdo',
    'ahora', 'al', 'algo', 'alguien', 'alli', 'allí', 'ante', 'antes',
    'aprender', 'aqui', 'aquí', 'asi', 'asustada', 'asustado', 'así',
    'avergonzado', 'biblioteca', 'bien', 'buena', 'bueno', 'buscar',
    'cada', 'cansada', 'cansado', 'casa', 'casi', 'casual', 'cierto',
    'como', 'con', 'confundido', 'constante', 'continuar', 'correcta',
    'correcto', 'cosa', 'cosas', 'crecer', 'cree', 'creemos', 'crees',
    'creo', 'cual', 'cuando', 'cuál', 'cómo', 'dar', 'de', 'decimos',
    'decir', 'del', 'desde', 'desesperado', 'después', 'dice', 'dicen',
    'dices', 'digo', 'divertida', 'donde', 'durante', 'ejemplo', 'el',
    'ella', 'embarazada', 'emocionada', 'emocionado', 'emocionante', 'en',
    'encontrar', 'enseñar', 'entender', 'entonces', 'entre', 'era',
    'eres', 'es', 'esa', 'esas', 'escribir', 'escuchar', 'ese', 'eso',
    'esos', 'español', 'esta', 'estamos', 'estar', 'estas', 'este',
    'esto', 'estos', 'estoy', 'estreñido', 'está', 'están', 'estás',
    'falso', 'fiesta', 'forma', 'frase', 'fue', 'gente', 'grande',
    'gusta', 'gusto', 'hablar', 'había', 'hace', 'hacemos', 'hacen',
    'hacer', 'haces', 'hago', 'hay', 'hoy', 'incorrecto', 'increible',
    'increíble', 'inglés', 'interesada', 'interesado', 'invitacion',
    'invitación', 'ir', 'la', 'las', 'le', 'leer', 'les', 'librería',
    'libro', 'lo', 'los', 'lugar', 'mala', 'malo', 'manera', 'mas', 'me',
    'mejor', 'mi', 'misma', 'mismo', 'momento', 'mucha', 'muchas',
    'mucho', 'muchos', 'mundo', 'muy', 'más', 'nada', 'necesita',
    'necesitamos', 'necesitas', 'necesito', 'ni', 'no', 'nos', 'nueva',
    'nuevo', 'nunca', 'o', 'opcion', 'opciones', 'opción', 'otra', 'otro',
    'outfit', 'palabra', 'para', 'peor', 'pequeño', 'pero', 'personas',
    'piensa', 'poca', 'poco', 'podemos', 'por', 'porque', 'practicar',
    'pregunta', 'pretender', 'progresar', 'puede', 'pueden', 'puedes',
    'puedo', 'que', 'queremos', 'quien', 'quiere', 'quieren', 'quieres',
    'quiero', 'qué', 'realizar', 'recordar', 'recuerda', 'rendirse',
    'repite', 'resfriado', 'respondido', 'respuesta', 'sabe', 'sabemos',
    'saben', 'sabes', 'sabias', 'sabías', 'se', 'sensible', 'sensitivo',
    'ser', 'si', 'siempre', 'significa', 'sigues', 'sin', 'sobre', 'solo',
    'somos', 'son', 'soportar', 'soy', 'su', 'sus', 'sé', 'sólo',
    'tambien', 'también', 'tan', 'te', 'tenemos', 'tengo', 'ti', 'tiempo',
    'tiene', 'tienen', 'tienes', 'tipo', 'tipos', 'todo', 'traducción',
    'tu', 'tus', 'un', 'una', 'unas', 'uno', 'unos', 'usa', 'usan',
    'usar', 'va', 'vamos', 'veas', 'venir', 'ver', 'verbo', 'verdad',
    'vez', 'vida', 'y', 'ya', 'yo', 'éxito'
}

#: Historical alias. Four modules called their local copy SPANISH_COMMON;
#: keeping that name importable means their call sites did not have to change.
SPANISH_COMMON = SPANISH_FILTER


# ============== AUDIO UTILITIES ==============

# Threshold for locating the edge of speech inside a clip.
#
# THE SINGLE SOURCE. src/qa_gate.py imports this rather than keeping its own
# copy, so the number the generator DECLARES and the number the gate MEASURES
# can never drift apart — which is the whole failure mode this project has
# been unwinding, and exactly what five forked Spanish stoplists cost us.
#
# Calibrated empirically, not guessed; full derivation in
# docs/qa-gate-calibration.md. -45 dB sits ~5 dB above the loudest silence
# observed in either TTS model and ~27 dB below speech.
SPEECH_EDGE_THRESHOLD_DB = -45.0
SPEECH_EDGE_MIN_DUR = 0.10


def measure_speech_end(audio_path: str, threshold_db: float = None,
                       min_dur: float = None) -> float:
    """Offset inside a clip where SPEECH ends, ignoring trailing silence.

    A TTS clip does not end when its speech ends — the model leaves anywhere
    from 0.3 to 1.3 s of trailing silence in the file. Recording the FILE end
    as the segment end makes the renderer hold text on screen long after the
    voice has stopped. Measured over the corpus: quiz option ends overran by
    0.32-0.42 s, `think` by 0.245 s, and old-generator educational segments by
    up to 1.29 s.

    The audio is NOT trimmed. Trailing silence is real pacing and stays in the
    mix; only the DECLARED end changes, so the renderer follows the voice
    instead of the file.

    Falls back to the full duration when no speech edge is found — a clip that
    is silent throughout, or one ffmpeg cannot parse, must not silently report
    a zero-length segment.
    """
    import re
    import subprocess

    threshold_db = SPEECH_EDGE_THRESHOLD_DB if threshold_db is None else threshold_db
    min_dur = SPEECH_EDGE_MIN_DUR if min_dur is None else min_dur

    duration = get_audio_duration(audio_path)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", audio_path, "-af",
             f"silencedetect=noise={threshold_db}dB:d={min_dur}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return duration

    # Trailing silence is the LAST silence region, provided it runs to the end
    # of the file. Do not look for an unterminated silence_start — ffmpeg
    # closes the final region at EOF (verified on 8.0.1: 27 starts, 27 ends),
    # so an "open start" heuristic silently never fires and every clip reports
    # its full duration.
    spans, start = [], None
    for kind, value in re.findall(r"silence_(start|end):\s*(-?[\d.]+)", proc.stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            spans.append((start, float(value)))
            start = None
    if start is not None:                      # genuinely unterminated
        spans.append((start, duration))

    if not spans:
        return duration

    last_start, last_end = spans[-1]
    if last_end >= duration - 0.05 and last_start > 0:
        return min(last_start, duration)
    return duration


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

    # 1. Normalize typographic quotes to straight ones.
    #
    # EXACT TWIN of the bug fixed in script_generator: the first line was
    # .replace("'", "'"), apostrophe to apostrophe, a no-op; the second read
    # .replace(""", '"'), in which Python sees a TRIPLE-quoted string and the
    # statement collapses to replacing the literal substring `, '"').replace(`
    # with `"`. Neither has ever normalized anything, so smart quotes have
    # always reached the TTS models raw.
    #
    # Written as \u escapes so an editor cannot silently de-smarten them back
    # into a no-op, which is how the original was born.
    _SMART_APOS = "\u2018\u2019\u201a\u201b\u2032"
    _SMART_DBL = "\u201c\u201d\u201e\u201f\u2033"
    text = text.translate({ord(c): "'" for c in _SMART_APOS}
                          | {ord(c): '"' for c in _SMART_DBL})

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

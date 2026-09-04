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
import os
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
# RAISED BACK 0.15 -> 0.40 now that clip-intrinsic silence is trimmed.
#
# 0.15 was a compromise forced by silence we did not control: with each clip
# carrying 0.5-1.4s of its own trailing quiet, the only way to shorten the
# block was to shrink the deliberate gaps. Trimming removes ~4.3s of that, so
# the gaps can be what they should be.
#
# 0.40 keeps the ORDERING intact — the gap between two options must read as
# larger than the gap inside one, or the label stops grouping with its word.
# With the clips trimmed, the measured gaps are now essentially the constants
# themselves (the deliberate 0.08s tail sits below silencedetect's 0.10s
# window), so 0.40 vs 0.30 is a real 1.33:1 separation rather than one masked
# by whatever silence the model happened to emit.
#
# The prediction that 0.15 would invert the ordering was refuted at the time
# ONLY because clip trailing silence was inflating the between-option gap.
# Remove that and the prediction holds, which is why this goes back up in the
# SAME commit as the trim rather than after it.
PAUSE_BETWEEN_OPTIONS = 0.40
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


#: Deliberate tail left on every trimmed clip.
#:
#: NOT zero. Trimming to the exact speech end cuts the decay of a final
#: consonant — the release of a plosive, the fade of a fricative — and sounds
#: clipped. 0.08s preserves it.
#:
#: It is also deliberately BELOW SPEECH_EDGE_MIN_DUR (0.10s), so the tail we
#: leave is shorter than silencedetect's own detection window. The tail
#: therefore never registers as a silence region, which means the gaps a
#: listener and the QA gate measure are exactly the spliced constants —
#: deterministic by construction rather than by luck.
TRIM_TAIL_PAD = 0.08

#: Leading silence is already small (0-0.096s measured), so this only avoids
#: clipping the attack of the first phoneme.
TRIM_LEAD_PAD = 0.02


def measure_speech_start(audio_path: str, threshold_db: float = None,
                         min_dur: float = 0.03) -> float:
    """Offset where speech STARTS, i.e. the length of the leading silence.

    Uses a shorter min_dur than measure_speech_end because leading silence is
    an order of magnitude smaller — measured 0.000s to 0.096s across real
    option clips, all of which would be invisible at the 0.10s window.
    """
    import re
    import subprocess

    threshold_db = SPEECH_EDGE_THRESHOLD_DB if threshold_db is None else threshold_db
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", audio_path, "-af",
             f"silencedetect=noise={threshold_db}dB:d={min_dur}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return 0.0

    spans, start = [], None
    for kind, value in re.findall(r"silence_(start|end):\s*(-?[\d.]+)", proc.stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            spans.append((start, float(value)))
            start = None
    # Leading silence only counts if it begins at the very top of the file.
    if spans and spans[0][0] <= 0.02:
        return spans[0][1]
    return 0.0


def trim_clip_silence(audio_path: str, out_path: str = None) -> dict:
    """Trim a TTS clip to its speech, leaving TRIM_TAIL_PAD at the end.

    WHY: measured across nine real option clips, 4.87s of 13.36s — 36% — was
    leading or trailing silence, and the word clips were up to 67% silence
    ("dessert." is 0.743s of speech in a 2.160s file). That silence is also
    NON-REPRODUCIBLE: the same script produced 1.957s of it on one run and
    2.916s on another, which made block duration unmeasurable.

    NEVER CUTS SPEECH. The trim is computed from measured boundaries and then
    verified: if the trimmed clip does not retain the speech the original had,
    the original is kept and a warning is logged. Losing a word to save 200ms
    is not a trade worth making silently.

    Returns a dict describing what happened, so a caller can log or assert on
    it rather than trusting that it worked.
    """
    import subprocess

    out_path = out_path or audio_path
    before = get_audio_duration(audio_path)
    lead = measure_speech_start(audio_path)
    speech_end = measure_speech_end(audio_path)

    start = max(0.0, lead - TRIM_LEAD_PAD)
    end = min(before, speech_end + TRIM_TAIL_PAD)
    result = {"path": audio_path, "before": before, "lead": lead,
              "speech_end": speech_end, "start": start, "end": end,
              "trimmed": False, "after": before, "reason": None}

    if end - start < 0.05:
        result["reason"] = "would leave under 50ms; refusing"
        return result
    if before - (end - start) < 0.02:
        result["reason"] = "nothing meaningful to remove"
        return result

    tmp = f"{out_path}.trim.mp3"
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}",
             "-to", f"{end:.3f}", "-i", audio_path, "-c:a", "libmp3lame",
             "-q:a", "2", "-ar", "44100", "-ac", "1", tmp],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0 or not os.path.exists(tmp):
            result["reason"] = f"ffmpeg failed: {proc.stderr[:120]}"
            return result

        # OVER-TRIM GUARD. Compare the speech actually retained against the
        # speech the original carried; a shortfall means we cut into it.
        orig_speech = speech_end - lead
        new_speech = measure_speech_end(tmp) - measure_speech_start(tmp)
        if new_speech + 0.05 < orig_speech:
            logger.warning("trim would lose speech in %s (%.3fs -> %.3fs); keeping original",
                           audio_path, orig_speech, new_speech)
            result["reason"] = "over-trim guard tripped"
            os.remove(tmp)
            return result

        os.replace(tmp, out_path)
        result.update(trimmed=True, after=get_audio_duration(out_path))
        return result
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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


# ── punctuation-only tokens in a word timeline ───────────────────────────
#
# ElevenLabs' character alignment returns punctuation as SEPARATE tokens
# with their own start and end, because _chars_to_words splits on
# whitespace and "hola , que" really does contain a lone comma. Nothing
# merged them back, so a token whose entire content is a mark survived into
# the word timeline and was treated as a word.
#
# The visible damage was in the karaoke — cards opening on ", que significa
# uno", a period highlighted on its own after "a different size?", quote
# marks floating as words in "' four ' balloons".
#
# THE INVISIBLE DAMAGE IS THE REASON THIS IS FIXED IN THE TIMELINE AND NOT
# IN THE GROUPER. An orphan token carries its own SPAN, and those spans feed
# measure_speech_end, the declared-silence envelope and the QA gate. The C
# work measured '(noun)' holding 3.07 -> 4.12 — 1.05 s of declared speech
# for something never said. Fixing only the display would have left the
# timing polluted and the gate still reading a span that is not speech.

#: Unicode categories that make a token punctuation rather than content.
#: Symbol categories are included because '=' shows up as a token: the
#: script generator writes mnemonics like "Assure = promise" into
#: full_script and the narrator is handed an equals sign to say.
_PUNCT_CATEGORIES = ("Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps", "Sm", "Sk", "So")


def is_punctuation_token(token) -> bool:
    """True when a token's ENTIRE content is punctuation or symbols."""
    import unicodedata

    text = str(token or "").strip()
    if not text:
        return False
    return all(unicodedata.category(ch) in _PUNCT_CATEGORIES for ch in text)


def merge_punctuation_tokens(words, boundary_key: str = "segment_id"):
    """Absorb punctuation-only tokens into the neighbouring real word.

    NO TOKEN IS DROPPED AND NO TIME IS LOST. The mark is appended to the
    preceding word, which keeps its own start and takes the punctuation's
    end, so the span is absorbed rather than deleted and the timeline still
    covers the same audio. A mark with no preceding word in its segment is
    merged into the FOLLOWING word instead, which then takes the
    punctuation's start.

    Segment boundaries are respected when the words carry `boundary_key`,
    so a period ending one sentence never attaches itself to the first word
    of the next.
    """
    out = []
    pending = []          # leading marks waiting for a word to attach to
    for item in words or []:
        if not isinstance(item, dict) or "word" not in item:
            out.append(item)
            continue

        same_segment = bool(out) and (
            boundary_key is None
            or item.get(boundary_key) == out[-1].get(boundary_key))

        if is_punctuation_token(item["word"]):
            if out and same_segment:
                previous = out[-1]
                previous["word"] = f"{previous['word']}{str(item['word']).strip()}"
                previous["end"] = max(float(previous["end"]), float(item["end"]))
            else:
                pending.append(item)
            continue

        merged = dict(item)
        if pending:
            # No preceding word in this segment: the marks lead instead.
            merged["word"] = "".join(
                str(p["word"]).strip() for p in pending) + str(merged["word"])
            merged["start"] = min([float(merged["start"])]
                                  + [float(p["start"]) for p in pending])
            pending = []
        out.append(merged)

    # Trailing marks with nothing after them: give them to the last word.
    for item in pending:
        if out:
            out[-1]["word"] = f"{out[-1]['word']}{str(item['word']).strip()}"
            out[-1]["end"] = max(float(out[-1]["end"]), float(item["end"]))
        else:
            out.append(item)
    return out

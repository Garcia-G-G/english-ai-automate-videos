#!/usr/bin/env python3
"""
ElevenLabs TTS Module for English AI Video Generator

Uses ElevenLabs API for high-quality bilingual speech synthesis.
Uses eleven_multilingual_v2 model for Spanish/English support.

Advantages:
- Excellent Spanish pronunciation
- Natural bilingual flow with human-like delivery
- SSML break tags for natural pauses (breathing, hesitation)
- Speed control for clearer educational content
- High quality voices
- Consistent output
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.types import VoiceSettings

from tts_common import (
    get_audio_duration, generate_silence,
    extract_english_words_from_script,
    PAUSE_AFTER_QUESTION, PAUSE_AFTER_OPTION, PAUSE_AFTER_THINK,
    PAUSE_AFTER_ANSWER, PAUSE_AFTER_EXPLANATION,
)

# Load environment variables (override=True so .env always wins over stale process env)
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# ElevenLabs configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Voice IDs (you can get these from ElevenLabs dashboard)
# Popular multilingual voices:
VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",      # Female, warm
    "bella": "EXAVITQu4vr4xnSDxMaL",        # Female, soft
    "antoni": "ErXwobaYiN019PkySvjV",       # Male, warm
    "josh": "TxGEqnHWrfWFTfGW9XjX",         # Male, deep
    "arnold": "VR6AewLTigWG4xSOukaG",       # Male, crisp
    "adam": "pNInz6obpgDQGcFmaJgB",         # Male, deep
    "sam": "yoZ06aMxZJJ28mfd3POQ",          # Male, raspy
    "nicole": "piTKgcLEGmPE4e6mEKli",       # Female, whisper
    "matilda": "XrExE9yKIg1WjnnlVkGX",      # Female, warm
    "english-teacher": "ZOgeDYxfyev5qgOXq2lN",  # Custom, bilingual teacher
}

# Default voice (english-teacher - custom bilingual educational voice)
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "ZOgeDYxfyev5qgOXq2lN")

# Model — eleven_v3: best quality, 74 languages, emotional control via text cues
# NOTE: v3 does NOT support SSML <break> tags — use "..." or narrative text for pauses
MODEL_ID = "eleven_v3"

# ============== VOICE SETTINGS ==============
# Stability 0.50: expressive enough to sound human, stable enough to avoid
#   hallucinated mini-words / random vocalizations
# Style 0.05: minimal — just enough warmth, prevents filler-sound artifacts
DEFAULT_STABILITY = 0.50
DEFAULT_SIMILARITY = 0.80
DEFAULT_STYLE = 0.05
DEFAULT_SPEAKER_BOOST = True

# ============== SPEED CONTROL ==============
# All 1.0 — ElevenLabs v3 handles pacing naturally.
# Structure kept so we can fine-tune individual segments later.
GLOBAL_SPEED = 1.0
SEGMENT_SPEEDS = {
    'question':     1.0,
    'transition':   1.0,
    'options':      1.0,
    'english_word': 1.0,
    'answer':       1.0,
    'explanation':  1.0,
    'think':        1.0,
    'default':      1.0,
}

# ============== NATURAL SPEECH HELPERS ==============
# eleven_v3 does NOT support SSML <break> tags.
# Use text-based cues: "..." for pauses, natural punctuation.

MAX_PAUSE_MARKERS = 5  # Cap on "..." markers to avoid instability

def add_natural_pauses(text: str, segment_type: str = 'default') -> str:
    """
    Add text-based pause cues for eleven_v3 model.

    Uses "..." for pauses (v3 interprets these as natural hesitation).
    Keeps it minimal to avoid artifacts — max MAX_PAUSE_MARKERS ellipses.

    Args:
        text: Raw text to enhance
        segment_type: Type of segment for context-aware pausing

    Returns:
        Text with natural pause cues inserted
    """
    if not text or not text.strip():
        return text

    # --- 1. Pause before answer reveal ---
    if segment_type == 'answer':
        text = text.replace(
            'La respuesta es',
            '... La respuesta es'
        )
        text = text.replace('Correcto.', 'Correcto...')

    # --- 2. Pause between sentences in explanations ---
    if segment_type == 'explanation':
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) > 1:
            text = ' ... '.join(sentences)

    # --- 3. Pause after transition phrase ---
    if segment_type == 'transition' or 'Escucha las opciones' in text:
        text = text.replace(
            'Escucha las opciones.',
            'Escucha las opciones...'
        )

    # --- 4. Pause between options ---
    if segment_type == 'options' or 'Opción' in text:
        text = re.sub(
            r'(Opción [A-D0-4],\s*[^.]+\.)\s+(Opción)',
            r'\1 ... \2',
            text
        )

    # --- Safety cap: limit total "..." markers ---
    count = text.count('...')
    if count > MAX_PAUSE_MARKERS:
        # Remove excess markers starting from the end
        while text.count('...') > MAX_PAUSE_MARKERS:
            # Find last "..." and replace with single space
            idx = text.rfind('...')
            text = text[:idx] + ' ' + text[idx + 3:]

    # Clean up multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()


def enhance_bilingual_text(text: str, english_words: set) -> str:
    """
    Enhance text for correct bilingual pronunciation.

    For eleven_v3, the model handles code-switching well,
    but we can help it by:
    1. Replacing commonly mispronounced English words with phonetic hints
    2. Keeping English words clearly separated (no SSML — v3 doesn't support it)

    Args:
        text: Text containing Spanish and English
        english_words: Set of words that should be pronounced in English

    Returns:
        Enhanced text optimized for bilingual TTS
    """
    if not english_words or not text:
        return text

    # Phonetic spelling hints for words the Spanish model commonly
    # mispronounces. Only applied to detected English teaching words.
    PRONUNCIATION_HINTS = {
        'comfortable': 'cómfortable',
        'vegetable': 'végetable',
        'wednesday': 'wénzday',
        'february': 'fébruary',
        'library': 'láibrary',
        'recipe': 'résipee',
        'schedule': 'skéjool',
        'breakfast': 'brékfast',
        'through': 'thruu',
        'tough': 'tuff',
        'enough': 'enúff',
        'thought': 'thot',
        'although': 'olthóu',
    }

    for word in english_words:
        if word.lower() in text.lower():
            pattern = re.compile(
                r'(?<!\w)(' + re.escape(word) + r')(?!\w)',
                re.IGNORECASE
            )

            hint = PRONUNCIATION_HINTS.get(word.lower())
            if hint:
                text = pattern.sub(hint, text)

    return text

def get_client() -> ElevenLabs:
    """Get ElevenLabs client."""
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY not set in environment")
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)


def estimate_word_timestamps(text: str, duration: float, english_phrases: list = None) -> tuple:
    """
    Estimate word-level timestamps from text and audio duration.

    Splits by sentences first, then distributes words proportionally
    within each sentence.  Each word gets segment_id and segment_end
    fields so the video renderer can group words by sentence without
    needing add_sentence_boundaries().

    Args:
        text: Original full_script text (NOT TTS-cleaned)
        duration: Total audio duration in seconds
        english_phrases: List of English phrases for is_english detection

    Returns:
        (words, segments) — lists ready for the video renderer
    """
    if not text or not text.strip():
        return [], []

    # Build english set for is_english detection
    # Filter: only use short phrases (≤5 words) — longer ones are likely bad data
    # Also exclude common Spanish words that often leak in
    SPANISH_COMMON = {
        'a', 'al', 'algo', 'alguien', 'ante', 'así', 'bien', 'bueno',
        'cada', 'casa', 'casi', 'como', 'con', 'cual', 'cuando',
        'de', 'del', 'decir', 'donde', 'el', 'ella', 'en', 'era',
        'es', 'esa', 'ese', 'eso', 'esta', 'estar', 'este', 'esto',
        'forma', 'fue', 'hay', 'hoy', 'ir', 'la', 'las', 'le', 'les',
        'lo', 'los', 'más', 'me', 'mi', 'muy', 'nada', 'ni', 'no',
        'nos', 'o', 'otra', 'otro', 'para', 'pero', 'por', 'puede',
        'que', 'quien', 'se', 'ser', 'si', 'sin', 'sobre', 'son',
        'su', 'sus', 'tan', 'te', 'ti', 'tiene', 'todo', 'tu', 'tus',
        'un', 'una', 'uno', 'usar', 'usa', 'usan', 'va', 'vamos',
        'ver', 'vez', 'vida', 'y', 'ya', 'yo', 'palabra', 'ejemplo',
        'recuerda', 'cuando', 'veas', 'entonces', 'también', 'ahora',
        'aceptar', 'invitación', 'divertida', 'casual',
    }
    english_set = set()
    if english_phrases:
        for phrase in english_phrases:
            phrase_words = phrase.lower().split()
            if len(phrase_words) > 5:
                continue  # Skip long phrases — likely bad AI data
            for w in phrase_words:
                cleaned = re.sub(r'[^\w]', '', w)
                if cleaned and cleaned not in SPANISH_COMMON:
                    english_set.add(cleaned)

    # Split text into sentences — same regex as add_sentence_boundaries()
    sentence_pattern = r'(?<=[.!?])\s+|\s+(?=[¿¡])'
    sentences = [s.strip() for s in re.split(sentence_pattern, text.strip()) if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    # Build per-sentence word lists and total character count
    sentence_word_lists = []
    total_chars = 0
    for sent in sentences:
        sent_words = sent.split()
        sentence_word_lists.append(sent_words)
        for w in sent_words:
            total_chars += len(w) + 1  # +1 for inter-word gap

    if total_chars == 0:
        return [], []

    buffer = 0.15
    usable = max(0.5, duration - 2 * buffer)

    words = []
    segments = []
    current_time = buffer

    for sent_idx, (sentence, sent_words) in enumerate(zip(sentences, sentence_word_lists)):
        if not sent_words:
            continue

        # This sentence's share of total time (proportional to char count)
        sent_chars = sum(len(w) + 1 for w in sent_words)
        sent_duration = (sent_chars / total_chars) * usable

        word_time = current_time
        sent_start = current_time

        for word_idx, raw_word in enumerate(sent_words):
            # Filter out "..." pause markers that might have leaked in
            stripped = raw_word.strip('.,!?¿¡:;\'"')
            if stripped in ('...', '..', '') or set(stripped) == {'.'}:
                continue

            word_dur = ((len(raw_word) + 1) / sent_chars) * sent_duration
            word_dur = max(0.08, word_dur)  # minimum 80ms per word

            is_last = (word_idx == len(sent_words) - 1)
            word_clean = re.sub(r'[^\w]', '', raw_word).lower()

            words.append({
                'word': raw_word,
                'start': round(word_time, 3),
                'end': round(word_time + word_dur, 3),
                'is_english': word_clean in english_set,
                'segment_id': sent_idx,
                'segment_end': is_last,
            })
            word_time += word_dur

        sent_end = word_time
        segments.append({
            'start': round(sent_start, 3),
            'end': round(sent_end, 3),
            'text': sentence,
        })
        current_time = sent_end

    logger.info("Estimated %d word timestamps and %d segments from %.2fs audio",
                len(words), len(segments), duration)
    return words, segments


def _elevenlabs_with_retry(client, output_path: str, max_retries: int = 3, **kwargs) -> None:
    """Call ElevenLabs TTS API with exponential backoff retry."""
    import time as _time

    # Track cost
    try:
        from cost_tracker import get_tracker
        text = kwargs.get('text', '')
        model_id = kwargs.get('model_id', 'eleven_v3')
        get_tracker().log_elevenlabs_tts(characters=len(text), model=model_id, label="tts_segment")
    except Exception:
        pass

    for attempt in range(max_retries):
        try:
            audio_generator = client.text_to_speech.convert(**kwargs)
            with open(output_path, 'wb') as f:
                for chunk in audio_generator:
                    f.write(chunk)
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning("ElevenLabs attempt %d failed (%s), retrying in %ds...", attempt + 1, e, wait)
            _time.sleep(wait)


def generate_segment_audio(
    text: str,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
    style: float = DEFAULT_STYLE,
    use_speaker_boost: bool = DEFAULT_SPEAKER_BOOST,
    speed: float = None,
    segment_type: str = 'default',
    english_words: set = None,
    humanize: bool = True,
) -> float:
    """
    Generate a single audio segment using ElevenLabs TTS.

    Now with natural speech enhancements:
    - SSML break tags for breathing pauses
    - Per-segment speed control
    - Bilingual pronunciation hints
    - Human-like delivery with micro-pauses

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice_id: ElevenLabs voice ID
        stability: Voice stability (0-1, lower = more expressive)
        similarity_boost: Similarity to original voice (0-1)
        style: Style exaggeration (0-1, subtle warmth)
        use_speaker_boost: Enable speaker boost for clarity
        speed: Speech speed (0.7-1.2, default from SEGMENT_SPEEDS)
        segment_type: Type of segment for context-aware enhancements
        english_words: Set of English words for bilingual pronunciation
        humanize: Whether to add natural pauses and breathing (default True)

    Returns:
        Duration in seconds
    """
    client = get_client()
    voice_id = voice_id or DEFAULT_VOICE_ID

    # Determine speed: explicit > per-segment > global
    if speed is None:
        speed = SEGMENT_SPEEDS.get(segment_type, GLOBAL_SPEED)

    # Apply humanization: natural pauses, breathing, emphasis
    if humanize:
        text = add_natural_pauses(text, segment_type)

    # Enhance bilingual pronunciation
    if english_words:
        text = enhance_bilingual_text(text, english_words)

    logger.debug("TTS [%s] speed=%.2f text='%s'", segment_type, speed, text[:80])

    # Clamp speed to ElevenLabs range
    speed = max(0.7, min(1.2, speed))

    _elevenlabs_with_retry(
        client, output_path,
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        voice_settings=VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            speed=speed,
        ),
        output_format="mp3_44100_128",
    )

    duration = get_audio_duration(output_path)
    if duration <= 0:
        raise RuntimeError(f"ElevenLabs TTS produced zero-length audio for: {text[:60]}")
    return duration


def generate_quiz_audio_segmented(
    script: dict,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
) -> dict:
    """
    Generate quiz audio using ElevenLabs TTS.

    Uses segment-based architecture:
    1. Pre-recorded standard phrases (if available)
    2. Fresh TTS for: question, options (combined), answer, explanation
    3. Assembly via ffmpeg concatenation

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    voice_id = voice_id or DEFAULT_VOICE_ID

    # Extract script data
    from tts_common import clean_for_tts
    question = clean_for_tts(script.get('question', '').replace('¿', '').replace('?', '?'))
    options = script.get('options', {})
    correct = script.get('correct', 'A')
    explanation = clean_for_tts(script.get('explanation', ''))

    # Get correct answer text
    correct_text = clean_for_tts(options.get(correct, '').strip("'\""))

    # Extract English words
    english_words = extract_english_words_from_script(script)
    logger.info("English words detected: %s", english_words)

    # Create temp directory for assembly
    with tempfile.TemporaryDirectory() as temp_dir:
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
            logger.debug("[%s] %s...", seg_id, text[:50])
            logger.debug("  %0.2fs - %0.2fs (%0.2fs)", start, end, end - start)
            return segment

        logger.info("=" * 60)
        logger.info("ELEVENLABS TTS - QUIZ AUDIO (HUMANIZED)")
        logger.info("=" * 60)
        logger.info("Voice ID: %s", voice_id)
        logger.info("Model: %s", MODEL_ID)
        logger.info("Global speed: %.2f", GLOBAL_SPEED)
        logger.info("English words: %s", english_words)

        # ============================================================
        # 1. QUESTION
        # ============================================================
        logger.info("[1] QUESTION")
        q_path = os.path.join(temp_dir, "question.mp3")
        generate_segment_audio(
            text=question,
            output_path=q_path,
            voice_id=voice_id,
            stability=stability,
            similarity_boost=similarity_boost,
            segment_type='question',
            english_words=english_words,
        )
        q_start, q_end, _ = add_audio(q_path)
        add_segment('question', question, q_start, q_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # ============================================================
        # 2-3. TRANSITION + OPTIONS (COMBINED)
        # Generate all options in ONE call for consistency
        # ============================================================
        logger.info("[2-3] OPTIONS (combined)")

        # Build combined text with natural pauses between options
        option_lines = ["Escucha las opciones."]
        option_words = {}
        for letter in ['A', 'B', 'C', 'D']:
            word = options.get(letter, '').strip("'\"")
            option_words[letter] = word
            option_lines.append(f"Opción {letter}, {word}.")

        combined_text = " ".join(option_lines)
        logger.debug("Combined text (%d chars):", len(combined_text))
        for line in option_lines:
            logger.debug("  %s", line)

        # Generate combined options with natural pauses
        combined_path = os.path.join(temp_dir, "options_combined.mp3")
        generate_segment_audio(
            text=combined_text,
            output_path=combined_path,
            voice_id=voice_id,
            stability=stability,
            similarity_boost=similarity_boost,
            segment_type='options',
            english_words=english_words,
        )

        combined_duration = get_audio_duration(combined_path)
        logger.debug("Combined duration: %.2fs", combined_duration)

        # Add combined audio
        combined_start = running_time
        add_audio(combined_path)

        # Estimate segment times
        transition_duration = 1.5
        options_duration = combined_duration - transition_duration
        per_option = options_duration / 4

        add_segment('transition', 'Escucha las opciones.',
                   combined_start, combined_start + transition_duration)

        for i, letter in enumerate(['A', 'B', 'C', 'D']):
            opt_start = combined_start + transition_duration + (i * per_option)
            opt_end = opt_start + per_option
            add_segment(f'option_{letter.lower()}',
                       f"Opción {letter}, {option_words[letter]}.",
                       opt_start, opt_end)

        add_silence(PAUSE_AFTER_OPTION)

        # ============================================================
        # 4. THINK (always generated dynamically for voice consistency)
        # ============================================================
        logger.info("[4] THINK")
        think_gen_path = os.path.join(temp_dir, "think.mp3")
        generate_segment_audio(
            "¡Piensa bien!", think_gen_path, voice_id,
            segment_type='think',
        )
        think_start, think_end, _ = add_audio(think_gen_path)
        add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # ============================================================
        # 5. COUNTDOWN (VISUAL ONLY - audio is silent)
        # The countdown numbers appear on screen during this silence.
        # Total silence: ~7s (1.5s pre + 3 x 1.5s intervals + 1.0s before answer)
        # ============================================================
        logger.info("[5] COUNTDOWN (visual only, audio silence)")
        countdown_interval = 1.5  # 1.5 seconds per number for full visual display
        for num in ['3', '2', '1']:
            cd_start = running_time
            add_silence(countdown_interval)
            cd_end = running_time
            add_segment(f'countdown_{num}', f'[{num}]', cd_start, cd_end)
            logger.info("  [countdown_%s] %.2fs - %.2fs (silent)", num, cd_start, cd_end)

        # Dramatic pause before answer reveal - ensures "1" fully displays
        add_silence(1.0)

        # ============================================================
        # 6. ANSWER (with emphasis and natural delivery)
        # ============================================================
        logger.info("[6] ANSWER")
        answer_start = running_time
        full_answer_text = f"Correcto. La respuesta es {correct}, {correct_text}."
        logger.debug("Answer: '%s'", full_answer_text)

        ans_path = os.path.join(temp_dir, "answer.mp3")
        generate_segment_audio(
            full_answer_text, ans_path, voice_id,
            segment_type='answer',
            english_words=english_words,
        )
        add_audio(ans_path)

        answer_end = running_time
        add_segment('answer', full_answer_text, answer_start, answer_end)
        add_silence(PAUSE_AFTER_ANSWER)

        # ============================================================
        # 7. EXPLANATION (conversational, warm delivery)
        # ============================================================
        if explanation.strip():
            logger.info("[7] EXPLANATION")
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            generate_segment_audio(
                text=explanation,
                output_path=exp_path,
                voice_id=voice_id,
                stability=stability,
                similarity_boost=similarity_boost,
                segment_type='explanation',
                english_words=english_words,
            )
            exp_start, exp_end, _ = add_audio(exp_path)
            add_segment('explanation', explanation, exp_start, exp_end)
            add_silence(PAUSE_AFTER_EXPLANATION)

        total_duration = running_time
        logger.info("=" * 60)
        logger.info("Total duration: %.2fs", total_duration)
        logger.info("=" * 60)

        # ============================================================
        # CONCATENATE
        # ============================================================
        logger.info("Concatenating audio files...")
        concat_list_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_list_path, 'w') as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file}'\n")

        # Concatenate with re-encoding to ensure compatibility
        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_list_path,
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-ar', '44100', '-ac', '1',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("FFmpeg error: %s", result.stderr)
            raise RuntimeError(f"FFmpeg concatenation failed: {result.stderr}")

        logger.info("Audio saved: %s", output_path)

        # Build result
        segment_times = {seg['id']: {
            'start': seg['start'],
            'end': seg['end'],
            'duration': seg['duration']
        } for seg in segments}

        result = {
            'duration': total_duration,
            'segments': segments,
            'segment_times': segment_times,
            'type': 'quiz',
            'question': script.get('question', ''),
            'options': options,
            'correct': correct,
            'explanation': explanation,
            'full_script': script.get('full_script', ''),
            'translations': script.get('translations', {}),
            'hashtags': script.get('hashtags', []),
            'words': [],
            '_meta': script.get('_meta', {}),
        }

        # Save timestamps JSON
        json_path = output_path.replace('.mp3', '.json')
        import json
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("Timestamps saved: %s", json_path)

        return result


def generate_fill_blank_audio_segmented(
    script: dict,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
) -> dict:
    """
    Generate fill-in-the-blank audio using ElevenLabs TTS.

    Segments:
    1. sentence - The sentence with blank read aloud
    2. options - All options read together
    3. think - "Piensa bien" (generated dynamically)
    4. countdown_3/2/1 - VISUAL ONLY (silent), 1.5s each
    5. answer - "La respuesta correcta es X"
    6. explanation - The explanation

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    import shutil
    voice_id = voice_id or DEFAULT_VOICE_ID

    from tts_common import clean_for_tts

    sentence = script.get('sentence', '')
    options = script.get('options', [])
    correct = script.get('correct', '')
    explanation = script.get('explanation', '')
    translation = script.get('translation', '')

    clean_sentence = clean_for_tts(sentence)
    english_words = extract_english_words_from_script(script)

    temp_dir = tempfile.mkdtemp(prefix="el_fb_segments_")

    try:
        logger.info("=" * 60)
        logger.info("ELEVENLABS TTS - FILL-IN-THE-BLANK AUDIO")
        logger.info("=" * 60)

        segments = []
        audio_files = []
        running_time = 0.0

        def add_audio(path: str, duration: float = None):
            nonlocal running_time
            if duration is None:
                duration = get_audio_duration(path)
            audio_files.append(path)
            start = running_time
            running_time += duration
            return start, running_time, duration

        def add_silence(dur: float):
            nonlocal running_time
            silence_path = os.path.join(temp_dir, f"silence_{len(audio_files)}.mp3")
            generate_silence(dur, silence_path)
            audio_files.append(silence_path)
            running_time += dur

        def add_segment(seg_id: str, text: str, start: float, end: float):
            segment = {
                'id': seg_id,
                'text': text,
                'start': round(start, 3),
                'end': round(end, 3),
                'duration': round(end - start, 3),
            }
            segments.append(segment)
            logger.info("  [%s] %s...", seg_id, text[:50])
            return segment

        # 1. SENTENCE
        logger.info("[1] SENTENCE")
        sentence_text = f"¿Cómo completarías esta frase? {clean_sentence}"
        s_path = os.path.join(temp_dir, "sentence.mp3")
        generate_segment_audio(
            text=sentence_text, output_path=s_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='question', english_words=english_words,
        )
        s_start, s_end, _ = add_audio(s_path)
        add_segment('sentence', sentence_text, s_start, s_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # 2. OPTIONS
        logger.info("[2] OPTIONS")
        option_lines = ["Aquí van las opciones."]
        for i, opt in enumerate(options[:4]):
            option_lines.append(f"Opción {i+1}, {opt}.")
        combined_text = " ".join(option_lines)

        opt_path = os.path.join(temp_dir, "options.mp3")
        generate_segment_audio(
            text=combined_text, output_path=opt_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='options', english_words=english_words,
        )
        opt_start, opt_end, _ = add_audio(opt_path)
        add_segment('options', combined_text, opt_start, opt_end)
        add_silence(PAUSE_AFTER_OPTION)

        # 3. THINK
        logger.info("[3] THINK")
        think_path = os.path.join(temp_dir, "think.mp3")
        generate_segment_audio(
            "¡Piensa bien!", think_path, voice_id, segment_type='think',
        )
        think_start, think_end, _ = add_audio(think_path)
        add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # 4. COUNTDOWN (VISUAL ONLY - silent)
        logger.info("[4] COUNTDOWN (visual only, audio silence)")
        countdown_interval = 1.5
        for num in ['3', '2', '1']:
            cd_start = running_time
            add_silence(countdown_interval)
            cd_end = running_time
            add_segment(f'countdown_{num}', f'[{num}]', cd_start, cd_end)
            logger.info("  [countdown_%s] %.2fs - %.2fs (silent)", num, cd_start, cd_end)

        # Dramatic pause before answer
        add_silence(1.0)

        # 5. ANSWER
        logger.info("[5] ANSWER")
        answer_text = f"La respuesta correcta es '{correct}'."
        ans_path = os.path.join(temp_dir, "answer.mp3")
        generate_segment_audio(
            text=answer_text, output_path=ans_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='answer', english_words=english_words,
        )
        ans_start, ans_end, _ = add_audio(ans_path)
        add_segment('answer', answer_text, ans_start, ans_end)
        add_silence(PAUSE_AFTER_ANSWER)

        # 6. EXPLANATION
        if explanation.strip():
            logger.info("[6] EXPLANATION")
            clean_explanation = clean_for_tts(explanation)
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            generate_segment_audio(
                text=clean_explanation, output_path=exp_path, voice_id=voice_id,
                stability=stability, similarity_boost=similarity_boost,
                segment_type='explanation', english_words=english_words,
            )
            exp_start, exp_end, _ = add_audio(exp_path)
            add_segment('explanation', clean_explanation, exp_start, exp_end)
            add_silence(PAUSE_AFTER_EXPLANATION)

        total_duration = running_time
        logger.info("=" * 60)
        logger.info("Total duration: %.2fs", total_duration)
        logger.info("=" * 60)

        # Concatenate
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
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-ar', '44100', '-ac', '1',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

        logger.info("Audio saved: %s", output_path)

        segment_times = {seg['id']: {'start': seg['start'], 'end': seg['end'], 'duration': seg['duration']} for seg in segments}

        result_data = {
            'duration': round(total_duration, 3),
            'segments': segments,
            'segment_times': segment_times,
            'type': 'fill_blank',
            'sentence': sentence,
            'options': options,
            'correct': correct,
            'explanation': explanation,
            'translation': translation,
            'full_script': script.get('full_script', ''),
            'translations': script.get('translations', {}),
            'hashtags': script.get('hashtags', []),
            'words': [],
            '_meta': script.get('_meta', {}),
        }

        # Save timestamps JSON
        import json
        json_path = output_path.replace('.mp3', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        logger.info("Timestamps saved: %s", json_path)

        return result_data

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def generate_true_false_audio_segmented(
    script: dict,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
) -> dict:
    """
    Generate true/false audio using ElevenLabs TTS.

    Segments:
    1. statement - The statement to evaluate
    2. options - "¿Verdadero o falso?"
    3. think - "Piensa bien" (generated dynamically)
    4. countdown_3/2/1 - VISUAL ONLY (silent), 1.5s each
    5. answer - "¡Correcto! La respuesta es Verdadero/Falso."
    6. explanation - The explanation

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    import shutil
    voice_id = voice_id or DEFAULT_VOICE_ID

    from tts_common import clean_for_tts

    statement = script.get('statement', '')
    correct = script.get('correct', False)
    explanation = script.get('explanation', '')

    # Strip "¿Verdadero o falso?" from statement to avoid reading it twice
    stripped = re.sub(r'\s*¿?\s*[Vv]erdadero\s+o\s+[Ff]also\s*\??\s*$', '', statement)
    clean_statement = clean_for_tts(stripped.strip())
    clean_statement = clean_statement.lstrip('¿').strip()
    answer_word = "Verdadero" if correct else "Falso"

    english_words = extract_english_words_from_script(script)

    temp_dir = tempfile.mkdtemp(prefix="el_tf_segments_")

    try:
        logger.info("=" * 60)
        logger.info("ELEVENLABS TTS - TRUE/FALSE AUDIO")
        logger.info("=" * 60)

        segments = []
        audio_files = []
        running_time = 0.0

        def add_audio(path: str, duration: float = None):
            nonlocal running_time
            if duration is None:
                duration = get_audio_duration(path)
            audio_files.append(path)
            start = running_time
            running_time += duration
            return start, running_time, duration

        def add_silence(dur: float):
            nonlocal running_time
            silence_path = os.path.join(temp_dir, f"silence_{len(audio_files)}.mp3")
            generate_silence(dur, silence_path)
            audio_files.append(silence_path)
            running_time += dur

        def add_segment(seg_id: str, text: str, start: float, end: float):
            segment = {
                'id': seg_id,
                'text': text,
                'start': round(start, 3),
                'end': round(end, 3),
                'duration': round(end - start, 3),
            }
            segments.append(segment)
            logger.info("  [%s] %s...", seg_id, text[:50])
            return segment

        # 1. STATEMENT
        logger.info("[1] STATEMENT")
        s_path = os.path.join(temp_dir, "statement.mp3")
        generate_segment_audio(
            text=clean_statement, output_path=s_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='question', english_words=english_words,
        )
        s_start, s_end, _ = add_audio(s_path)
        add_segment('statement', clean_statement, s_start, s_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # 2. OPTIONS
        logger.info("[2] OPTIONS")
        options_text = "¿Verdadero o falso?"
        opt_path = os.path.join(temp_dir, "options.mp3")
        generate_segment_audio(
            text=options_text, output_path=opt_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='options', english_words=english_words,
        )
        opt_start, opt_end, _ = add_audio(opt_path)
        add_segment('options', options_text, opt_start, opt_end)
        add_silence(PAUSE_AFTER_OPTION)

        # 3. THINK
        logger.info("[3] THINK")
        think_path = os.path.join(temp_dir, "think.mp3")
        generate_segment_audio(
            "¡Piensa bien!", think_path, voice_id, segment_type='think',
        )
        think_start, think_end, _ = add_audio(think_path)
        add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # 4. COUNTDOWN (VISUAL ONLY - silent)
        logger.info("[4] COUNTDOWN (visual only, audio silence)")
        countdown_interval = 1.5
        for num in ['3', '2', '1']:
            cd_start = running_time
            add_silence(countdown_interval)
            cd_end = running_time
            add_segment(f'countdown_{num}', f'[{num}]', cd_start, cd_end)
            logger.info("  [countdown_%s] %.2fs - %.2fs (silent)", num, cd_start, cd_end)

        # Dramatic pause before answer
        add_silence(1.0)

        # 5. ANSWER
        logger.info("[5] ANSWER")
        answer_text = f"¡Correcto! La respuesta es {answer_word}."
        ans_path = os.path.join(temp_dir, "answer.mp3")
        generate_segment_audio(
            text=answer_text, output_path=ans_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='answer', english_words=english_words,
        )
        ans_start, ans_end, _ = add_audio(ans_path)
        add_segment('answer', answer_text, ans_start, ans_end)
        add_silence(PAUSE_AFTER_ANSWER)

        # 6. EXPLANATION
        if explanation.strip():
            logger.info("[6] EXPLANATION")
            clean_explanation = clean_for_tts(explanation)
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            generate_segment_audio(
                text=clean_explanation, output_path=exp_path, voice_id=voice_id,
                stability=stability, similarity_boost=similarity_boost,
                segment_type='explanation', english_words=english_words,
            )
            exp_start, exp_end, _ = add_audio(exp_path)
            add_segment('explanation', clean_explanation, exp_start, exp_end)
            add_silence(PAUSE_AFTER_EXPLANATION)

        total_duration = running_time
        logger.info("=" * 60)
        logger.info("Total duration: %.2fs", total_duration)
        logger.info("=" * 60)

        # Concatenate
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
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-ar', '44100', '-ac', '1',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

        logger.info("Audio saved: %s", output_path)

        segment_times = {}
        for seg in segments:
            segment_times[seg['id']] = {
                'start': seg['start'],
                'end': seg['end'],
                'duration': seg['duration'],
            }

        result_data = {
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
            '_meta': script.get('_meta', {}),
        }

        # Save timestamps JSON
        import json
        json_path = output_path.replace('.mp3', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        logger.info("Timestamps saved: %s", json_path)

        return result_data

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def generate_vocabulary_audio_segmented(
    script: dict,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
) -> dict:
    """
    Generate vocabulary list audio using ElevenLabs TTS.

    Segments:
    1. title - The vocabulary topic title
    2. pair_0..N - Each Spanish/English pair spoken sequentially

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    import shutil
    voice_id = voice_id or DEFAULT_VOICE_ID

    from tts_common import clean_for_tts

    title = script.get('title', 'Vocabulario del día')
    pairs = script.get('pairs', [])
    english_words = extract_english_words_from_script(script)

    temp_dir = tempfile.mkdtemp(prefix="el_vocab_segments_")

    try:
        logger.info("=" * 60)
        logger.info("ELEVENLABS TTS - VOCABULARY AUDIO")
        logger.info("=" * 60)

        segments = []
        audio_files = []
        running_time = 0.0

        def add_audio(path: str, duration: float = None):
            nonlocal running_time
            if duration is None:
                duration = get_audio_duration(path)
            audio_files.append(path)
            start = running_time
            running_time += duration
            return start, running_time, duration

        def add_silence(dur: float):
            nonlocal running_time
            silence_path = os.path.join(temp_dir, f"silence_{len(audio_files)}.mp3")
            generate_silence(dur, silence_path)
            audio_files.append(silence_path)
            running_time += dur

        def add_segment(seg_id: str, text: str, start: float, end: float):
            segment = {
                'id': seg_id,
                'text': text,
                'start': round(start, 3),
                'end': round(end, 3),
                'duration': round(end - start, 3),
            }
            segments.append(segment)
            logger.info("  [%s] %s...", seg_id, text[:60])
            return segment

        # 1. TITLE
        logger.info("[1] TITLE")
        clean_title = clean_for_tts(title)
        t_path = os.path.join(temp_dir, "title.mp3")
        generate_segment_audio(
            text=clean_title, output_path=t_path, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost,
            segment_type='question', english_words=english_words,
        )
        t_start, t_end, _ = add_audio(t_path)
        add_segment('title', clean_title, t_start, t_end)
        add_silence(0.8)  # Pause after title

        # 2. PAIRS
        for i, pair in enumerate(pairs):
            spanish = pair.get('spanish', '')
            english = pair.get('english', '')
            logger.info("[%d] PAIR: %s → %s", i + 2, spanish, english)

            # Speak: "spanish, english."
            pair_text = clean_for_tts(f"{spanish}... {english}.")
            p_path = os.path.join(temp_dir, f"pair_{i}.mp3")
            generate_segment_audio(
                text=pair_text, output_path=p_path, voice_id=voice_id,
                stability=stability, similarity_boost=similarity_boost,
                segment_type='options', english_words=english_words,
            )
            p_start, p_end, _ = add_audio(p_path)
            add_segment(f'pair_{i}', pair_text, p_start, p_end)
            add_silence(0.5)  # Pause between pairs

        total_duration = running_time
        logger.info("=" * 60)
        logger.info("Total duration: %.2fs", total_duration)
        logger.info("=" * 60)

        # Concatenate
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
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-ar', '44100', '-ac', '1',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

        logger.info("Audio saved: %s", output_path)

        segment_times = {}
        for seg in segments:
            segment_times[seg['id']] = {
                'start': seg['start'],
                'end': seg['end'],
                'duration': seg['duration'],
            }

        result_data = {
            'duration': round(total_duration, 3),
            'segments': segments,
            'segment_times': segment_times,
            'type': 'vocabulary',
            'title': title,
            'difficulty': script.get('difficulty', ''),
            'pairs': pairs,
            'full_script': script.get('full_script', ''),
            'translations': script.get('translations', {}),
            'english_phrases': script.get('english_phrases', []),
            'hashtags': script.get('hashtags', []),
            'words': [],
            '_meta': script.get('_meta', {}),
        }

        # Save timestamps JSON
        import json
        json_path = output_path.replace('.mp3', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        logger.info("Timestamps saved: %s", json_path)

        return result_data

    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def list_voices() -> None:
    """List available ElevenLabs voices."""
    client = get_client()
    response = client.voices.get_all()

    logger.info("Available ElevenLabs voices:")
    for voice in response.voices:
        logger.info("  %s (ID: %s)", voice.name, voice.voice_id)
        if voice.labels:
            logger.debug("    Labels: %s", voice.labels)


def test_voice(
    text: str = "Hola, esta es una prueba. ¿Qué significa 'library' en español? Significa biblioteca.",
    voice_id: str = None,
    output_path: str = "output/test_elevenlabs.mp3",
) -> None:
    """Test an ElevenLabs voice."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    voice_id = voice_id or DEFAULT_VOICE_ID

    logger.info("Testing voice: %s", voice_id)
    logger.debug("Text: %s", text)

    duration = generate_segment_audio(
        text=text,
        output_path=output_path,
        voice_id=voice_id,
    )

    logger.info("Duration: %.2fs", duration)
    logger.info("Saved: %s", output_path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ElevenLabs TTS Module")
    parser.add_argument("--script", "-s", help="Path to script JSON file")
    parser.add_argument("--list-voices", "-l", action="store_true", help="List available voices")
    parser.add_argument("--test", "-t", action="store_true", help="Test TTS with sample text")
    parser.add_argument("--text", default="Hola, ¿qué significa 'embarrassed' en inglés?", help="Text to test")
    parser.add_argument("--voice", default=DEFAULT_VOICE_ID, help="Voice ID to use")
    parser.add_argument("--output", "-o", default="output/test_elevenlabs.mp3", help="Output path")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
    elif args.script:
        from tts_common import clean_for_tts

        with open(args.script, 'r', encoding='utf-8') as f:
            script_data = json.load(f)

        video_type = script_data.get('type', 'quiz')
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data, output_path=args.output, voice_id=args.voice,
            )
        elif video_type == 'fill_blank':
            result = generate_fill_blank_audio_segmented(
                script=script_data, output_path=args.output, voice_id=args.voice,
            )
        elif video_type == 'true_false':
            result = generate_true_false_audio_segmented(
                script=script_data, output_path=args.output, voice_id=args.voice,
            )
        elif video_type == 'vocabulary':
            result = generate_vocabulary_audio_segmented(
                script=script_data, output_path=args.output, voice_id=args.voice,
            )
        else:
            # educational, pronunciation — single TTS call
            text = script_data.get('full_script', '')
            if not text:
                print(f"Script missing 'full_script' for type '{video_type}'")
                import sys; sys.exit(1)
            tts_text = clean_for_tts(text)
            english_words_set = extract_english_words_from_script(script_data)
            duration = generate_segment_audio(
                tts_text, args.output, voice_id=args.voice,
                segment_type='explanation', english_words=english_words_set,
            )
            english_phrases = script_data.get('english_phrases', [])

            # --- Get REAL word timestamps from Whisper ---
            whisper_words = []
            try:
                from tts_openai import extract_timestamps_whisper
                logger.info("Extracting real word timestamps with Whisper...")
                whisper_result = extract_timestamps_whisper(
                    args.output,
                    original_text=text,
                    explicit_english=english_phrases,
                )
                whisper_words = whisper_result.get('words', [])
                whisper_duration = whisper_result.get('duration', duration)
                if whisper_words:
                    duration = whisper_duration
                    logger.info("Whisper: got %d real word timestamps", len(whisper_words))
                else:
                    logger.warning("Whisper returned no words, falling back to estimation")
            except Exception as e:
                logger.warning("Whisper failed (%s), falling back to character estimation", e)

            if whisper_words:
                # Use real Whisper timestamps — add sentence boundaries
                from video.educational import add_sentence_boundaries
                words_with_segments = add_sentence_boundaries(whisper_words, text)

                # Build segments from sentence boundaries
                segments = []
                current_seg_id = None
                seg_words = []
                for w in words_with_segments:
                    sid = w.get('segment_id', 0)
                    if sid != current_seg_id:
                        if seg_words:
                            segments.append({
                                'start': seg_words[0]['start'],
                                'end': seg_words[-1]['end'],
                                'text': ' '.join(sw['word'] for sw in seg_words),
                            })
                        seg_words = [w]
                        current_seg_id = sid
                    else:
                        seg_words.append(w)
                if seg_words:
                    segments.append({
                        'start': seg_words[0]['start'],
                        'end': seg_words[-1]['end'],
                        'text': ' '.join(sw['word'] for sw in seg_words),
                    })

                result = {
                    'duration': duration,
                    'words': words_with_segments,
                    'segments': segments,
                }
            else:
                # Fallback: estimate timestamps from character count
                est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
                result = {'duration': duration, 'words': est_words, 'segments': est_segments}

            for key in ('type', 'question', 'options', 'correct', 'explanation',
                        'full_script', 'translations', 'hashtags', 'word', 'phonetic',
                        'english_phrases', 'tip', 'sentence'):
                if key in script_data:
                    result[key] = script_data[key]

            # Save companion JSON
            json_out = args.output.replace('.mp3', '.json')
            with open(json_out, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\nSuccess!")
        print(f"  Audio: {args.output}")
        print(f"  Duration: {result['duration']:.2f}s")
    elif args.test:
        test_voice(args.text, args.voice, args.output)
    else:
        parser.print_help()

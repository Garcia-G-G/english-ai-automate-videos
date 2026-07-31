#!/usr/bin/env python3
"""
Google Cloud TTS Module for English AI Video Generator

Uses Google Cloud Text-to-Speech API for natural bilingual speech.
Supports SSML for precise language switching between Spanish and English.

Advantages over OpenAI TTS:
- Consistent Spanish pronunciation
- SSML support for language tags
- Polyglot voices for bilingual content
- More reliable for short phrases
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from google.cloud import texttospeech

from tts_common import (
    get_audio_duration, generate_silence, measure_speech_end,
    extract_english_words_from_script, SPANISH_FILTER,
    ASSETS_DIR, SPANISH_DIR, WORDS_DIR,
    PAUSE_AFTER_QUESTION, PAUSE_AFTER_OPTION, PAUSE_AFTER_THINK,
    PAUSE_AFTER_COUNTDOWN, PAUSE_AFTER_LAST_COUNT, PAUSE_AFTER_ANSWER,
    PAUSE_AFTER_EXPLANATION,
    PAUSE_LETTER_TO_WORD, PAUSE_BETWEEN_OPTIONS,
)

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Voice configurations
# Spanish voices (for main content)
SPANISH_VOICES = {
    "es-US-Neural2-A": "US Spanish, Female",
    "es-US-Neural2-B": "US Spanish, Male",
    "es-US-Neural2-C": "US Spanish, Male 2",
    "es-MX-Neural2-A": "Mexican Spanish, Female",
    "es-MX-Neural2-B": "Mexican Spanish, Male",
    "es-US-Polyglot-1": "US Spanish Polyglot (bilingual)",
}

# English voices (for English words/phrases)
ENGLISH_VOICES = {
    "en-US-Neural2-A": "US English, Male",
    "en-US-Neural2-C": "US English, Female",
    "en-US-Neural2-J": "US English, Male 2",
}

# Default voices
DEFAULT_SPANISH_VOICE = "es-US-Neural2-A"  # Clear female Spanish voice
DEFAULT_ENGLISH_VOICE = "en-US-Neural2-J"  # For English words
DEFAULT_SPEED = 0.9  # Slightly slower for clarity

def get_client() -> texttospeech.TextToSpeechClient:
    """Get Google Cloud TTS client."""
    return texttospeech.TextToSpeechClient()


def text_to_ssml(text: str, english_words: set = None) -> str:
    """
    Convert plain text to SSML with language tags for English words.

    Args:
        text: Plain text (Spanish with some English words)
        english_words: Set of words that should be pronounced in English

    Returns:
        SSML string with proper language tags
    """
    if not english_words:
        # Pure Spanish, no SSML needed
        return text

    # Escape XML special characters
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Find English words/phrases in quotes and tag them
    # Pattern: 'word' or "word"
    def tag_quoted_english(match):
        word = match.group(1)
        # Check if this word is in our English set
        word_lower = word.lower().strip()
        if word_lower in english_words or any(w in word_lower for w in english_words):
            return f"'<lang xml:lang=\"en-US\">{word}</lang>'"
        return match.group(0)

    # Tag words in single quotes
    text = re.sub(r"'([^']+)'", tag_quoted_english, text)

    # Wrap in speak tags
    ssml = f'<speak>{text}</speak>'
    return ssml


def generate_segment_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_SPANISH_VOICE,
    speed: float = DEFAULT_SPEED,
    use_ssml: bool = False,
    english_words: set = None,
) -> float:
    """
    Generate a single audio segment using Google Cloud TTS.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Google Cloud voice name
        speed: Speech speed (0.25 to 4.0)
        use_ssml: Whether to treat text as SSML
        english_words: Set of English words for SSML tagging

    Returns:
        Duration in seconds
    """
    client = get_client()

    # Prepare input
    if use_ssml:
        synthesis_input = texttospeech.SynthesisInput(ssml=text)
    elif english_words:
        # Convert to SSML with language tags
        ssml_text = text_to_ssml(text, english_words)
        synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
    else:
        synthesis_input = texttospeech.SynthesisInput(text=text)

    # Parse voice name to get language code
    # Format: es-US-Neural2-A -> es-US
    parts = voice.split('-')
    language_code = f"{parts[0]}-{parts[1]}"

    # Voice configuration
    voice_params = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice,
    )

    # Audio configuration
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speed,
        pitch=0.0,  # Default pitch
    )

    # Generate speech
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )

    # Save audio
    with open(output_path, 'wb') as f:
        f.write(response.audio_content)

    return get_audio_duration(output_path)


def generate_quiz_audio_segmented(
    script: dict,
    output_path: str,
    voice: str = DEFAULT_SPANISH_VOICE,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Generate quiz audio using Google Cloud TTS.

    Uses the same segment-based architecture as the OpenAI module:
    1. Pre-recorded standard phrases (assets/audio/spanish/)
    2. Fresh TTS for: question, options (combined), answer, explanation
    3. Assembly via ffmpeg concatenation

    Returns:
        Dictionary with exact segment timestamps and audio metadata
    """
    # Extract script data
    question = script.get('question', '').replace('¿', '').replace('?', '?')
    options = script.get('options', {})
    correct = script.get('correct', 'A')
    explanation = script.get('explanation', '')

    # Get correct answer text
    correct_text = options.get(correct, '').strip("'\"")

    # Extract English words for SSML
    english_words = extract_english_words_from_script(script)
    logger.info("English words detected: %s", english_words)

    # Create temp directory for assembly
    with tempfile.TemporaryDirectory() as temp_dir:
        segments = []
        audio_files = []
        running_time = 0.0

        def add_audio(path: str, duration: float = None):
            """Add audio file to sequence.

            Returns (start, file_end, duration, speech_end). `speech_end` is
            where the VOICE stops; `file_end` is where the CLIP stops, and the
            two differ by the trailing silence every TTS model leaves behind.
            Segments must be recorded against speech_end — see
            tts_common.measure_speech_end. The audio itself is untouched.
            """
            nonlocal running_time
            if duration is None:
                duration = get_audio_duration(path)
            audio_files.append(path)
            start = running_time
            speech_end = start + measure_speech_end(path)
            running_time += duration
            return start, running_time, duration, speech_end

        def add_silence(duration: float):
            """Add silence to sequence."""
            nonlocal running_time
            silence_path = os.path.join(temp_dir, f"silence_{len(audio_files)}.mp3")
            generate_silence(duration, silence_path, sample_rate=24000)
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
        logger.info("GOOGLE CLOUD TTS - QUIZ AUDIO")
        logger.info("=" * 60)
        logger.info("Voice: %s", voice)
        logger.info("Speed: %s", speed)

        # ============================================================
        # 1. QUESTION
        # ============================================================
        logger.info("[1] QUESTION")
        q_path = os.path.join(temp_dir, "question.mp3")
        generate_segment_audio(
            text=question,
            output_path=q_path,
            voice=voice,
            speed=speed,
            english_words=english_words,
        )
        q_start, q_end, _, q_end_speech = add_audio(q_path)
        add_segment('question', question, q_start, q_end_speech)
        add_silence(PAUSE_AFTER_QUESTION)

        # ============================================================
        # 2-3. TRANSITION + OPTIONS — one TTS call per part, every
        #      boundary MEASURED
        # ============================================================
        # Was one combined call with invented boundaries — transition_duration
        # = 1.5 and per_option = options_duration / 4. See the equivalent
        # block in tts_elevenlabs.py for the measurements that condemned it.
        logger.info("[2-3] OPTIONS (split: letter | silence | word)")

        option_words = {}
        for letter in ['A', 'B', 'C', 'D']:
            option_words[letter] = options.get(letter, '').strip("'\"")

        trans_path = os.path.join(temp_dir, "transition.mp3")
        generate_segment_audio(text="Escucha las opciones.",
                               output_path=trans_path, voice=voice, speed=speed)
        trans_start, trans_end, _, trans_end_speech = add_audio(trans_path)
        add_segment('transition', 'Escucha las opciones.', trans_start, trans_end_speech)
        add_silence(PAUSE_BETWEEN_OPTIONS)

        for i, letter in enumerate(['A', 'B', 'C', 'D']):
            word = option_words[letter]

            letter_path = os.path.join(temp_dir, f"option_{letter}_letter.mp3")
            generate_segment_audio(text=f"Opción {letter},",
                                   output_path=letter_path, voice=voice, speed=speed)
            letter_start, _le, _, le_speech = add_audio(letter_path)

            add_silence(PAUSE_LETTER_TO_WORD)

            word_path = os.path.join(temp_dir, f"option_{letter}_word.mp3")
            generate_segment_audio(text=f"{word}.",
                                   output_path=word_path, voice=voice, speed=speed)
            _ws, word_end, _, word_end_speech = add_audio(word_path)

            add_segment(f'option_{letter.lower()}',
                        f"Opción {letter}, {word}.", letter_start, word_end_speech)

            if i < 3:
                add_silence(PAUSE_BETWEEN_OPTIONS)

        add_silence(PAUSE_AFTER_OPTION)

        # ============================================================
        # 4. THINK (pre-recorded)
        # ============================================================
        logger.info("[4] THINK")
        think_path = str(SPANISH_DIR / "piensa_bien.mp3")
        if os.path.exists(think_path):
            think_start, think_end, _, think_end_speech = add_audio(think_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end_speech)
        else:
            # Generate if not pre-recorded
            think_gen_path = os.path.join(temp_dir, "think.mp3")
            generate_segment_audio("¡Piensa bien!", think_gen_path, voice, speed)
            think_start, think_end, _, think_end_speech = add_audio(think_gen_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end_speech)
        add_silence(PAUSE_AFTER_THINK)

        # ============================================================
        # 5. COUNTDOWN (pre-recorded)
        # ============================================================
        logger.info("[5] COUNTDOWN")
        for num, name in [('3', 'tres'), ('2', 'dos'), ('1', 'uno')]:
            cd_path = str(SPANISH_DIR / f"{name}.mp3")
            if os.path.exists(cd_path):
                cd_start, cd_end, _, cd_end_speech = add_audio(cd_path)
            else:
                cd_gen_path = os.path.join(temp_dir, f"countdown_{num}.mp3")
                generate_segment_audio(f"{name.capitalize()}.", cd_gen_path, voice, speed)
                cd_start, cd_end, _, cd_end_speech = add_audio(cd_gen_path)
            add_segment(f'countdown_{num}', f'{name.capitalize()}.', cd_start, cd_end_speech)
            pause = PAUSE_AFTER_LAST_COUNT if num == '1' else PAUSE_AFTER_COUNTDOWN
            add_silence(pause)

        # ============================================================
        # 6. ANSWER
        # ============================================================
        logger.info("[6] ANSWER")
        answer_start = running_time
        full_answer_text = f"Correcto. La respuesta es {correct}, {correct_text}."
        logger.debug("Answer: '%s'", full_answer_text)

        ans_path = os.path.join(temp_dir, "answer.mp3")
        generate_segment_audio(full_answer_text, ans_path, voice, speed)
        add_audio(ans_path)

        answer_end = running_time
        add_segment('answer', full_answer_text, answer_start, answer_end)
        add_silence(PAUSE_AFTER_ANSWER)

        # ============================================================
        # 7. EXPLANATION
        # ============================================================
        if explanation.strip():
            logger.info("[7] EXPLANATION")
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            generate_segment_audio(
                text=explanation,
                output_path=exp_path,
                voice=voice,
                speed=speed,
                english_words=english_words,
            )
            exp_start, exp_end, _, exp_end_speech = add_audio(exp_path)
            add_segment('explanation', explanation, exp_start, exp_end_speech)
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
            '-ar', '24000', '-ac', '1',
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


def list_voices(language_code: str = "es") -> None:
    """List available voices for a language."""
    client = get_client()
    response = client.list_voices(language_code=language_code)

    logger.info("Available voices for '%s':", language_code)
    for voice in response.voices:
        logger.info("  %s", voice.name)
        logger.debug("    Language codes: %s", voice.language_codes)
        logger.debug("    Gender: %s", voice.ssml_gender.name)


def test_voice(
    text: str = "Hola, esta es una prueba de voz. La palabra en inglés es 'library'.",
    voice: str = DEFAULT_SPANISH_VOICE,
    output_path: str = "output/test_google_tts.mp3",
) -> None:
    """Test a Google Cloud TTS voice."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info("Testing voice: %s", voice)
    logger.debug("Text: %s", text)

    duration = generate_segment_audio(
        text=text,
        output_path=output_path,
        voice=voice,
        speed=DEFAULT_SPEED,
        english_words={'library'},
    )

    logger.info("Duration: %.2fs", duration)
    logger.info("Saved: %s", output_path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Google Cloud TTS Module")
    parser.add_argument("--list-voices", "-l", action="store_true", help="List available voices")
    parser.add_argument("--language", default="es", help="Language code for listing voices")
    parser.add_argument("--test", "-t", action="store_true", help="Test TTS with sample text")
    parser.add_argument("--text", default="Hola, ¿qué significa 'embarrassed' en inglés?", help="Text to test")
    parser.add_argument("--voice", default=DEFAULT_SPANISH_VOICE, help="Voice to use")
    parser.add_argument("--output", "-o", default="output/test_google_tts.mp3", help="Output path")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="Speech speed (0.25-4.0)")

    args = parser.parse_args()

    if args.list_voices:
        list_voices(args.language)
    elif args.test:
        test_voice(args.text, args.voice, args.output)
    else:
        parser.print_help()

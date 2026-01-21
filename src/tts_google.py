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

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.cloud import texttospeech

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

# Audio library paths (same as OpenAI module)
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"
SPANISH_DIR = ASSETS_DIR / "spanish"
WORDS_DIR = ASSETS_DIR / "words"

# Timing constants (same as OpenAI module)
PAUSE_AFTER_QUESTION = 0.5
PAUSE_AFTER_OPTION = 0.6
PAUSE_AFTER_THINK = 0.5
PAUSE_AFTER_COUNTDOWN = 1.0
PAUSE_AFTER_LAST_COUNT = 0.6
PAUSE_AFTER_ANSWER = 0.3
PAUSE_AFTER_EXPLANATION = 0.5


def get_client() -> texttospeech.TextToSpeechClient:
    """Get Google Cloud TTS client."""
    return texttospeech.TextToSpeechClient()


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


def generate_silence(duration: float, output_path: str) -> None:
    """Generate a silence audio file of specified duration."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'anullsrc=r=24000:cl=mono',
        '-t', str(duration),
        '-acodec', 'libmp3lame', '-q:a', '2',
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


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


def extract_english_words_from_script(script: dict) -> set:
    """
    Extract English teaching words from script.
    Same logic as OpenAI module.
    """
    english_words = set()

    # Spanish words to filter out
    SPANISH_FILTER = {
        'resfriado', 'embarazada', 'biblioteca', 'librería', 'sensible',
        'actualmente', 'pretender', 'éxito', 'recordar', 'realizar',
        'soportar', 'avergonzado', 'confundido', 'desesperado',
        'continuar', 'rendirse', 'progresar', 'crecer',
    }

    question = script.get('question', '')
    quoted_pattern = r"'([^']+)'"

    # Determine quiz type
    is_que_significa = '¿qué significa' in question.lower() or 'que significa' in question.lower()

    if is_que_significa:
        # "What does X mean" - X is English
        for match in re.findall(quoted_pattern, question):
            for word in match.lower().split():
                clean = re.sub(r'[^\w]', '', word)
                if clean and len(clean) > 1 and clean not in SPANISH_FILTER:
                    english_words.add(clean)

    return english_words


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
    print(f"  English words detected: {english_words}")

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
            print(f"  [{seg_id}] {text[:50]}...")
            print(f"    {start:.2f}s - {end:.2f}s ({end-start:.2f}s)")
            return segment

        print("=" * 60)
        print("GOOGLE CLOUD TTS - QUIZ AUDIO")
        print("=" * 60)
        print(f"  Voice: {voice}")
        print(f"  Speed: {speed}")
        print()

        # ============================================================
        # 1. QUESTION
        # ============================================================
        print("\n[1] QUESTION")
        q_path = os.path.join(temp_dir, "question.mp3")
        generate_segment_audio(
            text=question,
            output_path=q_path,
            voice=voice,
            speed=speed,
            english_words=english_words,
        )
        q_start, q_end, _ = add_audio(q_path)
        add_segment('question', question, q_start, q_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # ============================================================
        # 2-3. TRANSITION + OPTIONS (COMBINED)
        # ============================================================
        print("\n[2-3] OPTIONS (combined)")

        # Build combined text
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

        # Generate combined options
        combined_path = os.path.join(temp_dir, "options_combined.mp3")
        generate_segment_audio(
            text=combined_text,
            output_path=combined_path,
            voice=voice,
            speed=speed,
        )

        combined_duration = get_audio_duration(combined_path)
        print(f"  Combined duration: {combined_duration:.2f}s")

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
        # 4. THINK (pre-recorded)
        # ============================================================
        print("\n[4] THINK")
        think_path = str(SPANISH_DIR / "piensa_bien.mp3")
        if os.path.exists(think_path):
            think_start, think_end, _ = add_audio(think_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end)
        else:
            # Generate if not pre-recorded
            think_gen_path = os.path.join(temp_dir, "think.mp3")
            generate_segment_audio("¡Piensa bien!", think_gen_path, voice, speed)
            think_start, think_end, _ = add_audio(think_gen_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # ============================================================
        # 5. COUNTDOWN (pre-recorded)
        # ============================================================
        print("\n[5] COUNTDOWN")
        for num, name in [('3', 'tres'), ('2', 'dos'), ('1', 'uno')]:
            cd_path = str(SPANISH_DIR / f"{name}.mp3")
            if os.path.exists(cd_path):
                cd_start, cd_end, _ = add_audio(cd_path)
            else:
                cd_gen_path = os.path.join(temp_dir, f"countdown_{num}.mp3")
                generate_segment_audio(f"{name.capitalize()}.", cd_gen_path, voice, speed)
                cd_start, cd_end, _ = add_audio(cd_gen_path)
            add_segment(f'countdown_{num}', f'{name.capitalize()}.', cd_start, cd_end)
            pause = PAUSE_AFTER_LAST_COUNT if num == '1' else PAUSE_AFTER_COUNTDOWN
            add_silence(pause)

        # ============================================================
        # 6. ANSWER
        # ============================================================
        print("\n[6] ANSWER")
        answer_start = running_time
        full_answer_text = f"Correcto. La respuesta es {correct}, {correct_text}."
        print(f"  Answer: '{full_answer_text}'")

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
            print("\n[7] EXPLANATION")
            exp_path = os.path.join(temp_dir, "explanation.mp3")
            generate_segment_audio(
                text=explanation,
                output_path=exp_path,
                voice=voice,
                speed=speed,
                english_words=english_words,
            )
            exp_start, exp_end, _ = add_audio(exp_path)
            add_segment('explanation', explanation, exp_start, exp_end)
            add_silence(PAUSE_AFTER_EXPLANATION)

        total_duration = running_time
        print(f"\n{'=' * 60}")
        print(f"Total duration: {total_duration:.2f}s")
        print(f"{'=' * 60}")

        # ============================================================
        # CONCATENATE
        # ============================================================
        print("\nConcatenating audio files...")
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
            print(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg concatenation failed: {result.stderr}")

        print(f"Audio saved: {output_path}")

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
        print(f"Timestamps saved: {json_path}")

        return result


def list_voices(language_code: str = "es") -> None:
    """List available voices for a language."""
    client = get_client()
    response = client.list_voices(language_code=language_code)

    print(f"\nAvailable voices for '{language_code}':")
    for voice in response.voices:
        print(f"  {voice.name}")
        print(f"    Language codes: {voice.language_codes}")
        print(f"    Gender: {voice.ssml_gender.name}")
        print()


def test_voice(
    text: str = "Hola, esta es una prueba de voz. La palabra en inglés es 'library'.",
    voice: str = DEFAULT_SPANISH_VOICE,
    output_path: str = "output/test_google_tts.mp3",
) -> None:
    """Test a Google Cloud TTS voice."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"Testing voice: {voice}")
    print(f"Text: {text}")

    duration = generate_segment_audio(
        text=text,
        output_path=output_path,
        voice=voice,
        speed=DEFAULT_SPEED,
        english_words={'library'},
    )

    print(f"Duration: {duration:.2f}s")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Google Cloud TTS Module")
    parser.add_argument("--script", "-s", help="Path to script JSON file (for quiz generation)")
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
    elif args.script:
        # Generate audio from script JSON file
        with open(args.script, 'r', encoding='utf-8') as f:
            script_data = json.load(f)

        video_type = script_data.get('type', 'quiz')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data,
                output_path=args.output,
                voice=args.voice,
                speed=args.speed,
            )
            print(f"\nSuccess!")
            print(f"  Audio: {args.output}")
            print(f"  Duration: {result['duration']:.2f}s")
        else:
            print(f"Unsupported video type: {video_type}")
            print("Currently only 'quiz' type is supported.")
    elif args.test:
        test_voice(args.text, args.voice, args.output)
    else:
        parser.print_help()

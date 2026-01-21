#!/usr/bin/env python3
"""
ElevenLabs TTS Module for English AI Video Generator

Uses ElevenLabs API for high-quality bilingual speech synthesis.
Uses eleven_multilingual_v2 model for Spanish/English support.

Advantages:
- Excellent Spanish pronunciation
- Natural bilingual flow
- High quality voices
- Consistent output
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.types import VoiceSettings

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

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
}

# Default voice (Rachel - good for educational content)
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", VOICES.get("rachel", "21m00Tcm4TlvDq8ikWAM"))

# Model for multilingual content
MODEL_ID = "eleven_multilingual_v2"

# Voice settings for educational content
DEFAULT_STABILITY = 0.5       # Balanced - not too robotic, not too variable
DEFAULT_SIMILARITY = 0.75     # High similarity to original voice
DEFAULT_STYLE = 0.0           # Neutral style for educational content
DEFAULT_SPEAKER_BOOST = True  # Enhance speaker clarity

# Audio library paths (same as other modules)
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"
SPANISH_DIR = ASSETS_DIR / "spanish"
WORDS_DIR = ASSETS_DIR / "words"

# Timing constants
PAUSE_AFTER_QUESTION = 0.5
PAUSE_AFTER_OPTION = 0.6
PAUSE_AFTER_THINK = 0.5
PAUSE_AFTER_COUNTDOWN = 1.0
PAUSE_AFTER_LAST_COUNT = 0.6
PAUSE_AFTER_ANSWER = 0.3
PAUSE_AFTER_EXPLANATION = 0.5


def get_client() -> ElevenLabs:
    """Get ElevenLabs client."""
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY not set in environment")
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)


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
        '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=mono',
        '-t', str(duration),
        '-acodec', 'libmp3lame', '-q:a', '2',
        output_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


def generate_segment_audio(
    text: str,
    output_path: str,
    voice_id: str = None,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY,
    style: float = DEFAULT_STYLE,
    use_speaker_boost: bool = DEFAULT_SPEAKER_BOOST,
) -> float:
    """
    Generate a single audio segment using ElevenLabs TTS.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice_id: ElevenLabs voice ID
        stability: Voice stability (0-1)
        similarity_boost: Similarity to original voice (0-1)
        style: Style exaggeration (0-1)
        use_speaker_boost: Enable speaker boost for clarity

    Returns:
        Duration in seconds
    """
    client = get_client()
    voice_id = voice_id or DEFAULT_VOICE_ID

    # Generate audio
    audio_generator = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        voice_settings=VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
        ),
        output_format="mp3_44100_128",
    )

    # Save audio
    with open(output_path, 'wb') as f:
        for chunk in audio_generator:
            f.write(chunk)

    return get_audio_duration(output_path)


def extract_english_words_from_script(script: dict) -> set:
    """
    Extract English teaching words from script.
    """
    english_words = set()

    SPANISH_FILTER = {
        'resfriado', 'embarazada', 'biblioteca', 'librería', 'sensible',
        'actualmente', 'pretender', 'éxito', 'recordar', 'realizar',
        'soportar', 'avergonzado', 'confundido', 'desesperado',
        'continuar', 'rendirse', 'progresar', 'crecer',
    }

    question = script.get('question', '')
    quoted_pattern = r"'([^']+)'"

    is_que_significa = '¿qué significa' in question.lower() or 'que significa' in question.lower()

    if is_que_significa:
        for match in re.findall(quoted_pattern, question):
            for word in match.lower().split():
                clean = re.sub(r'[^\w]', '', word)
                if clean and len(clean) > 1 and clean not in SPANISH_FILTER:
                    english_words.add(clean)

    return english_words


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
    question = script.get('question', '').replace('¿', '').replace('?', '?')
    options = script.get('options', {})
    correct = script.get('correct', 'A')
    explanation = script.get('explanation', '')

    # Get correct answer text
    correct_text = options.get(correct, '').strip("'\"")

    # Extract English words
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
        print("ELEVENLABS TTS - QUIZ AUDIO")
        print("=" * 60)
        print(f"  Voice ID: {voice_id}")
        print(f"  Model: {MODEL_ID}")
        print()

        # ============================================================
        # 1. QUESTION
        # ============================================================
        print("\n[1] QUESTION")
        q_path = os.path.join(temp_dir, "question.mp3")
        generate_segment_audio(
            text=question,
            output_path=q_path,
            voice_id=voice_id,
            stability=stability,
            similarity_boost=similarity_boost,
        )
        q_start, q_end, _ = add_audio(q_path)
        add_segment('question', question, q_start, q_end)
        add_silence(PAUSE_AFTER_QUESTION)

        # ============================================================
        # 2-3. TRANSITION + OPTIONS (COMBINED)
        # Generate all options in ONE call for consistency
        # ============================================================
        print("\n[2-3] OPTIONS (combined)")

        # Build combined text
        option_lines = ["Escucha las opciones."]
        option_words = {}
        for letter in ['A', 'B', 'C', 'D']:
            word = options.get(letter, '').strip("'\"")
            option_words[letter] = word
            option_lines.append(f"Opción {letter}, {word}.")

        combined_text = " ".join(option_lines)
        print(f"  Combined text ({len(combined_text)} chars):")
        for line in option_lines:
            print(f"    {line}")

        # Generate combined options
        combined_path = os.path.join(temp_dir, "options_combined.mp3")
        generate_segment_audio(
            text=combined_text,
            output_path=combined_path,
            voice_id=voice_id,
            stability=stability,
            similarity_boost=similarity_boost,
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
        # 4. THINK (pre-recorded or generate)
        # ============================================================
        print("\n[4] THINK")
        think_path = str(SPANISH_DIR / "piensa_bien.mp3")
        if os.path.exists(think_path):
            think_start, think_end, _ = add_audio(think_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end)
        else:
            think_gen_path = os.path.join(temp_dir, "think.mp3")
            generate_segment_audio("¡Piensa bien!", think_gen_path, voice_id)
            think_start, think_end, _ = add_audio(think_gen_path)
            add_segment('think', '¡Piensa bien!', think_start, think_end)
        add_silence(PAUSE_AFTER_THINK)

        # ============================================================
        # 5. COUNTDOWN (pre-recorded or generate)
        # ============================================================
        print("\n[5] COUNTDOWN")
        for num, name in [('3', 'tres'), ('2', 'dos'), ('1', 'uno')]:
            cd_path = str(SPANISH_DIR / f"{name}.mp3")
            if os.path.exists(cd_path):
                cd_start, cd_end, _ = add_audio(cd_path)
            else:
                cd_gen_path = os.path.join(temp_dir, f"countdown_{num}.mp3")
                generate_segment_audio(f"{name.capitalize()}.", cd_gen_path, voice_id)
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
        generate_segment_audio(full_answer_text, ans_path, voice_id)
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
                voice_id=voice_id,
                stability=stability,
                similarity_boost=similarity_boost,
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
            '-ar', '44100', '-ac', '1',
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


def list_voices() -> None:
    """List available ElevenLabs voices."""
    client = get_client()
    response = client.voices.get_all()

    print("\nAvailable ElevenLabs voices:")
    for voice in response.voices:
        print(f"  {voice.name} (ID: {voice.voice_id})")
        if voice.labels:
            print(f"    Labels: {voice.labels}")
        print()


def test_voice(
    text: str = "Hola, esta es una prueba. ¿Qué significa 'library' en español? Significa biblioteca.",
    voice_id: str = None,
    output_path: str = "output/test_elevenlabs.mp3",
) -> None:
    """Test an ElevenLabs voice."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    voice_id = voice_id or DEFAULT_VOICE_ID

    print(f"Testing voice: {voice_id}")
    print(f"Text: {text}")

    duration = generate_segment_audio(
        text=text,
        output_path=output_path,
        voice_id=voice_id,
    )

    print(f"Duration: {duration:.2f}s")
    print(f"Saved: {output_path}")


def regenerate_audio_library(voice_id: str = None) -> None:
    """
    Regenerate all standard audio library files with ElevenLabs.
    """
    voice_id = voice_id or DEFAULT_VOICE_ID

    # Ensure directory exists
    SPANISH_DIR.mkdir(parents=True, exist_ok=True)

    # Standard phrases to generate
    phrases = {
        "escucha_opciones.mp3": "Escucha las opciones.",
        "opcion_a.mp3": "Opción A.",
        "opcion_b.mp3": "Opción B.",
        "opcion_c.mp3": "Opción C.",
        "opcion_d.mp3": "Opción D.",
        "piensa_bien.mp3": "¡Piensa bien!",
        "tres.mp3": "Tres.",
        "dos.mp3": "Dos.",
        "uno.mp3": "Uno.",
        "correcto_a.mp3": "Correcto. La respuesta es A.",
        "correcto_b.mp3": "Correcto. La respuesta es B.",
        "correcto_c.mp3": "Correcto. La respuesta es C.",
        "correcto_d.mp3": "Correcto. La respuesta es D.",
    }

    print(f"Regenerating audio library with ElevenLabs voice: {voice_id}")
    print(f"Output directory: {SPANISH_DIR}")
    print()

    for filename, text in phrases.items():
        output_path = str(SPANISH_DIR / filename)
        print(f"  Generating: {filename}")
        print(f"    Text: {text}")

        try:
            duration = generate_segment_audio(
                text=text,
                output_path=output_path,
                voice_id=voice_id,
            )
            print(f"    Duration: {duration:.2f}s")
            print(f"    Saved: {output_path}")
        except Exception as e:
            print(f"    ERROR: {e}")

        print()

    print("Audio library regeneration complete!")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ElevenLabs TTS Module")
    parser.add_argument("--script", "-s", help="Path to script JSON file (for quiz generation)")
    parser.add_argument("--list-voices", "-l", action="store_true", help="List available voices")
    parser.add_argument("--test", "-t", action="store_true", help="Test TTS with sample text")
    parser.add_argument("--regenerate-library", action="store_true", help="Regenerate audio library")
    parser.add_argument("--text", default="Hola, ¿qué significa 'embarrassed' en inglés?", help="Text to test")
    parser.add_argument("--voice", default=DEFAULT_VOICE_ID, help="Voice ID to use")
    parser.add_argument("--output", "-o", default="output/test_elevenlabs.mp3", help="Output path")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
    elif args.regenerate_library:
        regenerate_audio_library(args.voice)
    elif args.script:
        # Generate audio from script JSON file
        with open(args.script, 'r', encoding='utf-8') as f:
            script_data = json.load(f)

        video_type = script_data.get('type', 'quiz')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data,
                output_path=args.output,
                voice_id=args.voice,
            )
            print(f"\nSuccess!")
            print(f"  Audio: {args.output}")
            print(f"  Duration: {result['duration']:.2f}s")
        else:
            print(f"Unsupported video type: {video_type}")
    elif args.test:
        test_voice(args.text, args.voice, args.output)
    else:
        parser.print_help()

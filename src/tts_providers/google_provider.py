"""Google Cloud TTS provider — wraps tts_google.py."""

import logging
from typing import Dict

from tts_base import TTSProvider

logger = logging.getLogger(__name__)


class GoogleTTSProvider(TTSProvider):
    name = "google"

    def __init__(self, voice: str = None, speed: float = None):
        from tts_google import DEFAULT_SPANISH_VOICE, DEFAULT_SPEED
        self.voice = voice or DEFAULT_SPANISH_VOICE
        self.speed = speed or DEFAULT_SPEED

    def generate_from_script(self, script_data: Dict, output_path: str, **kwargs) -> Dict:
        from tts_google import generate_quiz_audio_segmented, generate_segment_audio

        voice = kwargs.get('voice', self.voice)
        speed = kwargs.get('speed', self.speed)
        video_type = script_data.get('type', 'educational')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data, output_path=output_path, voice=voice, speed=speed,
            )
        else:
            text = script_data.get('full_script', '')
            if not text:
                raise ValueError("Script missing 'full_script' field")

            from tts_common import clean_for_tts
            text = clean_for_tts(text)
            duration = generate_segment_audio(text, output_path, voice=voice, speed=speed)
            result = {'duration': duration, 'words': [], 'segments': []}
            self.copy_script_metadata(script_data, result)

        self.save_json(output_path, result)
        return result

    def generate_audio(self, text: str, output_path: str, **kwargs) -> Dict:
        from tts_google import generate_segment_audio

        voice = kwargs.get('voice', self.voice)
        speed = kwargs.get('speed', self.speed)
        duration = generate_segment_audio(text, output_path, voice=voice, speed=speed)
        return {'duration': duration, 'words': []}

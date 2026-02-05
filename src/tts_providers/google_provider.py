"""Google Cloud TTS provider — wraps tts_google.py."""

import json
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
        from tts_common import get_audio_duration

        voice = kwargs.get('voice', self.voice)
        speed = kwargs.get('speed', self.speed)

        video_type = script_data.get('type', 'educational')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data,
                output_path=output_path,
                voice=voice,
                speed=speed,
            )
        else:
            # Google only has segment-based for quiz; fall back to simple
            # generation for other types
            text = script_data.get('full_script', '')
            if not text:
                raise ValueError("Script missing 'full_script' field")

            duration = generate_segment_audio(text, output_path, voice=voice, speed=speed)
            result = {
                'duration': duration,
                'words': [],
                'segments': [],
            }
            result['type'] = video_type
            for key in ('question', 'options', 'correct', 'explanation',
                        'full_script', 'translations', 'hashtags',
                        'english_phrases', 'statement', 'sentence',
                        'word', 'phonetic', 'common_mistake', 'tip'):
                if key in script_data:
                    result[key] = script_data[key]

        self._save_json(output_path, result)
        return result

    def generate_audio(self, text: str, output_path: str, **kwargs) -> Dict:
        from tts_google import generate_segment_audio
        from tts_common import get_audio_duration

        voice = kwargs.get('voice', self.voice)
        speed = kwargs.get('speed', self.speed)

        duration = generate_segment_audio(text, output_path, voice=voice, speed=speed)
        return {
            'duration': duration,
            'words': [],
        }

    @staticmethod
    def _save_json(output_path: str, result: Dict):
        json_path = output_path.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

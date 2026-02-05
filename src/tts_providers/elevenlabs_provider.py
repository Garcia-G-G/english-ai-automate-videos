"""ElevenLabs TTS provider — wraps tts_elevenlabs.py."""

import json
import logging
from typing import Dict

from tts_base import TTSProvider

logger = logging.getLogger(__name__)


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, voice_id: str = None):
        from tts_elevenlabs import DEFAULT_VOICE_ID
        self.voice_id = voice_id or DEFAULT_VOICE_ID

    def generate_from_script(self, script_data: Dict, output_path: str, **kwargs) -> Dict:
        from tts_elevenlabs import generate_quiz_audio_segmented, generate_segment_audio
        from tts_common import get_audio_duration

        voice_id = kwargs.get('voice_id', self.voice_id)

        video_type = script_data.get('type', 'educational')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data,
                output_path=output_path,
                voice_id=voice_id,
            )
        else:
            # ElevenLabs only has segment-based for quiz; fall back to
            # simple generation for other types
            text = script_data.get('full_script', '')
            if not text:
                raise ValueError("Script missing 'full_script' field")

            duration = generate_segment_audio(text, output_path, voice_id=voice_id)
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
        from tts_elevenlabs import generate_segment_audio
        from tts_common import get_audio_duration

        voice_id = kwargs.get('voice_id', self.voice_id)

        duration = generate_segment_audio(text, output_path, voice_id=voice_id)
        return {
            'duration': duration,
            'words': [],
        }

    @staticmethod
    def _save_json(output_path: str, result: Dict):
        json_path = output_path.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

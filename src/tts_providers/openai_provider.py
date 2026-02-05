"""OpenAI TTS provider — wraps tts_openai.py."""

import json
import logging
from typing import Dict

from tts_base import TTSProvider

logger = logging.getLogger(__name__)


class OpenAITTSProvider(TTSProvider):
    name = "openai"

    def __init__(self, voice: str = None, model: str = None, speed: float = None):
        from tts_openai import DEFAULT_VOICE, DEFAULT_MODEL, DEFAULT_SPEED
        self.voice = voice or DEFAULT_VOICE
        self.model = model or DEFAULT_MODEL
        self.speed = speed or DEFAULT_SPEED

    def generate_from_script(self, script_data: Dict, output_path: str, **kwargs) -> Dict:
        from tts_openai import (
            generate_quiz_audio_segmented,
            generate_true_false_audio_segmented,
            text_to_speech,
        )

        voice = kwargs.get('voice', self.voice)
        model = kwargs.get('model', self.model)
        speed = kwargs.get('speed', self.speed)

        video_type = script_data.get('type', 'educational')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(script_data, output_path, voice, model, speed)
        elif video_type == 'true_false':
            result = generate_true_false_audio_segmented(script_data, output_path, voice, model, speed)
        else:
            text = script_data.get('full_script', '')
            if not text:
                raise ValueError("Script missing 'full_script' field")

            # Collect explicit English words from script
            explicit_english = None
            script_path = kwargs.get('script_path')
            if script_path:
                from tts_common import extract_english_words_from_script
                explicit_english = extract_english_words_from_script(script_data)

            timestamps = text_to_speech(
                text, output_path, voice=voice, model=model, speed=speed,
                explicit_english=explicit_english,
            )
            result = {**timestamps}
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
        from tts_openai import text_to_speech

        voice = kwargs.get('voice', self.voice)
        model = kwargs.get('model', self.model)
        speed = kwargs.get('speed', self.speed)
        explicit_english = kwargs.get('explicit_english')

        return text_to_speech(text, output_path, voice=voice, model=model,
                              speed=speed, explicit_english=explicit_english)

    @staticmethod
    def _save_json(output_path: str, result: Dict):
        json_path = output_path.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

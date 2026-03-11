"""Edge TTS provider — wraps tts.py (free, local)."""

import asyncio
import logging
from typing import Dict

from tts_base import TTSProvider

logger = logging.getLogger(__name__)


class EdgeTTSProvider(TTSProvider):
    name = "edge"

    def __init__(self, voice: str = None, rate: str = None, mode: str = "hybrid"):
        from tts import DEFAULT_VOICE, DEFAULT_RATE
        self.voice = voice or DEFAULT_VOICE
        self.rate = rate or DEFAULT_RATE
        self.mode = mode

    def generate_from_script(self, script_data: Dict, output_path: str, **kwargs) -> Dict:
        """Edge TTS generates audio from full_script for all types."""
        text = script_data.get('full_script', '')
        if not text:
            raise ValueError("Script missing 'full_script' field")

        from tts_common import clean_for_tts
        text = clean_for_tts(text)
        result = self.generate_audio(text, output_path, **kwargs)
        self.copy_script_metadata(script_data, result)
        self.save_json(output_path, result)
        return result

    def generate_audio(self, text: str, output_path: str, **kwargs) -> Dict:
        mode = kwargs.get('mode', self.mode)
        voice = kwargs.get('voice', self.voice)
        rate = kwargs.get('rate', self.rate)

        if mode == "hybrid":
            from tts import text_to_speech_hybrid, DEFAULT_ENGLISH_VOICE
            english_voice = kwargs.get('english_voice', DEFAULT_ENGLISH_VOICE)
            result = asyncio.run(text_to_speech_hybrid(
                text, output_path,
                spanish_voice=voice, english_voice=english_voice,
                spanish_rate=rate,
            ))
        elif mode == "ssml":
            from tts import text_to_speech_ssml
            result = asyncio.run(text_to_speech_ssml(
                text, output_path, voice=voice, rate=rate,
            ))
        else:
            from tts import text_to_speech
            result = asyncio.run(text_to_speech(
                text, output_path, voice=voice, rate=rate,
            ))

        return result

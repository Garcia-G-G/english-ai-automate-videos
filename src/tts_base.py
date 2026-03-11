"""Abstract base class for TTS providers."""

import json
from abc import ABC, abstractmethod
from typing import Dict, Optional


# Keys copied from script_data to result JSON in every provider.
SCRIPT_DATA_KEYS = (
    'question', 'options', 'correct', 'explanation',
    'full_script', 'translations', 'hashtags',
    'english_phrases', 'statement', 'sentence',
    'word', 'phonetic', 'common_mistake', 'tip',
    'translation', 'cta',
)


class TTSProvider(ABC):
    """Base class for all TTS providers.

    Each provider wraps an existing TTS module and exposes a uniform
    interface so main.py can call any provider the same way.

    The two core methods correspond to the two TTS flows used by the
    pipeline:

    * generate_from_script — takes a script JSON dict, produces audio
      and a result dict with timestamps.  Handles quiz, true_false,
      educational, etc. based on the script's "type" field.

    * generate_audio — low-level: takes raw text, returns timestamps
      dict.  Used by the Edge fallback path and simple text mode.
    """

    name: str = "base"

    @abstractmethod
    def generate_from_script(
        self,
        script_data: Dict,
        output_path: str,
        **kwargs,
    ) -> Dict:
        """Generate audio from a script dict."""
        pass

    @abstractmethod
    def generate_audio(
        self,
        text: str,
        output_path: str,
        **kwargs,
    ) -> Dict:
        """Generate audio from raw text (simple/fallback flow)."""
        pass

    def get_name(self) -> str:
        return self.name

    # ── Shared helpers ────────────────────────────────────────────

    @staticmethod
    def save_json(output_path: str, result: Dict) -> None:
        """Write the companion JSON next to the audio file."""
        json_path = output_path.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    @staticmethod
    def copy_script_metadata(script_data: Dict, result: Dict) -> None:
        """Copy standard script keys into the result dict."""
        result['type'] = script_data.get('type', 'educational')
        for key in SCRIPT_DATA_KEYS:
            if key in script_data:
                result[key] = script_data[key]

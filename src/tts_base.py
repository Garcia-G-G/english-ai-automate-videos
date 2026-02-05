"""Abstract base class for TTS providers."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


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
        """Generate audio from a script dict.

        This is the primary entry point used by the pipeline.

        Args:
            script_data: Parsed script JSON (must contain 'type' and
                'full_script' at minimum).
            output_path: Where to write the MP3 file.

        Returns:
            Result dict with at least:
                duration: float
                words: list[dict]  (may be empty for segment-based)
                segments: list[dict]
                segment_times: dict  (for quiz/true_false)
        """
        pass

    @abstractmethod
    def generate_audio(
        self,
        text: str,
        output_path: str,
        **kwargs,
    ) -> Dict:
        """Generate audio from raw text (simple/fallback flow).

        Args:
            text: Plain text to speak.
            output_path: Where to write the MP3 file.

        Returns:
            Result dict with at least:
                duration: float
                words: list[dict]
        """
        pass

    def get_name(self) -> str:
        return self.name

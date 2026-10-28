"""TTS provider factory.

Usage:
    from tts_providers import get_tts_provider
    provider = get_tts_provider("elevenlabs")
    result = provider.generate_from_script(script_data, "output.mp3")

ElevenLabs is reached through OpenRouter only (tts_elevenlabs -> tts_openrouter). The OpenAI,
Google and Edge providers were removed (2026-10-27): OpenRouter is the only paid AI.
"""

from tts_base import TTSProvider


def get_tts_provider(name: str, **kwargs) -> TTSProvider:
    """Create a TTS provider by name. Only "elevenlabs" exists.

    Raises:
        ValueError: If provider name is unknown.
    """
    if name != "elevenlabs":
        raise ValueError(f"Unknown TTS provider: {name!r}. Available: elevenlabs")
    from tts_providers.elevenlabs_provider import ElevenLabsTTSProvider
    return ElevenLabsTTSProvider(voice_id=kwargs.get('voice_id'))

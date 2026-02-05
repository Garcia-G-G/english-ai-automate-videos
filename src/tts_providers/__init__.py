"""TTS provider factory.

Usage:
    from tts_providers import get_tts_provider
    provider = get_tts_provider("openai")
    result = provider.generate_from_script(script_data, "output.mp3")
"""

from tts_base import TTSProvider


def get_tts_provider(name: str, **kwargs) -> TTSProvider:
    """Create a TTS provider by name.

    Args:
        name: Provider name — "openai", "elevenlabs", "google", or "edge".
        **kwargs: Provider-specific constructor args (voice, model, etc.).

    Returns:
        A TTSProvider instance.

    Raises:
        ValueError: If provider name is unknown.
    """
    # Lazy imports to avoid loading unnecessary dependencies
    providers = {
        'openai': lambda: _make_openai(**kwargs),
        'elevenlabs': lambda: _make_elevenlabs(**kwargs),
        'google': lambda: _make_google(**kwargs),
        'edge': lambda: _make_edge(**kwargs),
    }

    if name not in providers:
        available = ', '.join(sorted(providers.keys()))
        raise ValueError(f"Unknown TTS provider: {name!r}. Available: {available}")

    return providers[name]()


def _make_openai(**kwargs):
    from tts_providers.openai_provider import OpenAITTSProvider
    return OpenAITTSProvider(
        voice=kwargs.get('voice'),
        model=kwargs.get('model'),
        speed=kwargs.get('speed'),
    )


def _make_elevenlabs(**kwargs):
    from tts_providers.elevenlabs_provider import ElevenLabsTTSProvider
    return ElevenLabsTTSProvider(
        voice_id=kwargs.get('voice_id'),
    )


def _make_google(**kwargs):
    from tts_providers.google_provider import GoogleTTSProvider
    return GoogleTTSProvider(
        voice=kwargs.get('voice'),
        speed=kwargs.get('speed'),
    )


def _make_edge(**kwargs):
    from tts_providers.edge_provider import EdgeTTSProvider
    return EdgeTTSProvider(
        voice=kwargs.get('voice'),
        rate=kwargs.get('rate'),
        mode=kwargs.get('mode', 'hybrid'),
    )

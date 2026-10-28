"""STEP 79 §00 / STEP 80 §1: whether a render may voice, and the panel header's balance line.

The voice goes through OpenRouter only (2026-10-27), so its monthly cap is the one balance that
decides: `panel_voice(chars)` grants voice to a panel render that fits the cap. The ElevenLabs
plan reading (and its key) were removed.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Optional


def script_chars(script: Optional[Dict]) -> Optional[int]:
    """A rough count of what a script would voice: its spoken text. None when not known."""
    if not script:
        return None
    if script.get("voice"):                                   # «Hecho con Claude»: one line per beat
        return sum(len(x) for x in script["voice"])
    if script.get("full_script"):
        parts = script["full_script"]
        return sum(len(p if isinstance(p, str) else p.get("text", "")) for p in parts) if isinstance(parts, list) else len(parts)
    return None


def openrouter_refusal(chars: int, spent: Optional[float] = None, cap: Optional[float] = None) -> Optional[str]:
    """None when a render voicing `chars` characters fits OpenRouter's monthly cap."""
    import tts_openrouter
    s = tts_openrouter._settings()
    spent = tts_openrouter.month_spend() if spent is None else spent
    cap = s["monthly_usd"] if cap is None else cap
    need = tts_openrouter.price_usd(chars, s["model"])
    if spent + need > cap:
        return (f"Tope mensual de OpenRouter: este mes van ${spent:.2f} de ${cap:.2f} y este render "
                f"necesitaría ≈ ${need:.2f}. No se gasta.")
    return None


def header_lines(openrouter_spent: Optional[float], cap: float) -> list:
    """The panel header: OpenRouter's spend this month against its cap. Dollars as entities, never LaTeX."""
    return ["OpenRouter: sin datos" if openrouter_spent is None
            else f"OpenRouter: &#36;{openrouter_spent:.2f} de &#36;{cap:.0f} este mes"]


class VoiceRefused(RuntimeError):
    """The panel refused to voice a render: it would pass OpenRouter's monthly cap."""


def cap_chars() -> int:
    """The most one video may voice: the per-video TTS cap in characters (when the script is not
    known yet, e.g. a random pick)."""
    from cost_tracker import per_video_tts_usd, tts_price_per_1k
    return int(per_video_tts_usd() / tts_price_per_1k("eleven_v3") * 1000)


@contextmanager
def panel_voice(chars: int):
    """The panel's «Crear video» / «Generar audio» actions only. Yields a grant token (voice
    allowed). Raises VoiceRefused when the render would pass OpenRouter's monthly cap."""
    import voice_lock
    why = openrouter_refusal(chars)
    if why:
        raise VoiceRefused(why)
    with voice_lock.panel_grant() as token:
        yield token

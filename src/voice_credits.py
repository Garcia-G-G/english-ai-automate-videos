"""STEP 79 §00: what is left on the ElevenLabs plan, and whether a render may voice.

`remaining()` reads GET /v1/user/subscription, which is free and generates nothing; it is cached
for CACHE_S so a panel page draw does not ask on every rerun. `refusal(chars)` is the panel's
check before it grants voice to a render.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from contextlib import contextmanager
from typing import Dict, Optional

URL = "https://api.elevenlabs.io/v1/user/subscription"
CACHE_S = 60.0
#: A render may not leave less than this share of the plan.
FLOOR = 0.05

_cache: Dict = {"at": 0.0, "value": None}


def _fetch(timeout: float = 6.0) -> Optional[Dict]:
    from env_setup import ensure_env_loaded
    ensure_env_loaded()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if len(key) < 10:
        return None
    request = urllib.request.Request(URL, headers={"xi-api-key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
        used, limit = int(data["character_count"]), int(data["character_limit"])
    except Exception:                                       # noqa: BLE001 — unreachable is an answer
        return None
    return {"used": used, "limit": limit, "remaining": max(0, limit - used),
            "resets": data.get("next_character_count_reset_unix")}


def remaining(fetch=None, now=time.time) -> Optional[Dict]:
    """{used, limit, remaining, resets}, or None when the endpoint cannot be reached. Under
    pytest nothing is fetched unless a test passes `fetch`."""
    if fetch is None:
        import sys
        if "pytest" in sys.modules:
            return None
        fetch = _fetch
    if _cache["at"] and now() - _cache["at"] < CACHE_S:   # a failed read is cached too (STEP 80 §3:
        return _cache["value"]                            # a 401 cost 0.4 s on every click)
    value = fetch()
    _cache.update(at=now(), value=value)
    return value


def header_text(info: Optional[Dict]) -> str:
    if info is None:
        return "Voz: no se pudo leer el saldo de ElevenLabs (solo audio en caché)"
    return f"Voz: {info['remaining']:,} caracteres restantes".replace(",", ".")


def refusal(chars: int, info: Optional[Dict]) -> Optional[str]:
    """None when a render needing `chars` characters may voice; otherwise why not, in Spanish.
    With no reading (info None) the render may still run, but only from cache: the caller does
    not grant voice."""
    if info is None:
        return ("No se pudo leer el saldo de ElevenLabs: solo se permiten renders con todo el audio "
                "en caché.")
    left = info["remaining"] - chars
    if chars > info["remaining"]:
        return (f"Sin voz suficiente: este render necesita ≈ {chars:,} caracteres y quedan "
                f"{info['remaining']:,}.").replace(",", ".")
    if left < FLOOR * info["limit"]:
        return (f"Este render (≈ {chars:,} caracteres) dejaría {left:,} de {info['limit']:,}, menos del "
                f"5 % del plan. No se gasta.").replace(",", ".")
    return None


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


def header_lines(info: Optional[Dict], openrouter_spent: Optional[float], cap: float) -> list:
    """The panel header (STEP 80 §1): both balances. Dollars as entities, never LaTeX."""
    eleven = ("Voz ElevenLabs: no se pudo leer el saldo" if info is None
              else f"Voz ElevenLabs: {info['remaining']:,} car.".replace(",", "."))
    router = ("OpenRouter: sin datos" if openrouter_spent is None
              else f"OpenRouter: &#36;{openrouter_spent:.2f} de &#36;{cap:.0f} este mes")
    return [eleven, router]


class VoiceRefused(RuntimeError):
    """The panel refused to voice a render: not enough characters left on the plan."""


def cap_chars() -> int:
    """The most one video may voice: the per-video TTS cap in characters (when the script is not
    known yet, e.g. a random pick)."""
    from cost_tracker import per_video_tts_usd, tts_price_per_1k
    return int(per_video_tts_usd() / tts_price_per_1k("eleven_v3") * 1000)


@contextmanager
def panel_voice(chars: int, note=lambda message: None, read=None):
    """The panel's «Crear video» / «Generar audio» actions only. Yields a grant token (voice
    allowed) or None (the balance could not be read: cache only). Raises VoiceRefused when the
    render needs more than remains or would leave less than 5 % of the plan."""
    import voice_lock
    import tts_openrouter
    if tts_openrouter.active():                           # STEP 80 §1: OpenRouter's monthly cap decides
        why = openrouter_refusal(chars)
        if why:
            raise VoiceRefused(why)
        with voice_lock.panel_grant() as token:
            yield token
        return
    info = (read or remaining)()
    if info is None:
        note(refusal(chars, None))
        yield None
        return
    why = refusal(chars, info)
    if why:
        raise VoiceRefused(why)
    with voice_lock.panel_grant() as token:
        yield token

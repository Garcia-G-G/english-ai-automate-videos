"""STEP 80 §1: ElevenLabs voice through OpenRouter (ElevenLabs' own plan is at 7K characters
until 1 Nov).

    POST https://openrouter.ai/api/v1/audio/speech
    {"model": "elevenlabs/eleven-v4", "input": text, "voice": <the channel's voice id>,
     "response_format": "mp3",
     "provider": {"options": {"elevenlabs": {"language_code", "voice_settings", "previous_text", "next_text"}}}}

No `speed` (v4 refuses it). The answer is audio only, no timestamps: the callers already handle a
plain-convert segment. Before every request: the STEP 79 §00 voice lock (only the panel's own click
may spend), the voice's category (a cloned or generated voice only works with BYOK, which would
spend the same ElevenLabs quota) and the caps — $0.25 of OpenRouter per Short, $15 a month.
Every answered request is one row in output/costs/ (api_type «openrouter_tts»).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, Optional

URL = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "elevenlabs/eleven-v4"
KEY_NAME = "OPENROUTER_API_KEY"
PER_SHORT_USD, MONTHLY_USD = 0.25, 15.0
#: Voice categories OpenRouter can speak with the channel's voice id (no BYOK).
USABLE_CATEGORIES = {"premade", "library", "shared", "professional_library"}
#: v3 tags → what v4 lists (OpenRouter's examples: [curious], [cheerfully], [whispering]).
V4_TAGS = {"cheerful": "cheerfully", "whispers": "whispering"}


class OpenRouterRefused(RuntimeError):
    """The request was not sent: a cap, the voice, or a missing key. The message is Spanish."""


def _settings() -> Dict:
    import queue_priority
    cfg = queue_priority._config()                          # parsed once per change of config.yaml
    audio = cfg.get("audio") or {}
    costs = cfg.get("costs") or {}
    voice = audio.get("openrouter_voice") or {}
    return {"provider": audio.get("provider", "elevenlabs"),
            "voice_name": voice.get("name"), "voice_category": voice.get("category", audio.get("voice_category")),
            "humanize": bool(audio.get("humanize_v4", True)),
            "model": audio.get("openrouter_model", MODEL),
            "per_short_usd": float(costs.get("openrouter_per_short_usd", PER_SHORT_USD)),
            "monthly_usd": float(costs.get("openrouter_monthly_usd", MONTHLY_USD))}


def active() -> bool:
    """config.yaml audio.provider is «openrouter»."""
    try:
        return _settings()["provider"] == "openrouter"
    except Exception:                                       # noqa: BLE001 — no config: not active
        return False


def price_usd(characters: int, model: str = MODEL) -> float:
    from cost_tracker import PRICING
    return characters * PRICING[model]["per_1m_chars"] / 1_000_000


def month_spend(costs_dir: Optional[Path] = None) -> float:
    """OpenRouter dollars logged this calendar month (output/costs/)."""
    from cost_tracker import COSTS_DIR, get_tracker
    folder = Path(costs_dir) if costs_dir else COSTS_DIR
    total = 0.0
    for path in folder.glob(f"costs_{date.today():%Y-%m}-*.jsonl"):
        total += _file_spend(path)
    tracker = get_tracker()                                 # this job's rows, not saved yet
    total += sum(e["cost_usd"] for e in tracker.entries[tracker._saved:]
                 if str(e.get("api_type", "")).startswith("openrouter"))
    return round(total, 4)


_FILE_SPEND: Dict[tuple, float] = {}


def _file_spend(path: Path) -> float:
    """OpenRouter dollars in one cost file, cached by (path, mtime, size): the panel asks every click."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _FILE_SPEND:
        total = 0.0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if str(row.get("api_type", "")).startswith("openrouter"):
                total += float(row.get("cost_usd") or 0)
        _FILE_SPEND[key] = total
    return _FILE_SPEND[key]


def short_spend() -> float:
    from cost_tracker import get_tracker
    return sum(e["cost_usd"] for e in get_tracker().entries if str(e.get("api_type", "")).startswith("openrouter"))


def check_caps(upcoming_usd: float, settings: Optional[Dict] = None) -> None:
    s = settings or _settings()
    spent = short_spend()
    if spent + upcoming_usd > s["per_short_usd"]:
        raise OpenRouterRefused(f"Tope de OpenRouter por vídeo: este vídeo lleva ${spent:.3f} y la siguiente "
                                f"petición costaría ${upcoming_usd:.3f}; el tope es ${s['per_short_usd']:.2f}. "
                                f"No se pidió nada más.")
    month = month_spend()
    if month + upcoming_usd > s["monthly_usd"]:
        raise OpenRouterRefused(f"Tope mensual de OpenRouter: este mes van ${month:.2f} de ${s['monthly_usd']:.2f}. "
                                f"No se pidió nada más.")


VOICE_ID_NAME = "OPENROUTER_VOICE_ID"


def voice_id(kwargs: Dict) -> str:
    """The voice OpenRouter speaks with: OPENROUTER_VOICE_ID (env/.env or the Keychain; Garcia chose
    Matilda, a female premade voice, 2026-10-26), else the channel's own voice id."""
    import secret_store
    return secret_store.get(VOICE_ID_NAME) or kwargs["voice_id"]


def check_voice(settings: Optional[Dict] = None) -> None:
    """The voice must be one OpenRouter can use without BYOK (config audio.openrouter_voice.category)."""
    import secret_store
    s = settings or _settings()
    if s.get("voice_name") is not None and not secret_store.get(VOICE_ID_NAME):
        raise OpenRouterRefused(
            f"Falta el id de la voz {s['voice_name']!r} ({VOICE_ID_NAME} no está en el entorno, .env ni el "
            "Llavero). Sin él se usaría la voz clonada del canal, que gasta la cuota de ElevenLabs. "
            "No se pidió nada.")
    category =s.get("voice_category") if (s.get("voice_name") is None or secret_store.get(VOICE_ID_NAME)) else None
    if category not in USABLE_CATEGORIES:
        raise OpenRouterRefused(
            "La voz del canal no está confirmada para OpenRouter (config.yaml audio.voice_category = "
            f"{category!r}). Solo una voz «premade» o de la biblioteca funciona sin BYOK; una clonada o "
            "generada gastaría la misma cuota de ElevenLabs. No se pidió nada.")


def v4_text(text: str) -> str:
    """The v3 tags v4 names differently ([cheerful] → [cheerfully])."""
    return re.sub(r"\[(\w+)\]", lambda m: f"[{V4_TAGS.get(m.group(1), m.group(1))}]", text)


#: A laugh the script itself asks for: «jaja», «haha», 😂 🤣 😅.
_LAUGH = re.compile(r"\b(?:ja(?:ja)+|ha(?:ha)+)\b[!.]*|[😂🤣😅]", re.I)


def humanize(text: str) -> str:
    """STEP 80 §1 (Garcia: pauses, a laugh — what ElevenLabs can do): the v4 delivery cues, taken
    from the script, never invented. Placeholders that are not tags go ([name]); a laugh the
    script writes becomes [laughs]; «...» becomes a [short pause]; a question the narration goes
    on to answer gets a [short pause] after it, the time to think."""
    from audio_tags import keep_known_tags
    out = keep_known_tags(text)
    out = _LAUGH.sub(" [laughs] ", out)
    out = re.sub(r"\s*(?:\.\.\.|…)\s*(?=\S)", " [short pause] ", out)
    out = re.sub(r"\?(\s+)(?=(?:\[[^\]]*\]\s*)*[¿A-ZÁÉÍÓÚÑa-záéíóúñ])", r"? [short pause]\1", out)
    out = re.sub(r"(\[laughs\]\s*){2,}", "[laughs] ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)          # no space left before punctuation
    return re.sub(r"\s{2,}", " ", v4_text(out)).strip()


def _voice_settings(vs) -> Dict:
    """VoiceSettings (pydantic) or a dict, without `speed` (v4 refuses it)."""
    raw = vs.model_dump() if hasattr(vs, "model_dump") else dict(vs or {})
    return {k: v for k, v in raw.items() if v is not None and k != "speed"}


def request_body(kwargs: Dict, model: str = MODEL) -> Dict:
    options = {"voice_settings": _voice_settings(kwargs.get("voice_settings"))}
    for key in ("language_code", "previous_text", "next_text"):
        if kwargs.get(key):
            options[key] = kwargs[key]
    text = humanize(kwargs["text"]) if kwargs.get("_humanize", True) else v4_text(kwargs["text"])
    return {"model": model, "input": text, "voice": voice_id(kwargs),
            "response_format": "mp3", "provider": {"options": {"elevenlabs": options}}}


#: Spend of requests sent but not yet recorded. Segments are voiced in parallel (6 at a time), so
#: each cap check must count the others in flight or the caps could be overshot by a few requests.
_IN_FLIGHT = {"usd": 0.0}
_IN_FLIGHT_LOCK = threading.Lock()


def speak(kwargs: Dict, out_path, opener=None, retries: int = 3) -> None:
    """One request through OpenRouter, the mp3 written to `out_path`. `kwargs` are the ElevenLabs
    convert arguments the callers already build (voice_id, text, model_id, language_code,
    voice_settings, previous_text, next_text)."""
    import voice_lock
    s = _settings()
    check_voice(s)
    cost = price_usd(len(kwargs["text"]), s["model"])
    voice_lock.check(f"una petición de {len(kwargs['text'])} caracteres a OpenRouter ({s['model']})")
    with _IN_FLIGHT_LOCK:
        check_caps(cost + _IN_FLIGHT["usd"], s)
        _IN_FLIGHT["usd"] += cost
    try:
        _send(kwargs, out_path, s, cost, opener, retries)
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT["usd"] -= cost


def _send(kwargs: Dict, out_path, s: Dict, cost: float, opener, retries: int) -> None:
    import secret_store
    from cost_tracker import get_tracker
    key = secret_store.get(KEY_NAME)
    if not key:
        raise OpenRouterRefused("No hay clave de OpenRouter (entorno o Llavero «english-ai-videos»). No se pidió nada.")
    body = json.dumps(request_body({**kwargs, "_humanize": s.get("humanize", True)}, s["model"])).encode()
    opener = opener or urllib.request.urlopen
    for attempt in range(retries):
        request = urllib.request.Request(URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "audio/mpeg",
            "X-Title": "English Unlimited"})
        try:
            with opener(request, timeout=180) as response:
                audio = response.read()
            break
        except urllib.error.HTTPError as error:
            if (error.code == 429 or error.code >= 500) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            detail = error.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"OpenRouter answered {error.code}: {detail}") from None
    if not audio:
        raise RuntimeError("OpenRouter answered with no audio")
    Path(out_path).write_bytes(audio)
    # one row per answered request, with what it cost (STEP 80 §1)
    get_tracker()._add_entry("openrouter_tts", s["model"], cost, "tts_segment",
                             {"characters": len(kwargs["text"]), "provider": "openrouter"})

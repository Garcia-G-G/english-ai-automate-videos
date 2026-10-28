#!/usr/bin/env python3
"""Real word timings from ASR, in place of a char-proportional estimate.

    from asr_timings import transcribe_words, backend_name
    words = transcribe_words("segment.mp3", language="es")
    # -> [{"word": "hola", "start": 0.0, "end": 0.42}, ...]  or None

THE DEBT THIS CLOSES. D5: word positions inside a narration segment were
estimated by splitting the clip's duration in proportion to each token's
character count. A uniform estimate cannot know that a voice pauses at a
comma, lingers on a stressed syllable, or stops 0.4 s before the file does,
so the last word's END — which is what a segment declares as its end —
routinely overran the real speech.

That was tolerable while nothing depended on it. Adding "repeat after me"
to pronunciation made it block a feature: the 0.9 s pedagogical pauses came
out as 1.6 s of measured silence against a declaration that explained only
0.33-0.44 s of each, so the QA gate rejected a correct artifact for dead
air. The gate was right to ask; the artifact had never declared honestly.

DEFERRED SINCE JULY "pending ASR", and the ASR was already paid for:
requirements.txt has declared openai-whisper since then and nothing ever
imported it.

OPENROUTER FIRST, LOCAL SECOND (2026-10-27, measured on hc_e002's 35 s narration on the M3).
OpenRouter's /audio/transcriptions with ElevenLabs Scribe v2: 2.5 s, word times + confidence,
~$0.002, and only inside a panel job (voice_lock) so STEPs, tests and tools spend nothing. Local is
mlx-whisper large-v3-turbo in its own Python 3.12 process (src/asr_worker.py): free and offline but
~22 s for the same file. Both heard «spill the tea», which the CPU `base` model they replace missed
(it also crashed when two panel jobs transcribed at once). OpenAI's own API is not used: its key is
dead on purpose. Which one ran is recorded on every result rather than
inferred, because "we have real timings now" is exactly the kind of claim that needs its source.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
#: The project's Python 3.12 venv, which has mlx-whisper (MLX needs >= 3.10). Still its own
#: process even when the panel runs on it: MLX is not thread-safe and job threads share a process.
VENV_PYTHON = Path(os.getenv("ASR_PYTHON") or ROOT / ".venv" / "bin" / "python")
LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "mlx-community/whisper-large-v3-turbo")
OPENROUTER_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
OPENROUTER_MODEL = "elevenlabs/scribe-v2"

_BACKEND: Optional[str] = None
#: One worker process per panel process; the lock makes job threads take turns on it.
_WORKER: Optional[subprocess.Popen] = None
_LOCK = threading.Lock()


def backend_name() -> Optional[str]:
    """Which backend actually ran, or None if none has yet."""
    return _BACKEND


def reset() -> None:
    """Stop the worker and forget the backend. For tests."""
    global _WORKER, _BACKEND
    with _LOCK:
        if _WORKER is not None:
            _WORKER.kill()
        _WORKER, _BACKEND = None, None


def _worker() -> Optional[subprocess.Popen]:
    """The running mlx worker, started on first use (call with _LOCK held). None without the venv."""
    global _WORKER
    if _WORKER is not None and _WORKER.poll() is None:
        return _WORKER
    if not VENV_PYTHON.is_file():
        logger.info("asr: no %s — local word timings unavailable", VENV_PYTHON)
        return None
    _WORKER = subprocess.Popen([str(VENV_PYTHON), str(Path(__file__).with_name("asr_worker.py"))],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, bufsize=1)
    return _WORKER


def _words_from_local(path: Path, language: Optional[str]) -> Optional[List[Dict]]:
    """mlx-whisper word timings, or None (never raises)."""
    global _WORKER
    with _LOCK:
        try:
            worker = _worker()
            if worker is None:
                return None
            worker.stdin.write(json.dumps({"path": str(path), "language": language,
                                           "model": LOCAL_MODEL}) + "\n")
            worker.stdin.flush()
            reply = json.loads(worker.stdout.readline() or "{}")
        except Exception:                                   # noqa: BLE001 — a dead worker is restarted next call
            logger.exception("asr: local worker failed for %s", path)
            if _WORKER is not None:
                _WORKER.kill()
            _WORKER = None
            return None
    if reply.get("error") or "words" not in reply:
        logger.warning("asr: local transcription failed for %s: %s", path, reply.get("error"))
        return None
    return reply["words"] or None


def _words_from_openrouter(path: Path, language: Optional[str]) -> Optional[List[Dict]]:
    """Scribe v2 through OpenRouter, billed per second and recorded. Only inside a panel job
    (voice_lock): STEPs, tests and tools spend nothing. None on any failure."""
    import voice_lock
    if voice_lock.locked():
        return None
    try:
        import secret_store
        key = secret_store.get("OPENROUTER_API_KEY")
        if not key:
            return None
        with tempfile.TemporaryDirectory() as tmp:          # a 64 kbps mono mp3: ~10x smaller than the wav
            mp3 = Path(tmp) / "a.mp3"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-b:a", "64k", str(mp3)],
                           check=True, timeout=120)
            data = base64.b64encode(mp3.read_bytes()).decode()
        body = {"model": OPENROUTER_MODEL, "input_audio": {"data": data, "format": "mp3"},
                "response_format": "verbose_json", "timestamp_granularities": ["word"],
                **({"language": language} if language else {})}
        import urllib.request
        req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            answer = json.load(resp)
    except Exception:                                       # noqa: BLE001
        logger.exception("asr: OpenRouter transcription failed for %s", path)
        return None
    try:
        from cost_tracker import get_tracker
        get_tracker()._add_entry("openrouter_asr", OPENROUTER_MODEL, float((answer.get("usage") or {}).get("cost") or 0.0),
                                 "asr_word_timings", {"seconds": answer.get("duration")})
    except Exception:                                       # noqa: BLE001
        logger.warning("asr: could not record the transcription cost")
    words = [{"word": str(w.get("word", "")).strip(), "start": round(float(w["start"]), 3),
              "end": round(float(w["end"]), 3)}
             for w in answer.get("words") or [] if str(w.get("word", "")).strip()]
    return words or None


def transcribe_words(path, language: str = None) -> Optional[List[Dict]]:
    """Real word timings for one audio file, or None.

    None, never an exception and never a fabricated timeline: the caller
    keeps the char-proportional estimate it already had. Degrading to the
    old behaviour is acceptable; inventing timings and presenting them as
    measured is the failure this whole project has been unwinding.
    """
    global _BACKEND
    path = Path(path)
    if not path.is_file():
        return None

    from tts_common import merge_punctuation_tokens

    for name, run in ((f"openrouter:{OPENROUTER_MODEL}", _words_from_openrouter),
                      (f"local:{LOCAL_MODEL}", _words_from_local)):
        words = run(path, language)
        if words:
            _BACKEND = name
            return merge_punctuation_tokens(words, boundary_key=None)

    logger.warning("asr: no backend produced timings for %s", path.name)
    return None


def fit_to_clip(words: List[Dict], clip_seconds: float,
                text: str = None) -> List[Dict]:
    """Clamp ASR words into the clip they came from.

    ASR occasionally reports an end a few milliseconds past the file, and a
    word end beyond the clip would push a segment's declared end past its
    own audio — the exact defect being fixed. Clamped rather than dropped:
    the timing is right, the bound is what is off.
    """
    out = []
    for w in words or []:
        start = max(0.0, min(float(w["start"]), clip_seconds))
        end = max(start, min(float(w["end"]), clip_seconds))
        out.append({**w, "start": round(start, 3), "end": round(end, 3)})
    return out


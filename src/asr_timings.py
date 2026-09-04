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

LOCAL FIRST, API SECOND. Local Whisper costs nothing per run and keeps the
narration off the network; the API costs $0.006/min (about $0.005 for a 50 s
video) and exists as the fallback for a machine without the model. Which one
ran is recorded on every result rather than inferred, because "we have real
timings now" is exactly the kind of claim that needs its source attached.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

#: Which local model to load. `base` is the smallest that produces stable
#: word timings on our clips; `tiny` drifts on short Spanish segments.
#: Overridable so a slower, better model can be tried without a code change.
LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "base")

#: OpenAI's published rate for whisper-1, per minute of audio.
API_COST_PER_MINUTE = 0.006

#: Loaded once per process. Loading `base` takes a few seconds and the
#: narration for one video is a dozen short clips.
_MODEL = None
_BACKEND: Optional[str] = None


def backend_name() -> Optional[str]:
    """Which backend actually ran, or None if none has yet."""
    return _BACKEND


def reset() -> None:
    """Drop the cached model. For tests."""
    global _MODEL, _BACKEND
    _MODEL, _BACKEND = None, None


def _local_model():
    """The local Whisper model, or None if it cannot be loaded.

    Never raises. A missing model must cost the estimate we already had,
    not the video.
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        import whisper
    except Exception:                                       # noqa: BLE001
        logger.info("asr: local whisper is not importable — will try the API")
        return None
    try:
        started = time.time()
        _MODEL = whisper.load_model(LOCAL_MODEL)
        logger.info("asr: loaded local whisper %r in %.1fs",
                    LOCAL_MODEL, time.time() - started)
        return _MODEL
    except Exception:                                       # noqa: BLE001
        logger.exception("asr: could not load local whisper %r", LOCAL_MODEL)
        return None


def _words_from_local(path: Path, language: Optional[str]) -> Optional[List[Dict]]:
    model = _local_model()
    if model is None:
        return None
    try:
        result = model.transcribe(str(path), word_timestamps=True,
                                  language=language, verbose=False)
    except Exception:                                       # noqa: BLE001
        logger.exception("asr: local transcription failed for %s", path)
        return None

    words = []
    for segment in result.get("segments") or []:
        for w in segment.get("words") or []:
            token = str(w.get("word", "")).strip()
            if not token:
                continue
            words.append({"word": token,
                          "start": round(float(w["start"]), 3),
                          "end": round(float(w["end"]), 3)})
    return words or None


def _words_from_api(path: Path, language: Optional[str]) -> Optional[List[Dict]]:
    """whisper-1, billed per minute. Logs its own cost to the tracker."""
    try:
        from openai import OpenAI
    except Exception:                                       # noqa: BLE001
        return None
    try:
        client = OpenAI()
        with open(path, "rb") as handle:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=handle,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                **({"language": language} if language else {}),
            )
    except Exception:                                       # noqa: BLE001
        logger.exception("asr: API transcription failed for %s", path)
        return None

    try:
        from cost_tracker import get_tracker
        from tts_common import get_audio_duration
        get_tracker().log_openai_whisper(
            duration_seconds=get_audio_duration(str(path)),
            label="asr_word_timings")
    except Exception:                                       # noqa: BLE001
        logger.warning("asr: could not record the whisper cost")

    words = []
    for w in (getattr(transcript, "words", None) or []):
        token = str(getattr(w, "word", "")).strip()
        if token:
            words.append({"word": token,
                          "start": round(float(w.start), 3),
                          "end": round(float(w.end), 3)})
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

    words = _words_from_local(path, language)
    if words:
        words = merge_punctuation_tokens(words, boundary_key=None)
        _BACKEND = f"local:{LOCAL_MODEL}"
        return words

    words = _words_from_api(path, language)
    if words:
        words = merge_punctuation_tokens(words, boundary_key=None)
        _BACKEND = "api:whisper-1"
        return words

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


def api_cost_for(seconds: float) -> float:
    """What the API fallback would bill for this much audio."""
    return round(max(0.0, float(seconds)) / 60.0 * API_COST_PER_MINUTE, 6)

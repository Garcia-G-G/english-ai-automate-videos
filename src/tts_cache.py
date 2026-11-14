"""A content-addressed cache of TTS calls (STEP 76 §4).

Every ElevenLabs request that makes audio goes through _elevenlabs_with_retry (convert) or
tts_bilingual._synthesize_segment (convert_with_timestamps). Both look here first. The key is
the sha1 of everything that changes the audio — voice, model, the final text, voice settings,
language, previous/next text, output format — plus the take index, so the onset gate's
re-asks are distinct entries rather than the same audio handed back. An aborted run that is
started again pays only for what it had not reached.

Entries live in output/cache/tts/: <key>.mp3 and <key>.json (the alignment, when the endpoint
returned one, and the request without its secrets). tools/cleanup.py never deletes output/cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "output" / "cache" / "tts"

#: Request fields that shape the audio. Anything else (client objects, timeouts) is not key.
KEY_FIELDS = ("voice_id", "model_id", "text", "voice_settings", "language_code", "previous_text",
              "next_text", "output_format", "seed", "endpoint")

#: A cache hit is free; counted so a caller (and a test) can see that nothing was asked.
STATS = {"hits": 0, "misses": 0}


def _plain(value: Any) -> Any:
    """VoiceSettings and friends as plain JSON."""
    if hasattr(value, "model_dump"):
        return {k: v for k, v in value.model_dump().items() if v is not None}
    if hasattr(value, "dict"):
        return {k: v for k, v in value.dict().items() if v is not None}
    return value


def key(request: Dict[str, Any], take: int = 0) -> str:
    material = {k: _plain(request.get(k)) for k in KEY_FIELDS if request.get(k) not in (None, "")}
    material["take"] = int(take)
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _paths(k: str):
    return CACHE_DIR / f"{k}.mp3", CACHE_DIR / f"{k}.json"


def restore(k: str, out_path) -> Optional[Dict]:
    """Copy a cached clip to `out_path`. Returns its record ({'alignment': …}) or None on a miss."""
    audio, meta = _paths(k)
    if not (audio.is_file() and meta.is_file()):
        STATS["misses"] += 1
        return None
    try:
        record = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        STATS["misses"] += 1
        return None
    shutil.copyfile(audio, out_path)
    STATS["hits"] += 1
    logger.info("tts cache: hit %s (%s)", k[:10], (record.get("request") or {}).get("text", "")[:50])
    return record


def store(k: str, audio_path, request: Dict[str, Any], alignment: Optional[Dict] = None) -> None:
    """Keep a clip the API just returned. Never raises: a cache that cannot write costs a
    cache entry, not the clip."""
    audio, meta = _paths(k)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(CACHE_DIR), suffix=".part")
        os.close(fd)
        shutil.copyfile(audio_path, tmp)
        os.replace(tmp, audio)
        record = {"request": {k2: _plain(request.get(k2)) for k2 in KEY_FIELDS if request.get(k2) is not None},
                  "alignment": alignment}
        meta.write_text(json.dumps(record, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        logger.exception("tts cache: could not store %s", k[:10])

"""Idempotent .env loading for modules that read os.environ directly.

WHY THIS EXISTS. Several modules read credentials from os.environ but never
load .env themselves. They worked anyway, because something upstream —
pipeline.py, admin.py, tts_elevenlabs at import — always happened to load it
first. The dependency was invisible until a module was invoked standalone.

That invisibility is the real cost, and it is not tidiness. Both confirmed
cases produced a MISLEADING MEASUREMENT:

  uploader.py         standalone, reported every platform "not configured"
                      while .env held valid credentials (recorded-debt 10)
  metadata_generator  standalone, os.environ.get("OPENAI_API_KEY") returned
                      None, the function took its silent fallback branch, and
                      the result looked exactly like "the API call never
                      fires" — the opposite of the truth

A silent fallback branch is indistinguishable from a feature that never runs.
Any harness that measures one of these modules standalone measures the wrong
code path and confirms the wrong hypothesis.

CALL THIS FROM AN ENTRY POINT, NOT AT IMPORT. Loading at module import would
change import-time side effects for every existing caller — the pipeline
already loads .env in its own order, and quietly reloading underneath it is
the kind of change that works until it does not.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _ROOT / ".env"

_loaded = False


def ensure_env_loaded(override: bool = False) -> bool:
    """Load .env once per process. Returns True if a file was read.

    Idempotent and safe to call from several entry points. `override` is False
    by default so an explicitly-exported environment variable always beats the
    file — a caller that has already set something meant to.
    """
    global _loaded
    if _loaded and not override:
        return True
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("python-dotenv not installed; relying on the ambient env")
        return False

    ok = load_dotenv(_ENV_PATH, override=override)
    _loaded = True
    if not ok:
        logger.debug("no .env at %s; relying on the ambient env", _ENV_PATH)
    return bool(ok)

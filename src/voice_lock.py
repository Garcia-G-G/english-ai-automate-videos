"""STEP 79 §00: the ElevenLabs lock. No STEP, test, tool or CLI run spends voice.

Every request that would reach ElevenLabs calls `check()` just before it is sent (after the
cache: a cache hit never gets here, so cached renders always work). `check()` raises VoiceLocked
unless the process holds a panel grant:

    the panel's own «Crear video» and lesson-voicing actions, clicked by Garcia, open
    `panel_grant()` for the job; a subprocess they launch gets the grant through `grant_env()`.

A grant is a one-off token file under output/.voice_grants/, removed when the job ends. Nothing
else creates one: the CLI, pytest, stills mode, tools/ and the lesson studio's commands run from a
terminal are locked by default.

`ELEVENLABS_LOCK=1` in the environment, or `costs.tts_lock: true` in config.yaml, locks even the
panel (an emergency stop). Neither can unlock anything.

Standard library only: the lesson studio's own venv imports this file too.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRANT_DIR = Path(os.environ.get("ELEVENLABS_GRANT_DIR") or ROOT / "output" / ".voice_grants")
CONFIG = ROOT / "config.yaml"
GRANT_ENV = "ELEVENLABS_GRANT"
LOCK_ENV = "ELEVENLABS_LOCK"

_ACTIVE: set = set()
_GUARD = threading.Lock()
#: Only the lock's own tests set this: under pytest a grant is never honoured otherwise.
_ALLOW_IN_TESTS = False


class VoiceLocked(RuntimeError):
    """A request would have reached ElevenLabs while voice is locked."""


def _on(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _config_lock() -> bool:
    """costs.tts_lock from config.yaml, read without yaml (this file is stdlib only)."""
    try:
        text = CONFIG.read_text(encoding="utf-8")
    except OSError:
        return False
    block = re.search(r"^costs:\s*\n((?:[ \t]+.*\n|\s*\n)*)", text, re.M)
    match = re.search(r"^\s+tts_lock:\s*(\S+)", block.group(1), re.M) if block else None
    return bool(match) and _on(match.group(1))


def forced() -> bool:
    """The emergency stop: the env or config.yaml locks everything, the panel included."""
    return _on(os.environ.get(LOCK_ENV, "")) or _config_lock()


def _in_tests() -> bool:
    return ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ) and not _ALLOW_IN_TESTS


def granted() -> bool:
    if _in_tests():
        return False
    with _GUARD:
        tokens = set(_ACTIVE)
    env = os.environ.get(GRANT_ENV, "")
    if env:
        tokens.add(env)
    return any(re.fullmatch(r"[0-9a-f]{32}", t) and (GRANT_DIR / t).exists() for t in tokens)


def locked() -> bool:
    return forced() or not granted()


def check(what: str = "una petición a ElevenLabs") -> None:
    """Raise VoiceLocked before `what` is sent, unless the panel granted voice."""
    if not locked():
        return
    why = ("ELEVENLABS_LOCK / costs.tts_lock está activado" if forced() else
           "solo «Crear video» o «Generar audio» del panel pueden gastar voz")
    raise VoiceLocked(f"Voz bloqueada: no se envió {what} ({why}). El audio en caché sí se usa.")


@contextmanager
def panel_grant():
    """For the panel's own render and voicing actions only: voice is allowed until the block ends."""
    token = secrets.token_hex(16)
    GRANT_DIR.mkdir(parents=True, exist_ok=True)
    path = GRANT_DIR / token
    path.write_text(str(os.getpid()), encoding="utf-8")
    with _GUARD:
        _ACTIVE.add(token)
    try:
        yield token
    finally:
        with _GUARD:
            _ACTIVE.discard(token)
        path.unlink(missing_ok=True)


def grant_env(token: str) -> dict:
    """The environment a subprocess of a granted panel job needs."""
    return {GRANT_ENV: token}

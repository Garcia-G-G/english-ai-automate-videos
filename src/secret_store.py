"""STEP 80 §1: a secret from the environment, else from the Mac's Keychain.

Garcia keeps the OpenRouter key in the login Keychain, never in a file:

    security add-generic-password -s english-ai-videos -a OPENROUTER_API_KEY -w

`get(name)` returns the value or None. It never prints, logs or writes it. Under pytest the
Keychain is never read (a test passes `reader`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable, Optional

SERVICE = "english-ai-videos"
_cache: dict = {}


def _keychain(name: str) -> Optional[str]:
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


def get(name: str, reader: Optional[Callable[[str], Optional[str]]] = None) -> Optional[str]:
    """The secret `name`: the environment first, then the Keychain (service «english-ai-videos»)."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if reader is None:
        if "pytest" in sys.modules:
            return None
        if name in _cache:
            return _cache[name]
        reader = _keychain
    value = reader(name)
    if reader is _keychain:
        _cache[name] = value
    return value


def where(name: str, reader: Optional[Callable[[str], Optional[str]]] = None) -> str:
    """For the panel: «entorno», «Llavero» or «no configurada» — never the value."""
    if os.environ.get(name, "").strip():
        return "entorno"
    return "Llavero" if get(name, reader) else "no configurada"

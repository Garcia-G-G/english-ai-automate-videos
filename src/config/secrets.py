"""API key validation and management.

Loads keys from .env, validates formats, and provides utilities
for masking, status reporting, and safe .env file updates.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Root .env path (project root)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Key definitions: name -> (required, format_regex, description)
_KEY_DEFINITIONS = {
    # OpenRouter is the only paid AI (2026-10-27); the OpenAI and ElevenLabs keys are gone.
    # Read through secret_store (the environment, then the Keychain), see get_api_status.
    "OPENROUTER_API_KEY": {
        "required": True,
        "pattern": r"^sk-or-.{20,}$",
        "description": "OpenRouter API key (sk-or-…)",
    },
    "OPENROUTER_VOICE_ID": {
        "required": False,
        "pattern": r"^[a-zA-Z0-9]{20,}$",
        "description": "Voice id OpenRouter speaks with (a premade ElevenLabs voice)",
    },
    "ELEVENLABS_VOICE_ID": {
        "required": False,
        "pattern": r"^[a-zA-Z0-9]{20,}$",
        "description": "ElevenLabs voice ID",
    },
    "TIKTOK_CLIENT_KEY": {
        "required": False,
        "pattern": r"^.{10,}$",
        "description": "TikTok client key",
    },
    "TIKTOK_CLIENT_SECRET": {
        "required": False,
        "pattern": r"^.{10,}$",
        "description": "TikTok client secret",
    },
    "YOUTUBE_CLIENT_ID": {
        "required": False,
        "pattern": r"^.{10,}\.apps\.googleusercontent\.com$",
        "description": "YouTube/Google OAuth client ID",
    },
    "YOUTUBE_CLIENT_SECRET": {
        "required": False,
        "pattern": r"^.{10,}$",
        "description": "YouTube/Google OAuth client secret",
    },
    "IG_USER_ID": {
        "required": False,
        "pattern": r"^\d{5,}$",
        "description": "Instagram account ID (optional; the Page's linked account is used)",
    },
    "FB_PAGE_ID": {
        "required": False,
        "pattern": r"^\d{5,}$",
        "description": "Facebook Page ID (numeric)",
    },
    "FB_PAGE_TOKEN": {
        "required": False,
        "pattern": r"^.{20,}$",
        "description": "Facebook long-lived Page access token",
    },
    "BREVO_API_KEY": {
        "required": False,
        "pattern": r"^xkeysib-.{20,}$",
        "description": "Brevo API key (transactional email)",
    },
}


def mask_key(key: Optional[str]) -> str:
    """Mask an API key, showing only the first 4 and last 4 characters.

    Returns '(not set)' for empty/None values and '****' for short keys.
    """
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def _validate_key(name: str, value: Optional[str]) -> dict:
    """Validate a single key and return its status dict."""
    definition = _KEY_DEFINITIONS.get(name, {})
    required = definition.get("required", False)
    pattern = definition.get("pattern", r"^.+$")
    description = definition.get("description", name)

    if not value:
        return {
            "name": name,
            "set": False,
            "valid": not required,
            "masked": "(not set)",
            "description": description,
            "error": "Required key is missing" if required else None,
        }

    format_ok = bool(re.match(pattern, value))
    return {
        "name": name,
        "set": True,
        "valid": format_ok,
        "masked": mask_key(value),
        "description": description,
        "error": f"Invalid format for {name}" if not format_ok else None,
    }


def get_api_status() -> dict:
    """Return a dict of all API key statuses keyed by name.

    Each entry contains: set, valid, masked, description, error.
    """
    import secret_store
    statuses = {}
    for name in _KEY_DEFINITIONS:
        # OpenRouter's key and voice may live in the Keychain instead of the environment
        value = secret_store.get(name) if name.startswith("OPENROUTER_") else os.environ.get(name)
        statuses[name] = _validate_key(name, value)
    return statuses


def voice_id_pattern() -> str:
    """The ElevenLabs voice-id format, as a regex.

    Exposed so config.yaml profile voice ids are checked against the SAME
    rule as the ELEVENLABS_VOICE_ID env var, rather than a second copy of it
    drifting in profiles.py.
    """
    return _KEY_DEFINITIONS["ELEVENLABS_VOICE_ID"]["pattern"]


def is_valid_voice_id(value: Optional[str]) -> bool:
    """True if `value` is a well-formed ElevenLabs voice id.

    A placeholder like "KIDS_VOICE_ID_PENDIENTE" is 22 characters, so a bare
    length check passes it; the underscores are what make it fail. Before
    this was wired up, such a placeholder resolved straight through
    profiles.apply_profile_env and reached the ElevenLabs API verbatim,
    failing at call time — after a video had already been scripted — rather
    than at config load.
    """
    return bool(value) and bool(re.match(voice_id_pattern(), value))



def save_env_key(key_name: str, value: str, env_path: Optional[Path] = None) -> None:
    """Safely update or add a key in the .env file.

    The value is checked against the key's pattern and may not contain a line break
    (one would add a second, unvalidated key). The file is written to a temp file and
    renamed over .env, so a crash mid-write cannot truncate it (STEP 75 §3).
    Preserves comments and every other line. Never logs the full key value.
    """
    if key_name not in _KEY_DEFINITIONS:
        raise ValueError(f"Unknown key: {key_name}")
    value = (value or "").strip()
    if any(c in value for c in "\r\n\0"):
        raise ValueError(f"{key_name}: a value cannot contain a line break")
    status = _validate_key(key_name, value)
    if not status["set"] or not status["valid"]:
        raise ValueError(f"{key_name}: {status['error'] or 'empty value'} — {status['description']}")

    path = Path(env_path) if env_path else _ENV_PATH
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []

    # Try to find and replace an existing definition
    pattern = re.compile(rf"^{re.escape(key_name)}\s*=")
    found = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key_name}={value}\n"
            found = True
            break

    if not found:
        # Ensure file ends with newline before appending
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key_name}={value}\n")

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("".join(lines))
        os.chmod(tmp, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    # Update the current process environment
    os.environ[key_name] = value

    # Log with masked value only
    print(f"Saved {key_name}={mask_key(value)} to {path.name}")

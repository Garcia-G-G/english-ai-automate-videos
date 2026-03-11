"""API key validation and management.

Loads keys from .env, validates formats, and provides utilities
for masking, status reporting, and safe .env file updates.
"""

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Root .env path (project root)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Key definitions: name -> (required, format_regex, description)
_KEY_DEFINITIONS = {
    "OPENAI_API_KEY": {
        "required": True,
        "pattern": r"^sk-.{20,}$",
        "description": "OpenAI API key (must start with 'sk-')",
    },
    "ELEVENLABS_API_KEY": {
        "required": False,
        "pattern": r"^[a-f0-9]{32}$",
        "description": "ElevenLabs API key (32-char hex string)",
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
    "INSTAGRAM_ACCESS_TOKEN": {
        "required": False,
        "pattern": r"^.{20,}$",
        "description": "Instagram/Meta access token",
    },
    "INSTAGRAM_BUSINESS_ACCOUNT_ID": {
        "required": False,
        "pattern": r"^\d{10,}$",
        "description": "Instagram business account ID (numeric)",
    },
    "TTS_PROVIDER": {
        "required": False,
        "pattern": r"^(openai|elevenlabs|google|edge)$",
        "description": "TTS provider name",
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
    statuses = {}
    for name in _KEY_DEFINITIONS:
        value = os.environ.get(name)
        statuses[name] = _validate_key(name, value)
    return statuses


def validate_all_keys() -> dict:
    """Validate all keys and return categorized warnings and errors.

    Returns:
        {"errors": [...], "warnings": [...], "ok": [...]}
    """
    result = {"errors": [], "warnings": [], "ok": []}
    statuses = get_api_status()

    for name, status in statuses.items():
        if status["error"]:
            if _KEY_DEFINITIONS[name]["required"]:
                result["errors"].append(f"{name}: {status['error']}")
            else:
                result["warnings"].append(f"{name}: {status['error']}")
        elif status["set"]:
            result["ok"].append(f"{name}: {status['masked']}")

    return result


def save_env_key(key_name: str, value: str) -> None:
    """Safely update or add a key in the .env file.

    Preserves existing comments and file structure. Creates the
    .env file if it does not exist. Never logs the full key value.
    """
    if key_name not in _KEY_DEFINITIONS:
        raise ValueError(f"Unknown key: {key_name}")

    lines = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text().splitlines(keepends=True)

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

    _ENV_PATH.write_text("".join(lines))

    # Update the current process environment
    os.environ[key_name] = value

    # Log with masked value only
    print(f"Saved {key_name}={mask_key(value)} to {_ENV_PATH.name}")

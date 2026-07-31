#!/usr/bin/env python3
"""Every module that reads credentials from the environment must ensure .env.

    python3 -m pytest tests/test_env_loading.py

Not tidiness. Both confirmed cases produced a MISLEADING MEASUREMENT, because
a silent fallback branch is indistinguishable from a feature that never runs:

  uploader.py         standalone, reported every platform "not configured"
                      while .env held valid credentials
  metadata_generator  standalone, OPENAI_API_KEY was None, the function took
                      its fallback branch, and it looked exactly like "the API
                      call never fires" — the opposite of the truth

Any future harness that measures one of these standalone measures the wrong
code path and confirms the wrong hypothesis.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

#: Environment variables that select a credential or an identity. Reading one
#: of these without .env produces wrong OUTPUT, not just a wrong report.
CREDENTIAL_VARS = {
    "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID",
    "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET",
    "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
    "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "VIDEO_PROFILE_VOICE_ID",
}

#: Modules that read a credential var but are documented as safe without
#: .env, with the reason. Anything else must ensure it.
DOCUMENTED_SAFE = {
    # profiles.py sets VIDEO_PROFILE_* itself; it is the writer, not a reader
    # that depends on .env for them.
    "profiles.py",
}


def _module_sources():
    for f in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        yield f, f.read_text(encoding="utf-8")


def _credential_reads(tree):
    """Line numbers where a CREDENTIAL_VARS name is read from the env."""
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        is_env = (
            (isinstance(fn, ast.Attribute) and fn.attr in ("getenv", "get"))
        )
        if not is_env or not n.args:
            continue
        first = n.args[0]
        if isinstance(first, ast.Constant) and first.value in CREDENTIAL_VARS:
            hits.append((n.lineno, first.value))
    return hits


def test_every_credential_reader_ensures_dotenv():
    offenders = []
    for path, src in _module_sources():
        if path.name in DOCUMENTED_SAFE:
            continue
        tree = ast.parse(src)
        reads = _credential_reads(tree)
        if not reads:
            continue
        ensures = ("load_dotenv" in src) or ("ensure_env_loaded" in src)
        if not ensures:
            names = sorted({v for _l, v in reads})
            offenders.append(f"{path.relative_to(ROOT)} reads {names}")

    assert not offenders, (
        "module reads a credential from the environment without ensuring "
        ".env is loaded — standalone it will take a silent fallback branch "
        "that looks like the feature never runs:\n  " + "\n  ".join(offenders))


def test_ensure_env_loaded_is_idempotent():
    from env_setup import ensure_env_loaded

    assert ensure_env_loaded() == ensure_env_loaded()


def test_ensure_env_loaded_does_not_clobber_an_explicit_export(monkeypatch):
    """A caller that already exported something meant to. override=False."""
    from env_setup import ensure_env_loaded
    monkeypatch.setenv("OPENAI_API_KEY", "explicitly-set-by-caller")

    ensure_env_loaded()

    import os
    assert os.environ["OPENAI_API_KEY"] == "explicitly-set-by-caller"


def test_the_two_confirmed_modules_are_guarded():
    """metadata_generator and tts_bilingual are the cases that actually
    produced wrong measurements."""
    for name in ("metadata_generator.py", "tts_bilingual.py"):
        src = (SRC / name).read_text(encoding="utf-8")
        assert "ensure_env_loaded" in src, f"{name} is unguarded again"


def test_env_is_ensured_at_an_entry_point_not_at_import():
    """Loading at import would change import-time side effects for every
    existing caller — the pipeline already loads .env in its own order."""
    for name in ("metadata_generator.py", "tts_bilingual.py"):
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        top_level_calls = [
            n for n in tree.body
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "ensure_env_loaded"
        ]
        assert not top_level_calls, (
            f"{name} calls ensure_env_loaded at import; it belongs in the "
            "entry point")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""Refuse writes into the real output/ tree while a test is running.

WHY THIS EXISTS, TWICE. An idempotency test wrote 13 fixture rows into the
real output/published/attempts.jsonl. PROMPT 3 covered that with a redirect
plus a runtime refusal — and then a SECOND leak turned up from the same test
run: output/uploaded/test_a_raising_platform_does_n0/, left by
move_uploaded_artifact before OUTPUT_DIR was isolated in that fixture.

Same class, one level up. The ledger had a single chokepoint
(record_publication) so its refusal could live in production code. The output
tree has no chokepoint: anything can shutil.move into it. So the chokepoint
here is the filesystem API itself, patched for the duration of every test.

WHAT IS AND IS NOT BLOCKED.

    reads       untouched. Many tests legitimately read real artifacts —
                the QA gate corpus, audio fixtures, rendered mp4s. Blocking
                those would gut the suite for no safety gain.

    writes      refused: open() in a writing mode, the shutil move/copy
                family, os replace/rename/remove/unlink, and the Path
                equivalents, when the target resolves inside output/.

    mkdir       refused only when it would CREATE something. A no-op
                mkdir(exist_ok=True) on a directory that already exists is
                allowed, because main.py does exactly that at import and an
                import is not pollution.

KNOWN LIMIT, stated rather than papered over: a subprocess writes without
going through these functions, so an ffmpeg invocation pointed at a real
output path is not caught. Layer 1 is what covers that — the directory
globals are redirected, so a test would have to construct a real path
deliberately to get there.
"""

from __future__ import annotations

import builtins
import os
import shutil
from pathlib import Path

#: The real tree, captured at import before any fixture can redirect it.
REAL_OUTPUT = (Path(__file__).resolve().parent.parent / "output").resolve()


class OutputTreeWriteRefused(RuntimeError):
    """A test tried to write into the real output/ tree."""


def _inside_real_output(path) -> bool:
    if path is None:
        return False
    try:
        p = Path(os.fspath(path))
    except (TypeError, ValueError):
        return False          # file descriptors and the like
    try:
        resolved = p if p.is_absolute() else (Path.cwd() / p)
        # Resolve without requiring existence, so a not-yet-created file in
        # the real tree is still caught.
        resolved = Path(os.path.normpath(str(resolved))).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == REAL_OUTPUT or REAL_OUTPUT in resolved.parents


def _refuse(path, what: str):
    raise OutputTreeWriteRefused(
        f"REFUSING {what} into the real output tree: {path}\n"
        f"A test left output/uploaded/test_a_raising_platform_does_n0/ behind "
        f"once already. Point the module's directory global at tmp_path (see "
        f"the autouse fixture in tests/conftest.py) instead of writing here."
    )


_WRITING_MODES = set("wax+")


def install(monkeypatch) -> None:
    """Patch the write primitives for the duration of one test."""

    real_open = builtins.open
    real_io_open = __import__("io").open

    def guarded_open(file, mode="r", *a, **kw):
        if set(str(mode)) & _WRITING_MODES and _inside_real_output(file):
            _refuse(file, f"open(mode={mode!r})")
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr("io.open", guarded_open)

    # ── shutil ───────────────────────────────────────────────────────
    for name in ("move", "copy", "copy2", "copyfile", "copytree"):
        real = getattr(shutil, name)

        def make(real=real, name=name):
            def guarded(src, dst, *a, **kw):
                if _inside_real_output(dst):
                    _refuse(dst, f"shutil.{name}")
                return real(src, dst, *a, **kw)
            return guarded
        monkeypatch.setattr(shutil, name, make())

    real_rmtree = shutil.rmtree

    def guarded_rmtree(path, *a, **kw):
        if _inside_real_output(path):
            _refuse(path, "shutil.rmtree")
        return real_rmtree(path, *a, **kw)
    monkeypatch.setattr(shutil, "rmtree", guarded_rmtree)

    # ── os ───────────────────────────────────────────────────────────
    for name, argno in (("replace", 1), ("rename", 1), ("remove", 0),
                        ("unlink", 0), ("rmdir", 0)):
        real = getattr(os, name)

        def make(real=real, name=name, argno=argno):
            def guarded(*a, **kw):
                if len(a) > argno and _inside_real_output(a[argno]):
                    _refuse(a[argno], f"os.{name}")
                return real(*a, **kw)
            return guarded
        monkeypatch.setattr(os, name, make())

    real_makedirs = os.makedirs

    def guarded_makedirs(name, *a, **kw):
        if _inside_real_output(name) and not Path(os.fspath(name)).exists():
            _refuse(name, "os.makedirs")
        return real_makedirs(name, *a, **kw)
    monkeypatch.setattr(os, "makedirs", guarded_makedirs)

    # ── pathlib (does NOT route through builtins.open) ───────────────
    real_write_text = Path.write_text
    real_write_bytes = Path.write_bytes
    real_path_open = Path.open
    real_mkdir = Path.mkdir
    real_touch = Path.touch
    real_p_unlink = Path.unlink

    def guarded_write_text(self, *a, **kw):
        if _inside_real_output(self):
            _refuse(self, "Path.write_text")
        return real_write_text(self, *a, **kw)

    def guarded_write_bytes(self, *a, **kw):
        if _inside_real_output(self):
            _refuse(self, "Path.write_bytes")
        return real_write_bytes(self, *a, **kw)

    def guarded_path_open(self, mode="r", *a, **kw):
        if set(str(mode)) & _WRITING_MODES and _inside_real_output(self):
            _refuse(self, f"Path.open(mode={mode!r})")
        return real_path_open(self, mode, *a, **kw)

    def guarded_mkdir(self, *a, **kw):
        # A no-op mkdir on an existing directory is not pollution; main.py
        # does exactly that at import time.
        if _inside_real_output(self) and not self.exists():
            _refuse(self, "Path.mkdir")
        return real_mkdir(self, *a, **kw)

    def guarded_touch(self, *a, **kw):
        if _inside_real_output(self):
            _refuse(self, "Path.touch")
        return real_touch(self, *a, **kw)

    def guarded_p_unlink(self, *a, **kw):
        if _inside_real_output(self):
            _refuse(self, "Path.unlink")
        return real_p_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "touch", guarded_touch)
    monkeypatch.setattr(Path, "unlink", guarded_p_unlink)

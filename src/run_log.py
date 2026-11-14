#!/usr/bin/env python3
"""One log file per run, so an unattended failure leaves evidence.

    from run_log import attach_run_log
    log_path = attach_run_log("job-ab4ed292")

WHY THIS EXISTS

Step 0 added logging.basicConfig at the render entry points, which installs a
StreamHandler on stderr. Nothing in this repo ever installed a FileHandler, so
every render log this project has produced went to whichever console launched
the process and nowhere else. Under `run_admin.sh` that is the terminal the
dashboard was started from — and on 2026-08-17 that terminal belonged to a
process started six days earlier, so a failure at 15:48 had no record at all.

Under 5a the pipeline publishes twice a day with nobody watching. A failure
at 3am that writes to a console nobody keeps is a failure nobody can diagnose.

DESIGN

Rotating, because a per-run file that grows without bound is the next
incident. Rotation is by SIZE rather than by time: runs are bursty (two a
day, minutes long) so a daily rotation would produce mostly-empty files while
one runaway render could still fill a disk.

The handler is attached to the ROOT logger, because the interesting records
come from modules that never configure logging themselves — video.compositor,
pipeline, tts_*, qa_gate — and they all propagate to root.

Idempotent: attaching twice for the same path does not double every line.
That matters because Streamlit re-executes its script on every rerun, and a
handler added at module scope would otherwise accumulate one copy per rerun.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"

MAX_BYTES = 10 * 1024 * 1024   # 10MB per file
BACKUP_COUNT = 5               # ~50MB ceiling for the whole directory

FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str) -> str:
    return _SAFE.sub("-", text).strip("-") or "run"


def run_log_path(label: str) -> Path:
    """Where this run's log will be written."""
    stamp = datetime.now().strftime("%Y%m%d")
    return LOG_DIR / f"{stamp}_{_slug(label)}.log"


def attach_run_log(label: str, level: int = logging.INFO) -> Path:
    """Attach a rotating file handler for this run and return its path.

    Safe to call repeatedly: a handler already writing to this path is left
    alone rather than duplicated.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = run_log_path(label)

    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            if Path(getattr(h, "baseFilename", "")) == path:
                return path

    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
    root.addHandler(handler)

    # basicConfig may never have run, in which case root defaults to WARNING
    # and every logger.info below it is dropped before reaching the file.
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)

    logging.getLogger(__name__).info(
        "run log attached: %s (pid %d)", path, os.getpid())
    return path


def detach_run_log(path: Optional[Path]) -> None:
    """Remove the handler for `path`, flushing and closing it."""
    if path is None:
        return
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler) and \
                Path(getattr(h, "baseFilename", "")) == Path(path):
            h.flush()
            h.close()
            root.removeHandler(h)

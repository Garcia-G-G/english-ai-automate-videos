"""What the dashboard must remember between clicks, kept in an IMPORTED module.

    import dashboard_state as ds
    with ds.RENDER_LOCK: ...
    version = ds.once("running_version", _running_version)

WHY THIS EXISTS. Streamlit runs src/admin.py with exec() in a FRESH module
namespace on every rerun -- that is, on every click. Everything admin.py
defined at module level was therefore rebuilt each time: its locks, its worker
list, its caches, its "read once at startup" values. Measured consequences on
2026-10-13:

  * _RENDER_LOCK was a new Lock per click, so two Generate clicks rendered in
    PARALLEL instead of queueing. Jobs ed730853 and ebe7bb3e overlapped; the
    render took 1153 s instead of ~290 s and the dashboard crawled throughout.
  * _JOBS_LOCK the same: the running worker and the page wrote the ledger
    under different locks, and job ebe7bb3e died on a rename race over
    generation_jobs.json.tmp.
  * the 20-second queue-audit cache was emptied by the very rerun that should
    have hit it; `ps` and `git` were forked on every click; the sidebar's
    "build ... started HH:MM" showed the time of the last click, not of the
    process start it exists to report.

An imported module runs once per process (until its own source is edited and
Streamlit's watcher reloads it), so state kept here lives exactly as long as
the server does.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

#: Read-modify-write of output/generation_jobs.json.
JOBS_LOCK = threading.RLock()
#: Read-modify-write of output/batch_queue.json.
BATCH_LOCK = threading.RLock()
#: One render at a time -- two in parallel do not finish sooner (measured).
RENDER_LOCK = threading.Lock()
#: Generation threads started by this process, for wait_for_generations().
WORKERS: list = []
#: admin._queue_bad's short-lived audit memo.
AUDIT_CACHE: dict = {"at": 0.0, "bad": None}

_ONCE: dict = {}
_ONCE_LOCK = threading.Lock()


def once(key: str, compute: Callable[[], Any]) -> Any:
    """compute() the first time `key` is asked for in this process; the stored
    value every time after."""
    with _ONCE_LOCK:
        if key not in _ONCE:
            _ONCE[key] = compute()
        return _ONCE[key]


_FILE_MEMO: dict = {}
_FILE_MEMO_LOCK = threading.Lock()


def per_file(path, compute: Callable[[Any], Any]) -> Any:
    """compute(path), recomputed only when the file's (mtime, size) changes.

    For the small derived facts the dashboard re-derives on every click from
    files that rarely change: a day's cost total, a sidecar's gate verdict.
    Raises OSError like stat() would, so callers keep their own handling.
    """
    import os
    st = os.stat(path)
    stamp = (st.st_mtime_ns, st.st_size)
    key = (str(path), getattr(compute, "__qualname__", repr(compute)))
    with _FILE_MEMO_LOCK:
        hit = _FILE_MEMO.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = compute(path)
    with _FILE_MEMO_LOCK:
        _FILE_MEMO[key] = (stamp, value)
    return value

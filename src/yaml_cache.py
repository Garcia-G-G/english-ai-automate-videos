"""config.yaml parsed once per edit, not once per caller.

    from yaml_cache import load_yaml
    config = load_yaml(CONFIG_PATH)      # a fresh deep copy every call

WHY. The dashboard re-runs its whole script on every click, and the Generate
page alone asked for config.yaml TEN times per rerun (profiles._load_config
x6, studio.audiences._load_config x4) -- each a full PyYAML parse of a 400-line
file: 0.4-0.8 s of every click, measured 2026-10-13 with cProfile.

The parse is keyed by the file's (mtime, size, inode), so an edit is seen on
the very next call -- nothing goes stale, which is the failure this repo has
paid for before (a dashboard that kept a topic list for four days). Callers
get a deep copy, so one that mutates its dict cannot poison the next.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path

import yaml

_CACHE: dict = {}
_LOCK = threading.Lock()


def load_yaml(path) -> object:
    """safe_load(path), memoised on the file's stat. Raises what open() and
    safe_load() raise, exactly as an uncached read would."""
    p = Path(path)
    st = p.stat()
    stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
    key = str(p.resolve())
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return copy.deepcopy(hit[1])
    with p.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    with _LOCK:
        _CACHE[key] = (stamp, data)
    return copy.deepcopy(data)

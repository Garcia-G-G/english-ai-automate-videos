"""Locks and caches survive a Streamlit rerun.

Streamlit exec()s src/admin.py in a fresh namespace on every click, so a lock
defined there was a new lock per click: two Generate clicks rendered in
parallel and the job ledger was written under two different locks (job
ebe7bb3e died of it on 2026-10-13). They now live in dashboard_state, an
imported module. Executing the dashboard script twice, as two reruns do, must
hand back the SAME objects.
"""
import runpy
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def test_two_reruns_share_locks_and_caches():
    warnings.filterwarnings("ignore")
    first = runpy.run_path(str(ROOT / "src" / "admin.py"), run_name="__rerun1__")
    second = runpy.run_path(str(ROOT / "src" / "admin.py"), run_name="__rerun2__")
    for name in ("_RENDER_LOCK", "_JOBS_LOCK", "_BATCH_LOCK", "_WORKERS",
                 "_AUDIT_CACHE", "_RUNNING_VERSION", "_STARTED_AT", "_OWNER_STARTED"):
        a, b = first[name], second[name]
        if isinstance(a, str):
            assert a == b, name
        else:
            assert a is b, f"{name} was rebuilt by a rerun"

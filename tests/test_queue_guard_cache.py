"""The audit is cached by the queue's own fingerprint.

It reads every queued script, validates each against its schema and lays its
text out with the real font: ten seconds on a hundred scripts. Streamlit
re-runs the whole page on every widget interaction and every job asks for the
next safe script, so an uncached audit put ten seconds in front of each.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import queue_guard  # noqa: E402


def test_a_second_audit_is_served_from_cache():
    queue_guard.audit(fresh=True)
    start = time.perf_counter()
    queue_guard.audit()
    assert time.perf_counter() - start < 1.0, "the cache did not hit"


def test_the_cache_key_is_not_the_per_script_key():
    """The regression this file exists for.

    `audit` binds `key` per script -- the (category, topic_id) pair -- so a
    cache variable of the same name was rebound inside the loop and every
    store landed under the last script's topic. The cache filled and never hit.
    """
    queue_guard.audit(fresh=True)
    queue_guard.audit()
    assert len(queue_guard._AUDIT_CACHE) == 1
    stored = next(iter(queue_guard._AUDIT_CACHE))
    assert stored == queue_guard._fingerprint(), \
        "stored under something other than the fingerprint"


def test_touching_a_script_invalidates_it():
    scripts = queue_guard.queued_scripts()
    if not scripts:
        return
    queue_guard.audit(fresh=True)
    queue_guard.audit()
    before = queue_guard._fingerprint()
    os.utime(scripts[0], None)
    assert queue_guard._fingerprint() != before, \
        "an edited script left the fingerprint unchanged"


def test_a_short_video_warns_and_a_repeat_blocks():
    """Severity is a property of the failure, not of the file.

    Refusing on duration produced nothing at all, and pushed every quiz,
    true_false and fill_blank job onto the GPT fallback and a dead API key.
    A short video is a real video; a repeated topic reaches the channel.
    """
    assert queue_guard.blocks("ALREADY PRODUCED: social/so008 has 11 video(s)")
    assert queue_guard.blocks("DUPLICATE of x.json: both claim a/b")
    assert queue_guard.blocks("NO SUCH TOPIC: work_office/wo001 is not in ...")
    assert queue_guard.blocks("schema: Invalid quiz script")
    assert queue_guard.blocks("UNKNOWN AUDIO TAG [emocionado]")

    assert not queue_guard.blocks("duration: 28 spoken words, band is 67-140")
    assert not queue_guard.blocks("length: explanation at x needs 5 lines")

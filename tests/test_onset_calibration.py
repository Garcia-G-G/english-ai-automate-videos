"""STEP 76 §3: the v3 onset gate, calibrated on the takes stored under _audit/onset_eleven_v3."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import stitch  # noqa: E402

TAKES = ROOT / "_audit" / "onset_eleven_v3" / "lv001"


@pytest.mark.skipif(not TAKES.exists(), reason="the stored v3 takes are not on this machine")
def test_the_threshold_flags_the_cut_ins_and_keeps_the_ones_rising_from_the_floor():
    import onset_calibrate as C
    levels = C.first_levels([TAKES])
    assert len(levels) == 30
    assert C.propose(list(levels.values())) == stitch.ONSET_FIRST_DBFS["eleven_v3"]
    for path, first in levels.items():
        v = stitch.onset_values(path)
        clean = stitch.onset_clean(v, "eleven_v3")
        if -20.0 <= first <= -16.0:
            assert not clean, path                                  # the band the owner hears
        if first < -40:
            assert clean or v["fragment"] or v["doubled_onset"], path   # rising from the floor
    flagged = sum(not stitch.onset_clean(stitch.onset_values(p), "eleven_v3") for p in levels)
    old = sum(not stitch.onset_clean({**stitch.onset_values(p), "first_dbfs": None}, "eleven_v3") for p in levels)
    assert flagged > old                                            # stricter than −6.5 dB start-to-peak


def test_first_dbfs_reads_the_first_ten_ms():
    x = np.concatenate([np.full(441, 0.1), np.zeros(4410)])        # 10 ms at −20 dBFS, then silence
    assert stitch.first_dbfs(x) == pytest.approx(-20.0, abs=0.1)
    assert stitch.first_dbfs(np.zeros(4410)) < -100


def test_without_a_first_level_the_old_limits_still_apply():
    """A measurement with no first-10 ms level (older records, test doubles) uses −6.5 dB."""
    v = {"start_db": -10.0, "fragment": None, "doubled_onset": None}
    assert stitch.onset_clean(v, "eleven_v3") is True
    assert stitch.onset_clean({**v, "start_db": -3.0}, "eleven_v3") is False
    assert stitch.onset_clean({**v, "first_dbfs": -18.0}, "eleven_v3") is False   # the new limit wins when present

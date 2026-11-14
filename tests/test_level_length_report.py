"""STEP 59 §1: every level script, queued or rendered, fits its box.

    python3 -m pytest tests/test_level_length_report.py
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


@pytest.mark.parametrize("vtype", ["level_test", "say_it_level"])
def test_all_hundred_scripts_fit(vtype):
    import length_spec
    from level_length_report import scripts
    paths = scripts(vtype)
    assert len(paths) == 100            # queue + _done: moving a rendered script must not lose it
    over = [(p.stem, v["where"], v["field"]) for p in paths
            for v in length_spec.check_script(json.loads(p.read_text(encoding="utf-8")))]
    assert over == []

"""STEP 78 §3–§6: every series style renders all 27 of its scripts, inside the safe areas, with
no text past its card. Smoke clips use estimated beats and silent audio: no TTS spend."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video.series import render as R  # noqa: E402
from video.series import series_kit as K  # noqa: E402

#: The styles built so far (§3 mensajes, §4 escena, §5 poster, §6 comic).
STYLES = ["mensajes", "escena", "poster"]
DRAFTS = sorted((ROOT / "content" / "hecho_con_claude" / "drafts").glob("hc_*.json"))


def _scripts(style):
    return [p for p in DRAFTS if json.loads(p.read_text(encoding="utf-8"))["style"] == style]


CASES = [(style, p) for style in STYLES for p in _scripts(style)]


@pytest.mark.parametrize("style, path", CASES, ids=lambda v: v if isinstance(v, str) else v.stem)
def test_every_readable_box_is_inside_the_safe_areas_and_nothing_overflows(style, path):
    script = json.loads(path.read_text(encoding="utf-8"))
    module = importlib.import_module(f"video.series.{style}")
    boxes = module.text_boxes(script)                       # fit() raises Overflow on any text too long
    assert boxes
    for label, box in boxes:
        assert K.in_safe_area(box), (script["id"], label, box)
    assert K.in_safe_area(K.outro_answer_box(script["challenge"]["answer"]))


@pytest.mark.parametrize("style, path", CASES, ids=lambda v: v if isinstance(v, str) else v.stem)
def test_frame_zero_shows_the_hook(style, path):
    script = json.loads(path.read_text(encoding="utf-8"))
    module = importlib.import_module(f"video.series.{style}")
    tl = R.estimated_timeline(script)
    hook = dict(module.text_boxes(script))["hook"]
    a = np.asarray(module.frame(0.0, script, tl).convert("RGB")).astype(int)
    blank = dict(script, hook_text=" ")
    try:
        b = np.asarray(module.frame(0.0, blank, tl).convert("RGB")).astype(int)
    except K.Overflow:
        pytest.skip("a blank hook is not a layout")
    x0, y0, x1, y1 = (int(v) for v in hook)
    assert np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).sum() > 50_000, script["id"]


@pytest.mark.parametrize("style", STYLES)
def test_a_two_second_smoke_clip_of_every_script(style, tmp_path, monkeypatch):
    import tts_bilingual
    monkeypatch.setattr(tts_bilingual, "generate_bilingual_narration",
                        lambda *a, **k: pytest.fail("a smoke clip voiced something"))
    for path in _scripts(style):
        script = json.loads(path.read_text(encoding="utf-8"))
        out = tmp_path / f"{script['id']}.mp4"
        info = R.render_series(script, out, tmp_path / "w", silent=True, seconds=2.0, workers=1)
        assert info["tts_usd"] == 0 and out.stat().st_size > 10_000, script["id"]
    assert len(_scripts(style)) == 27

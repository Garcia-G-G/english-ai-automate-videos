"""STEP 77 §2: the notebook page is memoised by state and frames render in a process pool."""
import copy
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from video import compositor as C  # noqa: E402


def _pure(t):
    img = np.zeros((32, 48, 3), np.uint8)
    img[:, :, 0] = int(t * 30) % 256
    img[int(t * 30) % 32, :, 1] = 200
    return img


def test_the_pool_returns_every_frame_in_order():
    one = [f.copy() for f in C.frames(_pure, 90, 30, workers=1)]
    many = list(C.frames(_pure, 90, 30, workers=3))
    assert len(many) == 90 and all(np.array_equal(a, b) for a, b in zip(one, many))


def _boom(t):
    if t > 1.0:
        raise RuntimeError("frame failed")
    return _pure(t)


def test_a_failing_frame_in_a_worker_fails_the_render():
    with pytest.raises(RuntimeError, match="frame failed"):
        list(C.frames(_boom, 60, 30, workers=2))


def test_workers_follow_the_environment(monkeypatch):
    monkeypatch.setenv("VIDEO_RENDER_WORKERS", "3")
    assert C.render_workers() == 3
    monkeypatch.delenv("VIDEO_RENDER_WORKERS")
    assert 1 <= C.render_workers() <= 6


def _hdys():
    spec = importlib.util.spec_from_file_location("t_hdys", ROOT / "tests" / "test_how_do_you_say.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._timeline(m._script())


def test_the_page_memo_reuses_identical_states_and_draws_the_same_frame(monkeypatch):
    from PIL import Image, ImageDraw
    import video.how_do_you_say as H
    monkeypatch.setattr(H, "create_base_frame", lambda t: (lambda f: (f, ImageDraw.Draw(f, "RGBA")))(
        Image.new("RGBA", (1080, 1920), (40, 60, 90, 255))))
    data, dur = _hdys()
    H._PAGES.clear()
    H.PAGE_STATS.update(drawn=0, reused=0)
    t = data["segment_times"]["think_3"]["start"] + 0.01
    a = H.create_frame_how_do_you_say(t, copy.deepcopy(data), dur)
    b = H.create_frame_how_do_you_say(t + 1 / 30, copy.deepcopy(data), dur)   # same dots, same page
    assert H.PAGE_STATS == {"drawn": 1, "reused": 1}
    H._PAGES.clear()
    again = H.create_frame_how_do_you_say(t, copy.deepcopy(data), dur)
    assert np.array_equal(a, again)                                           # memo or not, one frame


def test_the_pencil_lands_on_the_rotated_page_point():
    import video.how_do_you_say as H
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", (H.LAYER_W, H.LAYER_H), (0, 0, 0, 0))
    lx, ly = H._p(600, 900)
    ImageDraw.Draw(layer).ellipse([lx - 3, ly - 3, lx + 3, ly + 3], fill=(255, 0, 0, 255))
    rot = np.asarray(H._rotate(layer))[:, :, 3]
    ys, xs = np.nonzero(rot > 100)
    fx, fy = H.page_to_frame(600, 900)
    assert xs.mean() + H.PAGE_X - H.PAD == pytest.approx(fx, abs=0.5)
    assert ys.mean() + H.PAGE_Y - H.PAD == pytest.approx(fy, abs=0.5)


def test_a_busy_machine_gets_fewer_render_workers(monkeypatch):
    from video import compositor as C
    monkeypatch.delenv("VIDEO_RENDER_WORKERS", raising=False)
    monkeypatch.setattr(C.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(C.os, "getloadavg", lambda: (0.5, 0, 0))
    assert C.render_workers() == 6
    monkeypatch.setattr(C.os, "getloadavg", lambda: (6.0, 0, 0))
    assert C.render_workers() == 1
    monkeypatch.setattr(C.os, "getloadavg", lambda: (70.0, 0, 0))
    assert C.render_workers() == 1

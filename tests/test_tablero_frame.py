"""STEP 82 §2: Tablero's frames over the measured beats. No network, no audio."""
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from video.tablero import frame as F, kit  # noqa: E402
from video.how_do_you_say import Timeline  # noqa: E402


def _data():
    d = json.loads((ROOT / "content" / "queue" / "_done" / "bv002_casa.json").read_text(encoding="utf-8"))
    st = {"intro": {"start": 0.0, "end": 4.0}}
    t = 4.6
    for i in range(1, 11):
        st[f"es_{i}"] = {"start": t, "end": t + 0.8}; t += 0.8
        st[f"think_{i}"] = {"start": t, "end": t + 1.8}; t += 1.8
        st[f"en_{i}"] = {"start": t, "end": t + 1.6, "reveal_end": t + 0.7}; t += 2.0
    st["recap"] = {"start": t, "end": t + 9.0}; t += 9.6
    st["outro"] = {"start": t, "end": t + 4.0}
    d["segment_times"] = st
    d["design_variant"] = "tablero"
    return d, t + 4.0


def test_tablero_is_the_default_variant_and_a_script_can_ask_for_the_notebook():
    assert F.variant({}) == "tablero" and F.variant({"design_variant": "cuaderno"}) == "cuaderno"


def test_frame_zero_is_complete_and_the_first_item_is_blank():
    d, dur = _data()
    fr = F.create_frame_tablero(0.0, d, dur)
    assert fr.shape == (1920, 1080, 3) and fr.dtype == np.uint8
    tl = Timeline(d, dur)
    # until the first Spanish word nothing is lit: only the drifting dots and Bubi's breath move
    a, b = F.create_frame_tablero(0.5, d, dur), F.create_frame_tablero(1.0, d, dur)
    diff = np.argwhere((a != b).any(axis=2))
    assert tl.es[0][0] > 1.0 and len(diff) > 0
    assert diff[:, 0].min() >= 0


def test_the_tile_is_active_during_the_spanish_and_done_after_the_flip():
    d, dur = _data()
    tl = Timeline(d, dur)
    beats = F.Beats(tl)
    item = d["items"][0]
    assert F._tile_state(0, tl.es[0][0] + 0.5, tl, beats, item, None)[3] is True
    done = F._tile_state(0, beats.flip_end[0] + 0.01, tl, beats, item, None)
    assert done[0].tobytes() == kit.tile(0, item["emoji"], item["spanish"], item["english"], None, "done").tobytes()
    mid = F._tile_state(0, beats.fill_end[0] + F.FLIP_DUR / 2, tl, beats, item, None)
    assert mid[4] < 0.1                                    # edge-on at the middle of the flip


def test_letters_fill_left_to_right_over_035s():
    d, dur = _data()
    tl = Timeline(d, dur)
    beats = F.Beats(tl)
    item = d["items"][0]
    counts = []
    for k in range(4):
        t = tl.en[0][0] + F.FILL_DUR * k / 4 + 0.001
        img = F._tile_state(0, t, tl, beats, item, None)[0]
        counts.append(img.tobytes())
    assert len(set(counts)) >= 3


def test_the_counter_counts_flips_and_bubi_follows_the_beats():
    d, dur = _data()
    tl = Timeline(d, dur)
    beats = F.Beats(tl)
    assert beats.done_count(0) == 0 and beats.done_count(dur) == 10
    assert F.bubi_state(0, tl, beats)[0] == "simbolo"
    assert F.bubi_state(tl.es[0][0] + 0.2, tl, beats) == ("wow", F.SAY_ACTIVE)
    assert F.bubi_state(beats.flip_end[2] + 0.1, tl, beats)[0] == "bien_hecho"      # every third
    assert F.bubi_state(beats.flip_end[0] + 0.1, tl, beats)[0] == "wow"
    assert F.bubi_state(tl.recap[0] + 0.1, tl, beats)[0] == "lo_lograste"


def test_the_outro_card_dims_the_video_and_a_frame_is_a_pure_function_of_t():
    d, dur = _data()
    tl = Timeline(d, dur)
    t = tl.outro[0] + 1.0
    a = F.create_frame_tablero(t, copy.deepcopy(d), dur)
    assert (a == F.create_frame_tablero(t, copy.deepcopy(d), dur)).all()
    before = F.create_frame_tablero(tl.recap[0] + 1.0, copy.deepcopy(d), dur)
    assert a[:300].mean() < before[:300].mean()            # the dim


def test_the_title_emoji_comes_from_the_title_not_the_first_row():
    assert F.title_emoji({"video_title": "¿Cómo se dice CASA en inglés? 🏠", "items": [{"emoji": "🍎"}]}) == "🏠"
    assert F.title_emoji({"video_title": "sin emoji", "items": [{"emoji": "🍎"}]}) == "🍎"


def test_sfx_pop_per_tile_and_swish_per_flip_and_the_dispatch_reaches_it():
    d, dur = _data()
    import video.how_do_you_say as H
    events, spoken = H.sfx_events(d, dur)
    assert sorted(e[0] for e in events).count("pop") == 10 and [e[0] for e in events].count("swish") == 10
    d["design_variant"] = "cuaderno"
    assert ("scratch" in [e[0] for e in H.sfx_events(d, dur)[0]])


def test_rendering_a_busy_frame_stays_cheap():
    d, dur = _data()
    tl = Timeline(d, dur)
    ts = [tl.es[i][0] + 0.3 for i in range(0, 10, 3)] + [tl.outro[0] + 1]
    F.create_frame_tablero(ts[0], d, dur)                  # warm the caches
    t0 = time.perf_counter()
    for t in ts:
        F.create_frame_tablero(t, d, dur)
    assert (time.perf_counter() - t0) / len(ts) < 0.5


def test_every_moment_of_the_flip_renders():
    d, dur = _data()
    tl = Timeline(d, dur)
    beats = F.Beats(tl)
    for k in range(0, 11):
        F.create_frame_tablero(beats.fill_end[0] + F.FLIP_DUR * k / 10, d, dur)

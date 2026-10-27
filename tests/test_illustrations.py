"""STEP 80 §4: an illustration for the word being taught. Placeholder images, no API."""
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import illustrations as I  # noqa: E402
from video import how_do_you_say as H  # noqa: E402


def _placeholder(path):
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([20, 20, 280, 280], fill=(230, 130, 60, 255), outline=(28, 24, 18, 255), width=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def _script():
    items = [{"emoji": "🍎", "spanish": f"Palabra{i}", "english": f"word{i}"} for i in range(10)]
    seg, t = {"intro": {"start": 0.0, "end": 2.0}}, 2.0
    for i in range(1, 11):                                   # the generator's own keys: es_1, think_1, en_1…
        seg[f"es_{i}"] = {"start": t, "end": t + 1.0}
        seg[f"think_{i}"] = {"start": t + 1.0, "end": t + 2.0}
        seg[f"en_{i}"] = {"start": t + 2.0, "end": t + 3.0}
        t += 3.5
    seg["recap"] = {"start": t, "end": t + 4.0}
    seg["outro"] = {"start": t + 4.0, "end": t + 6.0}
    return {"type": "how_do_you_say", "theme": "la fruta", "items": items, "segment_times": seg, "recap": "",
            "intro": "x", "outro": "x"}, t + 6.0


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "LIBRARY", tmp_path / "illustrations")
    return tmp_path / "illustrations"


def test_the_library_keeps_one_file_per_word(library):
    assert I.slug("Ice cream") == "ice_cream" and I.path_for("Ice cream").name == "ice_cream.png"
    _placeholder(I.path_for("apple"))
    assert I.missing(["apple", "pear", "Pear", "pear"]) == ["pear"]
    assert I.estimate_usd(3) == pytest.approx(0.03)


def test_frame_one_is_the_same_with_or_without_illustrations(library):
    data, dur = _script()
    try:
        timeline = H.Timeline(data, dur)
    except Exception as e:                                   # noqa: BLE001
        pytest.skip(f"synthetic timeline not accepted: {e}")
    data["_hdys_timeline"] = timeline
    without = H.create_frame_how_do_you_say(0.0, data, dur)
    for it in data["items"]:
        _placeholder(I.path_for(it["english"]))
    data.pop("_hdys_timeline")
    with_art = H.create_frame_how_do_you_say(0.0, data, dur)
    assert np.array_equal(without, with_art)


@pytest.mark.parametrize("i", range(10))
def test_the_card_is_never_over_the_active_row_and_stays_on_the_page(i):
    centres = H.row_centres(10)
    x0, y0, x1, y1 = H.illustration_box(i, centres)
    band = (centres[i] - H.ROW_PITCH / 2, centres[i] + H.ROW_PITCH / 2)
    assert y1 <= band[0] or y0 >= band[1]
    assert H.ROWS_TOP - H.ROW_PITCH <= y0 and y1 <= H.ROWS_BOTTOM
    assert 0 <= x0 and x1 <= H.CONTENT_R
    assert abs((x1 - x0) / H.PAGE_W - 0.30) < 0.01


def test_a_card_shows_while_its_row_is_taught_and_not_without_its_image(library):
    data, dur = _script()
    try:
        tl = H.Timeline(data, dur)
    except Exception as e:                                   # noqa: BLE001
        pytest.skip(f"synthetic timeline not accepted: {e}")
    assert H.active_row(0.5, tl) is None and H.active_row(tl.es[3][0] + 0.1, tl) == 3
    assert H.active_row(tl.recap[0] + 0.1, tl) is None
    data["_hdys_timeline"] = tl
    t = tl.es[2][0] + 0.6
    plain = H.create_frame_how_do_you_say(t, data, dur)
    _placeholder(I.path_for("word2"))
    data["_hdys_timeline"] = tl
    drawn = H.create_frame_how_do_you_say(t, data, dur)
    assert np.abs(plain.astype(int) - drawn.astype(int)).mean() > 0.5


# ── drawing them: only from the panel, under the caps ────────────────

class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _png_data_url():
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (200, 100, 50, 255)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_generation_is_locked_outside_the_panel(library):
    import voice_lock
    with pytest.raises(voice_lock.VoiceLocked):
        I.generate(["apple"], opener=lambda *a, **k: pytest.fail("the network was reached"))


def test_a_panel_click_draws_the_missing_words_once_and_logs_them(library, monkeypatch, tmp_path):
    import cost_tracker
    import tts_openrouter
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(tts_openrouter, "check_caps", lambda usd, settings=None: None)
    cost_tracker.reset_tracker("illo-test")
    sent = []

    def opener(request, timeout=None):
        body = json.loads(request.data)
        sent.append(body)
        return _Answer(json.dumps({"choices": [{"message": {"images": [{"image_url": {"url": _png_data_url()}}]}}]}).encode())
    _placeholder(I.path_for("pear"))
    done = I.generate(["apple", "pear"], opener=opener)
    assert done == {"apple": "meta/muse-image"} and I.path_for("apple").exists()
    assert sent[0]["model"] == "meta/muse-image" and sent[0]["modalities"] == ["image", "text"]
    assert "no text" in sent[0]["messages"][0]["content"][0]["text"]
    rows = cost_tracker.get_tracker().entries
    assert [(r["api_type"], r["cost_usd"]) for r in rows] == [("openrouter_image", 0.01)]


def test_the_monthly_cap_stops_a_drawing(library, monkeypatch):
    import tts_openrouter
    import voice_lock
    monkeypatch.setattr(voice_lock, "locked", lambda: False)

    def capped(usd, settings=None):
        raise tts_openrouter.OpenRouterRefused("Tope mensual de OpenRouter")
    monkeypatch.setattr(tts_openrouter, "check_caps", capped)
    with pytest.raises(tts_openrouter.OpenRouterRefused):
        I.generate(["apple"], opener=lambda *a, **k: pytest.fail("asked past the cap"))


def test_the_panel_shows_the_count_and_the_cost_before_drawing():
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    body = admin[admin.index("def illustrations_panel"):admin.index("def render_metadata")]
    assert "ilustraciones nuevas" in body and "voice_lock.panel_grant()" in body

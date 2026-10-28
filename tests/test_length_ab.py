"""The short «¿Cómo se dice…?» A/B (src/length_ab.py): 5 words, no recap, every other NEW topic."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import length_ab as L  # noqa: E402

_spec = importlib.util.spec_from_file_location("t_hdys_for_ab", ROOT / "tests" / "test_how_do_you_say.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)


def _hdys(theme="la cara", n=10):
    items = [{"emoji": e, "spanish": f"Palabra{i}", "english": f"word{i}"}
             for i, e in enumerate("🍎🍌🍇🍉🍒🍓🥝🍍🥥🥑"[:n])]
    return {"type": "how_do_you_say", "title": "¿Cómo se dice…?", "theme": theme, "level": "A1",
            "intro": "[excited] Reto rápido: diez palabras. ¿Cuántas aciertas?", "items": items,
            "recap": "Otra vez, todas seguidas: " + ", ".join(i["english"] for i in items) + ".",
            "outro": "[curious] ¿Cuál no sabías? Cuéntamelo abajo.",
            "video_description": "Diez partes de la cara que casi nadie sabe decir.",
            "english_phrases": [i["english"] for i in items],
            "translations": {i["english"]: i["spanish"] for i in items},
            "full_script": "intro " * 5, "hashtags": ["#a"]}


def test_new_topics_alternate_and_a_topic_keeps_its_group():
    got = [L.assign(f"a{i}", _hdys(theme=t))["variant"] for i, t in enumerate(["la cara", "el mar", "la ropa"])]
    assert got == ["short", "long", "short"]
    again = L.assign("a3", _hdys(theme="el mar"))                 # a re-render after a reject
    assert again["variant"] == "long" and again["why"] == "el tema ya tenía grupo"
    assert L.variants() == {"a0": "short", "a1": "long", "a2": "short", "a3": "long"}
    assert L.assign("q", {"type": "quiz", "theme": "x"}) is None    # only «¿Cómo se dice…?»


def test_the_short_script_has_five_words_no_recap_and_still_passes_the_schema():
    from script_schema import ScriptValidationError, validate_script
    short = L.apply(_hdys(), L.SHORT)
    assert len(short["items"]) == 5 and short["recap"] == "" and short["variant"] == "short"
    assert "cinco palabras" in short["intro"] and short["video_description"].startswith("Cinco")
    assert short["english_phrases"] == [f"word{i}" for i in range(5)] and len(short["translations"]) == 5
    validate_script(short, "how_do_you_say")
    assert L.apply(_hdys(), L.LONG) == _hdys()                      # long is untouched
    with pytest.raises(ScriptValidationError):                      # 5 words without the variant: refused
        validate_script({**short, "variant": None, "recap": "x"}, "how_do_you_say")


def test_the_short_audio_has_no_recap_voice_and_a_zero_length_recap(tmp_path, monkeypatch):
    import tts_elevenlabs as TE
    calls = []

    def fake(text, output_path, **kw):
        calls.append(text)
        H._tone(output_path, [(0.05, 0.55), (0.95, 1.45)] if text.count(".") >= 2 and len(text) < 40
                else [(0.05, 0.75)], 1.6 if text.count(".") >= 2 and len(text) < 40 else 0.9)
        return 0.0
    monkeypatch.setattr(TE, "generate_segment_audio", fake)
    monkeypatch.setattr(TE, "DEFAULT_VOICE_ID", "test-voice")
    out = TE.generate_how_do_you_say_audio_segmented(L.apply(_hdys(), L.SHORT), str(tmp_path / "a.mp3"))
    assert len(calls) == 2 * 5 + 2, "intro + es/en per word + outro, no recap"
    rec = out["segment_times"]["recap"]
    assert rec["start"] == rec["end"] == pytest.approx(out["segment_times"]["en_5"]["end"] + TE.HDYS_ITEM_GAP_S, abs=0.01)


def test_the_short_variant_is_judged_on_its_own_window():
    import duration_spec as ds
    ds.reload()
    assert ds.check("how_do_you_say", 33.0, measured_video_seconds=37.0, variant="short")["status"] == ds.PASS
    assert ds.check("how_do_you_say", 33.0, measured_video_seconds=37.0)["status"] == ds.OUT_OF_BAND
    assert ds.check("how_do_you_say", 70.0, measured_video_seconds=74.0, variant="unknown")["status"] == ds.PASS


def test_the_groups_are_compared_only_when_each_has_eight_mature_videos():
    vids = [{"length_variant": g, "views": v, "avg_view_pct": p, "days": d}
            for g, v, p, d in [("short", 900, 80.0, 5)] * 8 + [("long", 700, 60.0, 5)] * 7
            + [("long", 9999, 99.0, 1)]]                            # too young to count
    cmp = L.compare(vids)
    assert not cmp["ready"] and cmp["groups"]["long"]["n"] == 7
    assert cmp["groups"]["short"] == {"n": 8, "views": 900, "viewed_pct": 80.0}
    assert L.compare(vids + [{"length_variant": "long", "views": 700, "avg_view_pct": 60.0, "days": 9}])["ready"]


def test_frame_one_already_shows_every_row():
    """The top-16 Shorts showed the whole list on frame 1; the opening cascade must be over by t=0."""
    from video import how_do_you_say as V
    assert all(V.cascade(i, 0.0) == 1.0 for i in range(10))

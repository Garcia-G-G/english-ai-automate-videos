#!/usr/bin/env python3
"""STEP 65: no empty titles, no second copy of a topic, no upload without a QA verdict.

    python3 -m pytest tests/test_upload_content_guard.py

8yA7dbOZeUY went up as «¿Cómo se dice  en inglés?» with the fallback CTA: its
render timed out, the mp4 reached approved/ with no sidecar, and the Upload
page built metadata from `{}`. Nothing here uploads.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import upload_guard as G  # noqa: E402
from metadata_generator import generate_metadata  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "scripts"
GOOD = {"title": "¿Cómo se dicen los sitios de la CIUDAD en inglés? 🏙️",
        "description": "Diez lugares para orientarte en cualquier ciudad. 🗺️\n\n#LearnEnglish",
        "gate": "PASS"}


def _ledger(tmp_path, *rows):
    path = tmp_path / "ledger.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _decide(tmp_path, ledger=None, **content):
    return G.decide("cómo_se_dice_new", "youtube", ledger_path=ledger or _ledger(tmp_path),
                    attempts_path=tmp_path / "attempts.jsonl", **{**GOOD, **content})


def test_the_bv010_metadata_is_refused(tmp_path):
    meta = generate_metadata({}, "how_do_you_say")        # what the Upload page built from no script
    assert meta["title"] == "¿Cómo se dice  en inglés?"
    v = _decide(tmp_path, title=meta["title"], description=meta["description"])
    assert v.action == G.REFUSE and not v.should_upload and "hueco" in v.reason


def test_every_empty_slot_shape_is_refused(tmp_path):
    for title in ("¿Cómo se dice  en inglés?", "Frases de {theme}", "Test de None", "  "):
        assert _decide(tmp_path, title=title).action == G.REFUSE, title


def test_the_fallback_cta_alone_is_refused_even_with_site_line_and_hashtags(tmp_path):
    desc = f"{G.FALLBACK_CTA}\n\nMás lecciones en https://learningroutes.com\n\n#LearnEnglish #AprendeIngles"
    v = _decide(tmp_path, description=desc)
    assert v.action == G.REFUSE and "CTA" in v.reason
    assert _decide(tmp_path, description=f"Diez lugares.\n\n{G.FALLBACK_CTA}").should_upload


def test_no_gate_verdict_is_refused(tmp_path):
    for gate in (None, ""):
        v = _decide(tmp_path, gate=gate)
        assert v.action == G.REFUSE and v.reason == G.NO_GATE
    assert _decide(tmp_path).should_upload


def test_a_caller_that_passes_no_content_is_not_content_checked(tmp_path):
    """The manim lessons have their own review page and pass nothing."""
    assert G.decide("lesson", "youtube", ledger_path=_ledger(tmp_path),
                    attempts_path=tmp_path / "a.jsonl").should_upload


def test_a_second_video_of_a_published_topic_is_refused_then_overridden(tmp_path, caplog):
    audio = tmp_path / "audio" / "how_do_you_say"
    audio.mkdir(parents=True)
    (audio / "cómo_se_dice_old.json").write_text(json.dumps({"_meta": {"topic_id": "bv010"}}))
    ledger = _ledger(tmp_path, {"artifact": "cómo_se_dice_old", "video_type": "how_do_you_say",
                                "platform": "youtube", "upload_id": "jKbncpSxnuY",
                                "url": "https://youtube.com/shorts/jKbncpSxnuY"})
    G.AUDIO_DIR, real = tmp_path / "audio", G.AUDIO_DIR
    try:
        v = _decide(tmp_path, ledger, topic_id="bv010", topic_name="la ciudad")
        assert v.action == G.REFUSE
        assert v.reason == "Ya hay un vídeo de bv010 (la ciudad) subido: https://youtube.com/shorts/jKbncpSxnuY"
        assert _decide(tmp_path, ledger, topic_id="bv011").should_upload
        with caplog.at_level("WARNING", logger="upload_guard"):
            assert _decide(tmp_path, ledger, topic_id="bv010", allow_duplicate=True).should_upload
        assert "DUPLICATE OVERRIDE" in caplog.text and "bv010" in caplog.text
    finally:
        G.AUDIO_DIR = real


def test_a_topic_on_another_platform_is_not_a_duplicate(tmp_path):
    ledger = _ledger(tmp_path, {"artifact": "x", "platform": "tiktok", "topic_id": "bv010", "url": "u"})
    assert _decide(tmp_path, ledger, topic_id="bv010").should_upload


# ── the Upload page's side ───────────────────────────────────────────

def test_without_a_sidecar_the_upload_page_reads_the_audio_json(tmp_path, monkeypatch):
    import admin
    script = json.loads((FIXTURES / "how_do_you_say_bv001.json").read_text(encoding="utf-8"))
    (tmp_path / "how_do_you_say").mkdir()
    (tmp_path / "how_do_you_say" / "cómo_se_dice_x.json").write_text(json.dumps(script), encoding="utf-8")
    monkeypatch.setattr(admin, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(admin, "SCRIPTS_DIR", tmp_path / "none")
    video = {"type": "how_do_you_say", "name": "cómo_se_dice_x", "meta": {},
             "path": tmp_path / "approved" / "how_do_you_say" / "cómo_se_dice_x.mp4"}
    got = admin.script_for_upload(video)
    assert got["video_title"] == script["video_title"]
    content = admin.upload_content(video, got, got["video_title"], got["video_description"])
    assert content["gate"] is None and content["topic_id"] == script["_meta"]["topic_id"]
    assert G.content_refusal(**content).reason == G.NO_GATE      # no sidecar, no verdict


def test_a_level_test_script_uploads_with_its_own_title():
    from upload_metadata import NO_OPERATOR_EDITS, resolve_upload_metadata
    script = json.loads((FIXTURES / "level_test_lv001.json").read_text(encoding="utf-8"))
    meta = resolve_upload_metadata("qué_nivel_tienes_x", script, "youtube", "level_test", "",
                                   NO_OPERATOR_EDITS)
    assert meta["title"].removesuffix(" #Shorts") == script["video_title"]
    assert meta["description"].startswith(script["video_description"])
    assert G.content_refusal(title=meta["title"], description=meta["description"], gate="PASS") is None

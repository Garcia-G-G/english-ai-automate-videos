"""STEP 56: the long Manim lessons go to YouTube through the Shorts' uploader and guard.

    python3 -m pytest tests/test_manim_youtube.py
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import manim_studio as M  # noqa: E402
import uploader  # noqa: E402

if M.STUDIO_IMPORT_ERROR:
    pytest.skip(f"Manim studio tree missing: {M.STUDIO_IMPORT_ERROR}", allow_module_level=True)

CHAPTERS = "0:00 Introducción\n0:24 Parte 1 · El problema\n1:18 Parte 2 · Make crea\n6:50 Parte 9 · Resumen\n"


def _lesson(**extra):
    beats = [{"id": "b01", "type": "title", "narration": "Hola. Hoy dos verbos. En inglés se parten en [[make]] y [[do]]. Vamos."},
             {"id": "b02", "type": "heading", "text": "Parte 1 · El problema", "narration": "x"},
             {"id": "b03", "type": "heading", "text": "Parte 2 · Make crea", "narration": "x"},
             {"id": "b04", "type": "heading", "text": "Parte 9 · Resumen", "narration": "x"}]
    return {"id": "make-vs-do", "title": "Make y do: dos verbos, una confusión", "kicker": "Inglés · Verbos · A2–B1",
            "beats": beats, **extra}


def _render(tmp_path, chapters=CHAPTERS):
    (tmp_path / "renders" / "l").mkdir(parents=True)
    (tmp_path / "renders" / "l" / "r.chapters.txt").write_text(chapters, encoding="utf-8")
    return {"file": "l/r.mp4", "chapters": "l/r.chapters.txt", "poster": "l/r.jpg"}


def test_the_metadata_comes_from_the_lesson(tmp_path):
    meta = M.youtube_metadata(_lesson(), _render(tmp_path), tmp_path)
    assert meta["title"] == "Make y do: dos verbos, una confusión | Inglés A2–B1"
    assert len(meta["title"]) <= 100 and "#Shorts" not in meta["title"] + meta["description"]
    d = meta["description"]
    assert d.startswith("Hoy dos verbos. En inglés se parten en make y do.")          # 2 sentences, no «Hola»
    assert "• El problema\n• Make crea" in d and "• Resumen" not in d
    chapters = d[d.index("0:00"):].split("\n\n")[0]
    assert chapters == CHAPTERS.strip()                                                   # as written, 0:00 first
    assert M.YT_CTA in d and len(meta["tags"]) <= 15


def test_hashtags_appear_once_and_at_most_five(tmp_path):
    meta = M.youtube_metadata(_lesson(hashtags=["#MakeVsDo", "#AprenderInglés", "#Verbos", "#Hacer"]), _render(tmp_path), tmp_path)
    d = meta["description"]
    tags_in_text = [w for w in d.split() if w.startswith("#")]
    assert len(tags_in_text) <= 5 and len(set(tags_in_text)) == len(tags_in_text)       # the old Shorts bug: the block twice
    assert d.count("#AprenderInglés") == 1


def test_a_chapter_list_not_starting_at_zero_is_left_out(tmp_path):
    meta = M.youtube_metadata(_lesson(), _render(tmp_path, "0:05 Intro\n1:00 Parte 1\n"), tmp_path)
    assert "0:05" not in meta["description"]


def test_a_long_title_is_cut_to_100(tmp_path):
    meta = M.youtube_metadata(_lesson(title="x" * 120), _render(tmp_path), tmp_path)
    assert len(meta["title"]) <= 100


# ── the uploader ─────────────────────────────────────────────────────

class _Resp:
    status_code, ok, text = 200, True, ""
    headers = {"Location": "https://upload.example/session"}

    def raise_for_status(self):
        return None

    @staticmethod
    def json():
        return {"id": "vid123"}


def _capture(monkeypatch):
    sent = {"post": [], "put": []}
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: sent["post"].append((url, kw)) or _Resp())
    monkeypatch.setattr(uploader.requests, "put", lambda url, **kw: sent["put"].append((url, kw)) or _Resp())
    return sent


def _yt():
    yt = uploader.YouTubeUploader()
    yt._token_data = {"access_token": "tok", "scope": " ".join(uploader.YOUTUBE_SCOPES)}
    return yt


def test_the_shorts_request_is_unchanged(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    video = tmp_path / "v.mp4"; video.write_bytes(b"x" * 16)
    result = _yt().upload_video(str(video), "T", "D", ["Alpha"])
    body = sent["post"][0][1]["json"]
    assert body == {"snippet": {"title": "T #Shorts", "description": "D", "tags": ["Alpha"], "categoryId": "27"},
                    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    assert sent["put"][0][1]["timeout"] == uploader.UPLOAD_TIMEOUT_SECONDS
    assert result.url == "https://youtube.com/shorts/vid123"


def test_a_lesson_keeps_its_title_and_gets_a_watch_url(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    video = tmp_path / "v.mp4"; video.write_bytes(b"x" * 16)
    progress = []
    result = _yt().upload_video(str(video), "Make y do | Inglés A2–B1", "D", [], shorts=False, privacy="unlisted",
                                on_progress=lambda s, t: progress.append((s, t)))
    body = sent["post"][0][1]["json"]
    assert body["snippet"]["title"] == "Make y do | Inglés A2–B1" and body["status"]["privacyStatus"] == "unlisted"
    assert result.url == "https://www.youtube.com/watch?v=vid123" and progress == [(16, 16)]


def test_the_timeout_grows_with_the_file():
    assert uploader.upload_timeout(5_000_000) == uploader.UPLOAD_TIMEOUT_SECONDS
    assert uploader.upload_timeout(25_000_000) == 500


def test_captions_wait_for_the_force_ssl_consent(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    yt = _yt()
    yt._token_data["scope"] = " ".join(s for s in uploader.YOUTUBE_SCOPES if s != uploader.YOUTUBE_FORCE_SSL)
    ok, note = yt.upload_captions("vid123", str(tmp_path / "x.srt"))
    assert not ok and "force-ssl" in note and sent["post"] == []


def test_a_failed_thumbnail_is_a_note_not_an_error(monkeypatch, tmp_path):
    class No(_Resp):
        status_code, ok, text = 403, False, "forbidden"
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: No())
    jpg = tmp_path / "p.jpg"; jpg.write_bytes(b"\xff\xd8")
    ok, note = _yt().set_thumbnail("vid123", str(jpg))
    assert not ok and "403" in note


# ── one click, one publication ───────────────────────────────────────

def test_a_render_is_uploaded_once_then_refused(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    row = _render(tmp_path)
    (tmp_path / "renders" / "l" / "r.mp4").write_bytes(b"x" * 16)
    (tmp_path / "renders" / "l" / "r.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHola\n", encoding="utf-8")
    manager = uploader.UploadManager()
    yt = manager.uploaders["youtube"]
    yt._token_data = {"access_token": "tok", "scope": " ".join(uploader.YOUTUBE_SCOPES)}
    monkeypatch.setattr(yt, "authenticate", lambda: True)
    meta = {"title": "T", "description": "D", "tags": ["a"], "hashtags": []}
    out = M.upload_to_youtube(row, meta, privacy="unlisted", studio_dir=tmp_path, manager=manager)
    assert out["ok"] and out["url"].endswith("vid123")
    assert out["notes"] == ["no poster beside the render", "captions uploaded (es)"]
    assert json.loads((tmp_path / "renders" / "l" / "r.youtube.json").read_text()) == meta
    assert M.youtube_publication(row)["upload_id"] == "vid123"
    before = len(sent["post"])
    again = M.upload_to_youtube(row, meta, studio_dir=tmp_path, manager=manager)
    assert not again["ok"] and again["refused"] and len(sent["post"]) == before

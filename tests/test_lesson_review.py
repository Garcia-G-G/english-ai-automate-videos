"""STEP 61 Part A: lessons are reviewed, then uploaded, on one «Revisar y subir» tab.

    python3 -m pytest tests/test_lesson_review.py
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import manim_studio as M  # noqa: E402

if M.STUDIO_IMPORT_ERROR:
    pytest.skip(f"Manim studio tree missing: {M.STUDIO_IMPORT_ERROR}", allow_module_level=True)


def _studio(tmp_path, rows, missing=()):
    """A studio dir with a render ledger; every file exists on disk unless named in `missing`."""
    renders = tmp_path / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    with (renders / "ledger.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
            if row["file"] not in missing:
                (renders / row["file"]).parent.mkdir(parents=True, exist_ok=True)
                (renders / row["file"]).write_bytes(b"x")
    return tmp_path


def _row(lesson, at, quality="1080p30"):
    return {"at": at, "lesson": lesson, "file": f"{lesson}/{at}.mp4", "quality": quality, "voice": "v", "duration_s": 461}


ROWS = [_row("make-vs-do", "2026-10-13T11:34:37"), _row("make-vs-do", "2026-10-15T09:11:37"),
        _row("make-vs-do", "2026-10-14T09:19:51"), _row("used-to", "2026-10-14T09:32:31"),
        _row("demo-motion", "2026-10-15T10:00:00"), _row("used-to", "2026-10-15T12:00:00", quality="720p30")]


def test_current_render_is_the_newest_per_lesson_without_demos_or_drafts(tmp_path):
    studio = _studio(tmp_path, ROWS)
    current = M.current_render_per_lesson(ROWS, studio)
    assert set(current) == {"make-vs-do", "used-to"}
    assert current["make-vs-do"]["at"] == "2026-10-15T09:11:37"
    assert current["used-to"]["at"] == "2026-10-14T09:32:31"     # the 720p draft is newer but never counts


def test_the_review_ledger_round_trips_and_the_last_line_wins(tmp_path):
    M.record_review("a.mp4", "aprobada", "bien", studio_dir=tmp_path)
    M.record_review("a.mp4", "rehacer", "  b04 suena mal ", studio_dir=tmp_path)
    M.record_review("b.mp4", "aprobada", studio_dir=tmp_path)
    last = M.latest_reviews(tmp_path)
    assert last["a.mp4"]["status"] == "rehacer" and last["a.mp4"]["note"] == "b04 suena mal"
    assert last["b.mp4"]["status"] == "aprobada"
    assert len(M.reviews_path(tmp_path).read_text().splitlines()) == 3
    with pytest.raises(ValueError):
        M.record_review("a.mp4", "subida", studio_dir=tmp_path)    # «subida» comes from the ledger only


def test_a_new_render_starts_por_revisar_and_older_ones_go_to_anteriores(tmp_path):
    board = M.review_board(_studio(tmp_path, ROWS), publication=lambda r: None)
    assert [r["file"] for r, _ in board["por_revisar"]] == ["used-to/2026-10-14T09:32:31.mp4",
                                                            "make-vs-do/2026-10-15T09:11:37.mp4"]
    assert board["aprobadas"] == [] and len(board["anteriores"]) == 2


def test_only_aprobada_reaches_listas_para_subir(tmp_path):
    studio = _studio(tmp_path, ROWS)
    M.record_review("make-vs-do/2026-10-15T09:11:37.mp4", "aprobada", studio_dir=studio)
    M.record_review("used-to/2026-10-14T09:32:31.mp4", "rehacer", "otra voz", studio_dir=studio)
    M.record_review("make-vs-do/2026-10-14T09:19:51.mp4", "aprobada", studio_dir=studio)   # an old one: no effect
    board = M.review_board(studio, publication=lambda r: None)
    assert [r["file"] for r, _ in board["aprobadas"]] == ["make-vs-do/2026-10-15T09:11:37.mp4"]
    assert board["por_revisar"] == [] and [r["lesson"] for r, _ in board["rehacer"]] == ["used-to"]


def test_a_render_with_a_missing_file_is_never_uploadable(tmp_path):
    newest = "make-vs-do/2026-10-15T09:11:37.mp4"
    studio = _studio(tmp_path, ROWS, missing={newest})
    M.record_review(newest, "aprobada", studio_dir=studio)
    board = M.review_board(studio, publication=lambda r: None)
    assert newest not in [r["file"] for r, _ in board["aprobadas"] + board["por_revisar"]]
    assert (next(r for r, _ in board["anteriores"] if r["file"] == newest), True) in board["anteriores"]
    # the next-newest file on disk becomes current
    assert "make-vs-do/2026-10-14T09:19:51.mp4" in [r["file"] for r, _ in board["por_revisar"]]


def test_usar_esta_version_makes_an_older_render_current(tmp_path):
    studio = _studio(tmp_path, ROWS)
    old = "make-vs-do/2026-10-13T11:34:37.mp4"
    M.record_review(old, "por revisar", reopen=True, studio_dir=studio)
    board = M.review_board(studio, publication=lambda r: None)
    assert old in [r["file"] for r, _ in board["por_revisar"]]
    assert "make-vs-do/2026-10-15T09:11:37.mp4" in [r["file"] for r, _ in board["anteriores"]]


def test_an_uploaded_render_shows_in_subidas_with_its_link(tmp_path):
    studio = _studio(tmp_path, ROWS)
    done = "make-vs-do/2026-10-15T09:11:37.mp4"
    link = {"published_at": "2026-10-15T13:00:00", "url": "https://www.youtube.com/watch?v=vid123"}
    board = M.review_board(studio, publication=lambda r: link if r["file"] == done else None)
    assert board["subidas"] == [(next(r for r in ROWS if r["file"] == done), link)]
    assert done not in [r["file"] for r, _ in board["aprobadas"] + board["por_revisar"]]


def test_english_flags_list_the_beats_to_listen_to(tmp_path):
    audit = tmp_path / "audio" / "make-vs-do" / "v"
    audit.mkdir(parents=True)
    (audit / "english_audit.json").write_text(json.dumps({
        "b04": {"rows": [{"expected": "make", "verdict": "FAIL"}, {"expected": "do", "verdict": "ok"}]},
        "b34": {"rows": [{"expected": "did", "verdict": "FAIL"}]}}))
    assert M.english_flags(_row("make-vs-do", "x"), tmp_path) == [("b04", "make"), ("b34", "did")]
    assert M.english_flags(_row("used-to", "x"), tmp_path) == []


def test_the_page_has_two_tabs_and_the_editor_has_no_upload_button(monkeypatch):
    from streamlit.testing.v1 import AppTest

    # The app runs in this process, on these very modules: patch them with monkeypatch
    # so they are restored. Assigning inside app() left publish.fetch_routes a stub for
    # every later test (test_publish failed after this one, STEP 60 §3).
    monkeypatch.setattr(M, "fetch_voices", lambda key: [])
    monkeypatch.setattr(M.P, "fetch_routes", lambda *a, **k: [])
    monkeypatch.setattr(M, "review_board", lambda *a, **k: {"por_revisar": [], "aprobadas": [], "rehacer": [],
                                                            "subidas": [], "anteriores": []})

    def app():
        import manim_studio as M
        M.render()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == ["Hacer lección", "Revisar y subir (0)"]
    assert "Subir a YouTube" not in [b.label for b in at.button]

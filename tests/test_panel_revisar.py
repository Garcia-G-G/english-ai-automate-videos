"""STEP 83 §3: Revisar. Frames, the six checks with «sin dato», reject reasons, the page itself."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from panel import revisar as R  # noqa: E402


def _mp4(path: Path, seconds=6):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=270x480:r=10:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def test_frame_times_cover_0_25_50_75_the_outro_and_the_end():
    t = R.frame_times(60.0, 55.0)
    assert t[:4] == [0.0, 15.0, 30.0, 45.0] and t[4] == 55.0 and t[5] == pytest.approx(59.9)
    assert R.frame_times(60.0)[4] == 56.0                                  # no outro known: the last 4 s


def test_frames_are_drawn_once_and_cached_next_to_the_video(tmp_path):
    mp4 = tmp_path / "a.mp4"
    _mp4(mp4)
    f0, strip = R.frames(mp4)
    assert f0.name == "a_f0.png" and strip.name == "a_strip.png"
    from PIL import Image
    assert Image.open(strip).size[0] == 6 * 186
    before = strip.stat().st_mtime_ns
    assert R.frames(mp4) == (f0, strip) and strip.stat().st_mtime_ns == before


def test_an_unreadable_video_gives_no_frames_not_an_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    assert R.frames(bad) == (None, None)


def test_missing_values_are_sin_dato_never_a_tick():
    rows = R.checks({}, None, None, False)
    assert [r["state"] for r in rows] == ["none"] * 6 and all(r["value"] == "sin dato" for r in rows)
    assert R.verdict({}, rows).startswith("Sin veredicto")


def test_the_checks_read_what_the_sidecar_and_the_guards_hold():
    meta = {"gate": "PASS", "deesser": {"input_lufs": -20.0}}
    rows = R.checks(meta, 1, None, True)
    by = {r["key"]: r for r in rows}
    assert by["volume"] == {"key": "volume", "label": "Volumen", "state": "ok", "value": "-20.0 LUFS"}
    assert by["words"]["state"] == "ok" and by["text"]["state"] == "ok" and by["sync"]["state"] == "none"
    assert R.verdict(meta, rows) == "Pasa el control de calidad: 3 de 6 comprobaciones con dato"
    assert R.checks({"deesser": {"input_lufs": -5.0}}, 7, "hueco vacío", True)[0]["state"] == "bad"
    bad = R.checks({"deesser": {"input_lufs": -20.0}}, 7, "hueco vacío", True)
    assert {r["key"]: r["state"] for r in bad}["words"] == "bad" and {r["key"]: r["state"] for r in bad}["text"] == "bad"


def test_a_failed_gate_names_its_flags():
    assert R.verdict({"gate": "REJECT", "blocking_flags": ["silence"]}, []) == "No pasa el control de calidad: silence"


def test_the_reject_reason_is_saved_in_the_sidecar(tmp_path):
    side = tmp_path / "a.json"
    side.write_text(json.dumps({"gate": "PASS"}))
    R.save_reject_reason(side, "audio", "  suena cortado  ", "2026-11-14T10:00:00")
    assert json.loads(side.read_text())["rejected"] == {"reason": "audio", "note": "suena cortado", "at": "2026-11-14T10:00:00"}
    assert R.REASONS == ["audio", "imagen", "texto", "otro"]
    R.save_reject_reason(tmp_path / "missing.json", "otro", "", "x")            # no sidecar: nothing raised


def test_the_cost_is_read_from_the_sidecar_or_sin_dato():
    assert R.cost_of({"cost": {"total_usd": 0.07}}) == 0.07 and R.cost_of({}) is None


def _app():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=180)
    at.session_state["current_page"] = "Review"
    return at


def test_an_empty_review_says_there_is_nothing_and_offers_inicio():
    at = _app()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Nada que revisar" in m.value for m in at.markdown) and any(b.label == "Ir a Inicio" for b in at.button)


def test_a_pending_video_shows_the_verdict_the_editor_and_the_three_actions(tmp_path, monkeypatch):
    pend = tmp_path / "_output" / "pending" / "how_do_you_say"
    pend.mkdir(parents=True)
    _mp4(pend / "v1.mp4")
    script = json.loads((ROOT / "content/queue/_done/bv002_casa.json").read_text(encoding="utf-8"))
    (pend / "v1.json").write_text(json.dumps({"gate": "PASS", "deesser": {"input_lufs": -20.0}, "cost": {"total_usd": 0.07},
                                              "script_data": script, "metadata": {"title": "¿Cómo se dice CASA? 🏠", "description": "d"}}))
    at = _app()
    import jobs
    monkeypatch.setattr(jobs, "PENDING_DIR", tmp_path / "_output" / "pending")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = {b.label for b in at.button}
    assert {"✓ Aprobar y programar", "✕ Rechazar", "↻ Volver a renderizar"} <= labels
    text = " ".join(m.value for m in at.markdown)
    assert "Pasa el control de calidad" in text and "1 de 1" in text and "Fotograma 0" in text
    assert any("0.07" in c.value and "lo que costó este vídeo" in c.value for c in at.caption)
    assert (pend / "v1_f0.png").exists() and (pend / "v1_strip.png").exists()

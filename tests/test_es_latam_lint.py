"""STEP 81 §7: neutral Latin-American Spanish. One fixture per mapped word, «tío» included (it stays)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import es_latam_lint as L  # noqa: E402

CASES = [
    ("Quiero coger el tren", "Quiero tomar el tren"), ("Él coge un taxi", "Él toma un taxi"), ("Hemos cogido el bus", "Hemos tomado el bus"),
    ("Mi móvil es nuevo", "Mi celular es nuevo"), ("Dos móviles", "Dos celulares"),
    ("Busco piso", "Busco departamento"), ("Un piso compartido", "Un departamento compartido"),
    ("Un zumo de naranja", "Un jugo de naranja"), ("Patatas fritas", "Papas fritas"), ("Una patata", "Una papa"),
    ("Vale, vamos", "Está bien, vamos"), ("¡Vale!", "¡Está bien!"),
    ("El camarero llega", "El mesero llega"), ("La camarera llega", "La mesera llega"),
    ("Mi ordenador va lento", "Mi computadora va lento"), ("Mis gafas", "Mis lentes"),
    ("El grifo gotea", "La llave del agua gotea"), ("Agua del grifo", "Agua de la llave"),
    ("Una tarta de queso", "Un pastel de queso"), ("Las tartas", "Los pasteles"),
    ("Un melocotón", "Un durazno"), ("Aparcar aquí", "Estacionar aquí"), ("Este finde", "Este fin de semana"),
    ("Me toca fregar", "Me toca lavar los platos"), ("Fregar los platos", "Lavar los platos"),
    ("Te echo de menos", "Te extraño"), ("Echar de menos a tu familia", "Extrañar a tu familia"),
    ("Estoy sin blanca", "Estoy sin dinero"), ("Vosotros sois", "Ustedes son"), ("Una chaqueta roja", "Una chamarra roja"),
]


@pytest.mark.parametrize("before,after", CASES)
def test_every_mapped_word(before, after):
    assert L.fix(before) == after


@pytest.mark.parametrize("text", ["Mi tío es médico", "Mi tío Juan vive en Madrid", "¿A qué piso vas?", "El primer piso", "No vale la pena",
                                  "¿Cuánto vale?"])
def test_what_must_stay_stays(text):
    # «tío» is not mapped; a floor is not a flat; «vale» the verb is not the interjection
    assert L.fix(text) == text


def test_english_markup_translations_and_hashtags_are_never_touched():
    data = {"type": "how_do_you_say", "items": [{"spanish": "El móvil", "english": "the móvil"}],
            "translations": {"phone": "móvil"}, "hashtags": ["#móvil"], "_meta": {"why": "coger"},
            "outro": "Toma [[coge el móvil]] y coge el tren"}
    new, changes = L.fix_script(data)
    assert new["items"][0] == {"spanish": "El celular", "english": "the móvil"}
    assert new["translations"] == {"phone": "móvil"} and new["hashtags"] == ["#móvil"] and new["_meta"] == {"why": "coger"}
    assert new["outro"] == "Toma [[coge el móvil]] y toma el tren" and {c[0] for c in changes} == {"items[0].spanish", "outro"}


def test_a_pair_made_equal_by_the_map_is_said_once():
    assert L.fix("Zumo / jugo") == "Jugo" and L.fix("Grifo / llave") == "Llave"


def test_the_report_lists_file_field_before_and_after_and_apply_rewrites(tmp_path, monkeypatch):
    q = tmp_path / "queue" / "quiz"
    q.mkdir(parents=True)
    (q / "a.json").write_text(json.dumps({"title": "Mi móvil", "options": {"A": "coger"}}), encoding="utf-8")
    monkeypatch.setattr(L, "QUEUE", tmp_path / "queue")
    monkeypatch.setattr(L, "ROOT", tmp_path)
    monkeypatch.setattr(L, "REPORT", tmp_path / "latam.md")
    L.main([])
    assert "title" in (tmp_path / "latam.md").read_text() and "Mi móvil → Mi celular" in (tmp_path / "latam.md").read_text()
    assert json.loads((q / "a.json").read_text())["title"] == "Mi móvil"                  # report mode changes nothing
    L.main(["--apply"])
    assert json.loads((q / "a.json").read_text()) == {"title": "Mi celular", "options": {"A": "tomar"}}


def test_the_queue_guard_reports_a_spain_only_word_without_blocking():
    import queue_guard
    found = queue_guard._content_problems({"type": "how_do_you_say", "theme": "el móvil", "items": []})
    assert any(p.startswith("latam:") for p in found) and not queue_guard.blocks("latam: theme")

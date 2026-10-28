"""STEP 80 §3: a faster panel, «Crear» without Inicio's blocks, and labels in Spanish."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def test_the_cleanup_plan_waits_for_its_switch():
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    body = admin[admin.index('st.markdown(\'<div class="section-header">Limpiar</div>\''):admin.index('elif page == "Manim"')]
    assert body.index('st.toggle("Calcular qué se puede limpiar"') < body.index("_clean.plan()")


@pytest.fixture(scope="module")
def crear():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=300)
    at.session_state["current_page"] = "Generate"
    at.run()
    assert not at.exception
    return at


def test_crear_no_longer_repeats_inicios_history(crear):
    text = " ".join(m.value for m in crear.markdown)
    assert "Recent (Last 5)" not in text and "**Status:**" not in text
    assert any("Lo terminado y los fallos están en «Inicio»" in c.value for c in crear.caption)


def test_crear_speaks_spanish_and_names_the_types(crear):
    labels = [w.label for w in crear.selectbox] + [w.label for w in crear.radio]
    assert "Tipo de vídeo" in labels and "Tema" in labels
    assert not {"Video Type", "Topic Selection", "Category", "Audience profile"} & set(labels)
    vt = next(w for w in crear.selectbox if w.label == "Tipo de vídeo")
    assert "Elige la correcta" in vt.options and "choose_level" not in vt.options
    mode = next(w for w in crear.radio if w.label == "Tema")
    assert mode.options == ["Al azar", "Elegir categoría", "Tema concreto"]


def test_type_label_is_the_types_own_name():
    import admin
    assert admin.type_label("choose_level") == "Elige la correcta"
    assert admin.type_label("how_do_you_say") == "Cómo se dice"
    assert admin.type_label("unknown_type") == "Unknown Type"

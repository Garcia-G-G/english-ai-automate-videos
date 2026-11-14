"""STEP 83 §4: every page opens with an h1 and one sentence, and no label is left in English."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")

PAGES = {"Generate": "Crear", "Queue": "Cola", "Upload": "Subir", "Library": "Biblioteca", "Scheduler": "Programar",
         "Topics": "Temas", "Settings": "Ajustes", "Comments": "Comentarios", "Performance": "Rendimiento", "Logs": "Registros",
         "Manim": "Lecciones", "Review": "Revisar", "Dashboard": "Inicio"}


@pytest.mark.parametrize("page,title", [(p, t) for p, t in PAGES.items() if p not in ("Review", "Dashboard")])
def test_each_page_uses_the_shared_header(page, title):
    block = SRC[SRC.index(f'page == "{page}"'):]
    first = block[:block.index("\nelif page ==") if "\nelif page ==" in block else len(block)]
    assert f'_page_header("{title}"' in first


def test_no_page_still_opens_with_a_bare_markdown_h2():
    assert not re.search(r'st\.markdown\("## (Crear|Cola|Subir|Biblioteca|Programar|Temas|Ajustes|Comentarios|Rendimiento|Registros)', SRC)


@pytest.mark.parametrize("english", ["Uploaded to", "Uploading to", "Regeneration failed", "No approved videos ready", "Upload module not available"])
def test_the_user_facing_english_is_gone(english):
    assert english not in SRC

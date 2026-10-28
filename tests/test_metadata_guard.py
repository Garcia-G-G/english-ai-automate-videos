"""STEP 80 §0: no empty quotes or leftover fields in a title, and money that is not LaTeX."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import metadata_generator as M  # noqa: E402


@pytest.mark.parametrize("text", ["¿Sabías que '' NO significa lo que crees? 😱", "Llevas TODA tu vida diciendo '' MAL 😬",
                                  'Di "" bien', "«» aquí", "¿Cómo se dice {theme}?", "Hola [[world]]", "‘’", "“  ”"])
def test_the_guard_refuses_empty_quotes_and_leftovers(text):
    assert M.metadata_problems(text)


@pytest.mark.parametrize("text", ["It's 'fine' 😎", "«Despite of»: el «of» que sobra", "¿Cómo se dice CASA en inglés? 🏠",
                                  "Don't say 'I go to home'"])
def test_the_guard_lets_real_quotes_through(text):
    assert M.metadata_problems(text) == []


@pytest.mark.parametrize("vtype", sorted(M.TITLE_TEMPLATES) + ["unknown_type"])
def test_no_type_fills_a_template_with_nothing(vtype):
    """The live bug: an empty `word` went into «'{word}'»."""
    for _ in range(30):                                      # the template is chosen at random
        meta = M.generate_metadata({}, vtype)
        assert M.metadata_problems(meta["title"]) == [], (vtype, meta["title"])
        assert M.metadata_problems(meta["description"]) == [], (vtype, meta["description"])


def test_a_word_still_fills_its_template():
    titles = {M._build_fallback_title({"word": "actually"}, "pronunciation") for _ in range(40)}
    assert any("'actually'" in t for t in titles)


def test_a_scripts_own_bad_title_is_replaced():
    meta = M.generate_metadata({"video_title": "Llevas TODA tu vida diciendo '' MAL 😬"}, "pronunciation")
    assert "''" not in meta["title"]


def test_a_series_video_uses_its_scripts_title_caption_and_hashtags():
    """hc_c010 went up as «¿Sabías que '' NO significa…»: the series had no template and the
    upload never saw its script."""
    script = json.loads((ROOT / "content" / "hecho_con_claude" / "drafts" / "hc_c010.json").read_text(encoding="utf-8"))
    meta = M.generate_metadata(script, "hecho_con_claude")
    assert meta["title"] == script["title"]
    assert meta["description"].startswith(script["caption"].strip()[:40])
    assert M.generate_metadata({}, "hecho_con_claude")["title"] == M.TITLE_TEMPLATES["hecho_con_claude"][0]


def test_the_upload_finds_a_series_videos_script_by_its_id():
    source = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    body = source[source.index("def script_for_upload"):source.index("def upload_content")]
    assert 'series.DRAFTS_DIR / f"{script_id}.json"' in body


def test_a_generated_title_with_empty_quotes_falls_back(monkeypatch):
    source = (ROOT / "src" / "metadata_generator.py").read_text(encoding="utf-8")
    body = source[source.index("def regenerate_for_platform"):]
    assert "generated metadata refused" in body


# ── money is not LaTeX ───────────────────────────────────────────────

@pytest.mark.parametrize("path", ["src/admin.py", "src/manim_studio.py"])
def test_no_bare_dollar_before_a_number_in_panel_text(path):
    """Two «$» on one line of st.markdown/caption/labels render as italic math."""
    bad = []
    for n, line in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"(?<![\\\;])\$\{", line):
            bad.append(f"{path}:{n}: {line.strip()[:90]}")
    assert bad == []


def test_the_guard_tool_finds_nothing_queued_and_lists_the_published():
    sys.path.insert(0, str(ROOT / "tools"))
    import metadata_guard as G
    assert G.check_queue()["now_bad"] == []
    texts = [r["text"] for r in G.check_published()]
    assert all(M.metadata_problems(t) for t in texts)

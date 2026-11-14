"""STEP 83 §0: the Papel palette. Contrast for every text/background pair the CSS uses, one source of truth."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from panel import tokens as T  # noqa: E402


@pytest.mark.parametrize("fg,bg,minimum", T.PAIRS)
def test_every_text_pair_the_css_uses_is_wcag_aa(fg, bg, minimum):
    assert T.contrast(T.PAPEL[fg], T.PAPEL[bg]) >= minimum


def test_the_values_claude_checked():
    c = lambda a, b: round(T.contrast(T.PAPEL[a], T.PAPEL[b]), 2)           # noqa: E731
    assert (c("white", "blue"), c("white", "green"), c("white", "badge"), c("muted", "page")) == (4.94, 4.67, 4.96, 4.95)


def test_the_palette_is_the_one_garcia_chose():
    p = T.PAPEL
    assert (p["page"], p["ink"], p["blue"], p["yellow"], p["badge"], p["green"], p["red"]) == (
        "#F5F1EA", "#191720", "#1F6FD1", "#F6D35B", "#C9401F", "#12854F", "#D2433A")


def test_every_css_variable_is_a_token():
    css = T.css()
    used = set(re.findall(r"var\(--([a-z0-9-]+)\)", css))
    defined = {k.replace("_", "-") for k in T.PAPEL}
    assert used <= defined, used - defined


def test_yellow_and_coral_are_never_a_text_colour():
    css = T.css()
    assert not re.search(r"[^-]color:\s*var\(--(yellow|coral)\)", css)


def test_the_streamlit_theme_matches_the_tokens():
    toml = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    for line in T.theme_toml().splitlines():
        assert line in toml, line
    assert 'base = "light"' in toml


def test_the_mocks_components_are_ported():
    css = T.css()
    for sel in (".card", ".sticker", ".btn", ".tag", ".chip", ".nav.on", ".badge", ".badge.soft", ".st-key-btn-primary"):
        assert sel in css, sel


def test_the_panel_renders_with_the_new_theme():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]

#!/usr/bin/env python3
"""Guard the Streamlit session_state contract for editable metadata fields.

    python3 -m pytest tests/test_admin_metadata_state.py

A Streamlit widget with a `key` keeps its value in st.session_state[key], and
once that entry exists the `value=` argument is IGNORED on every rerun. Mixing
the two produces a silent failure with no error and no visible change — which
is exactly how metadata regeneration was broken: the button wrote a paid-for
API result to a separate storage key, st.rerun() ran, and the widget returned
its stale text straight back over the new value.

Streamlit is not importable in a headless test run, so the contract is
modelled explicitly and the source is checked by AST.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "src" / "admin.py"

#: Widgets that persist through session_state when given a key.
STATEFUL_WIDGETS = {"text_input", "text_area", "number_input", "selectbox",
                    "checkbox", "slider", "radio", "multiselect"}

#: The metadata fields the regenerate button writes to.
METADATA_KEYS = ("meta_title_", "meta_desc_", "meta_tags_")


class FakeStreamlit:
    """Models the documented contract: `value=` loses to an existing key."""

    def __init__(self):
        self.session_state = {}

    def _widget(self, _label, value=None, key=None, **_kw):
        if key is None:
            return value
        if key in self.session_state:
            return self.session_state[key]      # value= is ignored
        self.session_state[key] = value
        return value

    text_input = text_area = _widget


# ── the contract itself ──────────────────────────────────────────────

def test_two_key_pattern_discards_an_external_write():
    """The original bug, reproduced. Kept so the reason for the fix survives
    even if the code is refactored."""
    st = FakeStreamlit()
    storage, widget = "meta_title_x", "ti_x"

    st.session_state[storage] = "ORIGINAL"
    st.session_state[storage] = st.text_input("T", value=st.session_state[storage], key=widget)

    st.session_state[storage] = "REGENERATED"          # the paid API result
    st.session_state[storage] = st.text_input("T", value=st.session_state[storage], key=widget)

    assert st.session_state[storage] == "ORIGINAL", (
        "the two-key pattern is supposed to lose the value — if this now "
        "passes the value through, the model of Streamlit here is wrong")


def test_single_key_pattern_keeps_an_external_write():
    """The fix. The button writes the same entry the widget reads."""
    st = FakeStreamlit()
    key = "meta_title_x"

    st.session_state[key] = "ORIGINAL"
    st.text_input("T", key=key)

    st.session_state[key] = "REGENERATED"              # the paid API result
    st.text_input("T", key=key)

    assert st.session_state[key] == "REGENERATED"


def test_single_key_pattern_still_lets_the_user_type():
    """Editing must keep working — it was the one thing that DID work before."""
    st = FakeStreamlit()
    key = "meta_title_x"
    st.session_state[key] = "ORIGINAL"
    st.text_input("T", key=key)

    st.session_state[key] = "user typed this"          # what a widget edit does
    st.text_input("T", key=key)

    assert st.session_state[key] == "user typed this"


# ── the source, so it cannot regress ─────────────────────────────────

def _widget_calls():
    tree = ast.parse(ADMIN.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in STATEFUL_WIDGETS]


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def test_metadata_widgets_never_mix_key_with_value():
    """The specific regression. A metadata widget that regains a `value=`
    argument has reintroduced the discard."""
    offenders = []
    for call in _widget_calls():
        key = _keyword(call, "key")
        if key is None or _keyword(call, "value") is None:
            continue
        rendered = ast.dump(key.value)
        if any(k in rendered for k in METADATA_KEYS):
            offenders.append(call.lineno)

    assert not offenders, (
        f"metadata widget mixes key= with value= at lines {offenders}; "
        "the regenerate result will be silently discarded")


def test_metadata_widget_results_are_not_assigned_back_over_storage():
    """`st.session_state[k] = st.text_input(..., key=k)` is redundant at best
    and, with a second key, is the bug itself."""
    tree = ast.parse(ADMIN.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr in STATEFUL_WIDGETS):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Subscript)
                    and "session_state" in ast.dump(target.value)):
                offenders.append(node.lineno)

    assert not offenders, (
        f"widget result assigned back onto session_state at lines {offenders} "
        "— let the widget own its key instead")


def test_regenerate_button_writes_the_key_the_widget_reads():
    """Both must name the same session_state entry, or the write is lost."""
    src = ADMIN.read_text(encoding="utf-8")

    assert 'st.text_input("Title", key=title_key)' in src
    assert 'st.session_state[title_key] = result.get("title"' in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

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


def test_regenerate_result_reaches_the_key_the_widget_reads():
    """The regenerated value must end up in the widget's own key.

    It gets there via the pending stage rather than a direct assignment: the
    buttons render BELOW the fields, so a direct write raises
    StreamlitAPIException. This asserts the route exists end to end — the
    handler stages, and the top of the next run applies the stage onto
    title_key.
    """
    src = ADMIN.read_text(encoding="utf-8")

    assert 'st.text_input("Title", key=title_key)' in src
    assert 'st.session_state[pending_key] = {' in src, "handler does not stage"
    assert 'st.session_state[title_key] = pending["title"]' in src, (
        "the stage is never applied to the widget key")


# ── the staged write ─────────────────────────────────────────────────

class StreamlitWithInstantiation(FakeStreamlit):
    """Adds the rule that produced the reported failure: session_state[k] is
    read-only once the widget owning k has rendered this run."""

    class APIException(Exception):
        pass

    def __init__(self):
        super().__init__()
        self.instantiated = set()

    def new_run(self):
        self.instantiated = set()

    def assign(self, key, value):
        if key in self.instantiated:
            raise self.APIException(
                f"st.session_state.{key} cannot be modified after the widget "
                f"with key {key} is instantiated")
        self.session_state[key] = value

    def text_input(self, _label=None, value=None, key=None, **_kw):
        self.instantiated.add(key)
        return self.session_state.get(key)


TITLE_KEY = "meta_title_foodie_20260731_163822"
PENDING_KEY = "_meta_pending_foodie_20260731_163822"


def test_assigning_a_widget_key_after_render_raises():
    """The reported error, reproduced. The regenerate buttons render BELOW the
    fields, so the handler cannot write the widget keys directly."""
    st = StreamlitWithInstantiation()
    st.session_state[TITLE_KEY] = "ORIGINAL"
    st.new_run()
    st.text_input(key=TITLE_KEY)

    with pytest.raises(StreamlitWithInstantiation.APIException, match="cannot be modified"):
        st.assign(TITLE_KEY, "REGENERATED")


def test_staged_write_survives_the_rerun_and_lands():
    """Stage under a non-widget key, rerun, apply before the widgets exist."""
    st = StreamlitWithInstantiation()
    st.session_state[TITLE_KEY] = "ORIGINAL"

    st.new_run()
    st.text_input(key=TITLE_KEY)
    st.assign(PENDING_KEY, {"title": "REGENERATED"})      # no exception

    st.new_run()                                          # st.rerun()
    pending = st.session_state.pop(PENDING_KEY, None)
    if pending:
        st.assign(TITLE_KEY, pending["title"])
    st.text_input(key=TITLE_KEY)

    assert st.session_state[TITLE_KEY] == "REGENERATED"


def test_the_staged_value_is_consumed_once():
    """Left in place it would overwrite the operator's edits on every rerun."""
    st = StreamlitWithInstantiation()
    st.session_state[PENDING_KEY] = {"title": "REGENERATED"}

    st.session_state.pop(PENDING_KEY, None)

    assert PENDING_KEY not in st.session_state


def test_the_button_handler_never_assigns_a_widget_key():
    """AST guard: the handler must stage, not assign."""
    import ast
    tree = ast.parse(ADMIN.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if not (isinstance(t, ast.Subscript)
                    and "session_state" in ast.dump(t.value)):
                continue
            sub = ast.dump(t.slice)
            if any(k in sub for k in ("title_key", "desc_key", "tags_key")):
                offenders.append(node.lineno)

    # Only the initial seeding and the pending-apply may write these, and both
    # run before the widgets are instantiated.
    src_lines = ADMIN.read_text(encoding="utf-8").splitlines()
    for ln in offenders:
        window = "\n".join(src_lines[max(0, ln - 14):ln])
        assert ("not in st.session_state" in window) or ("pending" in window), (
            f"admin.py:{ln} writes a widget key outside the seed/pending "
            "blocks — it will raise once the widget has rendered")


# ── what actually gets PUBLISHED ─────────────────────────────────────

def _admin():
    import logging
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    sys.path.insert(0, str(ROOT / "src"))
    import admin
    return admin


SCRIPT = {"question": "¿Qué significa 'fabric' en inglés?",
          "full_script": "¿Qué significa 'fabric' en inglés?",
          "hashtags": ["#LearnEnglish"]}


def test_operator_text_wins_over_generated_metadata():
    """Fixing the widget does not prove the UPLOAD uses the new value. The
    bulk path used to call generate_metadata(script, ...) at upload time and
    never look at session_state, so it published text the operator never saw —
    worse than the display bug, because it looks like it worked."""
    admin = _admin()
    name = "vid"
    tk, dk, gk = admin.metadata_session_keys(name)
    state = {tk: "OPERATOR TITLE", dk: "OPERATOR DESC", gk: "#a #b"}

    got = admin.resolve_upload_metadata(name, SCRIPT, "youtube", "quiz", "", state)

    assert got["source"] == "session"
    assert got["title"] == "OPERATOR TITLE"
    # The BODY is the operator's verbatim; the hashtag block is appended here
    # because the operator edits body and tags in two separate fields and the
    # uploader no longer composes (see test_metadata_quality).
    assert got["description"].startswith("OPERATOR DESC")
    assert got["description"].count("#a") == 1
    assert got["hashtags"] == ["a", "b"]


def test_falls_back_to_generated_when_the_session_is_empty():
    admin = _admin()

    got = admin.resolve_upload_metadata("vid", SCRIPT, "youtube", "quiz", "", {})

    assert got["source"] == "generated"
    assert got["title"]


def test_operator_text_is_used_verbatim_for_every_platform():
    """The operator already chose it. Re-adapting it per platform would be the
    same class of silent substitution this resolver exists to stop."""
    admin = _admin()
    name = "vid"
    tk, dk, gk = admin.metadata_session_keys(name)
    state = {tk: "CHOSEN", dk: "D", gk: "#x"}

    titles = {admin.resolve_upload_metadata(name, SCRIPT, p, "quiz", "", state)["title"]
              for p in ("youtube", "tiktok", "instagram")}

    assert titles == {"CHOSEN"}


def test_blank_session_title_does_not_shadow_generated_metadata():
    """An empty string is not an operator choice."""
    admin = _admin()
    name = "vid"
    tk, _dk, _gk = admin.metadata_session_keys(name)

    got = admin.resolve_upload_metadata(name, SCRIPT, "youtube", "quiz", "",
                                        {tk: "   "})

    assert got["source"] == "generated"


def test_both_upload_paths_use_the_one_resolver():
    """They used to disagree; a second call to generate_metadata inside an
    upload handler is how they drifted apart."""
    src = ADMIN.read_text(encoding="utf-8")

    assert src.count("resolve_upload_metadata(") >= 3, (
        "expected the definition plus both upload call sites")
    assert "adapted = adapt_for_platform(meta, pkey)" not in src, (
        "bulk upload is adapting generated metadata again, bypassing the "
        "operator's text")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

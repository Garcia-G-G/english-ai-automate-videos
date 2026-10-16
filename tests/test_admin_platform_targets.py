#!/usr/bin/env python3
"""The upload-target checkbox must follow auth status, not freeze at it.

    python3 -m pytest tests/test_admin_platform_targets.py

A keyed Streamlit widget IGNORES `value=` once st.session_state[key] exists,
so the ticked state froze at whatever it was the FIRST time the widget
rendered. Now that YouTube auth works, a session that rendered before auth
succeeded keeps showing YouTube unavailable forever.

The checkbox carries TWO kinds of state and that is why neither obvious fix
works alone:

    derived — is the platform configured/authenticated
    user    — does the operator want to publish there this time

Dropping the key destroys the user half; keeping the key alone destroys the
derived half. reconcile_platform_target owns the boundary.

The derived half decides what is SELECTABLE. It never decides what is
selected: every target defaults to unticked, and the operator opts in per
press. A destination nobody chose must not be armed on a page whose button
publishes irreversibly.
"""

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.getLogger("streamlit").setLevel(logging.CRITICAL)

from admin import reconcile_platform_target  # noqa: E402

YT = "YouTube Shorts"
KEY = f"target_{YT}"


class KeyedWidget:
    """Models the shipped Streamlit contract, for the before-the-fix proof."""

    def __init__(self):
        self.state = {}

    def checkbox(self, _label, value=None, disabled=False, key=None):
        if key in self.state:
            return self.state[key]          # value= is ignored
        self.state[key] = value
        return value


# ── the failure, reproduced ──────────────────────────────────────────

def test_shipped_pattern_freezes_at_the_first_render():
    """Before the fix: auth succeeds and the checkbox never notices."""
    w = KeyedWidget()

    w.checkbox("YT", value=False, disabled=True, key=KEY)     # auth not done
    after_auth = w.checkbox("YT", value=True, disabled=False, key=KEY)

    assert after_auth is False, (
        "the old pattern is supposed to freeze — if this passes the new value "
        "through, the model of Streamlit here is wrong")


def test_shipped_pattern_would_target_an_unconfigured_platform():
    """The dangerous direction, and the reason this is not merely cosmetic.

    A disabled checkbox still RETURNS its stored value, so a platform whose
    credentials were removed stays ticked and the upload is attempted with no
    way to authenticate."""
    w = KeyedWidget()

    w.checkbox("YT", value=True, disabled=False, key=KEY)      # configured
    after_removal = w.checkbox("YT", value=False, disabled=True, key=KEY)

    assert after_removal is True


# ── the fix ──────────────────────────────────────────────────────────

def test_becoming_available_does_not_arm_the_target():
    """Connecting a platform makes it selectABLE, not selected.

    This used to assert True — "what the operator almost certainly wants
    right after connecting". On a page whose button publishes irreversibly
    that is the wrong trade: it armed a destination nobody picked.
    """
    state = {}

    assert reconcile_platform_target(state, YT, enabled=False) is False
    assert reconcile_platform_target(state, YT, enabled=True) is False


def test_an_unavailable_platform_is_forced_off_even_if_stored_on():
    """Stale session_state must never win over "we cannot authenticate"."""
    state = {KEY: True, f"_target_seen_{YT}": True}

    assert reconcile_platform_target(state, YT, enabled=False) is False
    assert state[KEY] is False


def test_the_operator_choice_survives_while_the_platform_stays_available():
    """Dropping the key would have reset this to off on every rerun."""
    state = {}
    reconcile_platform_target(state, YT, enabled=True)     # defaults off
    state[KEY] = True                                      # operator ticks

    assert reconcile_platform_target(state, YT, enabled=True) is True


def test_reconnecting_does_not_re_arm_the_target():
    """Credentials coming back is not the operator choosing to publish."""
    state = {}
    reconcile_platform_target(state, YT, enabled=True)
    state[KEY] = True                                       # operator ticks
    reconcile_platform_target(state, YT, enabled=False)     # creds pulled

    assert reconcile_platform_target(state, YT, enabled=True) is False


def test_repeated_renders_are_stable():
    """No oscillation: the same inputs must give the same answer."""
    state = {}
    first = reconcile_platform_target(state, YT, enabled=True)
    for _ in range(5):
        assert reconcile_platform_target(state, YT, enabled=True) == first


def test_platforms_are_tracked_independently():
    state = {}
    reconcile_platform_target(state, "TikTok", enabled=True)
    reconcile_platform_target(state, YT, enabled=True)
    state[KEY] = True                                       # only YouTube ticked

    assert reconcile_platform_target(state, "TikTok", enabled=True) is False
    assert reconcile_platform_target(state, YT, enabled=True) is True


# ── the widget key is not permanent, and the sentinel is ─────────────

def test_the_widget_key_can_vanish_while_the_sentinel_remains():
    """The crash: KeyError 'target_TikTok' straight out of the dashboard.

    Streamlit garbage-collects a widget's key when that widget is not
    rendered on a run, and these checkboxes live inside `if approved:` —
    so an operator with nothing awaiting upload, or simply sitting on
    another tab, loses `target_<platform>`. The `_target_seen_<platform>`
    sentinel is NOT a widget key, so it survives.

    That leaves `previously == enabled` with no stored value to return,
    which is precisely the state the traceback proves the dashboard reached.
    """
    state = {f"_target_seen_{YT}": True}

    assert reconcile_platform_target(state, YT, enabled=True) is False
    assert KEY in state, "the caller renders a keyed widget straight after this"


def test_the_operator_choice_survives_the_widget_key_being_collected():
    """A deliberate tick must outlive a trip to another tab.

    Streamlit collecting the widget key must not throw away a choice the
    operator made. The default is off, but "off because it was never chosen"
    and "off because Streamlit lost it" have to stay distinguishable, which
    is what the durable _target_want_ mirror is for.
    """
    state = {}
    reconcile_platform_target(state, YT, enabled=True)      # defaults off
    state[KEY] = True                                       # operator ticks
    reconcile_platform_target(state, YT, enabled=True)      # a rerun happens

    del state[KEY]                                          # Streamlit collects it

    assert reconcile_platform_target(state, YT, enabled=True) is True


def test_a_collected_key_on_an_unavailable_platform_stays_off():
    """The dangerous direction, across the same boundary."""
    state = {f"_target_seen_{YT}": True}

    assert reconcile_platform_target(state, YT, enabled=False) is False
    assert state[KEY] is False


def test_the_function_always_leaves_the_widget_key_set():
    """Whatever the entry state, the caller can render the widget after."""
    for state in ({}, {f"_target_seen_{YT}": True}, {f"_target_seen_{YT}": False},
                  {KEY: True}, {KEY: False, f"_target_seen_{YT}": True}):
        for enabled in (True, False):
            s = dict(state)
            result = reconcile_platform_target(s, YT, enabled=enabled)
            assert KEY in s, f"{state} + enabled={enabled} left no widget key"
            assert s[KEY] is result
            assert isinstance(result, bool)


def test_the_widget_no_longer_passes_value():
    """A `value=` on this checkbox means the reconciliation was bypassed."""
    import ast
    tree = ast.parse((ROOT / "src" / "admin.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "checkbox"):
            continue
        kw = {k.arg for k in n.keywords}
        if "key" in kw:
            assert "value" not in kw, (
                f"admin.py:{n.lineno} checkbox passes both key= and value=; "
                "the keyed widget will ignore value= and freeze")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

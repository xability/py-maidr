"""Tests for the Streamlit integration in ``maidr.widget.streamlit``.

``maidr_html`` needs no Streamlit at all, so most of these run anywhere.
The two dispatch tests stub ``streamlit`` rather than driving a real app,
because what they check is which API is called with which arguments.
"""

from __future__ import annotations

import sys
import types
import warnings

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.util.dependencies import read_bundled_js  # noqa: E402
from maidr.widget.streamlit import maidr_html, render_maidr  # noqa: E402

#: A slice of the real bundle, so "is the bundle inlined?" is answered by
#: looking for the bundle rather than by a size threshold.
_BUNDLE_HEAD = read_bundled_js()[:200]


@pytest.fixture
def bar_axes():
    """Yield the axes of a two-bar chart, closed afterwards."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    yield ax
    plt.close(fig)


class _Recorder:
    """Records the call it received, standing in for a Streamlit function."""

    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "delta-generator"


def _stub_streamlit(monkeypatch, *, with_iframe: bool):
    """Install a fake ``streamlit`` module and return its recorders."""
    st = types.ModuleType("streamlit")
    components = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")

    v1.html = _Recorder()
    components.v1 = v1
    if with_iframe:
        st.iframe = _Recorder()
    st.components = components

    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "streamlit.components", components)
    monkeypatch.setitem(sys.modules, "streamlit.components.v1", v1)
    return st, v1


# ---------------------------------------------------------------------------
# maidr_html
# ---------------------------------------------------------------------------


def test_maidr_html_returns_a_string(bar_axes):
    """The point of the entry point is that it hands back a cacheable string."""
    assert isinstance(maidr_html(bar_axes), str)


def test_maidr_html_needs_no_streamlit(bar_axes, monkeypatch):
    """Rendering must not require the optional extra."""
    monkeypatch.setitem(sys.modules, "streamlit", None)
    assert maidr_html(bar_axes)


def test_maidr_html_emits_no_maidr_iframe(bar_axes):
    """Streamlit supplies the iframe; a second one nested inside it is a bug.

    This is the regression guard for ``Environment.is_shiny()``: while it
    reported "shiny is installed" rather than "a Shiny session is running",
    any Streamlit app with Shiny also on disk got exactly that nesting.
    """
    pytest.importorskip("shiny")  # the condition that used to trigger it
    assert "<iframe" not in maidr_html(bar_axes).lower()


@pytest.mark.parametrize(
    ("use_cdn", "expect_cdn", "expect_inline_bundle"),
    [(True, True, False), ("auto", True, False), (False, False, True)],
)
def test_each_cdn_mode_ships_the_source_it_promises(
    bar_axes, use_cdn, expect_cdn, expect_inline_bundle
):
    """Every mode must put a real source for maidr.js in the string.

    ``use_cdn=False`` has to inline: serialising to HTML is what makes the
    embed possible, and it drops ``HTMLDependency`` children on the way,
    so a reference to the bundle would not survive the trip.
    """
    html = maidr_html(bar_axes, use_cdn=use_cdn)
    assert ("cdn.jsdelivr" in html) is expect_cdn
    assert (_BUNDLE_HEAD in html) is expect_inline_bundle


def test_offline_bundle_precedes_the_bootstrap(bar_axes):
    """``window.main()`` is called by the tag; maidr.js must exist by then."""
    html = maidr_html(bar_axes, use_cdn=False)
    assert html.index(_BUNDLE_HEAD) < html.index("window.main")


def test_a_chart_with_no_runtime_warns(bar_axes, monkeypatch):
    """The silent failure this library can least afford gets a loud check."""
    import maidr.widget.streamlit as widget

    monkeypatch.setattr(widget, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: plt.figure())

    class _Bare:
        def get_html_string(self):
            return "<div>no runtime here</div>"

    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: _Bare())

    with pytest.warns(UserWarning, match="no source for maidr.js"):
        maidr_html(bar_axes, use_cdn=False)


# ---------------------------------------------------------------------------
# render_maidr dispatch
# ---------------------------------------------------------------------------


def test_render_maidr_prefers_st_iframe(bar_axes, monkeypatch):
    """``components.v1.html`` is deprecated; ``st.iframe`` is the successor."""
    st, v1 = _stub_streamlit(monkeypatch, with_iframe=True)

    render_maidr(bar_axes, use_cdn=True)

    assert len(st.iframe.calls) == 1
    assert v1.html.calls == []
    (args, kwargs) = st.iframe.calls[0]
    assert "cdn.jsdelivr" in args[0]
    assert kwargs == {"width": "stretch", "height": "content", "tab_index": 0}


def test_render_maidr_falls_back_to_components_html(bar_axes, monkeypatch):
    """Older Streamlit still works, and still gets a usable height."""
    _st, v1 = _stub_streamlit(monkeypatch, with_iframe=False)

    render_maidr(bar_axes, use_cdn=True)

    assert len(v1.html.calls) == 1
    (_args, kwargs) = v1.html.calls[0]
    # Never None: Streamlit renders that as 150px and crops the chart.
    assert isinstance(kwargs["height"], int)
    assert kwargs["height"] > 150


def test_legacy_fallback_passes_an_integer_height_through(bar_axes, monkeypatch):
    """An explicit int height is honoured rather than replaced."""
    _st, v1 = _stub_streamlit(monkeypatch, with_iframe=False)

    render_maidr(bar_axes, height=321, width=654, use_cdn=True)

    (_args, kwargs) = v1.html.calls[0]
    assert kwargs["height"] == 321
    assert kwargs["width"] == 654


def test_tab_index_defaults_to_zero(bar_axes, monkeypatch):
    """The chart is the interface, so it must be reachable by keyboard.

    The browser default leaves the frame out of the tab order, which for a
    library whose whole surface is keyboard-driven means unreachable
    without a mouse.
    """
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)

    render_maidr(bar_axes, use_cdn=True)

    assert st.iframe.calls[0][1]["tab_index"] == 0


def test_render_maidr_returns_none(bar_axes, monkeypatch):
    """A static embed sends nothing back; returning a handle would imply it does."""
    _stub_streamlit(monkeypatch, with_iframe=True)
    assert render_maidr(bar_axes, use_cdn=True) is None


def test_render_maidr_without_streamlit_names_the_extra(bar_axes, monkeypatch):
    """The error should say how to fix it."""
    monkeypatch.setitem(sys.modules, "streamlit", None)
    with pytest.raises(ImportError, match=r"maidr\[streamlit\]"):
        render_maidr(bar_axes, use_cdn=True)


def test_render_maidr_does_not_leak_warnings(bar_axes, monkeypatch):
    """A normal render is quiet."""
    _stub_streamlit(monkeypatch, with_iframe=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_maidr(bar_axes, use_cdn=True)
    assert not [w for w in caught if "maidr.js" in str(w.message)]

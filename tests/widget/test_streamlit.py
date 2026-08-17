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

    class _Bare:
        """A rendered tag that carries no source for maidr.js."""

        def get_html_string(self):
            return "<div>no runtime here</div>"

    # Both halves are needed: the render supplies nothing, and the inline
    # fallback that would otherwise rescue it is unavailable too.
    monkeypatch.setattr(widget, "inline_bundle_tags", lambda: None)
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
    assert kwargs == {"width": "stretch", "height": "content", "tab_index": None}


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


def test_tab_index_is_passed_through_verbatim(bar_axes, monkeypatch):
    """The default is the browser's, and an explicit value is honoured.

    An iframe's contents already take part in sequential focus navigation
    and maidr gives the chart its own tab stop, so the frame does not need
    one to be reachable. Forcing ``0`` would add an extra stop announced as
    "st.iframe" on every chart, so it is offered rather than imposed.
    """
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)

    render_maidr(bar_axes, use_cdn=True)
    assert st.iframe.calls[0][1]["tab_index"] is None

    render_maidr(bar_axes, tab_index=3, use_cdn=True)
    assert st.iframe.calls[1][1]["tab_index"] == 3


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


def _stub_legacy_html(monkeypatch, *, accepts_tab_index: bool):
    """Install a streamlit whose only embed API is ``components.v1.html``."""
    st, v1 = _stub_streamlit(monkeypatch, with_iframe=False)

    if accepts_tab_index:

        def html(body, width=None, height=None, scrolling=False, *, tab_index=None):
            v1.calls.append({"tab_index": tab_index, "height": height})

    else:

        def html(body, width=None, height=None, scrolling=False):
            v1.calls.append({"height": height})

    v1.calls = []
    v1.html = html
    return v1


def test_legacy_fallback_forwards_tab_index_when_supported(bar_axes, monkeypatch):
    """``tab_index`` reached ``components.v1.html`` well before ``st.iframe``.

    Streamlit 1.45 accepted it; ``st.iframe`` only arrived in 1.56. Treating
    "no ``st.iframe``" as "no ``tab_index``" would silently discard a value
    the caller passed, across every version in between.
    """
    v1 = _stub_legacy_html(monkeypatch, accepts_tab_index=True)

    render_maidr(bar_axes, tab_index=5, use_cdn=True)

    assert v1.calls[0]["tab_index"] == 5


def test_legacy_fallback_says_so_when_tab_index_cannot_be_set(
    bar_axes, monkeypatch
):
    """Older still: the argument cannot be honoured, so it is not dropped mutely."""
    v1 = _stub_legacy_html(monkeypatch, accepts_tab_index=False)

    with pytest.warns(UserWarning, match="too old to set tab_index"):
        render_maidr(bar_axes, tab_index=5, use_cdn=True)

    assert "tab_index" not in v1.calls[0]


def test_legacy_fallback_is_quiet_when_tab_index_is_unset(bar_axes, monkeypatch):
    """Nothing to honour, so nothing to warn about."""
    _stub_legacy_html(monkeypatch, accepts_tab_index=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_maidr(bar_axes, use_cdn=True)

    assert not [w for w in caught if "tab_index" in str(w.message)]


def test_a_chart_that_only_loads_maidr_remotely_is_not_inlined(
    bar_axes, monkeypatch
):
    """The Altair shape: ``use_cdn=False`` cannot be honoured, so say so.

    ``maidr.render`` hands an Altair chart to the Vega-Lite adapter before
    ``use_cdn`` is consulted, so the chart already names a remote runtime.
    Inlining on top of that adds ~1.9 MB the page never loads while still
    requiring the network.
    """
    import maidr.widget.streamlit as widget

    class _Remote:
        def get_html_string(self):
            return '<div><script src="https://cdn.example/maidr@1/vegalite.js">' "</script></div>"

    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: _Remote())

    _stub_streamlit(monkeypatch, with_iframe=True)

    # Both entry points, because they sit at different call depths and this
    # warning is raised a frame shallower than the no-runtime one.
    for call in (
        lambda: maidr_html(bar_axes, use_cdn=False),
        lambda: render_maidr(bar_axes, use_cdn=False),
    ):
        with pytest.warns(UserWarning, match="cannot be honoured") as caught:
            call()
        assert caught[0].filename == __file__, (
            f"warning was blamed on {caught[0].filename}, not the caller"
        )

    assert _BUNDLE_HEAD not in maidr_html(bar_axes, use_cdn=False)


def test_an_empty_bundle_does_not_vouch_for_a_missing_runtime(
    bar_axes, monkeypatch
):
    """A zero-byte bundle must not silence the no-runtime warning.

    A marker sliced from an empty file is ``""``, which is a substring of
    every string -- so a naive check would report a runtime present for a
    chart that has none, which is the one thing the check exists to catch.
    """
    import maidr.widget.streamlit as widget

    class _Bare:
        def get_html_string(self):
            return "<div>no runtime here</div>"

    monkeypatch.setattr(widget, "read_bundled_js", lambda: "")
    monkeypatch.setattr(widget, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: _Bare())
    widget._bundle_marker.cache_clear()
    try:
        with pytest.warns(UserWarning, match="no source for maidr.js"):
            maidr_html(bar_axes, use_cdn=False)
    finally:
        widget._bundle_marker.cache_clear()


def test_the_no_runtime_warning_blames_the_caller_not_the_library(
    bar_axes, monkeypatch
):
    """A warning that points inside maidr tells the reader nothing useful.

    ``render_maidr`` calls ``maidr_html``, so it sits one frame further out;
    a fixed ``stacklevel`` is right for one entry point and wrong for the
    other -- and the one it was wrong for is the documented one.
    """
    import maidr.widget.streamlit as widget

    class _Bare:
        def get_html_string(self):
            return "<div>no runtime here</div>"

    _stub_streamlit(monkeypatch, with_iframe=True)
    monkeypatch.setattr(widget, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: _Bare())

    library = widget.__file__

    for call in (
        lambda: maidr_html(bar_axes, use_cdn=False),
        lambda: render_maidr(bar_axes, use_cdn=False),
    ):
        with pytest.warns(UserWarning, match="no source for maidr.js") as caught:
            call()
        assert caught[0].filename != library, (
            f"warning was blamed on the library itself, at line {caught[0].lineno}"
        )
        assert caught[0].filename == __file__


def test_an_unrelated_cdn_script_does_not_vouch_for_maidr(bar_axes, monkeypatch):
    """A Plotly chart always carries ``cdn.plot.ly``; that is not maidr.

    Asking only whether *some* ``<script>`` and *some* ``src=`` appear is
    answered "yes" by every Plotly chart, so a Plotly render whose bundle
    could not be read would have had its no-runtime warning suppressed by a
    script tag belonging to a different library.
    """
    import maidr.widget.streamlit as widget

    class _PlotlyOnly:
        def get_html_string(self):
            return (
                '<div><script src="https://cdn.plot.ly/plotly-2.min.js">'
                "</script><div>chart</div></div>"
            )

    monkeypatch.setattr(widget, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(widget.maidr, "render", lambda *a, **k: _PlotlyOnly())

    with pytest.warns(UserWarning, match="no source for maidr.js"):
        maidr_html(bar_axes, use_cdn=False)


@pytest.mark.parametrize("use_cdn", [True, "auto"])
def test_a_normal_render_is_recognised_as_having_a_runtime(bar_axes, use_cdn):
    """The runtime check must not fire on the ordinary path.

    matplotlib and Plotly build the script element in JavaScript, so the
    markup carries no ``<script src=...>`` tag for maidr at all -- only the
    URL. A tag-shaped check would call every normal render broken.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        maidr_html(bar_axes, use_cdn=use_cdn)
    assert not [w for w in caught if "no source for maidr.js" in str(w.message)]

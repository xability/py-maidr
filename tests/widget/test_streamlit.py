"""Tests for the Streamlit integration in ``maidr.widget.streamlit``.

``maidr_html`` needs no Streamlit at all, so most of these run anywhere.
The two dispatch tests stub ``streamlit`` rather than driving a real app,
because what they check is which API is called with which arguments.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys
import types
import warnings

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.util.dependencies import read_bundled_js  # noqa: E402
import maidr.widget._document as document  # noqa: E402
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

    ``use_cdn=False`` has to inline: serializing to HTML is what makes the
    embed possible, and it drops ``HTMLDependency`` children on the way,
    so a reference to the bundle would not survive the trip.
    """
    html = maidr_html(bar_axes, use_cdn=use_cdn)
    # The maidr loader URL rather than the bare host: the inlined bundle
    # names jsDelivr itself, for the DotPad SDK it fetches on first connect
    # (#771), so the host alone is in every offline document too.
    assert ("cdn.jsdelivr.net/npm/maidr" in html) is expect_cdn
    assert (_BUNDLE_HEAD in html) is expect_inline_bundle


def test_offline_bundle_precedes_the_bootstrap(bar_axes):
    """``window.main()`` is called by the tag; maidr.js must exist by then."""
    html = maidr_html(bar_axes, use_cdn=False)
    assert html.index(_BUNDLE_HEAD) < html.index("window.main")


def test_a_chart_with_no_runtime_warns(bar_axes, monkeypatch):
    """The silent failure this library can least afford gets a loud check."""

    class _Bare:
        """A rendered tag that carries no source for maidr.js."""

        def get_html_string(self):
            return "<div>no runtime here</div>"

    # Both halves are needed: the render supplies nothing, and the inline
    # fallback that would otherwise rescue it is unavailable too.
    monkeypatch.setattr(document, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(document.maidr, "render", lambda *a, **k: _Bare())

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
    assert "cdn.jsdelivr.net/npm/maidr" in args[0]
    assert kwargs == {"width": "stretch", "height": "content", "tab_index": None}


def _stub_iframe_with_alt(monkeypatch):
    """Install a streamlit whose ``st.iframe`` takes ``alt`` (Streamlit #17040)."""
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)
    calls: list = []

    def iframe(src, *, width="stretch", height="content", tab_index=None, alt=None):
        calls.append({"alt": alt, "tab_index": tab_index})

    st.iframe = iframe
    return calls


def test_the_frame_is_named_after_its_chart(bar_axes, monkeypatch):
    """Where ``st.iframe`` takes ``alt``, the frame is named for the chart.

    Without it every chart on the page is announced as "st.iframe", so a
    screen-reader user tabbing a dashboard cannot tell them apart (#461).
    The name is the one py-maidr gives its own frames.
    """
    calls = _stub_iframe_with_alt(monkeypatch)
    bar_axes.set_title("Sales by region")

    render_maidr(bar_axes, use_cdn=True)

    assert calls[0]["alt"] == "Sales by region, accessible chart"


def test_an_untitled_chart_still_gets_a_name(bar_axes, monkeypatch):
    """No title still beats "st.iframe": it says the frame holds a chart."""
    calls = _stub_iframe_with_alt(monkeypatch)

    render_maidr(bar_axes, use_cdn=True)

    assert calls[0]["alt"] == "Accessible chart"


def test_plotly_and_altair_charts_are_named_too(monkeypatch):
    """Every renderer hands its title over, not only matplotlib's."""
    go = pytest.importorskip("plotly.graph_objects")
    alt = pytest.importorskip("altair")
    import pandas as pd

    calls = _stub_iframe_with_alt(monkeypatch)
    fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    fig.update_layout(title="Plotly title")
    chart = (
        alt.Chart(pd.DataFrame({"x": ["a", "b"], "y": [1, 2]}))
        .mark_bar()
        .encode(x="x", y="y")
        .properties(title="Altair title")
    )

    render_maidr(fig, use_cdn=True)
    render_maidr(chart)

    assert [c["alt"] for c in calls] == [
        "Plotly title, accessible chart",
        "Altair title, accessible chart",
    ]


def test_alt_is_not_passed_to_a_streamlit_without_it(bar_axes, monkeypatch):
    """Streamlit before #17040 would reject the keyword outright."""
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)
    calls: list = []

    def iframe(src, *, width="stretch", height="content", tab_index=None):
        calls.append(tab_index)

    st.iframe = iframe

    render_maidr(bar_axes, use_cdn=True)

    assert calls == [None]


def test_maidr_html_is_unchanged_by_the_title(bar_axes):
    """The title rides on the Python object, never in the markup."""
    bar_axes.set_title("Sales by region")
    assert "_maidr_chart_title" not in maidr_html(bar_axes, use_cdn=True)


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
    """An explicit int height is honored rather than replaced."""
    _st, v1 = _stub_streamlit(monkeypatch, with_iframe=False)

    render_maidr(bar_axes, height=321, width=654, use_cdn=True)

    (_args, kwargs) = v1.html.calls[0]
    assert kwargs["height"] == 321
    assert kwargs["width"] == 654


def test_tab_index_is_passed_through_verbatim(bar_axes, monkeypatch):
    """The default is the browser's, and an explicit value is honored.

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


def test_legacy_fallback_says_so_when_tab_index_cannot_be_set(bar_axes, monkeypatch):
    """Older still: the argument cannot be honored, so it is not dropped mutely."""
    v1 = _stub_legacy_html(monkeypatch, accepts_tab_index=False)

    with pytest.warns(UserWarning, match="too old to set tab_index"):
        render_maidr(bar_axes, tab_index=5, use_cdn=True)

    assert "tab_index" not in v1.calls[0]


def test_legacy_fallback_is_quiet_when_tab_index_is_unset(bar_axes, monkeypatch):
    """Nothing to honor, so nothing to warn about."""
    _stub_legacy_html(monkeypatch, accepts_tab_index=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_maidr(bar_axes, use_cdn=True)

    assert not [w for w in caught if "tab_index" in str(w.message)]


def test_a_chart_that_only_loads_maidr_remotely_is_not_inlined(bar_axes, monkeypatch):
    """The Altair shape: ``use_cdn=False`` cannot be honored, so say so.

    ``maidr.render`` hands an Altair chart to the Vega-Lite adapter before
    ``use_cdn`` is consulted, so the chart already names a remote runtime.
    Inlining on top of that adds ~1.9 MB the page never loads while still
    requiring the network.
    """

    class _Remote:
        def get_html_string(self):
            return (
                '<div><script src="https://cdn.example/maidr@1/vegalite.js">'
                "</script></div>"
            )

    monkeypatch.setattr(document.maidr, "render", lambda *a, **k: _Remote())

    _stub_streamlit(monkeypatch, with_iframe=True)

    # Both entry points, because they sit at different call depths and this
    # warning is raised a frame shallower than the no-runtime one.
    for call in (
        lambda: maidr_html(bar_axes, use_cdn=False),
        lambda: render_maidr(bar_axes, use_cdn=False),
    ):
        with pytest.warns(UserWarning, match="cannot be honored") as caught:
            call()
        assert (
            caught[0].filename == __file__
        ), f"warning was blamed on {caught[0].filename}, not the caller"

    assert _BUNDLE_HEAD not in maidr_html(bar_axes, use_cdn=False)


def test_an_empty_bundle_does_not_vouch_for_a_missing_runtime(bar_axes, monkeypatch):
    """A zero-byte bundle must not silence the no-runtime warning.

    A marker sliced from an empty file is ``""``, which is a substring of
    every string -- so a naive check would report a runtime present for a
    chart that has none, which is the one thing the check exists to catch.
    """

    class _Bare:
        def get_html_string(self):
            return "<div>no runtime here</div>"

    monkeypatch.setattr(document, "read_bundled_js", lambda: "")
    monkeypatch.setattr(document, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(document.maidr, "render", lambda *a, **k: _Bare())
    document._bundle_marker.cache_clear()
    try:
        with pytest.warns(UserWarning, match="no source for maidr.js"):
            maidr_html(bar_axes, use_cdn=False)
    finally:
        document._bundle_marker.cache_clear()


def test_the_no_runtime_warning_blames_the_caller_not_the_library(
    bar_axes, monkeypatch
):
    """A warning that points inside maidr tells the reader nothing useful.

    ``render_maidr`` calls ``maidr_html``, so it sits one frame further out;
    a fixed ``stacklevel`` is right for one entry point and wrong for the
    other -- and the one it was wrong for is the documented one.
    """

    class _Bare:
        def get_html_string(self):
            return "<div>no runtime here</div>"

    _stub_streamlit(monkeypatch, with_iframe=True)
    monkeypatch.setattr(document, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(document.maidr, "render", lambda *a, **k: _Bare())

    library = document.__file__

    for call in (
        lambda: maidr_html(bar_axes, use_cdn=False),
        lambda: render_maidr(bar_axes, use_cdn=False),
    ):
        with pytest.warns(UserWarning, match="no source for maidr.js") as caught:
            call()
        assert (
            caught[0].filename != library
        ), f"warning was blamed on the library itself, at line {caught[0].lineno}"
        assert caught[0].filename == __file__


def test_an_unrelated_cdn_script_does_not_vouch_for_maidr(bar_axes, monkeypatch):
    """A Plotly chart always carries ``cdn.plot.ly``; that is not maidr.

    Asking only whether *some* ``<script>`` and *some* ``src=`` appear is
    answered "yes" by every Plotly chart, so a Plotly render whose bundle
    could not be read would have had its no-runtime warning suppressed by a
    script tag belonging to a different library.
    """

    class _PlotlyOnly:
        def get_html_string(self):
            return (
                '<div><script src="https://cdn.plot.ly/plotly-2.min.js">'
                "</script><div>chart</div></div>"
            )

    monkeypatch.setattr(document, "inline_bundle_tags", lambda: None)
    monkeypatch.setattr(document.maidr, "render", lambda *a, **k: _PlotlyOnly())

    with pytest.warns(UserWarning, match="no source for maidr.js"):
        maidr_html(bar_axes, use_cdn=False)


@pytest.mark.parametrize("use_cdn", [True, "auto"])
def test_a_normal_render_is_recognized_as_having_a_runtime(bar_axes, use_cdn):
    """The runtime check must not fire on the ordinary path.

    matplotlib and Plotly build the script element in JavaScript, so the
    markup carries no ``<script src=...>`` tag for maidr at all -- only the
    URL. A tag-shaped check would call every normal render broken.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        maidr_html(bar_axes, use_cdn=use_cdn)
    assert not [w for w in caught if "no source for maidr.js" in str(w.message)]


def _run_smoke_app(monkeypatch):
    """Run the smoke app under Streamlit's own script runner.

    Returns the emitted ``IFrame`` proto.  Which of the two embedding APIs
    produced it depends on the installed Streamlit, and deliberately is not
    asserted here -- both marshal into the same proto, which is what lets
    one set of assertions cover both.
    """
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MAIDR_CDN_VERSION", "latest")
    app = pathlib.Path(__file__).parent / "apps" / "streamlit_smoke_app.py"
    at = AppTest.from_file(str(app), default_timeout=120).run()

    assert list(at.exception) == []

    frames = at.get("iframe")
    assert len(frames) == 1, f"expected one embed, got {len(frames)}"
    return frames[0].proto


def test_a_real_streamlit_app_embeds_the_chart_as_srcdoc(monkeypatch):
    """Drive the real Streamlit, not a stub, once end to end.

    The stubbed dispatch tests assert which function is called with which
    arguments; they cannot see what Streamlit then *does* with them. This
    is the check that the HTML really carries a self-contained document
    into the frame's ``srcdoc`` rather than being treated as a URL -- a
    mistake that would raise nothing in Python and show up only as a blank
    embed in a browser.

    Runs on whichever embedding API the installed Streamlit provides.
    ``st.iframe`` arrived in 1.56, and the extra allows 1.30, so on an
    older one this exercises the ``components.v1.html`` fallback instead --
    the path every user on a pre-1.56 Streamlit takes, and the one that had
    no end-to-end coverage at all while this test skipped itself there.
    """
    proto = _run_smoke_app(monkeypatch)

    assert not proto.src, "the HTML was treated as a URL, not as a document"
    assert proto.srcdoc, "no document reached the frame"
    # The chart and its runtime both have to survive the trip.
    assert "maidr=" in proto.srcdoc
    assert "cdn.jsdelivr.net/npm/maidr" in proto.srcdoc


def test_a_real_streamlit_app_leaves_tab_index_unset(monkeypatch):
    """``tab_index=None`` has to reach the frame as *absent*, not as 0.

    The two mean different things -- absent is the browser default, 0 makes
    the frame itself a tab stop ahead of the chart inside it -- and a
    protobuf scalar cannot tell them apart on its own. The field is
    declared with explicit presence, so ``HasField`` can; a Streamlit that
    dropped that would silently turn the default into an extra tab stop on
    every chart.
    """
    proto = _run_smoke_app(monkeypatch)

    assert proto.DESCRIPTOR.fields_by_name["tab_index"].has_presence, (
        "IFrame.tab_index lost explicit presence; unset is now "
        "indistinguishable from 0 and the default cannot be checked"
    )
    assert not proto.HasField("tab_index")


def test_tab_index_support_is_detected_on_the_real_streamlit():
    """Probe the installed function, not only hand-written stubs.

    Streamlit wraps ``components.v1.html`` in a deprecation decorator. If
    that wrapper did not carry ``__wrapped__``, ``inspect.signature`` would
    report the wrapper's own ``(*args, **kwargs)`` and the probe would call
    a version that supports ``tab_index`` too old for it -- warning falsely
    and dropping the argument. The stubs cannot catch that; only the real
    function can.
    """
    pytest.importorskip("streamlit")
    import streamlit.components.v1 as components

    from maidr.widget.streamlit import _accepts

    # Whatever the answer, it must be the true one for this install.
    expected = "tab_index" in inspect.signature(components.html).parameters
    assert _accepts(components.html, "tab_index") is expected
    assert hasattr(
        components.html, "__wrapped__"
    ), "streamlit stopped wrapping components.html; re-check the probe"
    assert expected is True, "this streamlit should support tab_index"


@pytest.mark.parametrize(
    ("url", "is_maidr"),
    [
        ("https://cdn.jsdelivr.net/npm/maidr@4.3.0/dist/maidr.js", True),
        ("https://cdn.jsdelivr.net/npm/maidr@latest/dist/vegalite.js", True),
        # The near-misses: a package whose name merely ends in "maidr",
        # and an unrelated library's CDN tag.
        ("https://cdn.example/notmaidr@1.0.0/dist/notmaidr.js", False),
        ("https://cdn.plot.ly/plotly-2.min.js", False),
    ],
)
def test_only_a_maidr_package_url_counts_as_a_runtime(url, is_maidr):
    """The runtime check names the package, not just the letters in it."""
    from maidr.widget._document import _references_maidr_runtime

    assert _references_maidr_runtime(f'<script src="{url}"></script>') is is_maidr


def test_the_resolved_mode_is_the_one_the_chart_was_built_with(bar_axes, monkeypatch):
    """``use_cdn`` is read once, not once here and again inside ``render``.

    ``set_use_cdn`` writes process-wide state and Streamlit runs sessions on
    separate threads, so reading it twice leaves a window where the inline
    decision is made against one answer and the chart built from another.
    """
    import maidr.widget.streamlit as widget

    seen = []
    real_render = document.maidr.render

    def spy(plot, use_cdn=None):
        seen.append(use_cdn)
        return real_render(plot, use_cdn=use_cdn)

    monkeypatch.setattr(document.maidr, "render", spy)
    monkeypatch.setattr(document.maidr, "get_use_cdn", lambda: "auto")

    widget.maidr_html(bar_axes)

    # Never ``None``: that would send ``render`` back to the shared default.
    assert seen == ["auto"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ModuleNotFoundError("No module named 'streamlit'", name="streamlit"),
            "maidr[streamlit]",
        ),
        # Streamlit's import chain reaches pyarrow, tornado, protobuf and
        # altair; a skew in any of them fails as a missing *name*, and
        # "install the extra" is the wrong answer for a package already
        # installed.
        (
            ImportError("cannot import name 'Foo' from 'pyarrow'"),
            "version skew",
        ),
    ],
)
def test_import_error_advice_matches_the_failure(
    bar_axes, monkeypatch, error, expected
):
    """ "Install the extra" is wrong advice for a package already installed."""
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("streamlit"):
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "streamlit", raising=False)
    monkeypatch.setattr(builtins, "__import__", failing_import)

    with pytest.raises(ImportError, match=re.escape(expected)):
        render_maidr(bar_axes, use_cdn=True)


# ---------------------------------------------------------------------------
# One render of a figure at a time (#454's lock, on this door)
# ---------------------------------------------------------------------------

#: Attributes that differ between two renders of the same chart by design --
#: fresh uuids per layer, and the timestamp matplotlib stamps into the SVG.
_VOLATILE_IN_SVG = re.compile(
    r'(\bid="[^"]*"|url\(#[^)]*\)|<dc:date>[^<]*</dc:date>'
    r'|xlink:href="#[^"]*"|maidr="[^"]*")'
)


def test_concurrent_renders_of_one_figure_agree():
    """Streamlit runs every session in its own thread; this door had no lock.

    ``savefig`` writes ``fig.dpi`` for its duration and restores it
    afterwards, so two renders of the **same** figure at once race on one
    mutable attribute and the loser draws the whole chart at the other
    call's dpi (#454). The Shiny renderer has held a per-figure lock since
    #504. Nothing held one here, and Streamlit is if anything more exposed:
    it runs each session's script on its own ScriptRunner thread, and
    ``@st.cache_resource`` is its documented way to share one object --
    a figure included -- across them.

    Measured on the shipped path before the fix: 1 of 30 concurrent renders
    came back as a complete, well-formed SVG of the same chart at the wrong
    scale, ``L 640 -134.4`` where every other render had ``L 460.8 0``. Not
    garbled markup and not an exception -- geometry is what the highlight
    overlay and the tactile export are positioned against, so a chart at
    72% scale is wrong in the modality a sighted reviewer checks least.

    Asserted as agreement between renders rather than against a fixed size,
    since the wrong-dpi output is internally consistent: it is only wrong
    relative to what every other render produced.

    The barrier synchronises the *start*, not the duration, so on a runner
    slow enough that each render finishes before the next thread is
    scheduled this passes with a broken lock -- a false negative rather
    than CI noise. Measured 10 of 10 runs mismatching with the lock
    removed and 10 of 10 identical with it.
    """
    import threading

    fig, ax = plt.subplots()
    ax.bar([str(i) for i in range(30)], list(range(30)))

    outputs: list[str] = []
    failures: list[Exception] = []
    # One constant for the barrier and the thread count, because they must
    # agree: a barrier expecting more arrivals than there are threads waits
    # forever (#506).
    workers = 6
    start = threading.Barrier(workers)

    def render() -> None:
        try:
            start.wait(timeout=30)
            outputs.append(_VOLATILE_IN_SVG.sub("", maidr_html(ax, use_cdn=True)))
        except Exception as error:  # noqa: BLE001 - re-raised after the join
            failures.append(error)

    threads = [threading.Thread(target=render, daemon=True) for _ in range(workers)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive(), "a render deadlocked on the lock"
    finally:
        plt.close(fig)

    assert not failures, failures
    assert len(outputs) == workers
    assert all(output == outputs[0] for output in outputs), (
        "concurrent renders of one figure disagree; they race on fig.dpi "
        "and one of them emits the chart at the wrong scale"
    )


def test_an_axes_less_current_figure_is_still_resolved_only_once(monkeypatch):
    """``maidr_html()`` resolves the current figure once, whatever it holds.

    ``plt.gcf()`` is process-global, so a call that resolved it twice
    could render a different figure than the one it started with, if
    another thread's ``plt.figure()`` landed between the two. This door
    resolved separately for its own lock until #532 and had to be fixed
    for exactly that; the lock is now taken in the core render path, so
    ``render`` is the only thing that resolves.

    Kept as a counter rather than a race: one ``plt.gcf()`` for the whole
    call, however few axes the figure has. A door that started resolving
    on its own account again would show up here.
    """
    import matplotlib.pyplot as pyplot

    plt.figure()  # current, and deliberately empty
    calls: list[int] = []
    real_gcf = pyplot.gcf

    def counting_gcf():
        calls.append(1)
        return real_gcf()

    monkeypatch.setattr(pyplot, "gcf", counting_gcf)
    try:
        # A figure with no axes used to raise out of the entry point; since
        # #694 it reaches the same warn-and-fall-back path as a figure with
        # an empty axes. What comes out is not the point -- the count is.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            maidr_html(use_cdn=True)
    finally:
        monkeypatch.setattr(pyplot, "gcf", real_gcf)
        plt.close("all")

    assert calls == [1], f"the current figure was resolved {len(calls)} times"


# ---------------------------------------------------------------------------
# The current-figure default (#713)
# ---------------------------------------------------------------------------


def test_no_plot_warns_and_blames_the_caller(bar_axes, monkeypatch):
    """Rendering with no plot still works, and says what it fell back on.

    ``plt.gcf()`` is process-global and Streamlit runs each session on its
    own thread, so a render that resolves it can serve one session another
    session's chart -- silently, since the render succeeds.  The default
    is kept, because it is ``maidr.render``'s and scripts rely on it, but
    it is not kept quiet.  Both entry points, because they sit at
    different call depths and the warning has to land on the user's line
    from either.
    """
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)
    # ``bar_axes`` is what makes there be a current figure to fall back to.
    assert plt.gcf() is bar_axes.figure

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        html = maidr_html(use_cdn=True)
    fallbacks = [w for w in caught if "current figure" in str(w.message)]
    assert len(fallbacks) == 1, [str(w.message) for w in caught]
    assert issubclass(fallbacks[0].category, UserWarning)
    assert (
        fallbacks[0].filename == __file__
    ), f"warning was blamed on {fallbacks[0].filename}, not the caller"
    # The default still renders the current figure; the warning is not a refusal.
    assert "maidr=" in html

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_maidr(use_cdn=True)
    fallbacks = [w for w in caught if "current figure" in str(w.message)]
    assert len(fallbacks) == 1, [str(w.message) for w in caught]
    assert (
        fallbacks[0].filename == __file__
    ), f"warning was blamed on {fallbacks[0].filename}, not the caller"
    assert "maidr=" in st.iframe.calls[0][0][0]


def test_an_explicit_plot_does_not_warn(bar_axes):
    """The warning is about the fallback, not about rendering."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        maidr_html(bar_axes, use_cdn=True)
    assert not [w for w in caught if "current figure" in str(w.message)]


# ---------------------------------------------------------------------------
# The same chart is the same string on every rerun (#460)
# ---------------------------------------------------------------------------

#: A uuid, the shape of the ids py-maidr mints.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _bar(ax):
    ax.bar(["a", "b"], [1, 2])
    ax.set_title("Sales by region")


def _line_and_scatter(ax):
    ax.plot([1, 2, 3], [1, 3, 2])
    ax.scatter([1, 2, 3], [3, 1, 2])


def _box(ax):
    ax.boxplot([[1, 2, 3, 9], [4, 5, 6]])


def _heat(ax):
    import seaborn as sns

    sns.heatmap([[1, 2, 3], [4, 5, 6]], ax=ax)


def _violin(ax):
    import seaborn as sns

    sns.violinplot(x=[1, 2, 2, 3, 5], ax=ax)


def _hatched_bar(ax):
    ax.bar(["a", "b"], [1, 2], hatch="//")


def _imshow(ax):
    ax.imshow([[1, 2, 3], [4, 5, 6]])


#: Between them, every kind of id a render mints: gids and selector ids,
#: schema ids in the SVG's attribute, and matplotlib's clip paths, markers,
#: path collections, hatches and images -- so a matplotlib release that
#: changes one of those prefixes fails here rather than in a reader's frame.
_CHARTS = [_bar, _line_and_scatter, _box, _heat, _violin, _hatched_bar, _imshow]


def _html_of(draw, use_cdn=True, **kwargs) -> str:
    """Build the chart ``draw`` describes on a new figure, as a rerun does."""
    fig, ax = plt.subplots()
    try:
        draw(ax, **kwargs)
        return maidr_html(ax, use_cdn=use_cdn)
    finally:
        plt.close(fig)


@pytest.mark.parametrize("draw", _CHARTS, ids=lambda draw: draw.__name__[1:])
def test_an_unchanged_chart_renders_to_the_same_string(draw):
    """What keeps Streamlit from reloading the frame on an unrelated rerun.

    Streamlit reruns the script on every widget interaction and gives the
    frame whatever this returned; a different string reloads it, and a
    reader inside is dropped with nothing said. Every render used to differ
    -- fresh uuids, a random matplotlib hash salt, a timestamp -- so every
    rerun did that. ``tests/browser/test_streamlit_rerun.py`` drives the
    consequence in a browser.

    Built on a new figure each time, as a rerun builds it, rather than one
    figure rendered twice, which would share the gids its first render set.
    """
    assert _html_of(draw) == _html_of(draw)


def test_the_offline_embed_is_the_same_string_too():
    """The bundle is inlined after the ids are settled, not serialized over them."""
    first = _html_of(_bar, use_cdn=False)
    assert _BUNDLE_HEAD in first
    assert first == _html_of(_bar, use_cdn=False)


def test_render_maidr_hands_streamlit_the_same_string_twice(monkeypatch):
    """The entry point most apps call, not only the string one."""
    st, _v1 = _stub_streamlit(monkeypatch, with_iframe=True)

    for _ in range(2):
        fig, ax = plt.subplots()
        _bar(ax)
        render_maidr(ax, use_cdn=True)
        plt.close(fig)

    (first, _), (second, _) = st.iframe.calls
    assert first == second


def test_a_changed_chart_is_a_different_string_with_different_ids():
    """The frame must still be rebuilt when the chart itself changed.

    And its ids change with it: they are derived from the chart, so two
    different charts do not share one.
    """

    def bars(ax, heights):
        ax.bar(["a", "b"], heights)

    before = _html_of(bars, heights=[1, 2])
    after = _html_of(bars, heights=[1, 3])

    assert before != after
    assert not set(_UUID.findall(before)) & set(_UUID.findall(after))


#: Every id a render mints: py-maidr's uuids, and matplotlib's clip paths,
#: markers, hatches, path collections and images.
_MINTED_IDS = re.compile(
    rf"{_UUID.pattern}"
    r"|\b(?:[hpm]|(?:Im_)?image|C[0-9a-f]+_[0-9a-f]+_)[0-9a-f]{10}\b"
)


def _shape(html: str) -> str:
    """The document with each id replaced by the order it first appears in."""
    seen: dict = {}
    html = re.sub(r"\s*<dc:date>[^<]*</dc:date>", "", html)
    return _MINTED_IDS.sub(
        lambda m: f"<{seen.setdefault(m.group(0), len(seen))}>", html
    )


def _raw_and_stable(plot) -> tuple[str, str]:
    """One render as ``maidr.render`` gives it, and as this module passes it on."""
    import maidr
    from maidr.widget._document import _stable_ids

    raw = str(maidr.render(plot, use_cdn=True).get_html_string())
    return raw, _stable_ids(raw)


def _assert_renamed_one_for_one(raw: str, stable: str) -> None:
    """Every minted id renamed, each everywhere it occurs, no two into one."""
    assert _shape(stable) == _shape(raw)
    assert len(set(_MINTED_IDS.findall(stable))) == len(set(_MINTED_IDS.findall(raw)))
    assert not set(_MINTED_IDS.findall(stable)) & set(_MINTED_IDS.findall(raw))


@pytest.mark.parametrize("draw", _CHARTS, ids=lambda draw: draw.__name__[1:])
def test_ids_are_renamed_one_for_one(draw):
    """Ids distinct in the document stay distinct, and keep their references.

    A selector names its layer's elements by id, and a ``url(#...)`` points
    at a clip path: renaming is only safe if every occurrence of an id
    becomes the same new id and no two ids become one. An occurrence missed
    would leave a reference to an id that no longer exists -- a highlight
    that silently lands nowhere.
    """
    fig, ax = plt.subplots()
    try:
        draw(ax)
        raw, stable = _raw_and_stable(ax)
    finally:
        plt.close(fig)

    _assert_renamed_one_for_one(raw, stable)


def test_a_uuid_in_the_charts_own_data_is_left_alone():
    """Only ids a render minted are renamed, never a value shaped like one.

    An order id on a category axis is data: renaming it would have the
    reader hear a different id from the one drawn.
    """
    order_id = "123e4567-e89b-42d3-a456-426614174000"

    def orders(ax):
        ax.bar([order_id, "other"], [1, 2])
        ax.set_title(order_id)

    html = _html_of(orders)

    assert html == _html_of(orders)
    # The category and the title in the schema, and the drawn title and
    # tick label in the SVG's comments.
    assert html.count(order_id) >= 3


def test_the_svg_timestamp_is_not_emitted():
    """matplotlib stamps the time it wrote the SVG, to the microsecond."""
    assert "<dc:date>" not in _html_of(_bar)


def test_an_altair_chart_renders_to_the_same_string():
    """Its one minted id carries a ``maidr-`` prefix, so it is renamed too."""
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")

    def chart() -> str:
        data = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
        return maidr_html(alt.Chart(data).mark_bar().encode(x="a", y="b"), use_cdn=True)

    assert chart() == chart()


def test_an_altair_datasets_id_column_is_left_alone():
    """Why an ``id`` key in raw JSON is never taken as minted by its shape.

    Altair inlines the whole DataFrame, so a column named ``id`` of uuids
    lands in the page as uuids under an ``id`` key -- where a Plotly
    schema's ids sit too. Only the schema py-maidr wrote is read for those.
    """
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    order_ids = [
        "123e4567-e89b-42d3-a456-426614174000",
        "9b2f4c1e-7d3a-4e8b-a1c2-3d4e5f607182",
    ]

    def chart():
        data = pd.DataFrame({"id": order_ids, "b": [1, 2]})
        return alt.Chart(data).mark_bar().encode(x="id", y="b")

    raw, stable = _raw_and_stable(chart())

    assert maidr_html(chart(), use_cdn=True) == maidr_html(chart(), use_cdn=True)
    for order_id in order_ids:
        assert stable.count(order_id) == raw.count(order_id) >= 1


def _plotly_bar(heights=(1, 2)):
    go = pytest.importorskip("plotly.graph_objects")
    fig = go.Figure(go.Bar(x=["a", "b"], y=list(heights)))
    fig.update_layout(title="Sales by region")
    return fig


def _plotly_grid():
    """Two subplots of a 2x2 grid: each names its ``axes_<uuid>``, two are gaps."""
    go = pytest.importorskip("plotly.graph_objects")
    subplots = pytest.importorskip("plotly.subplots")
    fig = subplots.make_subplots(rows=2, cols=2)
    fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[3, 1, 2]), row=2, col=2)
    return fig


_PLOTLY_CHARTS = [_plotly_bar, _plotly_grid]


@pytest.mark.parametrize("build", _PLOTLY_CHARTS, ids=["bar", "grid"])
@pytest.mark.parametrize("use_cdn", [True, False], ids=["cdn", "offline"])
def test_an_unchanged_plotly_chart_renders_to_the_same_string(build, use_cdn):
    """Plotly's schema ids are raw JSON, found by parsing the schema itself."""
    assert maidr_html(build(), use_cdn=use_cdn) == maidr_html(build(), use_cdn=use_cdn)


@pytest.mark.parametrize("build", _PLOTLY_CHARTS, ids=["bar", "grid"])
def test_plotly_ids_are_renamed_one_for_one(build):
    """The chart's div, and every figure, subplot, layer and ``axes_`` id."""
    raw, stable = _raw_and_stable(build())
    _assert_renamed_one_for_one(raw, stable)


def test_a_changed_plotly_chart_is_a_different_string_with_different_ids():
    """A new chart must still reach the reader, under ids of its own."""
    before = maidr_html(_plotly_bar((1, 2)), use_cdn=True)
    after = maidr_html(_plotly_bar((1, 3)), use_cdn=True)

    assert before != after
    assert not set(_UUID.findall(before)) & set(_UUID.findall(after))


def test_a_uuid_in_a_plotly_figures_own_json_is_left_alone():
    """The figure's ``meta`` has an ``id`` key too; it is the user's, not ours.

    It sits in raw JSON a few lines from the schema's, which is why the
    schema is parsed rather than matched.
    """
    order_id = "123e4567-e89b-42d3-a456-426614174000"

    def chart():
        fig = _plotly_bar()
        fig.update_layout(title=order_id, meta={"id": order_id})
        fig.update_traces(x=[order_id, "other"])
        return fig

    raw, stable = _raw_and_stable(chart())

    assert maidr_html(chart(), use_cdn=True) == maidr_html(chart(), use_cdn=True)
    assert re.search(rf'"meta":\s*\{{"id":\s*"{order_id}"\}}', stable)
    # Wherever it was -- the figure's category, title and ``meta``, and the
    # schema's category and title -- it still is.
    assert stable.count(order_id) == raw.count(order_id) >= 5


def test_a_bokeh_chart_is_renamed_consistently_if_not_stably():
    """Bokeh is not made stable, but what is renamed must not break it.

    Its model ids come from a process-wide counter and are referenced from
    Bokeh's document and from the highlight map in several shapes, beside
    data that can hold the same strings, so they are left alone and the
    chart is rebuilt on a rerun as before. Its wrapper's id is minted by
    py-maidr with a ``maidr-`` prefix and is renamed, and every reference
    to it has to follow.
    """
    plotting = pytest.importorskip("bokeh.plotting")
    plot = plotting.figure(title="t")
    plot.line([1, 2, 3], [1, 3, 2])

    raw, stable = _raw_and_stable(plot)
    wrapper = re.search(rf"maidr-bokeh-({_UUID.pattern})", raw)

    assert wrapper is not None, "the Bokeh wrapper's id changed shape"
    assert wrapper.group(1) not in stable
    assert _shape(stable) == _shape(raw)

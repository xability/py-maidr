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
    assert "cdn.jsdelivr" in proto.srcdoc


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

    from maidr.widget.streamlit import _accepts_tab_index

    # Whatever the answer, it must be the true one for this install.
    expected = "tab_index" in inspect.signature(components.html).parameters
    assert _accepts_tab_index(components.html) is expected
    assert hasattr(components.html, "__wrapped__"), (
        "streamlit stopped wrapping components.html; re-check the probe"
    )
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
    from maidr.widget.streamlit import _references_maidr_runtime

    assert _references_maidr_runtime(f'<script src="{url}"></script>') is is_maidr


def test_the_resolved_mode_is_the_one_the_chart_was_built_with(bar_axes, monkeypatch):
    """``use_cdn`` is read once, not once here and again inside ``render``.

    ``set_use_cdn`` writes process-wide state and Streamlit runs sessions on
    separate threads, so reading it twice leaves a window where the inline
    decision is made against one answer and the chart built from another.
    """
    import maidr.widget.streamlit as widget

    seen = []
    real_render = widget.maidr.render

    def spy(plot, use_cdn=None):
        seen.append(use_cdn)
        return real_render(plot, use_cdn=use_cdn)

    monkeypatch.setattr(widget.maidr, "render", spy)
    monkeypatch.setattr(widget.maidr, "get_use_cdn", lambda: "auto")

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
    """"Install the extra" is wrong advice for a package already installed."""
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


def test_the_current_figure_is_resolved_once_and_rendered(monkeypatch):
    """``maidr_html()`` locks the figure it renders, not whichever is current
    a moment later.

    ``plt.gcf()`` is process-global. Resolving it separately for the lock
    and for the render leaves a window in which another thread's
    ``plt.figure()`` moves the current figure between the two, so the lock
    guards one figure while the render writes another -- synchronised in
    appearance only. Raised in review of #531.

    Driven by moving the current figure *between* the two resolutions,
    which is the interleaving a second thread would produce.
    """
    import maidr.widget.streamlit as streamlit_module

    mine, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    locked: list[object] = []
    real_lock = streamlit_module.figure_lock

    def lock_and_move(figure):
        locked.append(figure)
        # What another thread plotting concurrently would do.
        plt.figure()
        return real_lock(figure)

    monkeypatch.setattr(streamlit_module, "figure_lock", lock_and_move)
    try:
        html = maidr_html(use_cdn=True)
    finally:
        plt.close("all")

    assert locked == [mine], "locked a different figure than the current one"
    # The chart rendered is the one that was locked: two bars, not an empty
    # figure. `_flatten_maidr` puts the data in the root `maidr` attribute.
    assert '&quot;y&quot;: 2' in html or '"y": 2' in html, html[:200]

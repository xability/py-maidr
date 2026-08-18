"""Tests for the Shiny integration in ``maidr.widget.shiny``.

These drive the renderer the way Shiny does -- ``_render(renderer)``
inside a session context -- without starting a server.
"""

from __future__ import annotations

import asyncio
import gc
import re
import sys
import threading
import time
import warnings
import weakref
from html import unescape

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

shiny = pytest.importorskip("shiny")

from shiny import module  # noqa: E402
from shiny.render import ui as render_ui  # noqa: E402
from shiny.render.renderer import Renderer  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.dependencies import read_bundled_js  # noqa: E402
from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

#: A slice of the real bundle, so "is the bundle inlined?" is answered by
#: looking for the bundle rather than by a size threshold that a large
#: enough chart could cross on its own.
_BUNDLE_HEAD = read_bundled_js()[:200]


def _bar_axes():
    """Return the axes of a freshly created two-bar chart."""
    _, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return ax


def _render(renderer):
    """Drive a renderer the way Shiny does.

    ``asyncio.run`` copies the current context, so the session installed by
    the ``fake_session`` fixture is visible inside the coroutine.  The
    suite already uses this shape in ``tests/core/test_cdn_event_loop.py``
    rather than taking on a pytest-asyncio dependency.
    """
    return asyncio.run(renderer.render())


def _iframe_document(html: str) -> str:
    """Return the srcdoc of an iframe payload, or the payload itself."""
    match = re.search(r'srcdoc="(.*?)"\s+width', html, re.S)
    return unescape(match.group(1)) if match else html


@pytest.fixture(autouse=True)
def _clean_figures():
    """Leave no figures or FigureManager entries behind between tests."""
    plt.close("all")
    FigureManager.figs.clear()
    yield
    plt.close("all")
    FigureManager.figs.clear()


# ---------------------------------------------------------------------------
# Renderer contract
# ---------------------------------------------------------------------------


def test_render_maidr_subclasses_renderer_not_a_concrete_renderer():
    """The documented base is ``Renderer``, not another renderer."""
    assert Renderer in render_maidr.__mro__
    assert render_ui not in render_maidr.__mro__


def test_render_maidr_implements_render_and_leaves_transform_alone():
    """``render`` is overridden; ``transform`` is not, so only one is in play."""
    assert "render" in render_maidr.__dict__
    assert "transform" not in render_maidr.__dict__


def test_bare_and_parenthesised_decoration_both_register(fake_session):
    """Both decorator spellings produce a registered renderer."""

    @render_maidr
    def bare():
        return _bar_axes()

    @render_maidr()
    def parenthesised():
        return _bar_axes()

    assert bare.output_id == "bare"
    assert parenthesised.output_id == "parenthesised"
    assert fake_session.outputs == [bare, parenthesised]


def test_options_are_accepted(fake_session):
    """The renderer takes options; previously any keyword was a TypeError."""

    @render_maidr(width="42px", height="7em", use_cdn=True)
    def sized():
        return _bar_axes()

    assert (sized.width, sized.height, sized.use_cdn) == ("42px", "7em", True)


def test_auto_output_ui_delegates_to_output_maidr(fake_session):
    """Express mode places a container carrying the configured size."""

    @render_maidr(width="42px", height="7em")
    def sized():
        return _bar_axes()

    rendered = str(sized.auto_output_ui())
    assert 'id="sized"' in rendered
    assert "width: 42px" in rendered
    assert "height: 7em" in rendered


def test_output_args_reaches_the_container(fake_session):
    """``@output_args`` is Shiny's documented way to size an Express output.

    Shiny splats it into ``auto_output_ui``, so a renderer that takes no
    keywords there raises ``TypeError`` -- which is what this one did, and
    is why ``shiny.render.plot`` accepts ``**kwargs``.  Driven through
    ``_render_auto_output_ui`` rather than ``auto_output_ui`` directly,
    since that splat is the step being tested.
    """
    from shiny.express import output_args

    @output_args(width="50%")
    @render_maidr(width="42px", height="7em")
    def sized():
        return _bar_axes()

    rendered = str(sized._render_auto_output_ui())
    assert "width: 50%" in rendered
    # Unmentioned arguments still come from the decorator: `@output_args`
    # overrides, it does not reset.
    assert "height: 7em" in rendered


def test_an_unknown_output_arg_names_the_ui_function(fake_session):
    """Forwarded rather than swallowed, so a typo is not silence.

    ``output_maidr`` takes a deliberately narrow set of arguments, and a
    keyword it does not know is a mistake worth raising -- an
    ``**kwargs``-absorbing container would drop it on the floor.
    """
    from shiny.express import output_args

    @output_args(not_an_argument=1)
    @render_maidr
    def sized():
        return _bar_axes()

    with pytest.raises(TypeError, match="output_maidr"):
        sized._render_auto_output_ui()


def test_output_maidr_applies_module_namespacing():
    """A module's output id is namespaced, so modules keep working."""
    with module.namespace_context("mod1"):
        assert 'id="mod1-my_plot"' in str(output_maidr("my_plot"))


# ---------------------------------------------------------------------------
# Rendered payload
# ---------------------------------------------------------------------------


def test_payload_has_the_shape_shiny_expects(fake_session):
    """``_process_ui`` returns ``{"deps", "html"}``; fail loudly if that moves."""

    @render_maidr
    def chart():
        return _bar_axes()

    payload = _render(chart)
    assert set(payload) == {"deps", "html"}


def test_the_payload_carries_the_focus_restore_script(fake_session):
    """Every render ships the hook that survives a re-render (#484).

    Shiny replaces the output container on each reactive flush, taking the
    focused element with it, which drops a reader out of the chart they
    were navigating. The script rides with the chart rather than with the
    container because ``output_maidr`` is not always what places the
    output -- Express mode goes through ``auto_output_ui``, and an app may
    write its own ``ui.output_ui`` -- but every chart comes through the
    renderer.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "__maidrShinyFocusRestore" in html


def test_the_rendered_iframe_is_marked_as_maidrs_own(fake_session):
    """The focus script must be able to tell our frame from anyone else's.

    Keying off a bare ``iframe`` would let the restore force focus onto an
    unrelated embed an app happened to put in the same output container.
    The marker is what makes the selector precise, so both sides of it are
    pinned here.
    """
    from maidr.widget._focus import FOCUS_RESTORE_JS

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "data-maidr-chart" in html
    assert "data-maidr-chart" in FOCUS_RESTORE_JS


def test_the_container_class_the_focus_script_looks_for_still_exists():
    """The script finds its container by a Shiny-internal class.

    ``.shiny-html-output`` is an implementation detail of
    ``ui.output_ui``, not a documented contract. If Shiny renames it, the
    script finds no containers and the fix goes silently inert -- no
    exception, no warning, and the only thing that would notice is the
    browser suite, which is opt-in and so not what a contributor runs.

    This ties the two sides together in the default suite, so a Shiny
    upgrade that moves the class fails here instead.
    """
    from maidr.widget._focus import FOCUS_RESTORE_JS

    assert "shiny-html-output" in FOCUS_RESTORE_JS
    assert "shiny-html-output" in str(output_maidr("chart"))


def test_the_focus_script_only_installs_once_per_page(fake_session):
    """It arrives on every render, so it has to be idempotent.

    Without the guard, N flushes would leave N samplers and N observers
    running, each restoring focus -- the cost of shipping it per render
    rather than per container.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "if (window.__maidrShinyFocusRestore) return;" in html


@pytest.mark.parametrize(
    ("use_cdn", "expect_cdn", "expect_inline_bundle"),
    [(True, True, False), ("auto", True, False), (False, False, True)],
)
def test_each_cdn_mode_ships_the_source_it_promises(
    fake_session, use_cdn, expect_cdn, expect_inline_bundle
):
    """Every mode must put a real source for maidr.js in the document.

    Regression test for the silent failure this replaces: an iframed
    ``use_cdn=False`` render emitted neither a script tag nor the bundle,
    so the chart arrived as a picture with no sonification, no braille and
    no keyboard navigation -- and no error to say so.

    Each mode is asserted exactly rather than as a disjunction. A single
    "some source is present" check would pass on the wrong source, and it
    would hide that ``payload["deps"]`` is always empty here -- the iframe
    wrapper serialises with ``Tag.get_html_string()``, which drops
    ``HTMLDependency`` children, which is the whole reason the bundle has
    to travel inline.

    ``"auto"`` is expected NOT to inline: it loads from the CDN, and its
    client-side offline fallback cannot resolve inside a ``srcdoc``
    iframe. ``use_cdn=False`` is the setting for an air-gapped app.
    """

    @render_maidr(use_cdn=use_cdn)
    def chart():
        return _bar_axes()

    payload = _render(chart)
    document = _iframe_document(payload["html"])

    assert payload["deps"] == [], "an iframed render cannot carry dependencies"
    assert ("cdn.jsdelivr" in document) is expect_cdn
    assert (_BUNDLE_HEAD in document) is expect_inline_bundle


# ---------------------------------------------------------------------------
# Value handling
# ---------------------------------------------------------------------------


def test_none_renders_nothing(fake_session):
    """Returning ``None`` leaves the output blank, per the Renderer contract."""

    @render_maidr
    def blank():
        return None

    assert _render(blank) is None


@pytest.mark.parametrize(
    ("value", "type_name"),
    [
        ("not a plot", "str"),
        (42, "int"),
        # ``FigureManager.get_axes`` is a resolver, not a validator. An
        # empty container makes it raise a bare ``StopIteration``, which
        # the async render turns into ``RuntimeError: coroutine raised
        # StopIteration``; a list of non-artists makes it raise
        # ``AttributeError``. Both used to escape as themselves.
        ([], "list"),
        ({}, "dict"),
        ([1, 2], "list"),
    ],
)
def test_unsupported_return_value_names_the_function_and_the_type(
    fake_session, value, type_name
):
    """The error says what came back and from where, whatever came back."""

    @render_maidr
    def wrong():
        return value

    with pytest.raises(TypeError, match=rf"'wrong'.*\b{type_name}\b"):
        _render(wrong)


# ---------------------------------------------------------------------------
# Figure lifetime
# ---------------------------------------------------------------------------


def test_repeated_renders_do_not_accumulate_open_figures(fake_session):
    """A figure per flush must not stay open for the life of the app.

    Twenty-five is past matplotlib's ``figure.max_open_warning``, so
    before this the suite itself would have shown the warning an app
    would.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    for _ in range(25):
        _render(chart)

    assert plt.get_fignums() == []


def test_figures_are_closed_even_when_rendering_fails(fake_session, monkeypatch):
    """A failed render must not leak the figure it opened."""
    import maidr.widget.shiny as widget

    def boom(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(widget.maidr, "render", boom)

    @render_maidr
    def chart():
        return _bar_axes()

    with pytest.raises(RuntimeError):
        _render(chart)

    assert plt.get_fignums() == []


def test_a_figure_the_app_owns_is_left_open_and_still_accessible(fake_session):
    """Only figures this render opened are closed.

    An app that builds one figure at module scope and returns it on every
    flush must keep working.  Closing it would drop its
    :class:`FigureManager` entry, and the next render would quietly fall
    back to a static image -- an accessible chart turning into a picture.
    """
    ax = _bar_axes()
    opened_before = plt.get_fignums()

    @render_maidr
    def chart():
        return ax

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(3):
            _render(chart)

    assert plt.get_fignums() == opened_before
    assert not [w for w in caught if "not yet supported" in str(w.message)]


def test_a_figure_built_lazily_and_cached_stays_accessible(fake_session):
    """The ``@reactive.calc`` shape: built on the first flush, reused after.

    This figure IS new during the first render, so anything that treats
    "not open beforehand" as "safe to forget" will drop maidr's record of
    it. Every later flush then renders a static image instead of a chart,
    with only a server-side warning to show for it -- which is the failure
    this whole cleanup path exists to avoid, not to cause.
    """
    cached = []

    @render_maidr
    def chart():
        if not cached:
            cached.append(_bar_axes())
        return cached[0]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        documents = [_iframe_document(_render(chart)["html"]) for _ in range(3)]

    assert not [w for w in caught if "not yet supported" in str(w.message)]
    for index, document in enumerate(documents):
        # ``subplots`` is a key of the MAIDR schema, so it is present only
        # while maidr still holds the data it extracted at plotting time.
        # The static-image fallback carries an ``<img>`` and no schema.
        assert "subplots" in document, f"render {index} lost the MAIDR schema"
        assert "<img" not in document, f"render {index} fell back to an image"


# ---------------------------------------------------------------------------
# Import-time errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ModuleNotFoundError("No module named 'shiny'", name="shiny"), "maidr[shiny]"),
        # The skew this repository actually hit: shiny installed, but its
        # import chain reaches an htmltools too old to satisfy it.
        (
            ImportError("cannot import name 'TagifiedTag' from 'htmltools'"),
            "version skew",
        ),
    ],
)
def test_import_error_advice_matches_the_failure(monkeypatch, error, expected):
    """"Install the extra" is wrong advice for a package already installed."""
    import builtins
    import importlib

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("shiny"):
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    monkeypatch.delitem(sys.modules, "maidr.widget.shiny", raising=False)

    with pytest.raises(ImportError, match=re.escape(expected)):
        importlib.import_module("maidr.widget.shiny")


# ---------------------------------------------------------------------------
# Not holding the event loop (#454)
# ---------------------------------------------------------------------------


def test_each_figure_gets_its_own_lock_and_keeps_it():
    """Per figure, not process-wide, and stable across calls.

    A single shared lock would serialise unrelated sessions and give back
    most of what moving off the loop buys, since ``savefig`` on *distinct*
    figures is safe in parallel. A lock that differed per call would guard
    nothing at all.
    """
    from maidr.widget.shiny import _figure_lock

    first, _ = plt.subplots()
    second, _ = plt.subplots()
    try:
        assert _figure_lock(first) is _figure_lock(first), "must be stable"
        assert _figure_lock(first) is not _figure_lock(second), "must be per figure"
    finally:
        plt.close(first)
        plt.close(second)


def test_an_unresolvable_figure_gets_a_fresh_lock_rather_than_a_shared_one():
    """Sharing one lock among things we cannot tell apart invites a deadlock.

    The render is safe on its own -- only the lock's scope is lost -- so the
    fallback hands back an unshared lock rather than a sentinel-keyed one.
    """
    from maidr.widget.shiny import _figure_lock

    assert _figure_lock(None) is not _figure_lock(None)


def test_the_lock_does_not_keep_a_closed_figure_alive():
    """The map is weak-keyed, so it adds no retention of its own (#498).

    Worth pinning because a strong map keyed by figure is exactly the shape
    that kept every registered figure alive for the life of the process
    (#456), and this one is keyed the same way.
    """
    from matplotlib.figure import Figure
    from maidr.widget.shiny import _figure_lock

    # A bare `Figure`, deliberately not `plt.subplots()`, so that nothing
    # but the lock map can be the reason this passes or fails. When this was
    # written `FigureManager` retained every figure and a pyplot figure
    # failed here for that reason rather than the lock map's; that is fixed
    # now, and the isolation is still worth keeping.
    figure = Figure()
    _figure_lock(figure)
    ref = weakref.ref(figure)

    del figure
    gc.collect()

    assert ref() is None, "the lock map is keeping the figure alive"


def test_the_render_runs_off_the_event_loop(fake_session, monkeypatch):
    """The whole point of #454: ``maidr.render`` must not run on the loop.

    Asserted by identity of the running thread rather than by timing, which
    would be a flake on a loaded machine. ``asyncio.run`` drives the loop on
    *this* thread, so the render must land on a different one.

    Driven through ``_render`` rather than as an ``async def`` test: this
    suite has no ``pytest-asyncio``, and an ``async def`` here is collected,
    silently **skipped**, and reported as a pass. The first version of this
    test was exactly that -- it did not fail when the render was put back on
    the loop, because it never ran.
    """
    import maidr.widget.shiny as shiny_module

    loop_thread = threading.get_ident()
    seen: list[int] = []

    real_render = shiny_module.maidr.render

    def spy(value, **kwargs):
        seen.append(threading.get_ident())
        return real_render(value, **kwargs)

    monkeypatch.setattr(shiny_module.maidr, "render", spy)

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:

        @render_maidr
        def chart():
            return ax

        _render(chart)
    finally:
        plt.close(fig)

    assert seen, "the render never ran"
    assert loop_thread not in seen, (
        "maidr.render ran on the event loop's thread; every other session "
        "on that worker is blocked for its full duration"
    )


def test_two_renders_of_one_figure_do_not_overlap(monkeypatch):
    """The scenario this whole change exists to make safe.

    The unit tests above check that ``_figure_lock`` hands back matching
    objects; none of them shows that two renders actually serialise. That
    is the one thing a race here would break, so it is worth exercising
    end to end.

    Detects **overlap** rather than measuring duration, so it cannot flake
    into a false pass on a loaded machine: if the lock works, the second
    render cannot enter while the first is inside, at any speed. The sleep
    only widens the window a broken lock would have to miss.

    Overlapping renders are not a theoretical concern. ``savefig`` writes
    ``fig.dpi`` for the duration of the write, so the loser of that race
    emits a valid SVG of the whole chart at the wrong scale -- measured at
    460.8x345.6 for a 640x480 figure, on 1 of 6 concurrent attempts.
    """
    import maidr.widget.shiny as shiny_module

    inside = 0
    overlapped = False
    bookkeeping = threading.Lock()

    def slow_render(value, **kwargs):
        nonlocal inside, overlapped
        with bookkeeping:
            inside += 1
            if inside > 1:
                overlapped = True
        time.sleep(0.05)
        with bookkeeping:
            inside -= 1
        return "rendered"

    monkeypatch.setattr(shiny_module.maidr, "render", slow_render)

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:
        renderer = render_maidr(lambda: ax)
        workers = [
            threading.Thread(target=renderer._render_off_loop, args=(ax,))
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            # Bounded: an unbounded join turns a broken lock into a hung
            # suite rather than a failed test (#506).
            worker.join(timeout=60)
            assert not worker.is_alive(), "a render deadlocked on the lock"
    finally:
        plt.close(fig)

    assert not overlapped, (
        "two renders of the same figure ran at once; they race on fig.dpi "
        "and one of them emits the chart at the wrong scale"
    )


def test_a_value_that_resolves_to_no_figure_still_renders(fake_session, monkeypatch):
    """The fallback branch, driven through the real path rather than alone.

    ``test_an_unresolvable_figure_gets_a_fresh_lock_...`` calls
    ``_figure_lock(None)`` directly, which shows the helper's behaviour and
    not that anything reaches it. This goes through ``render()``.

    Both shapes are covered because they are not the same shape, which an
    earlier comment in ``_render_off_loop`` got wrong: a foreign figure
    **returns** ``None`` from ``get_axes`` and never raises, while an empty
    container raises ``StopIteration``. Only the second reaches the
    ``except``; the first is handled by the ``getattr`` default.
    """
    import maidr.widget.shiny as shiny_module

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    monkeypatch.setattr(shiny_module.maidr, "render", lambda value, **kw: "rendered")
    monkeypatch.setattr(shiny_module, "_check_supported", lambda value, name: None)
    try:
        for resolver, label in (
            (lambda value: None, "returns None, as a foreign figure does"),
            (lambda value: next(iter([])), "raises, as an empty container does"),
        ):
            monkeypatch.setattr(
                shiny_module.FigureManager, "get_axes", staticmethod(resolver)
            )

            @render_maidr
            def chart():
                return ax

            assert _render(chart) is not None, label
    finally:
        plt.close(fig)


def test_an_unexpected_resolver_failure_is_logged_not_swallowed(
    fake_session, monkeypatch, caplog
):
    """A bug in ``get_axes`` must not vanish into "lock scope lost".

    The catch sits immediately before an unsynchronised render, so a real
    failure there is worth a record. It was a bare ``except Exception``
    with no logging until review of #504.
    """
    import logging

    import maidr.widget.shiny as shiny_module

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    monkeypatch.setattr(shiny_module.maidr, "render", lambda value, **kw: "rendered")
    monkeypatch.setattr(shiny_module, "_check_supported", lambda value, name: None)
    monkeypatch.setattr(
        shiny_module.FigureManager,
        "get_axes",
        staticmethod(lambda value: (_ for _ in ()).throw(AttributeError("boom"))),
    )
    try:
        with caplog.at_level(logging.DEBUG, logger=shiny_module.__name__):

            @render_maidr
            def chart():
                return ax

            _render(chart)
    finally:
        plt.close(fig)

    assert any("without a shared lock" in record.message for record in caplog.records)


def test_two_different_figures_rendering_at_once_keep_their_selectors():
    """The per-figure lock does not cover process-global highlight state.

    ``HighlightContextManager`` carries a render's element-to-selector
    wiring, and the artist ``draw`` methods and ``XMLWriter.start`` are
    patched *class-wide*, so every render in the process reads it while
    ``savefig`` walks its figure. A lock keyed by figure deliberately does
    not serialise **distinct** figures -- that parallelism is the point of
    rendering off the loop -- so nothing stopped two renders from
    overwriting each other's wiring.

    Measured with that state as plain class attributes: four concurrent
    renders of distinct figures went from 61 selectors each to
    ``[7, 1, 1, 1]``. Valid SVGs, with the interactive layer silently
    gone -- and only on concurrent traffic, so it would not reproduce from
    a bug report.

    Counts selectors rather than comparing whole documents, because ids
    are per-render uuids; the count is what goes missing.
    """
    from maidr.core.figure_manager import FigureManager

    def build():
        figure, axes = plt.subplots()
        axes.bar([str(i) for i in range(20)], list(range(1, 21)))
        return figure

    def selectors(figure):
        html = FigureManager.get_maidr(figure)._create_html_tag(
            use_iframe=False, use_cdn=True
        )
        return len(re.findall(r'maidr="[^"]+"', str(html)))

    figures = [build() for _ in range(4)]
    try:
        alone = [selectors(figure) for figure in figures]
        assert all(count == alone[0] for count in alone), alone

        together: dict[int, int] = {}

        def render(index, figure):
            together[index] = selectors(figure)

        workers = [
            threading.Thread(target=render, args=(index, figure))
            for index, figure in enumerate(figures)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=60)
            assert not worker.is_alive(), "a render deadlocked"

        assert [together[i] for i in range(len(figures))] == alone, (
            "a concurrent render of another figure stripped this one's "
            "selectors; the highlight wiring is process-global state"
        )
    finally:
        plt.close("all")


#: Attributes that differ between two renders of the same chart by design --
#: fresh uuids per layer, and the timestamp matplotlib stamps into the SVG.
_VOLATILE_IN_SVG = re.compile(
    r'(\bid="[^"]*"|url\(#[^)]*\)|<dc:date>[^<]*</dc:date>'
    r'|xlink:href="#[^"]*"|maidr="[^"]*")'
)


def test_concurrent_renders_of_one_figure_agree():
    """Concurrent renders of one figure must produce the same chart.

    Narrower than it first looks, and worth stating plainly:
    ``test_two_renders_of_one_figure_do_not_overlap`` above already fails
    without the lock, so this is not filling an unguarded gap. That one
    monkeypatches ``maidr.render`` to a sleeping stub, so it proves the
    lock *excludes* but cannot see what the exclusion is protecting. This
    runs the real render and asserts the consequence.

    ``savefig`` writes ``fig.dpi`` for its duration and restores it
    afterwards, so two renders of the **same** figure at once race on one
    mutable attribute and the loser draws the whole chart at the other
    call's dpi (#454). Distinct figures do not race; that is why the lock
    is per figure rather than process-wide.

    The failure is the kind this project treats as worst: not garbled
    markup and not an exception, but a complete, well-formed SVG of the
    same chart at the wrong size. Geometry is what the highlight overlay
    and the tactile export are positioned against, so a chart rendered at
    72% scale is wrong in the modality a sighted reviewer checks least.

    Asserted as agreement between renders rather than against a fixed size,
    since the wrong-dpi output is internally consistent -- it is only wrong
    relative to what every other render produced.

    The barrier synchronises the *start*, not the duration. On a runner
    slow or oversubscribed enough that each ``savefig`` finishes before
    the next thread is scheduled, this would pass with a broken lock --
    a false negative rather than a flaky failure, so it would show up as
    quietly reduced coverage rather than as CI noise. Measured 8 of 8
    detections here with the lock removed; the sibling test above detects
    overlap regardless of speed and is the one to trust on a bad day.

    Scope: **geometry, not data.** ``_VOLATILE_IN_SVG`` strips every
    ``maidr="..."`` attribute, and the one on the root ``<svg>`` carries
    the whole embedded schema, so a race that scrambled the announced
    values without moving a coordinate would pass this. The bug it guards
    is about ``fig.dpi``, which lives entirely in the ``<path d="...">``
    data the regex leaves alone.

    Measured 10 of 10 runs mismatching with the lock stubbed out and 10 of
    10 identical with it, so this runs in CI rather than under
    ``--run-benchmark``.

    The renders start from a barrier rather than from whenever each thread
    happens to be scheduled. Review raised the right worry -- a quiet or
    single-core runner could let six staggered renders complete without
    ever landing inside each other's ``dpi`` window, which would reduce
    this to a no-op that still passes. Raising the chart size does not
    address that (detection was 8 of 8 at 30, 100 and 200 bars alike, so
    the margin was never the variable); starting them together does,
    because it does not depend on the scheduler being busy.
    """
    fig, ax = plt.subplots()
    ax.bar([str(i) for i in range(30)], list(range(30)))
    renderer = render_maidr(lambda: ax)

    outputs: list[str] = []
    failures: list[BaseException] = []
    # One constant for the barrier and the thread count, because they must
    # agree: a barrier expecting more arrivals than there are threads waits
    # forever (#506).
    racers = 6
    start = threading.Barrier(racers)

    def render_once():
        try:
            start.wait(timeout=10)
            rendered = str(renderer._render_off_loop(ax))
            outputs.append(_VOLATILE_IN_SVG.sub("", rendered))
        except Exception as exc:  # reported below, not swallowed
            # Narrow enough to cover everything expected --
            # `BrokenBarrierError` is a `RuntimeError` -- while leaving
            # `KeyboardInterrupt` and `SystemExit` free to end the thread.
            failures.append(exc)

    workers = [threading.Thread(target=render_once) for _ in range(racers)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            # Longer than the barrier's own deadline above, so a thread
            # still legitimately waiting there is not reported as a
            # deadlocked render. A healthy run of this test is ~1.7s.
            worker.join(timeout=30)
            assert not worker.is_alive(), "a render deadlocked on the lock"

        assert not failures, f"a render raised: {failures[:2]}"
        assert len(outputs) == len(workers)
        assert len(set(outputs)) == 1, (
            "concurrent renders of one figure disagreed; one of them drew "
            "the chart at another render's dpi, which produces a valid SVG "
            "at the wrong scale rather than an error"
        )
    finally:
        plt.close(fig)

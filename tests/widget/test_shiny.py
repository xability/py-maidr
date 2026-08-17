"""Tests for the Shiny integration in ``maidr.widget.shiny``.

These drive the renderer the way Shiny does -- ``_render(renderer)``
inside a session context -- without starting a server.
"""

from __future__ import annotations

import asyncio
import re
import sys
import warnings
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

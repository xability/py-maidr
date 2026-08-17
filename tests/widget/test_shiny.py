"""Tests for the Shiny integration in ``maidr.widget.shiny``.

These drive the renderer the way Shiny does -- ``_render(renderer)``
inside a session context -- without starting a server.
"""

from __future__ import annotations

import asyncio
import re
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

"""A Quarto render builds one document, not a notebook (#888).

Quarto runs a document's Python cells in an ordinary Jupyter kernel, so
py-maidr saw a notebook there and did what a notebook needs: ``import maidr``
stashed the bundled ``maidr.js`` on the page, and every ``show()`` stashed it
again so that each cell would stand on its own. Every cell's output goes into
the same document, though, so a page with three charts carried four identical
2 MB copies.

These pin that a render under the default ``use_cdn="auto"`` stashes the
bundle once, with its first chart -- not with the import, whose cell is often a
setup cell Quarto drops the output of -- and that a notebook, and a render under
``use_cdn=False``, still give every chart its own copy. That the render also
resolves the CDN version is pinned with the other event-loop cases, in
``test_cdn_event_loop.py``.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr import api as maidr_api  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402

#: Set by Quarto's Jupyter engine in the kernel it renders a document with.
QUARTO_VARIABLE = "QUARTO_FIG_FORMAT"


@pytest.fixture
def page(monkeypatch):
    """A notebook page, recording what is displayed on it.

    Yields a function counting the bundle copies stashed so far.
    """
    ipython_display = pytest.importorskip("IPython.display")
    monkeypatch.delenv(QUARTO_VARIABLE, raising=False)
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    monkeypatch.setattr(maidr_api, "_NOTEBOOK_LOADED", False)
    # The chart itself is displayed through htmltools; only the stash goes
    # through IPython.display, which is what this records. The module is
    # patched rather than replaced: matplotlib reads IPython's version when
    # a figure is created.
    monkeypatch.setattr("htmltools._core.Tag.show", lambda self, *a, **k: None)
    displayed: list[str] = []
    monkeypatch.setattr(ipython_display, "HTML", lambda html: html)
    monkeypatch.setattr(ipython_display, "display", displayed.append)
    yield lambda: sum("window.__maidrJsSource" in html for html in displayed)


def _show_a_chart(**kwargs) -> None:
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1.0, 2.0, 3.0])
    try:
        FigureManager.get_maidr(fig).show(renderer="ipython", clear_fig=False, **kwargs)
    finally:
        plt.close(fig)


def test_is_quarto_reads_the_variable_quarto_sets_in_its_kernel(monkeypatch):
    monkeypatch.setenv(QUARTO_VARIABLE, "png")
    assert Environment.is_quarto() is True

    monkeypatch.setenv(QUARTO_VARIABLE, "")
    assert Environment.is_quarto() is False

    monkeypatch.delenv(QUARTO_VARIABLE)
    assert Environment.is_quarto() is False


def test_a_notebook_gives_every_chart_its_own_copy(page):
    """Unchanged: a cell-isolated frontend needs the copy in each output."""
    _show_a_chart()
    _show_a_chart()

    assert page() == 2


def test_a_quarto_render_stashes_the_bundle_once(page, monkeypatch):
    """The reported bug: every chart's frame reaches the first copy."""
    monkeypatch.setenv(QUARTO_VARIABLE, "png")

    _show_a_chart()
    _show_a_chart()
    _show_a_chart()

    assert page() == 1


def test_a_quarto_render_offline_still_gives_every_chart_its_own_copy(
    page, monkeypatch
):
    """Under ``use_cdn=False`` the copy is each chart's only source.

    ``quarto preview`` renders again in the kernel it already used, so a copy
    stashed in an earlier render is not in the page being built.
    """
    monkeypatch.setenv(QUARTO_VARIABLE, "png")

    _show_a_chart(use_cdn=False)
    _show_a_chart(use_cdn=False)

    assert page() == 2


def test_a_quarto_render_stashes_with_the_first_chart_not_the_import(page, monkeypatch):
    """A setup cell's output is often dropped, and the copy with it."""
    monkeypatch.setenv(QUARTO_VARIABLE, "png")

    maidr_api._init_notebook_on_import()
    assert page() == 0

    _show_a_chart()
    assert page() == 1


def test_a_notebook_still_stashes_on_import(page):
    maidr_api._init_notebook_on_import()

    assert page() == 1


def test_a_quarto_render_on_the_cdn_alone_stashes_nothing(page, monkeypatch):
    monkeypatch.setenv(QUARTO_VARIABLE, "png")

    _show_a_chart(use_cdn=True)

    assert page() == 0

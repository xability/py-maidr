"""`maidr.show(clear_fig=...)` acts on the figure it showed.

Two faults, one cause. `Maidr.show` closed the figure with a bare
`plt.close()`, which closes pyplot's *current* figure -- the one created or
activated last -- rather than the one it had just rendered, so showing an
older figure while a newer one was open closed the wrong one. And
`maidr.show(clear_fig=False)` was honoured only for an `Axes`: the `Figure`
form, which includes the default `plot=None`, went through a branch of
`maidr.show` that never forwarded `clear_fig`, so the figure was closed
regardless (#694).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402


@pytest.fixture(autouse=True)
def _quiet_show(monkeypatch):
    """Keep `show` off the screen; the figure bookkeeping is what matters."""
    monkeypatch.setattr("htmltools._core.Tag.show", lambda self, *a, **k: "shown")
    monkeypatch.setattr(
        "maidr.util.environment.Environment.is_notebook", staticmethod(lambda: False)
    )
    plt.close("all")
    yield
    plt.close("all")


def _bar():
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return fig, ax


def test_show_closes_the_figure_it_showed_and_not_the_current_one():
    older, older_ax = _bar()
    newer, _ = _bar()
    assert plt.gcf() is newer

    maidr.show(older, renderer="ipython", use_cdn=False)

    assert plt.get_fignums() == [newer.number]


def test_show_by_axes_closes_that_axes_figure():
    older, older_ax = _bar()
    newer, _ = _bar()

    maidr.show(older_ax, renderer="ipython", use_cdn=False)

    assert plt.get_fignums() == [newer.number]


@pytest.mark.parametrize("form", ["none", "figure", "axes"])
def test_clear_fig_false_keeps_the_figure_whatever_form_it_was_passed_in(form):
    fig, ax = _bar()
    plot = {"none": None, "figure": fig, "axes": ax}[form]

    maidr.show(plot, clear_fig=False, renderer="ipython", use_cdn=False)

    assert fig.number in plt.get_fignums()


@pytest.mark.parametrize("form", ["none", "figure", "axes"])
def test_clear_fig_true_closes_the_figure_whatever_form_it_was_passed_in(form):
    fig, ax = _bar()
    plot = {"none": None, "figure": fig, "axes": ax}[form]

    maidr.show(plot, clear_fig=True, renderer="ipython", use_cdn=False)

    assert fig.number not in plt.get_fignums()

"""
``ax.hist()`` returns ``(n, bins, patches)``, as matplotlib does.

The patch's bar branch returned the bars alone, so with maidr imported every
caller that unpacks the result failed::

    n, bins, patches = ax.hist(x)
    ValueError: too many values to unpack (expected 3)

That line is matplotlib's own idiom, the repository's
``example/histogram/matplotlib/example_mpl_hist.py``, and what pandas'
``Series.plot.hist()`` runs. With three bins it unpacked three ``Rectangle``
objects instead of raising. The step histtypes already returned all three.

``maidr.show(ax.hist(x))`` used to resolve through the bars it was handed. It
is now handed the tuple, and resolves through the bars inside it.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

import maidr
from maidr.core.figure_manager import FigureManager

HISTTYPES = ["bar", "barstacked", "step", "stepfilled"]

#: Ten in the first of two bins, then four and six.
ONE = np.array([1.0] * 10)
TWO = [ONE, np.array([1.0] * 4 + [3.0] * 6)]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _counts(fig) -> list:
    """Every layer's per-bin counts, in registration order."""
    return [
        [point["y"] for point in plot.schema["data"]]
        for plot in FigureManager.get_maidr(fig).plots
    ]


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("data", [ONE, TWO], ids=["one-dataset", "two-datasets"])
@pytest.mark.parametrize("histtype", HISTTYPES)
def test_ax_hist_returns_what_matplotlib_returns(histtype, data, orientation):
    _, ax = plt.subplots()
    _, reference_ax = plt.subplots()

    result = ax.hist(data, bins=2, histtype=histtype, orientation=orientation)
    # The function the patch wraps, called on axes of its own.
    reference = Axes.hist.__wrapped__(
        reference_ax, data, bins=2, histtype=histtype, orientation=orientation
    )

    assert type(result) is tuple and len(result) == 3
    n, bins, patches = result
    assert np.array_equal(n, reference[0])
    assert np.array_equal(bins, reference[1])
    assert isinstance(patches, type(reference[2]))
    assert len(patches) == len(reference[2])


@pytest.mark.parametrize("histtype", HISTTYPES)
def test_each_dataset_is_still_its_own_layer(histtype):
    fig, ax = plt.subplots()

    ax.hist(TWO, bins=2, histtype=histtype)

    assert _counts(fig) == [[10.0, 0.0], [4.0, 6.0]]


@pytest.mark.parametrize("bins", [3, 10])
def test_the_three_values_unpack(bins):
    # Ten bins raised `ValueError`, and three unpacked the three bars.
    _, ax = plt.subplots()

    n, edges, patches = ax.hist(np.arange(30.0), bins=bins)

    assert n.tolist() == [30.0 / bins] * bins
    assert len(edges) == bins + 1
    assert isinstance(patches, BarContainer)
    assert list(patches) == list(ax.patches)


def test_pyplot_hist_unpacks():
    plt.figure()

    n, edges, patches = plt.hist(np.arange(30.0), bins=10)

    assert len(n) == 10 and len(edges) == 11 and len(patches) == 10


def test_a_pandas_histogram_is_drawn_and_read():
    # pandas unpacks `ax.hist()` in `HistPlot._plot`, once per column.
    fig, ax = plt.subplots()

    pd.DataFrame({"a": TWO[0], "b": TWO[1]}).plot.hist(ax=ax, bins=[0, 2, 4])

    assert _counts(fig) == [[10.0, 0.0], [4.0, 6.0]]


@pytest.mark.parametrize("histtype", HISTTYPES)
def test_the_entry_points_resolve_what_ax_hist_returned(histtype):
    # The bar histtypes resolved through the bars they used to return; the
    # step histtypes returned the tuple already, and raised `TypeError`.
    fig, ax = plt.subplots()

    result = ax.hist(ONE, bins=2, histtype=histtype)

    assert FigureManager.get_axes(result) is ax
    assert len(maidr.render(result)._repr_html_()) > 0
    maidr.close(result)
    assert fig not in FigureManager.figs


def test_a_shiny_render_function_may_return_what_ax_hist_returned():
    pytest.importorskip("shiny")
    from maidr.widget.shiny import _check_supported

    _, ax = plt.subplots()

    _check_supported(ax.hist(ONE, bins=2), "chart")


def test_a_tuple_holding_no_artist_resolves_to_nothing():
    assert FigureManager.get_axes((np.arange(3.0), np.arange(4.0))) is None


def test_a_list_holding_what_ax_hist_returned_resolves():
    _, ax = plt.subplots()

    assert FigureManager.get_axes([ax.hist(ONE, bins=2)]) is ax


def test_a_tuple_passes_over_what_it_cannot_read():
    # `subplot_mosaic` returns `(fig, axd)`, and the dict branch cannot read
    # a dict of axes. A plain tuple never raised here before it was walked,
    # and `maidr.close()` is not to raise about what it was handed.
    fig, axd = plt.subplot_mosaic("AB")
    axd["A"].bar(["a"], [1])
    _, other = plt.subplots()

    assert FigureManager.get_axes((fig, axd)) is None
    assert FigureManager.get_axes([(fig, axd), other]) is other
    maidr.close((fig, axd))
    assert fig in FigureManager.figs

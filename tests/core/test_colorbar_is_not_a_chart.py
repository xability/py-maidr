"""A colorbar is a legend, and must not be read as a second chart.

A colorbar paints its gradient onto its own axes through the same entry
points the heatmap patch wraps, so MAIDR registered it as a ``heat`` layer of
its own. Two things followed, and the second is the one a user notices:

* a phantom layer -- a reader handed a second "heatmap" to page through that
  the figure does not contain;
* the render **died**. Extraction reaches the colorbar's outline, a
  ``LineCollection`` where a mappable is expected, and raises
  ``ExtractionError`` -- which is not confined to its own layer. It takes the
  whole figure with it, so a chart that would have read perfectly well
  produced nothing at all (#369).

Not specific to heatmaps: the fault is in what the colorbar's own draw
registers, so every plot type that wants a colour scale was affected.

Hidden this long because ``sns.heatmap()`` creates its colorbar *inside* the
patched call, where the recursion guard already suppressed it, and every
worked example in the documentation happens to take that path. Only a caller
writing ``fig.colorbar(...)`` themselves hit it.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layers(fig) -> list:
    """The plot types registered for a figure, or an empty list."""
    try:
        return [plot.type for plot in FigureManager.get_maidr(fig).plots]
    except KeyError:
        return []


def _mappables():
    """One chart per plot type that carries a colour scale."""
    rng = np.random.default_rng(20260814)

    def mesh(ax):
        return ax.pcolormesh(np.arange(12).reshape(3, 4))

    def scatter(ax):
        return ax.scatter(
            rng.normal(size=20), rng.normal(size=20), c=rng.normal(size=20)
        )

    def hexbin(ax):
        return ax.hexbin(rng.normal(size=80), rng.normal(size=80), gridsize=3)

    return [
        ("pcolormesh", mesh, PlotType.HEAT),
        ("scatter", scatter, PlotType.SCATTER),
        ("hexbin", hexbin, PlotType.HEXBIN),
    ]


@pytest.mark.parametrize("name,draw,expected", _mappables())
def test_a_colorbar_adds_no_layer_of_its_own(name, draw, expected) -> None:
    """The chart is registered once, and the colorbar is not a second chart.

    Asserted across three plot types because the fault was never about
    heatmaps -- it was about what the colorbar's own draw registers, which is
    the same whatever it is a legend for. ``pcolormesh`` came out as
    ``['heat', 'heat']``, and the duplicate was the legend.
    """
    fig, ax = plt.subplots()
    fig.colorbar(draw(ax), ax=ax, label="Legend")

    assert _layers(fig) == [expected]


@pytest.mark.parametrize("name,draw,expected", _mappables())
def test_a_figure_with_a_colorbar_still_renders(name, draw, expected) -> None:
    """The half a user notices, and the reason this is a crash not a wart.

    ``ExtractionError`` is fatal to the render rather than to the layer that
    raised it, so one unreadable phantom layer left the caller with no chart
    at all -- not a degraded one, none.
    """
    fig, ax = plt.subplots()
    fig.colorbar(draw(ax), ax=ax, label="Legend")

    schema = FigureManager.get_maidr(fig)._flatten_maidr()

    layers = schema["subplots"][0][0]["layers"]
    assert len(layers) == 1
    assert layers[0]["type"] == expected.value


def test_an_explicitly_placed_colorbar_is_covered_too() -> None:
    """``cax=`` is the other common idiom, and takes a different route in.

    ``Figure.colorbar`` steals space from the parent axes when given ``ax=``
    and skips that when handed a ``cax``, so the two paths diverge well before
    the draw. They converge at ``Colorbar._draw_all``, which is where the
    guard sits -- a test for "is this axes a colorbar" would have had to cover
    both, and would have been wrong about the timing anyway, since
    ``ax._colorbar`` is not assigned until after the draw that registers the
    layer.
    """
    fig, ax = plt.subplots()
    cax = fig.add_axes((0.92, 0.1, 0.02, 0.8))
    fig.colorbar(ax.pcolormesh(np.arange(12).reshape(3, 4)), cax=cax)

    assert _layers(fig) == [PlotType.HEAT]


def test_the_pyplot_level_colorbar_is_covered_too() -> None:
    """The third route in, and the last one not pinned by a test.

    ``plt.colorbar`` reaches the same ``Colorbar._draw_all`` as the two above,
    which is the argument for putting the guard there -- but an argument is
    not a test, and this is the one route where a reader would reasonably
    wonder whether the reasoning holds.
    """
    fig, ax = plt.subplots()
    plt.colorbar(ax.pcolormesh(np.arange(12).reshape(3, 4)), ax=ax)

    assert _layers(fig) == [PlotType.HEAT]


def test_the_chart_a_colorbar_belongs_to_is_unchanged() -> None:
    """Suppressing the legend must not suppress anything the chart says.

    The guard runs the colorbar's draw inside the recursion context, which is
    the same mechanism that stops a patched function registering the calls it
    makes internally. Scoped to the draw, so what the chart itself emitted
    beforehand is untouched -- asserted rather than assumed, because a context
    that leaked would silently swallow every layer after the first colorbar.
    """
    values = np.arange(12).reshape(3, 4)

    without = plt.figure()
    ax = without.add_subplot()
    ax.pcolormesh(values)
    bare = FigureManager.get_maidr(without)._flatten_maidr()

    with_bar = plt.figure()
    ax = with_bar.add_subplot()
    with_bar.colorbar(ax.pcolormesh(values), ax=ax, label="Legend")
    legended = FigureManager.get_maidr(with_bar)._flatten_maidr()

    assert legended["subplots"][0][0]["layers"][0]["data"] == (
        bare["subplots"][0][0]["layers"][0]["data"]
    )


def test_a_chart_drawn_after_a_colorbar_still_registers() -> None:
    """The context has to end with the draw, not outlive it.

    A guard that leaked would take the next chart with it, and the symptom --
    a figure quietly missing a layer -- looks nothing like a colorbar problem.
    """
    fig, ax = plt.subplots()
    fig.colorbar(ax.pcolormesh(np.arange(12).reshape(3, 4)), ax=ax)

    second = fig.add_subplot(2, 1, 2)
    second.scatter([1, 2, 3], [1, 2, 3])

    assert _layers(fig) == [PlotType.HEAT, PlotType.SCATTER]

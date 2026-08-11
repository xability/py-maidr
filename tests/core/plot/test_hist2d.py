"""Tests for 2D density plots.

``Axes.hist2d`` reads today, and reads by accident: it draws through
``Axes.pcolormesh``, which was patched for its own sake, so a rectangular 2D
histogram started registering as a heatmap without anyone deciding it should.

That is worth pinning rather than leaving implicit. A change to the heatmap
patch -- narrowing which entry points it wraps, say, or adding a guard that
skips nested draws -- would take this away silently: no error, no warning, just
a chart that used to be navigable and no longer is. These tests make that a
failure instead.

The other two 2D density paths do NOT read, and are asserted here too so the
boundary is visible in one place rather than discovered per bug report:

- ``Axes.hexbin`` renders a ``PolyCollection`` of hexagons, which is neither a
  mesh nor a rectangular grid.
- ``sns.kdeplot(x=, y=)`` renders filled or line contours, which need a
  contour trace to describe levels rather than cells.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


#: Two well-separated clusters, so the bin counts are lopsided and a
#: transposed or mis-shaped extraction cannot pass by symmetry.
_RNG = np.random.default_rng(20260811)
X = np.concatenate([_RNG.normal(-2, 0.3, 150), _RNG.normal(2, 0.3, 50)])
Y = np.concatenate([_RNG.normal(-1, 0.3, 150), _RNG.normal(1, 0.3, 50)])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _plots(fig):
    """
    Return the MAIDR plots registered for a figure, or an empty list.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list
        The registered plots; empty when the figure registered nothing.
    """
    try:
        return FigureManager.get_maidr(fig).plots
    except KeyError:
        return []


def test_hist2d_registers_a_heat_layer():
    """A rectangular 2D histogram is navigable as a heatmap."""
    fig, ax = plt.subplots()
    ax.hist2d(X, Y, bins=(3, 2))

    plots = _plots(fig)
    assert len(plots) == 1
    assert plots[0].type == PlotType.HEAT


def test_hist2d_extracts_the_bin_counts_as_a_grid():
    """
    The emitted cells are the bin counts, laid out as rows of bins.

    ``hist2d`` returns its counts transposed relative to the mesh it draws, so
    a grid that came back the wrong way round would still navigate -- it would
    just describe a different chart.
    """
    fig, ax = plt.subplots()
    counts, _x_edges, _y_edges, _mesh = ax.hist2d(X, Y, bins=(3, 2))

    points = _plots(fig)[0]._extract_plot_data()["points"]

    # `hist2d` counts are indexed [x, y]; the drawn mesh is [y, x].
    assert points == counts.T.tolist()


def test_hist2d_supports_highlighting():
    """
    The mesh is tagged, so the cell under the cursor can be highlighted.

    Both halves are asserted because the flag alone does not say the mesh was
    tagged. ``_support_highlighting`` starts True and is only ever cleared, so
    it reports which branch the extraction took; were the tagging inside that
    branch dropped, the flag would stay True and highlighting would break in
    silence. ``elements`` is the thing the docstring above actually claims.
    """
    fig, ax = plt.subplots()
    ax.hist2d(X, Y, bins=(3, 2))

    plot = _plots(fig)[0]
    plot._extract_plot_data()

    assert plot._support_highlighting is True
    assert plot.elements, "the QuadMesh should be tagged for highlighting"


def test_hist2d_registers_exactly_one_layer():
    """
    One call registers one layer.

    ``hist2d`` draws through ``pcolormesh``, and both would register were the
    context guard to regress -- leaving the user a second identical heatmap to
    navigate that the figure does not contain.
    """
    fig, ax = plt.subplots()
    ax.hist2d(X, Y, bins=(3, 2))

    assert len(_plots(fig)) == 1


def test_hexbin_is_not_registered_yet():
    """
    ``hexbin`` renders a ``PolyCollection`` of hexagons rather than a mesh.

    Asserted rather than left unsaid: it is the neighbouring call a user will
    reach for, and pinning the boundary here means the day hexagonal binning
    lands, this test fails and has to be rewritten as a positive one.
    """
    fig, ax = plt.subplots()
    ax.hexbin(X, Y, gridsize=3)

    assert _plots(fig) == []


@pytest.mark.parametrize("fill", [True, False])
def test_bivariate_kdeplot_is_not_registered_yet(fill):
    """
    A 2D KDE draws contours, filled or not, and MAIDR has no contour trace.

    A contour plot is not a heatmap with different colours: the level is the
    navigable object, not the cell, so describing one as a grid would be a
    different chart rather than an approximate one.
    """
    fig, ax = plt.subplots()
    sns.kdeplot(x=X, y=Y, fill=fill, ax=ax)

    assert _plots(fig) == []

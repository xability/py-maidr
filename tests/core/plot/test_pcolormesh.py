"""Tests for heatmaps drawn through ``pcolormesh`` and ``pcolor``.

``Axes.imshow`` is not the only way a matplotlib heatmap is drawn, and it is
not the most common one: ``pcolormesh`` is what you reach for whenever the grid
is irregular or the axes carry real coordinates rather than array indices.
Until it was patched, such a figure registered nothing at all -- the user got
silence, with nothing to say a chart had been missed.

Patching it introduces a second thing these tests pin down. ``seaborn.heatmap``
draws *through* ``Axes.pcolormesh``, so with both patched the inner call would
register a duplicate layer unless the context guard stops it. One call must
still register exactly one layer.
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


#: A 2x3 grid whose values are all distinct, so a transposed or mis-reshaped
#: extraction cannot pass by coincidence.
VALUES = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

#: Cell edges for the grid above: one more edge than cells on each axis.
X_EDGES = np.arange(VALUES.shape[1] + 1)
Y_EDGES = np.arange(VALUES.shape[0] + 1)


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _sole_plot(fig):
    """
    Return the one MAIDR plot registered for a figure.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    maidr.core.plot.MaidrPlot
        The single registered plot.

    Raises
    ------
    AssertionError
        If the figure registered anything other than exactly one plot.
    """
    plots = FigureManager.get_maidr(fig).plots
    assert len(plots) == 1, f"expected one layer, got {len(plots)}"
    return plots[0]


@pytest.mark.parametrize("draw", ["pcolormesh", "pcolor"])
def test_registers_a_heat_layer(draw):
    """A mesh heatmap registers, rather than being silently dropped."""
    fig, ax = plt.subplots()
    getattr(ax, draw)(X_EDGES, Y_EDGES, VALUES)

    assert _sole_plot(fig).type == PlotType.HEAT


@pytest.mark.parametrize("draw", ["pcolormesh", "pcolor"])
def test_extracts_the_grid_in_its_original_shape(draw):
    """
    Cell values come back as rows of cells, not as the flat array matplotlib
    stores them in.

    ``QuadMesh`` flattens its value array, so the row/column structure has to
    be recovered from the coordinate mesh. Getting that wrong does not fail
    loudly -- it yields a grid of the wrong shape that still navigates.
    """
    fig, ax = plt.subplots()
    getattr(ax, draw)(X_EDGES, Y_EDGES, VALUES)

    points = _sole_plot(fig)._extract_plot_data()["points"]

    assert points == VALUES.tolist()


def test_pcolormesh_supports_highlighting():
    """
    A ``pcolormesh`` grid is highlightable, because it renders as a
    ``QuadMesh`` and `patch/highlight.py` tags that class.

    ``_support_highlighting`` starts True and is only cleared while the data is
    extracted, so the extraction has to run before it means anything -- reading
    it straight off a fresh plot asserts the default and nothing more.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh(X_EDGES, Y_EDGES, VALUES)

    plot = _sole_plot(fig)
    plot._extract_plot_data()

    assert plot._support_highlighting is True
    assert plot.elements, "the QuadMesh should be tagged for highlighting"


def test_pcolor_reads_without_highlighting():
    """
    ``pcolor`` renders as a ``PolyQuadMesh``, which `patch/highlight.py` does
    not tag, so the layer reads through audio, text and braille but carries no
    visual highlight.

    Asserted rather than left implicit: it is the one way the two entry points
    differ, and a future change that starts tagging ``PolyCollection`` should
    have to come back and update this.
    """
    fig, ax = plt.subplots()
    ax.pcolor(X_EDGES, Y_EDGES, VALUES)

    plot = _sole_plot(fig)
    plot._extract_plot_data()

    assert plot._support_highlighting is False


def test_seaborn_heatmap_still_registers_one_layer():
    """
    ``sns.heatmap`` draws through ``Axes.pcolormesh``. With both patched, the
    inner call must be suppressed by the context guard -- otherwise one call
    registers two identical heatmaps, and the user is handed a second layer to
    navigate that does not exist in the figure.
    """
    fig, ax = plt.subplots()
    sns.heatmap(VALUES, ax=ax)

    assert _sole_plot(fig).type == PlotType.HEAT


def test_imshow_still_registers_one_layer():
    """The pre-existing entry point is unaffected by the new patches."""
    fig, ax = plt.subplots()
    ax.imshow(VALUES)

    assert _sole_plot(fig).type == PlotType.HEAT

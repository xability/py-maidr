"""``ax.pcolorfast`` draws the grid its three siblings do, and read nothing.

`imshow`, `pcolormesh` and `pcolor` have been patched as heatmaps since #337.
`pcolorfast` is matplotlib's optimised path for the same charts, and nothing
dispatched it -- so a figure drawn with it registered no layer at all and the
caller got silence with no indication anything had been missed, which is the
shape #337 was filed against.

It is not a new reading. Measured on matplotlib 3.10, every input form
`pcolorfast` accepts hands back an artist one of the three already produces::

    pcolorfast(Z)                  AxesImage    the artist `imshow` returns
    pcolorfast(x, y, Z)            AxesImage        "
    pcolorfast(X, Y, Z)  (2D)      QuadMesh     the artist `pcolormesh` returns

so the extraction was already proven for every shape the call can produce.

`tripcolor` colours cells too and is deliberately *not* patched: it colours
the triangles of a triangulation, and a heatmap is addressed by row and
column, which a mesh has neither of. Declined for the reason `triplot` is
(#572), and asserted below so the omission reads as a decision.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

import maidr  # noqa: F401  (installs the patches)
from maidr.core.figure_manager import FigureManager


def _layer_types(figure) -> list[str]:
    """The trace types a figure registered, in order."""
    try:
        plots = FigureManager.get_maidr(figure).plots
    except Exception:  # noqa: BLE001 - nothing registered at all
        return []
    return [plot.type.value for plot in plots]


@pytest.fixture()
def grid() -> np.ndarray:
    """A small rectangular field, the same one every form is drawn from."""
    return np.arange(20, dtype=float).reshape(4, 5)


@pytest.mark.parametrize(
    "form",
    ["uniform", "rectilinear", "irregular"],
    ids=["pcolorfast(Z)", "pcolorfast(x, y, Z)", "pcolorfast(X, Y, Z)"],
)
def test_pcolorfast_registers_a_heatmap(form: str, grid: np.ndarray) -> None:
    """Every input form reads as the heatmap it draws."""
    figure, ax = plt.subplots()
    try:
        if form == "uniform":
            ax.pcolorfast(grid)
        elif form == "rectilinear":
            ax.pcolorfast(np.arange(6), np.arange(5), grid)
        else:
            x_edges, y_edges = np.meshgrid(np.arange(6), np.arange(5))
            ax.pcolorfast(x_edges, y_edges, grid)

        assert _layer_types(figure) == ["heat"]
    finally:
        plt.close(figure)


def test_pcolorfast_reads_the_same_grid_as_pcolormesh(grid: np.ndarray) -> None:
    """The two spellings of one chart carry the same cells.

    The point of routing `pcolorfast` through the existing patch rather than
    giving it one: it is the same grid, so it has to read as the same data
    rather than as a second heatmap that happens to look similar.
    """
    fast_figure, fast_ax = plt.subplots()
    mesh_figure, mesh_ax = plt.subplots()
    try:
        fast_ax.pcolorfast(grid)
        mesh_ax.pcolormesh(grid)

        fast = FigureManager.get_maidr(fast_figure).plots[0].schema["data"]
        mesh = FigureManager.get_maidr(mesh_figure).plots[0].schema["data"]

        assert fast == mesh
    finally:
        plt.close(fast_figure)
        plt.close(mesh_figure)


def test_tripcolor_is_still_declined() -> None:
    """A triangulation is not a grid, so it is not read as one.

    The guard on the change: patching one more cell-colouring call must not
    become patching every one of them. `tripcolor` colours triangles, which
    have no row and no column for a reader to navigate by, so handing back a
    grid would mean handing back one the call never drew.
    """
    rng = np.random.default_rng(0)
    figure, ax = plt.subplots()
    try:
        ax.tripcolor(rng.random(9), rng.random(9), rng.random(9))

        assert _layer_types(figure) == []
    finally:
        plt.close(figure)

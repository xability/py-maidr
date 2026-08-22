"""
What a mesh, a filled contour and a vector field are read as (#572, #568).

Every call here draws something maidr has no trace for. The point of the
file is that they say so by registering *nothing* -- the figure falls back
to a picture, or reads whatever else is on the axes -- rather than being
given a reading that is wrong.

``ax.triplot`` was the exception and the reason this exists. It draws a
triangulation mesh by handing the flattened edge list to ``Axes.plot``::

    tri_lines = ax.plot(tri_lines_x.ravel(), tri_lines_y.ravel(), ...)

so the line patch saw an ordinary plot call and announced a LINE layer of
thirty-two points for a chart of eight, x running 0.04 -> 0.64 -> 0.04 ->
0.27 with the first point repeating as the third. A line trace offers a
reader a trend through ordered observations; a mesh has no order.

The filled contours are the interesting decline, because their unfilled
twins *do* read. Measured on one field with ``levels=[1, 2, 4]``:

    contour   3 paths, each at one level        (z = 1.0 / 2.0 / 4.0)
    contourf  2 paths, each spanning two        (path 0: z = 1.0 -> 2.0)

A filled contour draws the bands *between* levels, so calling one of those
outlines a level's own curve would be right for about half its vertices.
That is the rule xability/r-maidr's `Ggplot2ContourLayerProcessor` already
states for `geom_contour_filled()`, and the two bindings agreeing is worth
keeping.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def triangulation() -> tuple:
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 1, 8), rng.uniform(0, 1, 8)
    return x, y, x**2 + y**2


@pytest.fixture
def field() -> tuple:
    grid = np.linspace(-2, 2, 9)
    x, y = np.meshgrid(grid, grid)
    return grid, x, y, x**2 + y**2


def _layers(fig) -> list:
    try:
        return [plot.type.value for plot in FigureManager.get_maidr(fig).plots]
    except UnsupportedPlotError:
        return []


def test_a_triangulation_mesh_is_not_announced_as_a_line(triangulation):
    x, y, _ = triangulation
    fig, ax = plt.subplots()
    ax.triplot(x, y)

    assert _layers(fig) == []
    # And the figure is still a picture rather than nothing at all.
    assert len(maidr.render(fig)._repr_html_()) > 0


@pytest.mark.parametrize("mesh_first", [True, False])
def test_a_mesh_under_a_contour_does_not_cost_it_its_reading(
    triangulation, mesh_first
):
    # The way `triplot` is actually used: drawn beneath a `tricontour` to
    # show where the samples were. That half reads, and must keep reading
    # whichever order the two were drawn in.
    x, y, z = triangulation
    fig, ax = plt.subplots()
    if mesh_first:
        ax.triplot(x, y)
        ax.tricontour(x, y, z)
    else:
        ax.tricontour(x, y, z)
        ax.triplot(x, y)

    assert _layers(fig) == ["contour"]


def test_an_ordinary_line_after_a_mesh_still_reads(triangulation):
    # The decline is done by drawing inside the internal context, which is a
    # thing that could leak: if it did, every later call on the figure would
    # register nothing. Pinned because the failure would be silent and total.
    x, y, _ = triangulation
    fig, ax = plt.subplots()
    ax.triplot(x, y)
    ax.plot([1, 2, 3], [4, 5, 6])

    assert _layers(fig) == ["line"]


def test_an_unfilled_contour_reads(field):
    # The control for the two below: this is the same chart with lines
    # instead of bands, and it is read.
    _, x, y, z = field
    fig, ax = plt.subplots()
    ax.contour(x, y, z)

    assert _layers(fig) == ["contour"]


def test_a_filled_contour_path_spans_two_levels(field):
    # The measurement the decline rests on, asserted rather than described.
    # An unfilled path sits at one level; a filled one runs between two, so
    # announcing it as a level's own curve would be right for half of it.
    _, x, y, z = field

    fig, ax = plt.subplots()
    lines = ax.contour(x, y, z, levels=[1, 2, 4])
    for path in lines.get_paths():
        heights = (path.vertices**2).sum(axis=1)
        assert heights.max() - heights.min() < 0.5

    fig, ax = plt.subplots()
    bands = ax.contourf(x, y, z, levels=[1, 2, 4])
    spans = [
        np.ptp((path.vertices**2).sum(axis=1)) for path in bands.get_paths()
    ]
    assert all(span > 0.5 for span in spans)


@pytest.mark.parametrize("draw", ["contourf", "tricontourf", "tripcolor"])
def test_a_filled_contour_is_declined(field, triangulation, draw):
    _, x, y, z = field
    tx, ty, tz = triangulation

    fig, ax = plt.subplots()
    if draw == "contourf":
        ax.contourf(x, y, z)
    elif draw == "tricontourf":
        ax.tricontourf(tx, ty, tz)
    else:
        ax.tripcolor(tx, ty, tz)

    assert _layers(fig) == []
    assert len(maidr.render(fig)._repr_html_()) > 0


@pytest.mark.parametrize("draw", ["quiver", "barbs", "streamplot", "fill"])
def test_a_chart_with_no_trace_to_be_read_as_is_declined(field, draw):
    # A vector at a place carries a speed *and* a direction, which no trace
    # holds; `ax.fill` draws a closed polygon, which states no series. Pinned
    # together so that a future reading for one of them is a decision rather
    # than an accident.
    grid, x, y, _ = field

    fig, ax = plt.subplots()
    if draw == "quiver":
        ax.quiver([0, 1], [0, 1], [1, 1], [1, 1])
    elif draw == "barbs":
        ax.barbs([0, 1], [0, 1], [1, 1], [1, 1])
    elif draw == "streamplot":
        ax.streamplot(grid, grid, np.ones_like(x), np.ones_like(y))
    else:
        ax.fill([0, 1, 2, 0], [0, 2, 0, 0])

    assert _layers(fig) == []
    assert len(maidr.render(fig)._repr_html_()) > 0

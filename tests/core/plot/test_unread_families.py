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

``ax.fill`` is the decline that *could* be overturned, which is why its
reasoning is written down here rather than left to the parametrize list
(#685). Unlike a mesh or a vector field, a polygon is representable: ``fill``
returns ``Polygon`` patches carrying a closed ring of vertices, an ordered
sequence of positions, and a prototype reading each ring as its own LINE
layer worked end to end. It stays declined because a polygon states no
series. ``ax.plot`` is asked for as a sequence; ``ax.fill`` is asked for as
a shape, and announcing "line chart, four points" for a shaded region
describes the geometry rather than the chart -- ``line`` is the wrong name
for a filled mark, and ``area`` is worse, since that is a band against a
baseline and ``ax.fill([0, 1, 1, 0], [0, 0, 1, 1])`` is a square. The decline
also costs its neighbours nothing: a ``fill`` beside a scatter or a plot
leaves their reading exactly as it was, so the only figure that loses
anything holds a ``fill`` and nothing else, and that falls back to a picture
-- the designed answer for a chart maidr has no reading for.

The sweep at the bottom is the other half of the same promise. It walks every
matplotlib entry point that draws marks and pins what each one is read as
today, so that "nothing is unaccounted for" is a test rather than a claim in
an issue: a call that starts registering nothing, or a decline that starts
registering something, fails here by name.
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
    #
    # This one reads matplotlib's own output, with no maidr patch in the way,
    # which makes it the odd test here: it pins an assumption about
    # `contourf` rather than a behavior of ours. If a future matplotlib
    # changes how it builds those vertices this fails without anything in
    # maidr having regressed -- so it wants reading, not just re-running.
    # Kept because the decision not to patch `contourf` rests on it, and an
    # assumption nothing checks is how the two bindings drift apart.
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


@pytest.mark.parametrize("label", ["fit", "smooth", "regression"])
def test_a_mesh_labeled_like_a_fit_is_still_declined(triangulation, label):
    # The interaction review asked about, measured rather than traced.
    # `regplot.patched_plot` registers a SMOOTH layer when a plot call's
    # label matches `SMOOTH_KEYWORDS`, and `triplot` reaches `Axes.plot` --
    # so a mesh labeled "fit" is the shape where a second patch on the same
    # method could slip a layer through the decline. It does not: the
    # `common()` call that would register checks the context itself.
    x, y, _ = triangulation
    fig, ax = plt.subplots()
    ax.triplot(x, y, label=label)

    assert _layers(fig) == []


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (("scatter", "fill"), ["point"]),
        (("plot", "fill"), ["line"]),
        (("fill", "plot"), ["line"]),
    ],
)
def test_a_fill_beside_a_chart_that_reads_costs_it_nothing(order, expected):
    # What makes the `fill` decline a maintainer's call rather than a defect
    # (#685): a shaded region drawn next to a chart leaves the chart's reading
    # exactly as it was, whichever was drawn first.
    fig, ax = plt.subplots()
    for draw in order:
        if draw == "scatter":
            ax.scatter([1, 2, 3], [3, 1, 2])
        elif draw == "plot":
            ax.plot([1, 2, 3], [3, 1, 2])
        else:
            ax.fill([0, 1, 2, 0], [0, 2, 0, 0])

    assert _layers(fig) == expected


# Every matplotlib `Axes` method that draws marks, and what a figure holding
# just that call is read as. `[]` is a deliberate decline: the figure falls
# back to a picture. Grouped the way the readings group, not alphabetically.
SWEEP = {
    # a grid of values, addressed by row and column
    "imshow": ["heat"],
    "matshow": ["heat"],
    "spy": ["heat"],
    "specgram": ["heat"],
    # a value at a position, drawn as a stalk
    "stem": ["lollipop"],
    "acorr": ["lollipop"],
    "xcorr": ["lollipop"],
    # a spectrum is a series over frequency
    "psd": ["line"],
    "csd": ["line"],
    "cohere": ["line"],
    "magnitude_spectrum": ["line"],
    "angle_spectrum": ["line"],
    "phase_spectrum": ["line"],
    # level curves, one path per level
    "tricontour": ["contour"],
    # a vector at a place carries a speed *and* a direction; no trace holds both
    "quiver": [],
    "barbs": [],
    "streamplot": [],
    # a mesh states which points were joined, not an order to walk
    "triplot": [],
    # a filled band spans two levels; a heat grid is addressed by row and column
    "tripcolor": [],
    "contourf": [],
    "tricontourf": [],
    # a closed polygon states no series (see the module docstring)
    "fill": [],
}


def _draw(ax, call: str, field, triangulation) -> None:
    grid, x, y, z = field
    tx, ty, tz = triangulation
    signal = np.sin(np.linspace(0, 20, 256))
    if call in ("imshow", "matshow"):
        getattr(ax, call)(z)
    elif call == "spy":
        ax.spy(np.eye(5))
    elif call == "specgram":
        ax.specgram(signal, Fs=10, NFFT=64, noverlap=32)
    elif call == "stem":
        ax.stem([1, 2, 3], [3, 1, 2])
    elif call == "acorr":
        ax.acorr(signal[:64])
    elif call == "xcorr":
        ax.xcorr(signal[:64], signal[:64])
    elif call in ("psd", "magnitude_spectrum", "angle_spectrum", "phase_spectrum"):
        getattr(ax, call)(signal, Fs=10)
    elif call in ("csd", "cohere"):
        getattr(ax, call)(signal, np.roll(signal, 8), Fs=10, NFFT=64)
    elif call in ("tricontour", "tricontourf", "tripcolor"):
        getattr(ax, call)(tx, ty, tz)
    elif call in ("quiver", "barbs"):
        getattr(ax, call)([0, 1], [0, 1], [1, 1], [1, 1])
    elif call == "streamplot":
        ax.streamplot(grid, grid, np.ones_like(x), np.ones_like(y))
    elif call == "triplot":
        ax.triplot(tx, ty)
    elif call == "contourf":
        ax.contourf(x, y, z)
    elif call == "fill":
        ax.fill([0, 1, 2, 0], [0, 2, 0, 0])
    else:  # pragma: no cover - a new row needs a way to draw it
        raise AssertionError(f"no way to draw {call!r}")


@pytest.mark.parametrize("call", list(SWEEP))
def test_every_call_that_draws_is_accounted_for(field, triangulation, call):
    fig, ax = plt.subplots()
    _draw(ax, call, field, triangulation)

    assert _layers(fig) == SWEEP[call]
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_a_table_is_not_a_chart_and_the_message_says_so():
    # `ax.table` draws, but not marks: the figure is reported as empty, which
    # is accurate, rather than as a chart maidr cannot read, which would send
    # a user looking for a plot type that was never there.
    fig, ax = plt.subplots()
    ax.table(cellText=[["a", "b"], ["c", "d"]], loc="center")

    with pytest.raises(UnsupportedPlotError) as raised:
        FigureManager.get_maidr(fig)
    assert raised.value.is_empty
    assert "no plots on it yet" in str(raised.value)
    assert len(maidr.render(fig)._repr_html_()) > 0

"""A filled band from the baseline is an area chart; a band between two is not.

``Axes.fill_between`` was unregistered entirely, so a filled area chart drew
and read as a static image. ``stackplot`` already emitted an area layer for
the same picture (#356), which made the gap arbitrary from a reader's side:
the same chart read or did not depending on which function drew it.

The part that needed deciding rather than writing is that ``fill_between``
draws two different charts.

``fill_between(x, y1)`` fills from zero up to a curve. That is an area chart,
and it measures what a one-series ``stackplot`` band measures -- a magnitude
per position, from a baseline the reader can assume.

``fill_between(x, lo, hi)`` draws the **gap**. Its content is the distance
between the edges, not the height of either, so read as an area it would
announce ``hi`` as a magnitude and drop ``lo`` without saying so. The honest
reading is an estimate and its interval, and there is no estimate on the
chart -- inventing the midpoint would put a number in the reader's ear that
nothing drew. So it stays unregistered, and the figure keeps the static image
it had, rather than gaining a confident description of a different chart
(#339).

That decision is what these pin. The registration is the easy half.
"""

from __future__ import annotations

import json

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


X = np.arange(5)
Y = np.array([1.0, 3.0, 2.0, 5.0, 4.0])


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


def _layer(fig) -> dict:
    """The one emitted layer's schema, as JSON round-trips it."""
    schema = json.loads(json.dumps(FigureManager.get_maidr(fig)._flatten_maidr()))
    return schema["subplots"][0][0]["layers"][0]


def test_a_band_from_the_baseline_is_an_area():
    """The registration, and the values it carries.

    Read against the arguments the caller passed rather than against the
    drawn polygon: `fill_between` closes its outline, running forward along
    the curve and back along the baseline with the endpoints repeated, so a
    reading taken from the artist would have to undo the closure first.
    """
    fig, ax = plt.subplots()
    ax.set_xlabel("t")
    ax.set_ylabel("v")
    ax.fill_between(X, Y)

    assert _layers(fig) == [PlotType.AREA]

    layer = _layer(fig)
    assert layer["type"] == "area"
    assert layer["axes"]["x"]["label"] == "t"
    assert layer["axes"]["y"]["label"] == "v"

    points = layer["data"][0]
    assert [point["x"] for point in points] == X.tolist()
    assert [point["y"] for point in points] == Y.tolist()


def test_an_explicit_zero_baseline_is_the_same_chart():
    """``y2=0`` is what the default already means, written out."""
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, 0)

    assert _layers(fig) == [PlotType.AREA]
    assert [point["y"] for point in _layer(fig)["data"][0]] == Y.tolist()


def test_a_band_between_two_curves_is_declined():
    """The decision, not an oversight.

    Its content is the gap. Announced as an area, ``hi`` becomes a magnitude
    and ``lo`` disappears -- a complete, confident description of a chart
    nobody drew. The alternative reading needs an estimate the chart does not
    carry.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y - 1, Y + 1)

    assert _layers(fig) == []


def test_a_constant_second_edge_is_declined_too():
    """The same problem in miniature, and the one a zero-check alone misses.

    ``fill_between(x, y, 2)`` measures heights from two, and an area layer
    would announce them as though measured from zero. Nothing in the reading
    would mention the baseline it actually used.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, 2)

    assert _layers(fig) == []


def test_a_line_keeps_its_band_unannounced_rather_than_misannounced():
    """The common idiom, and what it still costs.

    A line with a confidence ribbon is the case a reader loses most from,
    and it is deliberately not fixed here: the band is an interval around
    the line, which is an `error_bar` reading rather than an area one, and
    matching a band to a line is a heuristic worth settling before writing.

    What is pinned is that it does not silently gain a *wrong* layer in the
    meantime -- the figure reads as the line it always did.
    """
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 1, Y + 1, alpha=0.3)

    assert _layers(fig) == [PlotType.LINE]


def test_a_masked_fill_is_declined():
    """``where=`` draws several bands, and an area layer is one series.

    ``fill_between(x, y, where=y > 0)`` fills only where the mask holds and
    leaves the chart blank elsewhere -- matplotlib returns three paths for
    the eight-point series below, against one for the unmasked call.

    Announced as an area it would report every position as filled, gaps
    included. That is the same thing declining the two-curve form avoids,
    so it is declined the same way rather than described partially: a reader
    walking left to right would otherwise cross a gap without being told
    there was one.
    """
    signed = np.array([1.0, 3.0, -2.0, 5.0, -4.0, 2.0, 6.0, 1.0])
    positions = np.arange(len(signed))

    fig, ax = plt.subplots()
    ax.fill_between(positions, signed, where=signed > 0)

    assert _layers(fig) == []


def test_a_mask_that_holds_everywhere_is_not_a_mask():
    """It draws the single band the default draws, and reads as one.

    Declining on the presence of the argument rather than on what it says
    would refuse a chart that is identical to one already accepted.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, where=np.ones_like(Y, dtype=bool))

    assert _layers(fig) == [PlotType.AREA]
    assert [point["y"] for point in _layer(fig)["data"][0]] == Y.tolist()


def test_an_array_of_zeros_is_the_default_spelled_out():
    """``fill_between(x, y, np.zeros_like(x))`` is the same chart as omitting it.

    Only a *non-zero* edge changes what the heights are measured from, so
    testing for a scalar zero alone would decline a chart identical to one
    already accepted.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, np.zeros_like(X, dtype=float))

    assert _layers(fig) == [PlotType.AREA]
    assert [point["y"] for point in _layer(fig)["data"][0]] == Y.tolist()


def test_the_pyplot_entry_point_is_covered_too():
    """``plt.fill_between`` reaches the same bound method through ``gca()``."""
    fig = plt.figure()
    fig.add_subplot()
    plt.fill_between(X, Y)

    assert _layers(fig) == [PlotType.AREA]


def test_fill_betweenx_is_the_same_chart_turned_over():
    """The shared axis is y and the magnitude runs along x.

    What a band measures does not change with which way it is drawn, so it
    is the same layer type -- and the arguments have to be read from their
    own parameter names rather than by position, since `x1` sits where `y1`
    does.

    Which axis each number is *read against* does change, and that is the one
    thing "turned over" costs: the two `AxisConfig` entries are exchanged, so
    the positions are announced under the y axis' title and the magnitudes
    under the x axis' (#566). The data stays where the trace sonifies it,
    which is why the two assertions below are unchanged. See
    `tests/core/plot/test_sideways_area.py`.
    """
    fig, ax = plt.subplots()
    ax.set_xlabel("horizontal")
    ax.set_ylabel("vertical")
    ax.fill_betweenx(X, Y)

    assert _layers(fig) == [PlotType.AREA]

    points = _layer(fig)["data"][0]
    assert [point["x"] for point in points] == X.tolist()
    assert [point["y"] for point in points] == Y.tolist()

    axes = _layer(fig)["axes"]
    assert (axes["x"]["label"], axes["y"]["label"]) == ("vertical", "horizontal")


def test_a_stackplot_still_reads_as_a_stack():
    """The thing most at risk: `stackplot` draws its bands through here.

    It calls `fill_between` once per band and reads the series itself, so a
    stacked chart could gain one area layer per band on top of its stack --
    every band described twice, once as its own value and once as a running
    total.

    Two things stop that, and it is worth being exact about which does the
    work, because the obvious answer is not the one that fires. The recursion
    guard would catch it, but never gets the chance: `stackplot` draws every
    band with two explicit edges (`fill_between(x, stack[i], stack[i + 1])`),
    so the baseline test declines them first. Removing the guard alone leaves
    this passing.

    Asserted on the outcome for that reason. It is the outcome that matters,
    and pinning it to one mechanism would make the test a description of
    matplotlib's `stackplot` rather than of this package.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, Y, Y + 1)

    assert _layers(fig) == [PlotType.STACKED_AREA]
    assert len(_layer(fig)["data"]) == 2


def test_a_scalar_curve_is_declined():
    """`fill_between(x, 3)` is a horizontal band, not a series.

    Matplotlib broadcasts the scalar across the positions. Pairing the two
    by index would describe a one-point chart out of a five-point one, and
    the count is the only thing that would have looked wrong.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, 3)

    assert _layers(fig) == []


def test_the_band_is_tagged_for_highlighting():
    """A selector per band, resolving to the drawn polygon.

    `AreaPlot` addresses its bands by the artist's own gid, which is
    assigned during extraction because the schema is built before the draw
    that would otherwise stamp one.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y)

    layer = _layer(fig)
    assert len(layer["selectors"]) == 1
    assert "maidr-" in layer["selectors"][0]


def test_a_label_is_carried_onto_the_points():
    """`label=` is what a legend would show, and names the series.

    Only when it is a string: matplotlib accepts other objects and renders
    them through `str()`, which is a decision about display rather than a
    name the reader should be handed.
    """
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, label="rainfall")

    assert all(point["z"] == "rainfall" for point in _layer(fig)["data"][0])


@pytest.mark.parametrize("method", ["fill_between", "fill_betweenx"])
def test_a_column_name_is_read_as_its_column(method):
    """``fill_between("x", "y", data=df)`` is the array spelling, by name.

    The call sits behind matplotlib's `_preprocess_data`, which looks each
    string up in ``data`` before drawing. The patch reads the arguments from
    outside that decorator, so it saw the names and emitted them as values: a
    one-point chart whose x was the string ``"x"`` and whose y was the string
    ``"y"``, reported without error over a chart that drew five numeric
    points (#712). Both spellings draw the same picture and have to read the
    same.
    """
    frame = pd.DataFrame({"x": X, "y": Y})

    fig_named, named = plt.subplots()
    getattr(named, method)("x", "y", data=frame)

    fig_arrays, arrays = plt.subplots()
    getattr(arrays, method)(frame["x"], frame["y"])

    assert _layers(fig_named) == [PlotType.AREA]
    assert _layer(fig_named)["data"] == _layer(fig_arrays)["data"]
    assert [point["y"] for point in _layer(fig_named)["data"][0]] == Y.tolist()


def test_a_named_second_edge_and_mask_are_read_by_name_too():
    """The declines resolve their arguments as well, and still decide.

    ``y2="zeros"`` names a column of zeros, which is the default baseline
    spelled out, and ``where="everywhere"`` names a mask that holds at every
    position, which is no mask: both are the chart the bare call draws and
    read as one. Left as names, each was an unreadable string and the chart
    was declined outright. A column that *is* a mask still declines, so
    resolving the name changes what is read and not whether the rule applies.
    """
    frame = pd.DataFrame(
        {
            "x": X,
            "y": Y,
            "zeros": np.zeros_like(Y),
            "everywhere": np.ones_like(Y, dtype=bool),
            "gap": Y > 2,
        }
    )

    fig_zero, zero = plt.subplots()
    zero.fill_between("x", "y", "zeros", data=frame)

    fig_everywhere, everywhere = plt.subplots()
    everywhere.fill_between("x", "y", where="everywhere", data=frame)

    fig_gap, gap = plt.subplots()
    gap.fill_between("x", "y", where="gap", data=frame)

    assert _layers(fig_zero) == [PlotType.AREA]
    assert _layers(fig_everywhere) == [PlotType.AREA]
    assert _layers(fig_gap) == []

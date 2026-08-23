"""A plotly parallel coordinates plot produced a figure with no layers.

`go.Parcoords` draws one polyline per observation crossing a row of vertical
axes, each axis a different variable. `maidr/plotly/` had no handling for it,
so it fell through `_extract_plots` to `PlotlyPlotFactory`, which returned
`None` (#627). The core has drawn it since xability/maidr's
`TraceType.PARALLEL`.

The payload is a line's -- a list of series, each a list of points -- because
`ParallelTrace` extends `LineTrace`. What the trace adds is the reason the
chart exists: the columns are not one scale, so a value is pitched against
*its own* axis rather than against the layer. Nothing here has to arrange
that; it only has to hand over the columns in the order they are drawn, and
name them.

Measured in Chromium, which decided two things this file asserts:

  * **There is nothing to highlight.** A two-axis `go.Parcoords` renders its
    observations to WebGL: the page holds three `<canvas>` elements, and the
    two `<path>`s inside `.parcoords` are axis furniture rather than
    observations.
  * **plotly truncates ragged dimensions.** Given columns of 3 and 2 values,
    `gd._fullData[0].dimensions` reported `_length: 2` for *both*, and the
    longer axis was scaled to its first two values. The third observation is
    not drawn at all.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

CARS = [
    {"label": "MPG", "values": [21.0, 22.8, 18.7]},
    {"label": "HP", "values": [110, 93, 175]},
    {"label": "Weight", "values": [2.62, 2.32, 3.44]},
]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _rows(layer: dict) -> list[list[tuple]]:
    """Each observation as ``(axis name, value)`` pairs."""
    return [[(point["x"], point["y"]) for point in row] for row in layer["data"]]


def test_a_parcoords_is_read_as_a_parallel_coordinates_layer() -> None:
    """The reproduction, and the type it becomes."""
    (layer,) = _layers(go.Figure([go.Parcoords(dimensions=CARS)]))

    assert layer["type"] is PlotType.PARALLEL


def test_an_observation_is_a_series_across_the_axes() -> None:
    """The payload a `LineTrace` takes, transposed out of the columns.

    plotly declares a parcoords by *column* -- one `dimensions` entry per
    variable, each holding every observation's value -- and the core reads it
    by *row*, one series per polyline. Getting this transposed would announce
    three observations of one variable as one observation of three.
    """
    (layer,) = _layers(go.Figure([go.Parcoords(dimensions=CARS)]))

    assert _rows(layer) == [
        [("MPG", 21.0), ("HP", 110), ("Weight", 2.62)],
        [("MPG", 22.8), ("HP", 93), ("Weight", 2.32)],
        [("MPG", 18.7), ("HP", 175), ("Weight", 3.44)],
    ]


def test_each_point_names_the_axis_it_sits_on() -> None:
    """What a reader is told on arriving at a value.

    The axis name is per *point*, not per layer, because that is the whole
    difference from a line chart: a line's columns are samples of one
    quantity and a parallel plot's are different quantities entirely.
    """
    (layer,) = _layers(go.Figure([go.Parcoords(dimensions=CARS)]))

    assert [point["x"] for point in layer["data"][0]] == ["MPG", "HP", "Weight"]


def test_a_hidden_dimension_is_not_a_column() -> None:
    """`visible: False` draws no axis, so announcing it invents one.

    Measured: with the middle dimension hidden, the drawn axis titles were
    `["A", "B"]` and `gd._fullData[0].dimensions[1]._length` was `null`. A
    reader arrowing across would otherwise pass through a variable that is
    not on the chart.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcoords(
                    dimensions=[
                        {"label": "A", "values": [1, 2]},
                        {"label": "Hidden", "values": [7, 8], "visible": False},
                        {"label": "B", "values": [3, 4]},
                    ]
                )
            ]
        )
    )

    assert _rows(layer) == [[("A", 1), ("B", 3)], [("A", 2), ("B", 4)]]


def test_ragged_dimensions_are_read_to_the_shortest() -> None:
    """Which is what plotly draws, not a defensive choice.

    Measured on columns of 3 and 2 values: `_length` came back as 2 for
    *both* dimensions and the longer axis was scaled to its first two values.
    The third observation has no line, so emitting it would announce one that
    is not there.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcoords(
                    dimensions=[
                        {"label": "A", "values": [1, 2, 3]},
                        {"label": "B", "values": [4, 5]},
                    ]
                )
            ]
        )
    )

    assert _rows(layer) == [[("A", 1), ("B", 4)], [("A", 2), ("B", 5)]]


def test_an_unnamed_axis_is_navigable_by_its_position() -> None:
    """plotly draws it with a blank title, which a reader cannot navigate by.

    The same answer a `dotchart` with no labels gives: positions are not
    names, but a reader with nothing at all cannot tell one axis from the
    next. Both spellings of "unnamed" are covered -- absent and empty --
    because plotly accepts either.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcoords(
                    dimensions=[
                        {"values": [1, 2]},
                        {"label": "", "values": [3, 4]},
                        {"label": "C", "values": [5, 6]},
                    ]
                )
            ]
        )
    )

    assert [point["x"] for point in layer["data"][0]] == ["1", "2", "C"]


def test_the_axes_say_what_the_names_and_the_numbers_are() -> None:
    """A parcoords draws no cartesian axes, so neither name is in the layout.

    Reading `layout.xaxis` would take some other trace's titles, or the
    generic fallback where the author had in fact named these. The words are
    the trace's own vocabulary: `ParallelTrace` asks where a value sits on
    its own *axis*.
    """
    (layer,) = _layers(go.Figure([go.Parcoords(dimensions=CARS)]))

    assert layer["axes"]["x"]["label"] == "Axis"
    assert layer["axes"]["y"]["label"] == "Value"


def test_a_parcoords_is_read_but_not_addressed() -> None:
    """A stated limit, not an oversight.

    plotly renders the observations to WebGL -- measured, three `<canvas>`
    elements and no per-observation SVG element. A `ParallelTrace` resolves
    one selector per observation and there is nothing in the document that is
    one, so the layer ships without a highlight and keeps its audio, braille
    and text: the outcome #145 established for a layer with nothing to point
    at.
    """
    (layer,) = _layers(go.Figure([go.Parcoords(dimensions=CARS)]))

    assert "selectors" not in layer


def test_a_parcoords_with_no_columns_carries_no_observations() -> None:
    """Nothing is drawn, so there is nothing to read.

    The layer itself still reaches the schema with an empty payload, which is
    the #421 ghost -- and *not* something this trace type introduced: an
    empty `go.Pie`, `go.Sankey` and `go.Scatterpolar` each emit one too,
    because the `draws_marks()` guard that filters an empty scatter only
    covers the line and area families. Filed separately rather than patched
    here, so the four are fixed in one place; this pins what the payload is
    meanwhile.
    """
    for empty in (
        go.Parcoords(dimensions=[]),
        go.Parcoords(dimensions=[{"label": "A"}]),
    ):
        (layer,) = _layers(go.Figure([empty]))
        assert layer["data"] == []

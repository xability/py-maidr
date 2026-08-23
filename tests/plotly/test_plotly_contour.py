"""A plotly contour plot produced a figure with no layers.

`go.Contour` draws a scalar field as the curves along which it is constant.
`maidr/plotly/` had no handling for it, so it fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None` (#627). The core has had
`TraceType.CONTOUR` for this shape since the matplotlib side was read (#539).

**The curves are not in the trace.** Plotly ships a grid and a level spacing
and traces the curves in the browser, so reading this chart means running the
same marching squares here -- `contourpy`, which is what matplotlib traces its
own contours with.

Two independent implementations agreeing is not a contract, so what they agree
about was measured. Across 33 fields and 207 levels -- random sums of
gaussians, a saddle, a monkey saddle, ripples, a staircase, noise -- plotly and
`contourpy` **always** found the same number of curves in a level, and put them
in the same order all but 18 times, five of those on ordinary two-peaked
gaussian fields. So the curves are the same curves, and it is only *which drawn
path is which curve* that is sometimes unanswerable -- which is exactly what
the selectors turn on, and why a layer with an island anywhere ships without
one.

Plotly's level list was pinned the same way: it steps `start`, `start + size`,
... while the level is below `end + size / 10`. Neither `<= end` (which drops
a level plotly draws at `start=0.2, end=0.8, size=0.05`) nor `end + size / 2`
(which adds one plotly does not draw at `start=0, end=0.9, size=0.5`) fits.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: A field with one peak, small enough to read by eye. At level 0.5 it draws a
#: single diamond around the middle cell.
ONE_PEAK = [
    [0, 0, 0],
    [0, 1, 0],
    [0, 0, 0],
]

#: The same field with a second peak. At level 0.5 it draws two diamonds, so
#: one level owns two curves -- the case whose drawn order is plotly's own.
TWO_PEAKS = [
    [0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0],
    [0, 0, 0, 0, 0],
]

#: What both fields' single-cell peaks look like at level 0.5: the diamond
#: whose corners are the midpoints of the four edges around the peak.
DIAMOND = [(1.0, 0.5), (1.5, 1.0), (1.0, 1.5), (0.5, 1.0), (1.0, 0.5)]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _curve(series: list[dict]) -> list[tuple[float, float]]:
    """One series as ``(x, y)`` pairs, rounded past floating-point noise."""
    return [(round(point["x"], 6), round(point["y"], 6)) for point in series]


def _levels(layer: dict) -> list[float]:
    """The level each series runs at, in emission order."""
    return [series[0]["level"] for series in layer["data"]]


def _contour(z: list, **contours: object) -> go.Contour:
    """A contour of ``z`` at explicit levels, drawn as lines."""
    return go.Contour(z=z, contours=dict(coloring="lines", **contours))


def test_a_contour_is_read_as_a_contour_layer() -> None:
    """The reproduction, and the type it becomes."""
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5)))

    assert layer["type"] is PlotType.CONTOUR


def test_a_curve_is_traced_from_the_grid_the_trace_ships() -> None:
    """The trace carries a grid and a spacing; the curve is computed here."""
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5)))

    assert [_curve(series) for series in layer["data"]] == [DIAMOND]


def test_a_level_with_two_islands_is_two_series() -> None:
    """One series per curve, which is what the grammar's unit is.

    A field with two peaks crosses a level twice. Read as one series the two
    islands would be joined by a straight run between the peaks -- a curve
    announced across ground the field never took, which is the defect
    xability/maidr#1079 describes for a gappy line.
    """
    (layer,) = _layers(go.Figure(_contour(TWO_PEAKS, start=0.5, end=0.5, size=0.5)))

    assert [_curve(series) for series in layer["data"]] == [
        DIAMOND,
        [(3.0, 0.5), (3.5, 1.0), (3.0, 1.5), (2.5, 1.0), (3.0, 0.5)],
    ]


def test_every_point_of_a_curve_carries_its_level() -> None:
    """`ContourPoint` puts the level on the point, so a flat reader has it.

    It is constant down a curve and carried on every point of it, the way `z`
    is -- the grammar's unit is the point, and a producer emitting a flat list
    has nowhere else to put it.
    """
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5)))

    (series,) = layer["data"]
    assert {point["level"] for point in series} == {0.5}


def test_a_level_past_the_end_is_not_stepped_to() -> None:
    """``end + size / 2`` would add one plotly does not draw.

    From 0 in steps of 0.5 with ``end`` at 0.9, plotly draws 0 and 0.5 and
    stops. The field peaks at 2, so a level at 1.0 would cross it plainly --
    it is absent because it is not declared, not because nothing reached it.
    """
    tall = [[0, 0, 0], [0, 2, 0], [0, 0, 0]]

    (layer,) = _layers(go.Figure(_contour(tall, start=0, end=0.9, size=0.5)))

    assert _levels(layer) == [0.0, 0.5]


def test_a_level_that_accumulates_a_hair_past_the_end_is_still_stepped_to() -> None:
    """``<= end`` would drop it, and plotly draws it.

    Stepping 0.05 from 0.2 lands on ``0.8000000000000002`` rather than 0.8,
    and plotly's thirteenth group is that level -- measured. The levels are
    accumulated here for exactly this reason, so the number announced, the
    number handed to the tracer and the number plotly drew are one number.
    """
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.2, end=0.8, size=0.05)))

    assert len(_levels(layer)) == 13
    assert _levels(layer)[-1] == 0.8000000000000002


def test_a_spec_written_backwards_is_read_the_way_plotly_draws_it() -> None:
    """Plotly swaps ``start`` and ``end`` rather than drawing nothing."""
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=2.5, end=0.5, size=1.0)))

    assert _levels(layer) == [0.5]


def test_a_level_the_field_never_reaches_still_counts_for_the_selector() -> None:
    """Plotly gives it a `g.contourlevel` holding no path at all.

    Measured. So the groups follow the *declared* levels while the series
    follow the drawn ones, and a series has to name its level's position
    rather than its own -- here the third of three levels, from the only one
    that draws.
    """
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=-1.5, end=0.5, size=1.0)))

    assert _levels(layer) == [0.5]
    assert layer["selectors"] == [
        ".subplot.xy .contourlayer > g.contour:nth-of-type(1) "
        "g.contourlevel:nth-of-type(3) path:nth-of-type(1)"
    ]


def test_a_layer_whose_levels_each_draw_one_curve_is_addressable() -> None:
    """One selector per series, naming the level group that draws it.

    With one curve in the level there is one path in its group, so the mapping
    is forced rather than chosen -- and the sweep found no field where plotly
    and `contourpy` disagreed about *how many* curves a level has.
    """
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.3, end=0.7, size=0.2)))

    prefix = ".subplot.xy .contourlayer > g.contour:nth-of-type(1) "
    assert layer["selectors"] == [
        f"{prefix}g.contourlevel:nth-of-type({index}) path:nth-of-type(1)"
        for index in (1, 2, 3)
    ]


def test_a_layer_with_an_island_ships_without_a_highlight() -> None:
    """Plotly's order for a level's curves is its own, and not derivable.

    Measured across 33 fields and 207 levels: 18 disagreements about the order
    of the curves within a level, five of them on ordinary two-peaked gaussian
    fields rather than contrived ones. A positional selector would resolve to
    a real element and to the wrong one -- and the core parses the resolved
    path to place the per-point highlights, so every point of that series
    would land on an island the reader is not on.

    So the layer keeps its audio, braille and text and claims no highlight,
    the outcome #145 established.
    """
    (layer,) = _layers(go.Figure(_contour(TWO_PEAKS, start=0.5, end=0.5, size=0.5)))

    assert len(layer["data"]) == 2
    assert "selectors" not in layer


def test_a_filled_contour_with_its_lines_off_has_nothing_to_point_at() -> None:
    """Measured: plotly then writes no `g.contourlevel` at all.

    The layer still reads. A band's boundary is exactly where the level curve
    runs, so what is announced is true of the drawing -- only the element to
    outline is missing.
    """
    figure = go.Figure(
        go.Contour(z=ONE_PEAK, contours=dict(start=0.5, end=0.5, size=0.5, showlines=False))
    )

    (layer,) = _layers(figure)

    assert [_curve(series) for series in layer["data"]] == [DIAMOND]
    assert "selectors" not in layer


def test_showlines_off_under_another_coloring_still_draws_the_curves() -> None:
    """`showlines` is only honoured for `coloring: "fill"` -- measured.

    Under `heatmap` the level groups are written whatever it says, so reading
    it as "no lines" would drop a highlight the chart does have.
    """
    figure = go.Figure(
        go.Contour(
            z=ONE_PEAK,
            contours=dict(
                start=0.5, end=0.5, size=0.5, coloring="heatmap", showlines=False
            ),
        )
    )

    (layer,) = _layers(figure)

    assert len(layer["selectors"]) == 1


def test_auto_levels_are_declined() -> None:
    """Plotly's rule for picking them lives in plotly.js and was not derivable.

    Measured across nine z ranges, eight fit "round ``(max - min) / 15`` up to
    a 1/2/5x10ⁿ step" and a field spanning 0 .. 3 does not. Reading the chart
    at levels it does not draw would announce curves that are not there, so
    the trace is left unread until the rule is settled (#642).
    """
    assert _layers(go.Figure(go.Contour(z=ONE_PEAK))) == []


@pytest.mark.parametrize(
    ("contours", "extra"),
    [
        pytest.param({"start": 0.5}, {}, id="start-without-end-or-size"),
        pytest.param({"size": 0.5}, {}, id="size-alone"),
        pytest.param({"start": 0.5, "end": 1.5}, {}, id="no-size"),
        pytest.param({"start": 0.5, "end": 1.5, "size": 0}, {}, id="zero-size"),
        pytest.param(
            {"start": 0.5, "end": 1.5, "size": 0.5},
            {"autocontour": True},
            id="autocontour-overrides-the-spec",
        ),
        pytest.param(
            {
                "type": "constraint",
                "operation": ">",
                "value": 0.5,
                "start": 0.1,
                "end": 0.9,
                "size": 0.2,
            },
            {},
            id="a-constraint-is-a-region-not-a-set-of-levels",
        ),
    ],
)
def test_a_half_written_spec_is_declined(contours: dict, extra: dict) -> None:
    """Each of these leaves plotly picking the levels, or picking a chart.

    ``size: 0`` is replaced by plotly with a computed spacing, and
    ``autocontour: True`` overrides an otherwise complete spec -- both
    measured. A ``constraint`` contour draws one curve at ``value`` and means
    "the region beyond it", which is a different chart from a set of levels --
    and it is written here *with* a full ``start``/``end``/``size`` on purpose,
    because plotly ignores them (measured: one group, at 0.5) while anything
    reading them would announce five levels the chart does not draw.
    """
    assert _layers(go.Figure(go.Contour(z=ONE_PEAK, contours=contours, **extra))) == []


def test_a_grid_with_no_coordinates_is_read_at_its_indices() -> None:
    """Which is what plotly draws it at."""
    (layer,) = _layers(go.Figure(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5)))

    assert _curve(layer["data"][0]) == DIAMOND


def test_x0_and_dx_place_the_grid() -> None:
    """Plotly's other way of writing evenly spaced coordinates."""
    figure = go.Figure(
        go.Contour(
            z=ONE_PEAK,
            x0=10,
            dx=2,
            y0=100,
            dy=5,
            contours=dict(coloring="lines", start=0.5, end=0.5, size=0.5),
        )
    )

    (layer,) = _layers(figure)

    assert _curve(layer["data"][0]) == [
        (12.0, 102.5),
        (13.0, 105.0),
        (12.0, 107.5),
        (11.0, 105.0),
        (12.0, 102.5),
    ]


def test_transpose_turns_the_grid_over_and_leaves_the_coordinates() -> None:
    """Measured on an asymmetric field: plotly draws the transposed reading.

    The peak sits in column 1 of a 2x3 grid; transposed it is in row 1 of a
    3x2 one, which puts the curve somewhere else entirely.
    """
    z = [[0, 1, 0], [0, 0, 0]]

    plain = _layers(go.Figure(_contour(z, start=0.5, end=0.5, size=0.5)))
    turned = _layers(
        go.Figure(go.Contour(z=z, transpose=True, contours=dict(start=0.5, end=0.5, size=0.5)))
    )

    assert plain != []
    # Transposed the grid is 3x2 with the peak on its edge, so the level
    # crosses it differently -- the point is that the two readings differ.
    assert [_curve(s) for s in plain[0]["data"]] != [_curve(s) for s in turned[0]["data"]]


def test_a_hole_in_the_grid_stops_the_curves_the_way_plotly_does() -> None:
    """A missing z is a hole in the field, not a reason to decline the trace.

    Measured on a field with its peak punched out: plotly and the tracer both
    dropped the level the hole ate and agreed on the rest.
    """
    z = [[0, 0, 0], [0, None, 0], [0, 0, 0]]

    assert _layers(go.Figure(_contour(z, start=0.5, end=0.5, size=0.5))) == []


@pytest.mark.parametrize(
    ("z", "extra"),
    [
        pytest.param([], {}, id="no-grid"),
        pytest.param([[1, 2, 3]], {}, id="one-row"),
        pytest.param([[1], [2], [3]], {}, id="one-column"),
        pytest.param([[0, 0, 0], [0, 1], [0, 0, 0]], {}, id="ragged"),
        pytest.param(
            ONE_PEAK, {"x": ["a", "b", "c"]}, id="a-category-is-not-a-position"
        ),
        pytest.param(ONE_PEAK, {"x": [0, 1]}, id="an-x-that-misses-the-width"),
    ],
)
def test_a_grid_that_cannot_be_traced_forms_no_layer(z: list, extra: dict) -> None:
    """Each of these has no field to trace, or none that was measured.

    Marching squares needs a cell, so it needs two rows and two columns. A
    **categorical** x is declined for a reason of its own: a contour crosses
    *between* columns, so a curve sits a fraction of the way from one category
    to the next -- a position a category name cannot express, and which naming
    the nearer category would misreport.
    """
    figure = go.Figure(
        go.Contour(z=z, contours=dict(start=0.5, end=0.5, size=0.5), **extra)
    )

    assert _layers(figure) == []


def test_a_contour_names_the_axes_the_author_titled() -> None:
    """It is a cartesian trace, so its axis titles are the layout's."""
    figure = go.Figure(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5))
    figure.update_layout(xaxis_title="Easting", yaxis_title="Northing")

    (layer,) = _layers(figure)

    assert layer["axes"]["x"]["label"] == "Easting"
    assert layer["axes"]["y"]["label"] == "Northing"


def test_two_contours_on_one_subplot_address_their_own_groups() -> None:
    """Plotly appends one `g.contour` per trace to the subplot's layer."""
    figure = go.Figure(
        [
            _contour(ONE_PEAK, start=0.5, end=0.5, size=0.5),
            _contour(ONE_PEAK, start=0.5, end=0.5, size=0.5),
        ]
    )

    first, second = _layers(figure)

    assert "g.contour:nth-of-type(1)" in first["selectors"][0]
    assert "g.contour:nth-of-type(2)" in second["selectors"][0]


def test_a_histogram2dcontour_shifts_the_group_index() -> None:
    """It draws into the same `contourlayer` -- measured.

    Counting only the contour traces would hand this one group 1, which is the
    histogram's, and the highlight would land on a chart the reader is not
    reading. maidr renders no layer for the histogram itself, so it is only
    ever counted, never emitted.
    """
    figure = go.Figure(
        [
            go.Histogram2dContour(x=[0, 1, 2, 1, 0], y=[0, 1, 2, 0, 1]),
            _contour(ONE_PEAK, start=0.5, end=0.5, size=0.5),
        ]
    )

    contours = [layer for layer in _layers(figure) if layer["type"] is PlotType.CONTOUR]

    assert len(contours) == 1
    assert "g.contour:nth-of-type(2)" in contours[0]["selectors"][0]


def test_a_contour_on_a_second_subplot_is_scoped_to_it() -> None:
    """Two subplots each hold a `contourlayer`, so the prefix separates them."""
    from plotly.subplots import make_subplots

    figure = make_subplots(rows=1, cols=2)
    figure.add_trace(go.Bar(x=["a"], y=[1]), row=1, col=1)
    figure.add_trace(_contour(ONE_PEAK, start=0.5, end=0.5, size=0.5), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    (contour_layer,) = grid[0][1]["layers"]
    assert contour_layer["selectors"][0].startswith(".subplot.x2y2 ")


def test_a_contour_with_no_grid_forms_no_layer() -> None:
    """Nothing is drawn, so there is nothing to read (#636)."""
    assert _layers(go.Figure(_contour([], start=0.5, end=0.5, size=0.5))) == []


def test_a_grid_that_cannot_be_traced_is_declined_outright() -> None:
    """Rather than left for the tracer to raise about.

    ``contourpy`` rejects both of these -- a coordinate array that does not
    describe the grid, and a grid with no cell in it -- and
    :meth:`PlotlyContourPlot._extract_plot_data` catches that, so the layer is
    dropped either way and no rendered figure can tell the two apart. They are
    still decisions rather than accidents: plotly draws *something* from a
    short ``x`` (measured), and declining says this reader will not guess
    what. Asserted here because that is the only place the difference shows.
    """
    from maidr.plotly.contour import _grid

    assert _grid({"z": ONE_PEAK, "x": [0, 1]}) is None
    assert _grid({"z": ONE_PEAK, "y": [0, 1, 2, 3]}) is None
    assert _grid({"z": [[1, 2, 3]]}) is None
    assert _grid({"z": [[1], [2], [3]]}) is None
    assert _grid({"z": ONE_PEAK, "x": [0, 1, 2]}) is not None


def test_a_spacing_that_asks_for_a_billion_levels_is_declined() -> None:
    """A schema must never cost the render (#421, #636).

    ``size`` is the author's, so this spec is writable, and tracing a billion
    levels would hang the export rather than produce a chart. Reached by
    calling the level list directly: a test that actually built one would be
    the hang it is guarding against.
    """
    from maidr.plotly.contour import declared_levels

    runaway = {"contours": {"start": 0, "end": 1, "size": 1e-9}}
    ordinary = {"contours": {"start": 0, "end": 1, "size": 0.5}}

    assert declared_levels(runaway) is None
    assert declared_levels(ordinary) == [0, 0.5, 1.0]


def test_a_tracer_that_raises_costs_one_layer_and_not_the_figure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building a schema must never take the render down (#421, #636).

    Every reason a *chart* declines is decided before contourpy is asked
    anything, so this stands in for the one case left: an environment that is
    not what it was measured to be. The **tracing** is where the work happens,
    so the tracing -- not only the generator's construction -- is what has to
    be guarded, or the exception escapes `render()` and the whole figure's
    schema goes with it. The bar beside it is the witness: it still arrives.
    """
    import contourpy

    class _Broken:
        def lines(self, level: float) -> tuple:
            raise RuntimeError("no marching squares here")

    monkeypatch.setattr(contourpy, "contour_generator", lambda **_: _Broken())

    figure = go.Figure(
        [
            go.Bar(x=["a"], y=[1]),
            _contour(ONE_PEAK, start=0.5, end=0.5, size=0.5),
        ]
    )

    assert [layer["type"] for layer in _layers(figure)] == [PlotType.BAR]

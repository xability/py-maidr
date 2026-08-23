"""A plotly contour plot produced a figure with no layers.

`go.Contour` draws a scalar field as the curves along which it is constant.
`maidr/plotly/` had no handling for it, so it fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None` (#627). The core has had
`TraceType.CONTOUR` for this shape since the matplotlib side was read (#539).

**Neither the curves nor, usually, the levels are in the trace.** Plotly ships
a grid, works out where to cut it, and traces the curves in the browser. So
reading this chart means doing both here: the levels by the rule below, the
curves with `contourpy` -- what matplotlib traces its own contours with.

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

**Where `start` and `end` come from** was #642's open problem, and it turned
out to be one comparison rather than a missing formula. Plotly divides the
field's range by `ncontours` (15 by default) and rounds that up to a 1/2/5x10ⁿ
step -- *strictly*, which is why a field spanning `0 .. 3` looked
unreproducible: its rough step is exactly 0.2 and plotly draws 0.5 (#646).
`start` and `end` are then the first and last multiples strictly inside the
range, and if those cross -- an `ncontours` too small to fit one -- plotly puts
a single level at their midpoint. Measured against the drawn levels on **49
figures**: 26 z ranges from `0 .. 0.07` to `0 .. 1000`, positive, negative and
straddling, 8 explicit `ncontours` from 1 to 30, and 15 ranges picked for
landing on a binary tie. All 49 agree, level for level.
"""

from __future__ import annotations

import numpy as np
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
        go.Contour(
            z=ONE_PEAK, contours=dict(start=0.5, end=0.5, size=0.5, showlines=False)
        )
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


#: What plotly picks for `ONE_PEAK`, whose field runs 0 .. 1: a rough step of
#: ``1 / 15`` rounded up to 0.1, then the multiples of it strictly inside the
#: range. Measured -- and the same nine whichever way the author fails to name
#: both ends.
AUTOMATIC = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


@pytest.mark.parametrize(
    ("contours", "extra"),
    [
        pytest.param({}, {}, id="nothing-named-at-all"),
        pytest.param({"start": 0.5}, {}, id="a-start-without-an-end"),
        pytest.param({"end": 0.5}, {}, id="an-end-without-a-start"),
        pytest.param({"size": 0.25}, {}, id="a-size-alone"),
        pytest.param(
            {"start": 0.2, "end": 0.8, "size": 0.2},
            {"autocontour": True},
            id="autocontour-overrides-a-complete-spec",
        ),
    ],
)
def test_the_levels_plotly_picks_are_the_ones_read(
    contours: dict, extra: dict
) -> None:
    """#642's open problem, and it was one comparison rather than a formula.

    Plotly coerces `autocontour` to true whenever `start` or `end` is missing,
    so each of these has its levels picked for it -- measured, all five draw
    the same nine. The rule is a rough step of ``(zmax - zmin) / ncontours``
    rounded up to a 1/2/5x10ⁿ value, then the multiples of it strictly inside
    the range.

    What made it look unreproducible was the round-up: a field spanning
    ``0 .. 3`` gives a rough step of exactly ``0.2``, and plotly draws ``0.5``
    because its `roundUp` is strictly greater (#646). With that read
    correctly, 34 figures agree level for level.
    """
    figure = go.Figure(go.Contour(z=ONE_PEAK, contours=contours, **extra))

    assert _levels(_layers(figure)[0]) == pytest.approx(AUTOMATIC)


def test_two_named_ends_with_no_width_get_one_derived_for_them() -> None:
    """Not a decline: plotly keeps the ends and rounds a width up for them.

    Measured on ``start=0.2, end=0.8``: both a missing ``size`` and a zero one
    draw a width of 0.05, which is ``(0.8 - 0.2) / 15`` rounded up by the same
    rule an automatic contour uses.
    """
    figure = go.Figure(go.Contour(z=ONE_PEAK, contours={"start": 0.2, "end": 0.8}))
    zeroed = go.Figure(
        go.Contour(z=ONE_PEAK, contours={"start": 0.2, "end": 0.8, "size": 0})
    )

    expected = [0.2 + 0.05 * step for step in range(13)]
    assert _levels(_layers(figure)[0]) == pytest.approx(expected)
    assert _levels(_layers(zeroed)[0]) == pytest.approx(expected)


def test_ncontours_is_how_many_levels_are_aimed_for() -> None:
    """It divides the range before the round-up, rather than being obeyed.

    Measured on ``start=0.2, end=0.8`` with ``ncontours=4``: a width of 0.2,
    which is ``0.6 / 4`` rounded up, and four levels rather than the thirteen
    the default fifteen gives.
    """
    figure = go.Figure(
        go.Contour(z=ONE_PEAK, contours={"start": 0.2, "end": 0.8}, ncontours=4)
    )

    assert _levels(_layers(figure)[0]) == pytest.approx([0.2, 0.4, 0.6, 0.8])


@pytest.mark.parametrize(
    ("ncontours", "expected"),
    [
        pytest.param(2, [0.5], id="two"),
        pytest.param(3, [0.5], id="three"),
    ],
)
def test_a_step_too_wide_for_the_range_leaves_one_level_at_its_middle(
    ncontours: int, expected: list
) -> None:
    """Plotly's own fallback for an `ncontours` that fits nothing inside.

    With a step at least as wide as the field, the first multiple above the
    floor is already past the last one below the ceiling -- the two cross, and
    plotly puts a single level at their midpoint. Measured: over a field
    running 0 .. 1, both of these draw one level at 0.5, and over ``0 .. 100``
    an ``ncontours`` of 2 draws one at 50.
    """
    figure = go.Figure(go.Contour(z=ONE_PEAK, ncontours=ncontours))

    assert _levels(_layers(figure)[0]) == pytest.approx(expected)


#: Two fields whose range does not divide by its own step evenly in binary,
#: one landing at each end of the level list. Both ramp left to right, so
#: every level inside them draws exactly one line and the layer is
#: addressable.
RAMP_TO_ZERO = [[-0.3, -0.15, 0.0], [-0.3, -0.15, 0.0], [-0.3, -0.15, 0.0]]
NARROW_RAMP = [
    [0.008, 0.0085, 0.009],
    [0.008, 0.0085, 0.009],
    [0.008, 0.0085, 0.009],
]


def test_a_group_below_the_field_is_still_one_the_selectors_count() -> None:
    """``-0.3 / 0.05`` is -5.999999999999999, and plotly rounds it up to -6.

    So plotly's first level is ``-0.30000000000000004`` -- a hair *below* the
    floor of the field, and holding no curve because of it -- and it still
    gets a ``g.contourlevel`` of its own. Measured: six groups, the first with
    no path in it, the five curves in the ones after. Which is why the
    selectors here start at the second group rather than the first.

    A ceiling taken at face value answers -5 instead, starting the list at
    -0.25. That loses no curve, so nothing in the data would look wrong -- but
    every group index shifts by one, and each highlight lands on the level
    below the one being read. The test that keeps a level off the floor has to
    be exact for the same reason: ``start`` is ``-0.30000000000000004`` and
    the floor is -0.3, near enough that a tolerant comparison would call them
    equal and step past the group plotly drew.
    """
    (layer,) = _layers(go.Figure(_contour(RAMP_TO_ZERO)))

    assert _levels(layer) == pytest.approx([-0.25, -0.2, -0.15, -0.1, -0.05])
    assert [selector.split("contourlevel:")[1] for selector in layer["selectors"]] == [
        f"nth-of-type({group}) path:nth-of-type(1)" for group in range(2, 7)
    ]


def test_a_ceiling_only_exact_arithmetic_reaches_keeps_its_level() -> None:
    """``0.009 / 0.0001`` is 89.99999999999999, and plotly rounds it down to 90.

    So the top level is ``0.009000000000000001``, which sits 1.7e-18 from the
    field's ceiling: near enough that a tolerant comparison would call it a
    level *on* the ceiling and drop it, far enough that plotly's own exact
    test keeps it. Measured: ten groups, each holding a curve, the last at
    0.009.

    A floor taken at face value loses that same level from the other side --
    it answers 89, and the field ends at 0.0089 with nine levels.
    """
    (layer,) = _layers(go.Figure(_contour(NARROW_RAMP)))

    expected = [0.008 + 0.0001 * step for step in range(1, 11)]
    assert _levels(layer) == pytest.approx(expected)


def test_a_constraint_is_still_a_region_rather_than_a_set_of_levels() -> None:
    """The one spec that declines, and it declines for what it *is*.

    A ``constraint`` contour draws one curve at ``value`` and means "the
    region beyond it". It is written here *with* a full ``start``/``end``/
    ``size`` on purpose, because plotly ignores them -- measured, one group at
    0.5 -- while anything reading them would announce five levels the chart
    does not draw.
    """
    figure = go.Figure(
        go.Contour(
            z=ONE_PEAK,
            contours={
                "type": "constraint",
                "operation": ">",
                "value": 0.5,
                "start": 0.1,
                "end": 0.9,
                "size": 0.2,
            },
        )
    )

    assert _layers(figure) == []


def test_a_field_with_no_range_forms_no_layer() -> None:
    """A constant field has no step to divide out of it.

    Plotly does draw one group, at the constant value itself -- measured, a
    grid of 3s gets a single level at 3 -- but that level *is* the whole
    field, so it holds no curve and the group carries no path. The layer comes
    out empty either way, and #636's guard drops it.
    """
    assert _layers(go.Figure(go.Contour(z=[[3, 3, 3], [3, 3, 3], [3, 3, 3]]))) == []


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
        go.Figure(
            go.Contour(z=z, transpose=True, contours=dict(start=0.5, end=0.5, size=0.5))
        )
    )

    assert plain != []
    # Transposed the grid is 3x2 with the peak on its edge, so the level
    # crosses it differently -- the point is that the two readings differ.
    assert [_curve(s) for s in plain[0]["data"]] != [
        _curve(s) for s in turned[0]["data"]
    ]


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

    Counting only the ``contour`` traces would hand the second one group 1,
    which is the histogram's, and the highlight would land on a chart the
    reader is not reading. The two are numbered together because plotly
    appends both to the same layer, which is what
    :func:`~maidr.plotly.candlestick.layer_position` is told.
    """
    figure = go.Figure(
        [
            go.Histogram2dContour(x=[0, 1, 2, 1, 0], y=[0, 1, 2, 0, 1]),
            _contour(ONE_PEAK, start=0.5, end=0.5, size=0.5),
        ]
    )

    binned, declared = _layers(figure)

    assert "g.contour:nth-of-type(1)" in binned["selectors"][0]
    assert "g.contour:nth-of-type(2)" in declared["selectors"][0]


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


def test_a_runaway_spec_declines_rather_than_falling_back_to_automatic() -> None:
    """The decline has to reach the layer, not just the level list.

    Reading the levels is now two routes rather than one, and the author's
    route answers None for two unrelated reasons: they did not name their own
    levels, and they named a billion of them. Treating both as "then pick
    some" would read the chart above at nine levels of maidr's choosing --
    every one of them a level plotly does not draw here, on a chart whose
    author was explicit about which levels they wanted.

    Reached through the whole layer rather than the level list, because the
    level list is where the two reasons already look alike.
    """
    figure = go.Figure(_contour(ONE_PEAK, start=0, end=1, size=1e-9))

    assert _layers(figure) == []


def test_a_masked_field_picks_its_levels_from_what_is_left() -> None:
    """The range behind automatic levels reads through the mask.

    A hole is masked *and* NaN today, so filtering on `isfinite` and
    filtering on the mask cannot be told apart -- until a masked value is a
    finite one, which is what this arranges by masking the peak of an
    otherwise ordinary field by hand. Reading around the mask would put the
    range at 0 .. 1 and the levels at every tenth; reading through it puts
    the range at 0 .. 0.5, where plotly's rule gives multiples of 0.05.
    """
    from maidr.plotly.contour import automatic_levels

    field = np.ma.masked_values([[0.0, 0.5, 0.0], [0.5, 1.0, 0.5], [0.0, 0.5, 0.0]], 1.0)

    assert automatic_levels({}, field) == pytest.approx(
        [0.05 * step for step in range(1, 10)]
    )


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

"""
``so.Band`` and ``so.Range`` drew an interval per position and registered
nothing (#670).

Both are the same reading from two drawings, which is why one class takes
both and one test file covers them. Measured on ``seaborn 0.13.2`` over
three positions::

    so.Band(), so.Est()    one Polygon         lower forward, upper backward
    so.Range(), so.Est()   one LineCollection  one segment per position

Neither draws a centre of its own, and that is the reading rather than a gap
to fill in: ``ErrorBarPoint.y`` is optional precisely for "a band that draws
only bounds". A chart wanting the estimate adds ``so.Dot(), so.Agg()``
beside it, which registers as its own layer.

Two things are read from the drawing rather than from the caller's spelling,
and each is measured here:

**Orientation.** The two bounds at one position share the coordinate the
position sits on, so whichever of the pair matches names the position axis.
That is true of a polygon's paired vertices and a segment's two endpoints
alike, and it holds whether the caller wrote ``orient="y"`` or not.

**The split.** A colour-split ``Band`` leaves one polygon per level; a split
``Range`` leaves *one* collection carrying a colour per segment. Both are
named through the legend the way every other colour split is, which is
available here only because #672 taught the lookup to find a
``seaborn.objects`` legend -- it is the figure's, never the axes'.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn.objects as so

from maidr.core.enum import PlotType
import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two groups over three positions, with enough replicates to estimate.

    One observation per cell would leave ``so.Est()`` with no spread, and a
    zero-width interval is measurably not the case under test -- the band
    collapses to a line and the bars to points.
    """
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        [
            {"x": x, "y": base + x + rng.normal(0, 0.5), "g": group}
            for group, base in (("a", 1.0), ("b", 5.0))
            for x in range(3)
            for _ in range(8)
        ]
    )


def _layers(plot) -> list[dict]:
    """Every layer the drawn plot registered, as schemas."""
    return [layer.schema for layer in FigureManager.get_maidr(plot.plot()._figure).plots]


def _only(plot) -> dict:
    """The one layer this plot registered."""
    schemas = _layers(plot)
    assert len(schemas) == 1, f"expected one layer, got {len(schemas)}"
    return schemas[0]


def _band(**kwargs):
    return so.Plot(_frame(), **kwargs).add(so.Band(), so.Est())


def _range(**kwargs):
    return so.Plot(_frame(), **kwargs).add(so.Range(), so.Est())


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_the_mark_is_read_as_an_interval_rather_than_registering_nothing(make, mark):
    # The reproduction. Before this both marks fell through `_READINGS` and
    # the chart was a static image with nothing to navigate.
    schema = _only(make(x="x", y="y"))

    assert schema["type"] is PlotType.ERRORBAR
    assert len(schema["data"]) == 3


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_each_position_carries_bounds_and_no_estimate(make, mark):
    # Not an omission: neither mark draws a centre, so inventing one -- the
    # midpoint, say -- would announce a value the chart never plotted.
    points = _only(make(x="x", y="y"))["data"]

    assert [point["x"] for point in points] == [0.0, 1.0, 2.0]
    assert all("y" not in point for point in points)
    assert all(point["yMin"] < point["yMax"] for point in points)


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_a_vertical_chart_says_so(make, mark):
    assert _only(make(x="x", y="y"))["orientation"] == "vert"


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_a_sideways_chart_is_read_from_the_drawing(make, mark):
    # `orient="y"` is what makes `so.Est()` aggregate down the page. The
    # orientation is then read back off the geometry rather than off that
    # keyword: the bounds still go in `yMin`/`yMax` and `orientation` says
    # which axis they are on, which is the convention `ErrorBarTrace`
    # depends on -- `ErrorBarPoint` has no `xMin`/`xMax` to put them in.
    schema = _only(
        so.Plot(_frame(), y="x", x="y").add(so.Band() if make is _band else so.Range(),
                                            so.Est(), orient="y")
    )

    assert schema["orientation"] == "horz"
    assert [point["x"] for point in schema["data"]] == [0.0, 1.0, 2.0]
    assert all(point["yMin"] < point["yMax"] for point in schema["data"])


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_a_colour_split_becomes_one_series_per_level(make, mark):
    # The grouped shape `ErrorBarPoint[][]` exists for exactly this (#942):
    # it is what lets a reader move between two levels' intervals at one
    # position, which is the comparison a grouped interval chart is drawn
    # for. Flattened, the two levels arrive as six readings in a row.
    schema = _only(make(x="x", y="y", color="g"))
    data = schema["data"]

    assert [len(series) for series in data] == [3, 3]
    assert [series[0]["z"] for series in data] == ["a", "b"]
    assert schema["axes"]["z"] == {"label": "g"}


@pytest.mark.parametrize(
    ("make", "mark"),
    [(_band, "Band"), (_range, "Range")],
    ids=["band", "range"],
)
def test_the_levels_do_not_overlap_so_a_swap_would_show(make, mark):
    # The fixture puts group `b` four units above group `a`, so a reading
    # that paired a level's name with the other's bounds is visible in the
    # numbers rather than only in the label.
    data = _only(make(x="x", y="y", color="g"))["data"]
    lower, upper = data

    assert max(point["yMax"] for point in lower) < min(point["yMin"] for point in upper)


def test_a_single_group_stays_flat_rather_than_becoming_a_list_of_one():
    # One group needs no name for itself, and wrapping it would make every
    # unsplit chart announce a grouping it does not have.
    data = _only(_range(x="x", y="y"))["data"]

    assert all(isinstance(point, dict) for point in data)
    assert all("z" not in point for point in data)


def test_a_band_is_told_apart_from_an_area_by_the_marks_name():
    # Both leave a `Polygon` in `patches`, and only the mark's name says
    # whether the fold is a series against a baseline or a pair of bounds.
    # Read by artist class alone, an area would come out as an interval.
    area = _only(so.Plot(_frame(), x="x", y="y").add(so.Area()))
    band = _only(_band(x="x", y="y"))

    assert area["type"] is PlotType.AREA
    assert band["type"] is PlotType.ERRORBAR


def test_a_range_outlines_each_interval_and_a_band_outlines_nothing():
    # A range draws one path per position, which is what a selector resolves
    # to. A band spans every position with a single path, so there is no
    # element per interval -- and promising highlightable paths the document
    # does not contain is worse than promising none.
    assert _only(_range(x="x", y="y")).get("selectors")
    assert not _only(_band(x="x", y="y")).get("selectors")


def test_a_split_range_declines_to_outline_rather_than_outlining_the_wrong_one():
    # One collection's paths run in drawing order while the payload is
    # grouped by level, so a positional selector would pair the second
    # level's first interval with the first level's. The grouped selector
    # shape is a question of its own (#814).
    assert not _only(_range(x="x", y="y", color="g")).get("selectors")


def test_an_estimate_drawn_beside_it_is_its_own_layer():
    # `so.Dot(), so.Agg()` is how a caller adds the centre these marks do
    # not draw. It registers as the scatter it is rather than being folded
    # into the interval, which is what keeps the interval honest about
    # having no estimate of its own.
    schemas = _layers(
        so.Plot(_frame(), x="x", y="y").add(so.Range(), so.Est()).add(so.Dot(), so.Agg())
    )

    assert [schema["type"] for schema in schemas] == [
        PlotType.ERRORBAR,
        PlotType.SCATTER,
    ]
    assert all("y" not in point for point in schemas[0]["data"])
    assert all("y" in point for point in schemas[1]["data"])

# --------------------------------------------------------------------------
# The guards below are asked of the helpers directly, or of the rendered SVG,
# because a schema alone cannot see them: a mutation that removes any of them
# leaves a schema identical to the right one and a chart that is not.
# --------------------------------------------------------------------------


def test_a_path_that_does_not_fold_in_half_is_declined():
    # `_folded` pairs vertex `i` with vertex `2n - 1 - i`, which only means
    # anything on a path with an even number of points after the closing
    # repeat is dropped. An odd one has a vertex with no partner, and folding
    # it anyway would pair every position with the wrong bound and report an
    # interval the chart never drew.
    from maidr.core.plot.intervalplot import _folded

    assert _folded(np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]])) == []


def test_a_closed_path_is_folded_without_its_closing_vertex():
    # matplotlib repeats the first vertex to close the polygon. Counting it
    # makes the path odd, which the guard above would then decline -- so the
    # band would read as nothing at all.
    from maidr.core.plot.intervalplot import _folded

    closed = np.array([[0.0, 1.0], [1.0, 2.0], [1.0, 4.0], [0.0, 3.0], [0.0, 1.0]])
    folded = _folded(closed)

    assert [tuple(position) for position, _, _ in folded] == [(0.0, 1.0), (1.0, 2.0)]
    assert [tuple(high) for _, _, high in folded] == [(0.0, 3.0), (1.0, 4.0)]


def test_one_colour_over_many_segments_is_cycled_rather_than_run_off():
    # `get_colors()` returns exactly what was set, and a collection given one
    # colour carries one row however many segments it draws. Indexing that
    # would leave every segment after the first unnamed, so a split whose
    # levels happen to share a set colour would lose its names.
    from maidr.core.plot.intervalplot import _segment_colours
    from matplotlib.collections import LineCollection

    one = LineCollection([[(0, 0), (0, 1)]] * 3, colors="C0")
    colours = _segment_colours(one, 3)

    assert len(colours) == 3
    assert len(set(colours)) == 1


def test_a_collection_with_no_colours_names_nothing_rather_than_raising():
    from maidr.core.plot.intervalplot import _segment_colours
    from matplotlib.collections import LineCollection

    bare = LineCollection([[(0, 0), (0, 1)]])
    bare.set_color([])

    assert _segment_colours(bare, 2) == [None, None]


def test_a_degenerate_first_interval_does_not_decide_the_orientation():
    # The two bounds at one position share the coordinate the position is on.
    # A zero-width interval shares *both*, so it names neither axis -- and
    # reading the orientation off it would answer from the chart's flattest
    # point. Reachable: `so.Est()` on a position with one observation draws
    # exactly that.
    lopsided = pd.DataFrame(
        [{"x": 0, "y": 1.0}]
        + [{"x": 1, "y": 4.0 + step} for step in range(6)]
        + [{"x": 2, "y": 9.0 + step} for step in range(6)]
    )
    upright = _only(so.Plot(lopsided, x="x", y="y").add(so.Range(), so.Est()))
    # The sideways chart is what makes this test bite: reading the flat first
    # interval says nothing, and answering from it falls back to vertical --
    # which would put the positions in `yMin`/`yMax` and the readings in `x`.
    sideways = _only(
        so.Plot(lopsided, y="x", x="y").add(so.Range(), so.Est(), orient="y")
    )

    assert upright["orientation"] == "vert"
    assert sideways["orientation"] == "horz"
    assert upright["data"][0]["yMin"] == upright["data"][0]["yMax"]
    assert upright["data"][1]["yMin"] < upright["data"][1]["yMax"]
    assert [point["x"] for point in sideways["data"]] == [0.0, 1.0, 2.0]


def test_a_range_selector_resolves_to_the_paths_it_promises():
    # The half a schema cannot check: the selector string is the same whether
    # or not the collection was tagged, so only the rendered document says
    # whether it finds anything. An untagged range promises highlightable
    # paths and outlines nothing.
    import io

    from lxml import etree

    plot = _range(x="x", y="y").plot()
    figure = plot._figure
    maidr.render(figure)._repr_html_()

    schema = FigureManager.get_maidr(figure).plots[0].schema
    buffer = io.BytesIO()
    figure.savefig(buffer, format="svg")
    root = etree.fromstring(buffer.getvalue())
    namespaces = {"s": "http://www.w3.org/2000/svg"}
    gid = schema["selectors"][0].split("'")[1]
    group = root.xpath(f"//s:g[@id='{gid}']", namespaces=namespaces)

    assert len(schema["selectors"]) == 3
    assert len(group) == 1
    assert len(group[0].xpath("./s:path", namespaces=namespaces)) == 3


def test_a_band_promises_no_selector_at_all():
    # The other side of the same fact: a band is one path over every
    # position, so there is nothing per-interval to address. Emitting the
    # inherited default would promise outlining that cannot happen.
    plot = _band(x="x", y="y").plot()
    figure = plot._figure
    maidr.render(figure)._repr_html_()

    schema = FigureManager.get_maidr(figure).plots[0].schema

    assert "selectors" not in schema


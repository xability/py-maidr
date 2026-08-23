"""A plotly choropleth map produced a figure with no layers.

`go.Choropleth` shades named regions by a value. `maidr/plotly/` had no
handling for it, so it fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None` (#627). The core has had
`TraceType.CHOROPLETH` for this shape.

**The centroids are not here to be read.** `ChoroplethPoint` takes an
optional `lon`/`lat` pair in degrees, which is what lets a reader walk the
map spatially rather than down a list. A `go.Choropleth` carries neither: it
names its regions -- `"USA"`, `"FRA"`, a US state -- and plotly resolves
those names against geometry it fetches in the browser. The grammar already
says what that means: "the map is read as a region list in declared order,
which is a poorer reading but the one the data supports". `neighbors` is
absent for the same reason and a stronger one -- adjacency "is not derivable
from rendered SVG paths, and not from centroids either".

**The map could not be measured where this was written**, which is why the
layer ships without a selector. See the test that says so.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _regions(layer: dict) -> list[tuple]:
    """Each region as ``(name, value)``."""
    return [(point["x"], point["y"]) for point in layer["data"]]


COUNTRIES = go.Choropleth(
    locations=["USA", "CAN", "MEX"],
    z=[10, 20, 30],
    locationmode="ISO-3",
    colorbar={"title": {"text": "Score"}},
)


def test_a_choropleth_is_read_as_a_map_layer() -> None:
    """The reproduction, and the type it becomes."""
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert layer["type"] is PlotType.CHOROPLETH


def test_each_region_carries_its_name_and_its_value() -> None:
    """In the trace's own order, which is what the reader navigates.

    Without centroids there is no spatial order to walk, so declared order is
    the order -- the grammar's own answer for a map that carries no
    ``lon``/``lat``.
    """
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert _regions(layer) == [("USA", 10), ("CAN", 20), ("MEX", 30)]


def test_the_colour_bar_title_names_the_value() -> None:
    """It is the one thing the author may have written about the value.

    A choropleth draws no cartesian axes, so `layout.xaxis` holds neither
    name and reading it would take another trace's titles. The colour bar's
    title is exactly what the shading means, so it is used where it is there.
    """
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert layer["axes"]["x"]["label"] == "Region"
    assert layer["axes"]["y"]["label"] == "Score"


def test_an_unnamed_colour_bar_falls_back_to_the_generic_word() -> None:
    """What the field holds, said plainly, rather than left blank."""
    (layer,) = _layers(go.Figure([go.Choropleth(locations=["USA"], z=[1])]))

    assert layer["axes"]["y"]["label"] == "Value"


def test_a_region_with_no_value_is_dropped() -> None:
    """Plotly leaves it unshaded, so it is not on the map to be read.

    Announcing it would put a region in the walk that the reader cannot be
    told anything about -- a name with nothing attached.
    """
    (layer,) = _layers(
        go.Figure([go.Choropleth(locations=["USA", "CAN", "MEX"], z=[1, None, 3])])
    )

    assert _regions(layer) == [("USA", 1), ("MEX", 3)]


def test_a_map_beside_a_cartesian_subplot_keeps_its_own_column() -> None:
    """A geo subplot is placed like a polar one, not like a pie.

    `go.Choropleth` carries no `domain` of its own -- its rectangle is
    `layout.geo.domain`, named by the trace's `geo` field. Read as a domain
    trace it would land at the origin, and the figure would collapse to one
    column holding both charts, which is the bug #635 fixed for polar.
    """
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "xy"}, {"type": "choropleth"}]]
    )
    figure.add_trace(go.Bar(x=["a"], y=[1]), row=1, col=1)
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    assert [layer["type"] for layer in grid[0][0]["layers"]] == [PlotType.BAR]
    assert [layer["type"] for layer in grid[0][1]["layers"]] == [PlotType.CHOROPLETH]


def test_two_maps_are_two_cells() -> None:
    """`layout.geo` and `layout.geo2`, exactly as `polar` and `polar2`."""
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "choropleth"}] * 2]
    )
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]), row=1, col=1)
    figure.add_trace(go.Choropleth(locations=["CAN"], z=[2]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    assert _regions(grid[0][0]["layers"][0]) == [("USA", 1)]
    assert _regions(grid[0][1]["layers"][0]) == [("CAN", 2)]


def test_a_choropleth_ships_without_a_highlight() -> None:
    """A limit of where this was written, not a property of the chart.

    The other three plotly layers with no highlight have a reason in the
    chart: a barpolar draws no per-series path (#635), a parcoords renders to
    WebGL (#637), a parcats is laid out in an order not computable offline
    (#639). This is none of those -- a choropleth almost certainly *is*
    addressable.

    It could not be measured. Plotly requests its geometry from
    `https://cdn.plot.ly/un/world_110m.json` at render time, and with no
    network the map never draws. Measured in Chromium: the request is made,
    `geo._topojson` stays false, `.geolayer` holds one empty `g.geo`, and
    there are **zero** `path` elements -- while `calcdata` has the one entry,
    so plotly did compute the trace and only the geometry is missing.

    A selector that has never resolved would be a guess, and a highlight on
    the wrong region is worse than none. Left to whoever can load the map;
    see #640.
    """
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert "selectors" not in layer


def test_a_map_with_no_regions_forms_no_layer() -> None:
    """Nothing is shaded, so there is nothing to read (#636)."""
    assert _layers(go.Figure([go.Choropleth(locations=[], z=[])])) == []

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

**The map is measured now.** Plotly fetches its geometry from
`cdn.plot.ly` at render time, which is why the layer first shipped without a
selector (#640). Served that topojson locally, a choropleth draws one
`path.choroplethlocation` per declared region in declared order, so each
region is addressed -- see the selector tests below, and
`tests/browser/test_plotly_selectors.py`, which resolves what they assert
against a real Chromium.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

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


def test_the_color_bar_title_names_the_value() -> None:
    """It is the one thing the author may have written about the value.

    A choropleth draws no cartesian axes, so `layout.xaxis` holds neither
    name and reading it would take another trace's titles. The color bar's
    title is exactly what the shading means, so it is used where it is there.
    """
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert layer["axes"]["x"]["label"] == "Region"
    assert layer["axes"]["y"]["label"] == "Score"


def test_an_unnamed_color_bar_falls_back_to_the_generic_word() -> None:
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


#: What a region's selector looks like, with the map and the trace it sits
#: on left open. Plotly writes a geo subplot's class as ``"geo " + id``, so
#: the first subplot's attribute is the doubled string ``"geo geo"``.
def _region_selector(block: str, position: int, index: int) -> str:
    return (
        f".geolayer > g[class='geo {block}'] > g.backplot > g.choroplethlayer "
        f"> g.trace.choropleth:nth-of-type({position}) "
        f"> path.choroplethlocation:nth-of-type({index})"
    )


def test_a_choropleth_addresses_the_region_it_shades() -> None:
    """The highlight #640 was waiting on a loadable map for.

    Measured in Chromium once the topojson was served locally: a
    `go.Choropleth` draws one `path.choroplethlocation` per declared region,
    inside `.geolayer > g.geo > g.backplot > g.choroplethlayer >
    g.trace.choropleth`, and their document order is the *declared* order --
    eight countries declared out of alphabetical order read back in the
    order they were declared. Nothing is sorted, so unlike the parcats
    ribbons of #639 the element a region is drawn as is computable offline.
    """
    (layer,) = _layers(go.Figure([COUNTRIES]))

    assert layer["selectors"] == [
        _region_selector("geo", 1, index) for index in (1, 2, 3)
    ]


def test_a_dropped_region_does_not_shift_the_ones_after_it() -> None:
    """The case a single blanket selector cannot survive.

    Plotly draws a path per *declared* pair, including the ones it can draw
    nothing for: measured, a region with no value keeps its slot in the DOM
    with no `d` attribute at all. `_extract_plot_data` drops it, so one
    selector matching every path would resolve three elements for two
    announced points -- and `ChoroplethTrace.mapToSvgElements` withdraws the
    layer's highlight entirely when the counts disagree.

    So each region names its own path, at the index it was *declared* at.
    The middle region here is dropped and `MEX` keeps `nth-of-type(3)`.
    """
    (layer,) = _layers(
        go.Figure([go.Choropleth(locations=["USA", "CAN", "MEX"], z=[1, None, 3])])
    )

    assert _regions(layer) == [("USA", 1), ("MEX", 3)]
    assert layer["selectors"] == [
        _region_selector("geo", 1, 1),
        _region_selector("geo", 1, 3),
    ]


def test_a_layer_names_exactly_as_many_elements_as_it_announces() -> None:
    """The count `ChoroplethTrace` gates the whole highlight on."""
    (layer,) = _layers(
        go.Figure([go.Choropleth(locations=["USA", "CAN", "MEX", "BRA"], z=[1, None, 3, None])])
    )

    assert len(layer["selectors"]) == len(layer["data"])


def test_a_second_map_is_scoped_to_its_own_geo_subplot() -> None:
    """The exact class attribute, because the class *token* is ambiguous.

    A polar subplot's `<g>` carries a distinct class per subplot, which is
    what #635 scoped on. A geo subplot's does not: plotly writes
    `class="geo " + id`, so the first map's attribute is the doubled string
    `"geo geo"` whose token list is the single token `geo` -- which every
    other geo subplot carries too. Measured in Chromium,
    `.geolayer > g.geo.geo` matched **both** maps of a two-map figure and
    all **three** of a three-map one, which is the one-keypress-outlines-two-
    charts bug #635 exists to prevent. The exact-attribute form matched
    exactly one on each.
    """
    figure = go.Figure()
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1], geo="geo"))
    figure.add_trace(go.Choropleth(locations=["CAN", "MEX"], z=[2, 3], geo="geo2"))
    figure.update_layout(
        geo={"domain": {"x": [0, 0.45]}}, geo2={"domain": {"x": [0.55, 1]}}
    )

    first, second = _layers(figure)

    # Spelled out rather than built through `_region_selector`, which
    # re-derives the production format string: a test that shares the
    # helper moves with it, so swapping the exact attribute back for the
    # ambiguous `g.geo.geo` token would leave this assertion green while
    # both maps lit up at once.
    assert first["selectors"] == [
        ".geolayer > g[class='geo geo'] > g.backplot > g.choroplethlayer "
        "> g.trace.choropleth:nth-of-type(1) "
        "> path.choroplethlocation:nth-of-type(1)"
    ]
    assert second["selectors"] == [
        ".geolayer > g[class='geo geo2'] > g.backplot > g.choroplethlayer "
        "> g.trace.choropleth:nth-of-type(1) "
        "> path.choroplethlocation:nth-of-type(1)",
        ".geolayer > g[class='geo geo2'] > g.backplot > g.choroplethlayer "
        "> g.trace.choropleth:nth-of-type(1) "
        "> path.choroplethlocation:nth-of-type(2)",
    ]


def test_a_second_map_on_one_subplot_counts_its_own_position() -> None:
    """Two choropleths on one map are two `.choroplethlayer` children."""
    figure = go.Figure()
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]))
    figure.add_trace(go.Choropleth(locations=["CAN", "MEX"], z=[2, 3]))

    first, second = _layers(figure)

    assert first["selectors"] == [_region_selector("geo", 1, 1)]
    assert second["selectors"] == [
        _region_selector("geo", 2, index) for index in (1, 2)
    ]


def test_a_marker_trace_takes_no_slot_in_the_region_layer() -> None:
    """The position counts choropleths, not every trace on the map.

    Measured in Chromium: a `scattergeo` draws into the geo subplot's
    `.scatterlayer`, under `g.layer.frontplot`, which is a sibling of the
    `g.layer.backplot` holding the `.choroplethlayer`. So it takes no slot
    there -- a choropleth declared after one is still `nth-of-type(1)`, and
    counting the raw trace index would have named an element plotly never
    drew.
    """
    figure = go.Figure()
    figure.add_trace(go.Scattergeo(lat=[1], lon=[2]))
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]))

    layers = _layers(figure)
    (choropleth,) = [
        layer for layer in layers if layer["type"] is PlotType.CHOROPLETH
    ]

    assert choropleth["selectors"] == [_region_selector("geo", 1, 1)]


@pytest.mark.parametrize("kind", ["choroplethmap", "choroplethmapbox"])
def test_a_choropleth_on_a_tiled_map_still_ships_without_one(kind: str) -> None:
    """A limit of the chart now, not of where this was written.

    The three spellings read identically and do not draw identically.
    Measured in Chromium on a fully painted `go.Choroplethmap` with
    `style="white-bg"`, so no tile server was needed: four `<canvas>`
    elements, an empty `<g class="geolayer">`, and zero `path` elements
    carrying any class but the modebar's. The regions are genuinely painted
    -- `queryRenderedFeatures` returned both with their fills -- but not as
    anything CSS can address. `go.Choroplethmapbox` measured the same under
    `.mapboxgl-canvas`.

    So the tiled pair keeps the #145 outcome the whole family had until now,
    for the `scattergl` reason of #668 rather than the "not measured yet" of
    #640.
    """
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "A",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    trace = go.Figure().add_trace(
        {"type": kind, "geojson": geojson, "locations": ["A"], "z": [1]}
    )

    (layer,) = _layers(trace)

    assert layer["type"] is PlotType.CHOROPLETH
    assert "selectors" not in layer


def test_an_empty_map_takes_no_position_from_the_ones_beside_it() -> None:
    """A trace plotly draws nothing for must not take an `nth-of-type` slot.

    Measured in Chromium: plotly writes a `g.trace.choropleth` exactly when
    a trace has at least one declared `(location, z)` pair, and nothing at
    all when it has none. A per-group loop where one group matched no rows
    is the ordinary way to get one, and counting it would number every later
    map on that subplot one past its own group -- resolving nothing, which
    withdraws the highlight outright rather than misplacing it.
    """
    figure = go.Figure()
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]))
    figure.add_trace(go.Choropleth(locations=[], z=[]))
    figure.add_trace(go.Choropleth(locations=["CAN"], z=[2]))

    first, second = _layers(figure)

    assert first["selectors"] == [_region_selector("geo", 1, 1)]
    assert second["selectors"] == [_region_selector("geo", 2, 1)]


def test_a_valueless_region_still_takes_its_position() -> None:
    """The other side of that boundary, which is the declared pair.

    `locations=["USA"], z=[None]` announces nothing, so the layer is
    dropped -- but plotly still draws a group holding one geometry-less
    path for it, so the map after it is `nth-of-type(2)`. The rule is what
    plotly draws, not what maidr announces.
    """
    figure = go.Figure()
    figure.add_trace(go.Choropleth(locations=["USA"], z=[None]))
    figure.add_trace(go.Choropleth(locations=["CAN"], z=[2]))

    (layer,) = _layers(figure)

    assert layer["selectors"] == [_region_selector("geo", 2, 1)]


def test_a_missing_value_from_a_dataframe_column_is_dropped_too() -> None:
    """`NaN` is what a gap in a column becomes, and it is a missing value.

    Plotly's validators coerce `None` in a `pd.Series` to `NaN` rather than
    keeping it, so a dataframe with a gap never reaches an `is not None`
    test. Plotly treats the two the same -- both draw a region with no
    geometry -- and announcing one would put a region in the walk the reader
    cannot be told anything about, as well as emitting the `NaN` token that
    stops the payload parsing as JSON at all (#427).
    """
    pd = pytest.importorskip("pandas")

    (layer,) = _layers(
        go.Figure(
            [
                go.Choropleth(
                    locations=pd.Series(["USA", "CAN", "MEX"]),
                    z=pd.Series([1.0, None, 3.0]),
                )
            ]
        )
    )

    assert _regions(layer) == [("USA", 1.0), ("MEX", 3.0)]
    assert layer["selectors"] == [
        _region_selector("geo", 1, 1),
        _region_selector("geo", 1, 3),
    ]


def test_an_animated_map_ships_without_a_highlight() -> None:
    """The reading is the first frame; the drawing is the last.

    A figure built with `animation_frame=` keeps its frames in
    `figure.frames`, which nothing under `maidr/plotly/` reads -- the
    payload is the base trace, plotly's first frame. Plotly.js advances the
    drawing to the **last** frame within about half a second of load, with
    no interaction. Measured on two frames naming the same four countries in
    opposite orders: the payload announces `USA, CAN, MEX, BRA` while the
    four paths are bound to `BRA, MEX, CAN, USA`. Four selectors resolve
    four elements, so the count agrees and the highlight stays live --
    on the wrong country at every step.

    The stale reading is older than #640 and shared with every other plotly
    layer; what is declined here is the confident highlight over it.
    """
    frame = {"data": [{"type": "choropleth", "locations": ["BRA", "USA"], "z": [2, 1]}]}
    figure = go.Figure(
        data=[go.Choropleth(locations=["USA", "BRA"], z=[1, 2])],
        frames=[frame],
    )

    (layer,) = _layers(figure)

    assert _regions(layer) == [("USA", 1), ("BRA", 2)]
    assert "selectors" not in layer


def test_a_map_with_no_regions_forms_no_layer() -> None:
    """Nothing is shaded, so there is nothing to read (#636)."""
    assert _layers(go.Figure([go.Choropleth(locations=[], z=[])])) == []

"""Every plotly selector is resolved against the chart it describes (#644).

`tests/plotly/` asserts on the emitted *strings*:

```python
assert "g.contour:nth-of-type(2)" in layer["selectors"][0]
```

which checks that the code built the string it meant to build, not that the
string finds anything. A selector that silently stops matching -- plotly.js
regrouping its DOM in a version bump, a class rename, a wrapper element
appearing -- passes every test in the repo and reaches users as a chart whose
highlight has quietly stopped working.

The matplotlib path has no such hole: the exported SVG is available in Python
and the `test` extra carries `cssselect` to resolve against it. A plotly
figure has no Python-side SVG -- plotly.js builds the DOM in the browser -- so
the same check needs a browser, which is what this file is.

## Against plotly's own page, not `save_html`'s

The figure is written with `include_plotlyjs=True` and opened directly. The
selectors describe **plotly's** DOM, which is the same whether maidr wraps it
or not, and `maidr.save_html` links plotly.js from `cdn.plot.ly` -- so
resolving against the wrapped page would put a network fetch in the middle of
a test that must not need one.

## What is asserted, and what is not yet

Three of the four steps #644 names:

1. render the figure and read the emitted schema;
2. resolve every selector in the browser;
3. assert the count is the one the layer's shape calls for -- one element per
   point where the trace draws a mark per point, one per series where it draws
   a path or an image.

Step 4 -- unprojecting the resolved element's position through the subplot's
axes and comparing it with the point the payload announces -- is done for the
**bar**, which is the shape where the unprojection is a single `p2d` call.
The other shapes need a per-shape table and are not covered here; what is
covered for them is that the selector finds the right *number* of elements,
which is what catches a selector that has stopped matching.

Several layers deliberately emit **no** selectors, each for a measured
reason: `barpolar` (#635), `parcoords` (#637), `parcats` (#639), and
`scattergl` and `scatterpolargl` (painted to canvas, #668). Those are listed
rather than skipped, so that a layer which starts declining silently fails
here.

A contour is the one layer whose selector may name **several** elements on
purpose: a level with islands draws a `<path>` per island in no dependable
order, so every series of that level names the level and the core outlines it
whole (#643, #658, xability/maidr#1142). That is the `"level"` shape below,
and it is the only thing in the repo that measures those selectors against a
drawn chart.

## The one figure that needs an asset

A `go.Choropleth` resolves its regions against geometry plotly fetches from
`cdn.plot.ly` while it draws, so with nothing to draw against there are no
region paths to resolve a selector to -- which is why #640 shipped without
one. The map is handed to the page before plotly.js parses instead of being
fetched, so the `file://` design above survives; `WORLD_110M_STUB` and
`PRELOAD_TOPOJSON` below carry the stub and the reasoning, and
`test_the_map_is_drawn_without_a_network_fetch` holds it to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.browser

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

def _ring(west: float, east: float, south: float, north: float) -> list[list[float]]:
    """One rectangular arc, as topojson's own ``[[lon, lat], ...]`` quantised
    off (``transform`` absent means the coordinates are already degrees)."""
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


_NOTHING = {"type": "GeometryCollection", "geometries": []}

#: The world plotly would fetch, cut down to the countries these tests name.
#:
#: A `go.Choropleth` resolves its region names against geometry plotly
#: requests from `cdn.plot.ly/un/world_110m.json` while it draws, and the
#: fetch is unconditional -- an inline `geojson=` does not avoid it, because
#: `locationmode` defaults to `"ISO-3"`. With no map there are no region
#: paths at all, so the selector tests below would have nothing to resolve
#: against.
#:
#: Fetching it would put a network request in the middle of a suite whose
#: whole argument is that it needs none, and a `file://` page cannot read a
#: sibling `file://` copy either -- Chromium refuses it as cross-origin
#: ("Cross origin requests are only supported for protocol schemes: chrome,
#: chrome-extension, chrome-untrusted, data, http, https, isolated-app").
#: So the asset is handed to the page instead; see `PRELOAD_TOPOJSON`.
#:
#: `objects.countries` is the key plotly reads for the default locationmode,
#: and each geometry's `id` is the ISO-3 code it matches on. The base layers
#: have to exist even when they are empty: plotly indexes
#: `topojson.objects[land|coastlines|...]` unconditionally and throws
#: "Cannot read properties of undefined" without them, drawing nothing.
WORLD_110M_STUB = {
    "type": "Topology",
    "arcs": [
        _ring(-125, -70, 25, 49),
        _ring(-140, -60, 50, 70),
        _ring(-117, -87, 15, 32),
    ],
    "objects": {
        "countries": {
            "type": "GeometryCollection",
            "geometries": [
                {"type": "Polygon", "id": "USA", "arcs": [[0]]},
                {"type": "Polygon", "id": "CAN", "arcs": [[1]]},
                {"type": "Polygon", "id": "MEX", "arcs": [[2]]},
            ],
        },
        "land": {
            "type": "GeometryCollection",
            "geometries": [
                {"type": "Polygon", "arcs": [[0]]},
                {"type": "Polygon", "arcs": [[1]]},
                {"type": "Polygon", "arcs": [[2]]},
            ],
        },
        "coastlines": {
            "type": "GeometryCollection",
            "geometries": [{"type": "LineString", "arcs": [0]}],
        },
        "ocean": _NOTHING,
        "lakes": _NOTHING,
        "rivers": _NOTHING,
        "subunits": _NOTHING,
    },
}

#: Hand the map over before plotly.js runs, so it never asks for one.
#:
#: Plotly skips the fetch for an asset already on the global -- its own
#: `PlotlyGeoAssets.topojson[name] === undefined && fetchTopojson()` -- and
#: it creates that global only if nothing has (`window.PlotlyGeoAssets ===
#: undefined && (window.PlotlyGeoAssets = {topojson: {}})`), so a value set
#: first survives. `world_110m` is what plotly names the default scope and
#: resolution: `scope + "_" + resolution + "m"`.
#:
#: Run through `add_init_script` rather than injected into the page, so it
#: is in place before the inlined bundle parses. It is inert for a figure
#: that draws no map.
PRELOAD_TOPOJSON = (
    "window.PlotlyGeoAssets = {topojson: {world_110m: "
    + json.dumps(WORLD_110M_STUB, separators=(",", ":"))
    + "}};"
)


#: Long enough for plotly to draw into the DOM on a slow runner. Waited on
#: through a condition rather than slept through, so a fast machine pays
#: nothing.
_DRAWN = "() => document.querySelector('.plot-container') !== null"
_DRAW_TIMEOUT_MS = 30_000

#: The datum plotly bound to each element a selector resolves to. A bar's
#: `x` is its category *index* on a categorical axis, which is the position
#: the payload's label sits at.
_BOUND_DATUM = """(query) => [...document.querySelectorAll(query)].map((el) => {
  const datum = el.__data__;
  return { x: datum.x, y: datum.y };
})"""

#: Samples that fall in more than one bin on each axis, so the 2-D binning
#: traces draw a grid rather than a single cell.
_SAMPLES = {"x": [1, 2, 2, 3], "y": [1, 2, 2, 3]}
_FIELD = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

#: A field with two peaks. At level 0.5 it draws one ring around each, so the
#: level is two `<path>` elements and both series name the level.
_TWO_PEAKS = [
    [0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0],
    [0, 0, 0, 0, 0],
]

#: Twenty samples along a diagonal band, binned into nine levels of which
#: three cross the band twice. The real-world island shape, as opposed to a
#: field built to have one.
_BAND = {
    "x": [1, 1, 2, 2, 2, 3, 3, 4, 5, 5, 5, 5, 6, 6, 7, 8, 8, 9, 9, 10],
    "y": [1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10],
}


def _figure(name: str) -> go.Figure:
    """One figure per plotly trace type py-maidr reads."""
    return {
        "bar": lambda: go.Figure(go.Bar(x=["a", "b", "c"], y=[1, 2, 3])),
        "scatter": lambda: go.Figure(
            go.Scatter(x=[1, 2, 3], y=[2, 1, 3], mode="markers")
        ),
        "line": lambda: go.Figure(
            go.Scatter(x=[1, 2, 3], y=[2, 1, 3], mode="lines")
        ),
        "histogram": lambda: go.Figure(go.Histogram(x=[1, 2, 2, 3, 3, 3])),
        "pie": lambda: go.Figure(go.Pie(labels=["a", "b"], values=[1, 2])),
        "candlestick": lambda: go.Figure(
            go.Candlestick(
                x=[1, 2], open=[1, 2], high=[3, 4], low=[0, 1], close=[2, 3]
            )
        ),
        "ohlc": lambda: go.Figure(
            go.Ohlc(x=[1, 2], open=[1, 2], high=[3, 4], low=[0, 1], close=[2, 3])
        ),
        "violin": lambda: go.Figure(go.Violin(y=[1, 2, 3, 4, 9])),
        "heatmap": lambda: go.Figure(go.Heatmap(z=_FIELD)),
        "histogram2d": lambda: go.Figure(go.Histogram2d(**_SAMPLES)),
        "contour": lambda: go.Figure(go.Contour(z=_FIELD)),
        "funnel": lambda: go.Figure(go.Funnel(y=["a", "b"], x=[10, 5])),
        "waterfall": lambda: go.Figure(go.Waterfall(x=["a", "b"], y=[3, -1])),
        "treemap": lambda: go.Figure(
            go.Treemap(labels=["a", "b"], parents=["", "a"], values=[3, 1])
        ),
        "sunburst": lambda: go.Figure(
            go.Sunburst(labels=["a", "b"], parents=["", "a"], values=[3, 1])
        ),
        "icicle": lambda: go.Figure(
            go.Icicle(labels=["a", "b"], parents=["", "a"], values=[3, 1])
        ),
        "sankey": lambda: go.Figure(
            go.Sankey(
                node={"label": ["a", "b"]},
                link={"source": [0], "target": [1], "value": [1]},
            )
        ),
        "radar": lambda: go.Figure(
            go.Scatterpolar(r=[1, 2, 3], theta=[0, 120, 240])
        ),
        "radar markers": lambda: go.Figure(
            go.Scatterpolar(r=[1, 2, 3], theta=[0, 120, 240], mode="markers")
        ),
        "gauge": lambda: go.Figure(
            go.Indicator(
                mode="gauge+number", value=5, gauge={"axis": {"range": [0, 10]}}
            )
        ),
        "barpolar": lambda: go.Figure(go.Barpolar(r=[1, 2], theta=[0, 90])),
        "parcoords": lambda: go.Figure(
            go.Parcoords(
                dimensions=[
                    {"label": "a", "values": [1, 2]},
                    {"label": "b", "values": [2, 1]},
                ]
            )
        ),
        "parcats": lambda: go.Figure(
            go.Parcats(
                dimensions=[
                    {"label": "a", "values": ["x", "y"]},
                    {"label": "b", "values": ["p", "q"]},
                ]
            )
        ),
        "scattergl": lambda: go.Figure(
            go.Scattergl(x=[1, 2, 3], y=[2, 1, 3], mode="markers")
        ),
        "scatterpolargl": lambda: go.Figure(
            go.Scatterpolargl(r=[1, 2, 3], theta=[0, 120, 240])
        ),
        "histogram2dcontour": lambda: go.Figure(
            go.Histogram2dContour(**_SAMPLES)
        ),
        # The three countries the preloaded stub map carries; see
        # `WORLD_110M_STUB` above.
        "choropleth": lambda: go.Figure(
            go.Choropleth(
                locations=["USA", "CAN", "MEX"], z=[10, 20, 30], locationmode="ISO-3"
            )
        ),
        # The hole is the case the declared-index rule exists for: plotly
        # keeps a slot for the region it draws nothing for, so `MEX` is the
        # third path while it is the second announced point.
        "choropleth hole": lambda: go.Figure(
            go.Choropleth(
                locations=["USA", "CAN", "MEX"], z=[10, None, 30], locationmode="ISO-3"
            )
        ),
        # Two maps, because a geo subplot's class token is ambiguous in a way
        # a polar one's is not -- see `PlotlyChoroplethPlot._get_selector`.
        "choropleth grid": lambda: go.Figure(
            [
                go.Choropleth(
                    locations=["USA"], z=[10], locationmode="ISO-3", geo="geo"
                ),
                go.Choropleth(
                    locations=["CAN", "MEX"],
                    z=[20, 30],
                    locationmode="ISO-3",
                    geo="geo2",
                ),
            ]
        ).update_layout(
            geo={"domain": {"x": [0, 0.45]}}, geo2={"domain": {"x": [0.55, 1]}}
        ),
        "contour islands": lambda: go.Figure(
            go.Contour(
                z=_TWO_PEAKS,
                contours=dict(coloring="lines", start=0.5, end=0.5, size=0.5),
            )
        ),
        "histogram2dcontour islands": lambda: go.Figure(
            go.Histogram2dContour(**_BAND)
        ),
    }[name]()


#: What each of a figure's layers should resolve to, layer by layer in the
#: order they are emitted. Measured in Chromium rather than reasoned about:
#:
#: * ``"point"`` -- one drawn element per announced point. A bar, a slice, a
#:   candle, a marker; also the single element a heatmap, a gauge and a
#:   sankey each announce as their one point.
#: * ``"series"`` -- one element per announced series. A path: a line, a
#:   contour level, a violin's KDE outline.
#: * ``"level"`` -- a contour whose selectors name levels rather than curves,
#:   so one selector may resolve to several elements and several series may
#:   share it. Checked per distinct selector instead of by a sum, and against
#:   the curve count only for the figures listed, which were measured.
#: * ``"none"`` -- the layer names nothing, each for a measured reason.
#:
#: A figure with two entries emits two layers: a ``go.Violin`` is read as a
#: box and a KDE, and only the KDE has an element of its own.
SHAPES: dict[str, tuple[str, ...]] = {
    "bar": ("point",),
    "scatter": ("point",),
    "line": ("series",),
    "histogram": ("point",),
    "pie": ("point",),
    "candlestick": ("point",),
    "ohlc": ("point",),
    # The box half of a violin is drawn inside the violin's own outline and
    # has no element to point at; the KDE curve is one path.
    "violin": ("none", "series"),
    "heatmap": ("point",),
    "histogram2d": ("point",),
    "contour": ("series",),
    "funnel": ("point",),
    "waterfall": ("point",),
    "treemap": ("point",),
    "sunburst": ("point",),
    "icicle": ("point",),
    "sankey": ("point",),
    "radar": ("series",),
    # A markers-only radar draws no outline, so its markers are named
    # instead -- one per sample (#656).
    "radar markers": ("point",),
    "gauge": ("point",),
    # `barpolar` draws one bar per spoke and no per-series path (#635).
    "barpolar": ("none",),
    # A parallel-coordinates axis is painted, not drawn per line (#637).
    "parcoords": ("none",),
    # Same for a parallel-categories ribbon (#639).
    "parcats": ("none",),
    # `scattergl` paints its markers to a canvas, so there is no element.
    "scattergl": ("none",),
    # And `scatterpolargl` paints its spokes to one, so neither the outline
    # an SVG radar names nor its markers exist (#668).
    "scatterpolargl": ("none",),
    # Every level of this field draws a single curve, so each selector
    # resolves to exactly one path and the reader keeps a per-point highlight.
    "histogram2dcontour": ("series",),
    # These two have levels that break into islands, which is where a selector
    # names the level and resolves to every path in it (#658).
    "contour islands": ("level",),
    "histogram2dcontour islands": ("level",),
    # One `path.choroplethlocation` per region, addressed one selector per
    # region (#640). The map is handed to the page rather than fetched --
    # see `PRELOAD_TOPOJSON` -- so this stays offline like the rest.
    "choropleth": ("point",),
    "choropleth hole": ("point",),
    "choropleth grid": ("point", "point"),
}


def _layers(figure: go.Figure) -> list[dict]:
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _selector_strings(layer: dict) -> list[str]:
    """Every CSS selector a layer carries, whatever shape it carries it in.

    A layer names its elements as a bare string, a list of them, a list of
    lists (one group per series), or -- a box -- a list of dicts whose values
    are the selectors for the parts of one box.

    Flattened in the layer's own order. That was not so while every caller
    only counted: taking the next item off the *end* of the pending stack
    read a list back to front, which no assertion here could see. A layer
    that names one element per point pairs its selectors with its points by
    position, so a test that checks *which* element a selector finds needs
    the order the layer stated.
    """
    found: list[str] = []
    pending: list[Any] = [layer.get("selectors")]
    while pending:
        item = pending.pop(0)
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, list):
            pending[:0] = item
        elif isinstance(item, dict):
            pending[:0] = list(item.values())
    return found


def _points(layer: dict) -> int:
    """How many points the layer announces, across all its series.

    A layer's `data` is a list of points, a list of series, or -- a gauge --
    a single object describing the whole chart, which is one point.
    """
    data = layer.get("data")
    if not isinstance(data, list):
        return 1
    if data and isinstance(data[0], list):
        return sum(len(series) for series in data)
    return len(data)


def _series(layer: dict) -> int:
    """How many series the layer announces."""
    data = layer.get("data")
    if not isinstance(data, list):
        return 1
    return len(data) if data and isinstance(data[0], list) else 1


def _drawn(browser, tmp_path: Path, figure: go.Figure):
    """Open plotly's own page for a figure and return the loaded page."""
    path = tmp_path / "figure.html"
    figure.write_html(str(path), include_plotlyjs=True, full_html=True)
    page = browser.new_page()
    page.add_init_script(PRELOAD_TOPOJSON)
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(_DRAWN, timeout=_DRAW_TIMEOUT_MS)
    # Plotly draws on the frame after the container appears; one more frame is
    # enough and is waited for rather than slept through.
    page.wait_for_function("() => document.querySelectorAll('svg').length > 0")
    return page


def _resolved(page, selectors: list[str]) -> list[int]:
    return [
        page.evaluate("(query) => document.querySelectorAll(query).length", query)
        for query in selectors
    ]


def _expected(layer: dict, shape: str) -> int:
    """How many elements a layer of this shape should resolve to."""
    return _points(layer) if shape == "point" else _series(layer)


def _names_per_selector(layer: dict) -> dict[str, int]:
    """How many series name each distinct selector."""
    counts: dict[str, int] = {}
    for selector in _selector_strings(layer):
        counts[selector] = counts.get(selector, 0) + 1
    return counts


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_emitted_selector_finds_the_element_it_names(
    browser, tmp_path, name: str
) -> None:
    """The check the repo did not have, and the one that catches a rename.

    A selector that resolves to nothing is a highlight the reader never
    sees, while the reading, the sonification and the braille stay correct --
    so nothing else in the suite can tell the difference. That is how the
    markers-only radar of #656 went unnoticed.
    """
    figure = _figure(name)
    layers = _layers(figure)
    page = _drawn(browser, tmp_path, figure)
    try:
        assert len(layers) == len(SHAPES[name])
        for layer, shape in zip(layers, SHAPES[name]):
            selectors = _selector_strings(layer)
            if shape == "none":
                assert selectors == [], f"{name}: expected to name nothing"
                continue
            assert selectors, f"{name}: named nothing"
            counts = _resolved(page, selectors)
            assert all(count > 0 for count in counts), (
                f"{name}: {json.dumps(dict(zip(selectors, counts)))}"
            )
    finally:
        page.close()


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_a_layer_names_as_many_elements_as_it_announces(
    browser, tmp_path, name: str
) -> None:
    """One element per point, or one per series, and never a count between.

    Counting matters as much as matching. `LineTrace.mapToSvgElements` takes
    a selector whose match count equals the series' point count and uses
    those elements directly; anything else falls through to parsing a single
    path, and a layer that has drifted off its count loses its highlight
    whether or not the selector still finds something.

    Summed across the layer's selectors, because a layer says this two ways
    -- one selector matching every mark, or one selector per mark -- and both
    are the same claim about the chart.
    """
    figure = _figure(name)
    layers = _layers(figure)
    page = _drawn(browser, tmp_path, figure)
    try:
        for layer, shape in zip(layers, SHAPES[name]):
            if shape == "none":
                continue
            if shape == "level":
                # Per distinct selector, not by a sum: a k-curve level
                # contributes k selectors of k matches each, so a sum would
                # square it.
                #
                # Measured on these two figures, a level's group holds one
                # path per curve naming it. That is not true of plotly
                # contours in general -- plotly joins two open curves whose
                # ends meet into one path, and draws a level reaching the
                # grid's own edge as the filled region's outline -- so a new
                # island figure failing here means plotly did not draw the
                # curves one for one, which is worth knowing and is not the
                # same as a broken selector.
                named = _names_per_selector(layer)
                assert named, f"{name}: named nothing"
                resolved = _resolved(page, list(named))
                assert dict(zip(named, resolved)) == named, f"{name}: {resolved}"
                continue
            counts = _resolved(page, _selector_strings(layer))
            assert sum(counts) == _expected(layer, shape), f"{name}: {counts}"
    finally:
        page.close()


def test_a_bar_is_outlined_on_the_bar_it_announces(browser, tmp_path) -> None:
    """The step that catches a selector resolving to the *wrong* element.

    Counting says a selector still matches; it cannot say it matches the mark
    the payload describes. Plotly binds each drawn mark to the datum it came
    from through the element's own ``__data__``, which is the link the
    library's event handling uses, so reading it back is asking plotly which
    datum this element is rather than measuring where it landed.

    That is the check that found the contour curve-ordering problem in #643 --
    a selector list built in the tracer's order resolved to real elements and
    the wrong ones -- run by hand, because nothing in the repo ran it.
    """
    figure = _figure("bar")
    (layer,) = _layers(figure)
    page = _drawn(browser, tmp_path, figure)
    try:
        drawn = page.evaluate(_BOUND_DATUM, _selector_strings(layer)[0])

        assert drawn == [
            {"x": index, "y": point["y"]}
            for index, point in enumerate(layer["data"])
        ]
    finally:
        page.close()


def test_a_scatter_point_is_outlined_on_the_point_it_announces(
    browser, tmp_path
) -> None:
    """The same check on the other positional shape.

    A scatter's marks are one element per point like a bar's, and its x is a
    position rather than a category -- so this is the case where a selector
    resolving to the right *count* in the wrong *order* would show.
    """
    figure = _figure("scatter")
    (layer,) = _layers(figure)
    page = _drawn(browser, tmp_path, figure)
    try:
        drawn = page.evaluate(_BOUND_DATUM, _selector_strings(layer)[0])

        assert drawn == [
            {"x": point["x"], "y": point["y"]} for point in layer["data"]
        ]
    finally:
        page.close()


#: What plotly bound to a region's path. A choropleth's datum carries the
#: region and its value rather than the `x`/`y` a positional mark does.
#: `drawn` is the geometry, and it is read for a reason: plotly keeps a
#: `path.choroplethlocation` for a region it resolved to nothing, with the
#: `d` attribute simply absent. Without it a stub that matched no region at
#: all would satisfy every count and identity check here on a blank map.
_BOUND_REGION = """(query) => [...document.querySelectorAll(query)].map((el) => {
  const datum = el.__data__;
  return { loc: datum.loc, z: datum.z, drawn: el.hasAttribute('d') };
})"""


def test_a_region_is_outlined_on_the_region_it_announces(browser, tmp_path) -> None:
    """Step 4 of #644 on the shape #640 left unaddressed.

    Counting says the selectors still match; it cannot say each one matches
    the region the payload names at that position. A choropleth is the shape
    where getting that wrong is worst -- the reader is told "France" while
    Brazil lights up -- and it is the shape where it is most likely, because
    the elements carry no identity of their own: measured, a region path's
    whole attribute set is `class`, `fill`, `d` and `style`, so position is
    all there is to go on.
    """
    figure = _figure("choropleth hole")
    (layer,) = _layers(figure)
    page = _drawn(browser, tmp_path, figure)
    try:
        drawn = [
            page.evaluate(_BOUND_REGION, query)
            for query in _selector_strings(layer)
        ]

        assert drawn == [
            [{"loc": point["x"], "z": point["y"], "drawn": True}]
            for point in layer["data"]
        ]
    finally:
        page.close()


def test_the_map_is_drawn_without_a_network_fetch(browser, tmp_path) -> None:
    """The claim the whole preload rests on, asserted rather than assumed.

    The stub can stop working two measured ways, and this covers both. If
    the key is absent or renamed, plotly asks `cdn.plot.ly` for the map --
    every other test here would still pass on any machine with a network
    while failing in CI, which is the exact silence this file exists to
    break, and the request assertion catches it. If the key is present but
    the topology is malformed, plotly does *not* fall back -- its skip
    condition is only that the asset is defined -- so it throws and draws
    nothing; that is what waiting on the geometry catches.
    """
    figure = _figure("choropleth")
    path = tmp_path / "figure.html"
    figure.write_html(str(path), include_plotlyjs=True, full_html=True)

    page = browser.new_page()
    page.add_init_script(PRELOAD_TOPOJSON)
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    try:
        page.goto(path.as_uri(), wait_until="load")
        # `[d]` rather than a bare count: plotly draws a slot for a region it
        # resolved to nothing, so counting elements is satisfied by a blank
        # map. Measured -- lowercasing the stub's ids so nothing matches
        # leaves three `path.choroplethlocation` with no geometry at all.
        page.wait_for_function(
            "() => document.querySelectorAll('path.choroplethlocation[d]').length === 3",
            timeout=_DRAW_TIMEOUT_MS,
        )

        assert [url for url in requested if not url.startswith("file:")] == []
    finally:
        page.close()

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
reason: `barpolar` (#635), `parcoords` (#637), `parcats` (#639), `choropleth`
(#640), `scattergl` (painted to canvas), and a contour whose level holds
islands (#643). Those are listed rather than skipped, so that a layer which
starts declining silently fails here.
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
        "histogram2dcontour": lambda: go.Figure(
            go.Histogram2dContour(**_SAMPLES)
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
    # Every level of this field draws a single curve, so each is addressed;
    # a level with islands declines instead, which #643 measured and
    # xability/maidr#1142 is what would let it be outlined whole.
    "histogram2dcontour": ("series",),
}


def _layers(figure: go.Figure) -> list[dict]:
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _selector_strings(layer: dict) -> list[str]:
    """Every CSS selector a layer carries, whatever shape it carries it in.

    A layer names its elements as a bare string, a list of them, a list of
    lists (one group per series), or -- a box -- a list of dicts whose values
    are the selectors for the parts of one box.
    """
    found: list[str] = []
    pending: list[Any] = [layer.get("selectors")]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item.values())
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

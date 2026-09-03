"""Plotly's two polar traces produced figures with no layers.

`go.Scatterpolar` and `go.Barpolar` draw spokes around a circle -- one
radius per angle -- and the core builds both on `RadarTrace`: a radar joins
the spokes into an outline, a polar area fills the wedge between them, and a
reader navigates the same spokes either way. `maidr/plotly/` had no handling
for either, so both fell through `_extract_plots` to `PlotlyPlotFactory`,
which returned `None` (#627). The core has drawn them since
xability/maidr#833.

The payload is a line's -- a list of *series*, each a list of points --
because that is what `RadarTrace` extends. So is the selector contract, and
that is what decides how far this goes: `LineTrace.mapToSvgElements`
compares `selectors.length` against the **series** count, not the point
count.

Measured in Chromium:

  * a `scatterpolar` draws exactly one `path.js-line` per trace, inside its
    own `.polarlayer .scatterlayer .trace` -- one element for one series,
    which is the shape the contract wants.
  * a `barpolar` draws no per-series path at all: four bars for four spokes,
    under `.polarlayer .barlayer`. Four selectors would be read as four
    series, and the one selector its single series is allowed would have to
    point at the whole `.trace.bars` group, which outlines every bar at once
    and so highlights the same thing at every step of the walk.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

SPOKES = ["N", "E", "S", "W"]
RADII = [3, 9, 5, 1]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _spokes(layer: dict) -> list[tuple]:
    """The one series' spokes as ``(angle, radius)``."""
    return [(point["x"], point["y"]) for point in layer["data"][0]]


def test_a_scatterpolar_is_read_as_a_radar() -> None:
    """The reproduction, and the type it becomes."""
    (layer,) = _layers(
        go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES, fill="toself")])
    )

    assert layer["type"] == PlotType.RADAR


def test_a_barpolar_is_read_as_a_polar_area() -> None:
    """The other painting of the same spokes."""
    (layer,) = _layers(go.Figure([go.Barpolar(r=RADII, theta=SPOKES)]))

    assert layer["type"] == PlotType.POLAR_AREA


@pytest.mark.parametrize("cls", [go.Scatterpolar, go.Barpolar])
def test_theta_is_the_angle_and_r_the_radius(cls) -> None:
    """Not `x` and `y`, which a polar trace does not carry at all.

    Reading the pair off the wrong keys would give an empty layer, and
    reading them the wrong way round would put the angle where the magnitude
    belongs -- no number to pitch, and the announcement inverted.
    """
    (layer,) = _layers(go.Figure([cls(r=RADII, theta=SPOKES)]))

    assert _spokes(layer) == list(zip(SPOKES, RADII))


def test_the_series_is_wrapped_for_the_list_of_series_shape() -> None:
    """`RadarTrace` extends the line trace, so `data` is a list of series.

    Shipping the spokes one level too shallow would have the frontend read
    the whole chart as a single series of one point.
    """
    (layer,) = _layers(go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)]))

    assert len(layer["data"]) == 1
    assert len(layer["data"][0]) == len(SPOKES)


def test_a_spoke_with_no_radius_is_dropped() -> None:
    """Plotly draws nothing for it, and the gap would rotate the rest.

    `RadarTrace` places its spokes at an equal share of the circle by
    *count*, so keeping an empty one would move every later spoke's angle --
    and the panning with it.
    """
    (layer,) = _layers(
        go.Figure([go.Scatterpolar(r=[3, None, 5], theta=["N", "E", "S"])])
    )

    assert _spokes(layer) == [("N", 3), ("S", 5)]


def test_a_gap_written_as_nan_is_dropped_too() -> None:
    """The same chart, held differently, must read the same way.

    A gap reaches the extractor in two spellings and the difference is not
    the author's: a plain list keeps its `None`, while the same list as a
    numpy array is exported base64-encoded and comes back through `as_list`
    as `nan`. Measured on `go.Scatter(y=np.array([4, np.nan, 6]))`, whose
    `to_dict()` is `{"dtype": "f8", "bdata": ...}`.

    Dropping only `None` left this chart with a spoke `RadarTrace` would
    count, rotating every later spoke -- the very thing the test above
    exists to prevent.
    """
    numpy = pytest.importorskip("numpy")

    (layer,) = _layers(
        go.Figure(
            [
                go.Scatterpolar(
                    r=numpy.array([3.0, numpy.nan, 5.0]), theta=["N", "E", "S"]
                )
            ]
        )
    )

    assert _spokes(layer) == [("N", 3.0), ("S", 5.0)]


def test_a_radar_addresses_its_outline() -> None:
    """One selector for one series, which is what the contract wants.

    Measured: a scatterpolar draws exactly one `path.js-line` per trace.
    """
    (layer,) = _layers(go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)]))

    assert layer["selectors"] == [
        ".polarlayer > g.polar .scatterlayer .trace:nth-child(1) path.js-line"
    ]


def test_a_markers_only_radar_addresses_its_markers() -> None:
    """"One `path.js-line` per trace" holds only where a line is drawn.

    A markers-only `scatterpolar` draws none, so the selector resolved to
    nothing at all and the layer lost its highlight while its reading, its
    sonification and its braille stayed correct (#656). Measured in
    Chromium on three spokes, counting inside the trace's own `<g>`:

    ```
    mode                 path.js-line   g.points path.point
    unset (default)            1               3
    "lines"                    1               3
    "lines+markers"            1               3
    "markers"                  0               3
    "text"                     0               0
    ```

    One `path.point` per sample is the shape `LineTrace.mapViaDomElements`
    already takes: a selector whose match count equals the series' point
    count is used element for element, with no path to parse.
    """
    (layer,) = _layers(
        go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES, mode="markers")])
    )

    assert layer["selectors"] == [
        ".polarlayer > g.polar .scatterlayer .trace:nth-child(1) "
        "g.points path.point"
    ]


@pytest.mark.parametrize("mode", ["lines", "lines+markers", "markers+lines"])
def test_a_radar_that_draws_a_line_still_addresses_it(mode: str) -> None:
    """The outline is preferred wherever there is one.

    It is one element for the whole series, which is what the multi-series
    contract wants; the markers are the fallback rather than the reading.
    """
    (layer,) = _layers(
        go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES, mode=mode)])
    )

    assert layer["selectors"] == [
        ".polarlayer > g.polar .scatterlayer .trace:nth-child(1) path.js-line"
    ]


def test_a_text_only_radar_is_read_but_not_addressed() -> None:
    """Nothing is drawn to point at, so nothing is named.

    The outcome #145 established and `barpolar` already has: the layer
    keeps its audio, braille and text and ships without a highlight, rather
    than naming an element the chart does not draw.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Scatterpolar(
                    r=RADII, theta=SPOKES, mode="text", text=list("abcd")
                )
            ]
        )
    )

    assert layer["type"] == PlotType.RADAR
    assert "selectors" not in layer
    assert _spokes(layer) == list(zip(SPOKES, RADII))


def test_a_polar_area_is_read_but_not_addressed() -> None:
    """A stated limit, not an oversight.

    A barpolar draws one bar per spoke and no per-series path. Four
    selectors would be read as four series; the single selector its one
    series is allowed would have to name the whole `.trace.bars` group,
    which outlines every bar at once and highlights the same thing at every
    step. Neither answers "where am I", so the layer ships without a
    highlight and keeps its audio, braille and text -- the outcome #145
    established for a layer with nothing to point at.
    """
    (layer,) = _layers(go.Figure([go.Barpolar(r=RADII, theta=SPOKES)]))

    assert "selectors" not in layer
    assert _spokes(layer) == list(zip(SPOKES, RADII))


def test_a_barpolar_does_not_shift_a_radar_position() -> None:
    """They are drawn into different layers.

    A `scatterpolar` is numbered among the polar *scatter* traces, because
    that is what the `.polarlayer .scatterlayer` groups hold. Measured on
    `[radar, bars, radar]`: the second radar's `nth-child(2)` resolved to
    its own outline.
    """
    first, _bars, second = _layers(
        go.Figure(
            [
                go.Scatterpolar(r=[3, 9, 5], theta=["N", "E", "S"], name="a"),
                go.Barpolar(r=[1, 4, 8], theta=["N", "E", "S"], name="bars"),
                go.Scatterpolar(r=[2, 6, 4], theta=["N", "E", "S"], name="b"),
            ]
        )
    )

    assert "nth-child(1)" in first["selectors"][0]
    assert "nth-child(2)" in second["selectors"][0]


def test_the_radius_is_named_from_the_polar_layout() -> None:
    """Plotly names it under `layout.polar`, not `xaxis`/`yaxis`.

    A polar chart has no cartesian axes to borrow from, so reading the
    cartesian pair would take another trace's titles or the generic
    fallback where the author had in fact named this one.
    """
    figure = go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)])
    figure.update_layout(polar={"radialaxis": {"title": {"text": "Speed"}}})

    (layer,) = _layers(figure)

    assert layer["axes"]["y"]["label"] == "Speed"


def test_the_angle_has_no_title_to_read() -> None:
    """`angularaxis` does not have the property at all.

    Measured: plotly rejects it outright -- *"Invalid property specified for
    object of type plotly.graph_objs.layout.polar.AngularAxis: 'title'"* --
    and `'title' in AngularAxis._valid_props` is False while the radial
    axis's is True. So the angle always takes the generic word, and reading
    a title off it would be reading a key plotly never writes.
    """
    from plotly.graph_objs.layout.polar import AngularAxis, RadialAxis

    assert "title" not in AngularAxis._valid_props
    assert "title" in RadialAxis._valid_props

    figure = go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)])
    figure.update_layout(polar={"radialaxis": {"title": {"text": "Speed"}}})

    (layer,) = _layers(figure)

    assert layer["axes"]["x"]["label"] == "Angle"


def test_unnamed_polar_axes_fall_back_to_the_generic_pair() -> None:
    """The control: the fallback must not overwrite a stated title."""
    (layer,) = _layers(go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)]))

    assert layer["axes"]["x"]["label"] == "Angle"
    assert layer["axes"]["y"]["label"] == "Radius"


def test_two_polar_subplots_are_two_cells() -> None:
    """A polar subplot's rectangle has to join the figure's grid.

    A polar trace names no axis pair, so `_extract_plots` groups every one
    of them under the cartesian defaults however many subplots they are
    spread over, and the grid is built from `layout.xaxis`/`yaxis` domains
    and from domain *traces* -- neither of which a polar subplot is. Its
    rectangle lives under `layout.polar`/`layout.polar2`, so before this a
    1x2 polar grid collected no starts at all and both charts landed in one
    cell.
    """
    figure = make_subplots(rows=1, cols=2, specs=[[{"type": "polar"}] * 2])
    figure.add_trace(go.Scatterpolar(r=[3, 9, 5], theta=SPOKES[:3]), row=1, col=1)
    figure.add_trace(go.Scatterpolar(r=[2, 6, 4], theta=SPOKES[:3]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    assert [layer["type"] for layer in grid[0][0]["layers"]] == [PlotType.RADAR]
    assert [layer["type"] for layer in grid[0][1]["layers"]] == [PlotType.RADAR]


def test_a_polar_beside_a_cartesian_subplot_keeps_its_own_column() -> None:
    """The common mixed grid, and the same omission.

    `make_subplots(1, 2, [xy, polar])` writes the bar's rectangle into
    `layout.xaxis.domain` and the radar's into `layout.polar.domain`. Only
    the first was collected, so the figure had one column and both layers
    were read as one chart.
    """
    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "xy"}, {"type": "polar"}]]
    )
    figure.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
    figure.add_trace(go.Scatterpolar(r=[3, 9, 5], theta=SPOKES[:3]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    assert [layer["type"] for layer in grid[0][0]["layers"]] == [PlotType.BAR]
    assert [layer["type"] for layer in grid[0][1]["layers"]] == [PlotType.RADAR]


def test_each_polar_subplot_addresses_its_own_outline() -> None:
    """One `.polarlayer` holds every polar subplot, so the scope matters.

    Measured in Chromium on a 1x2 polar grid: plotly draws
    `<g class="polar">` and `<g class="polar2">` under one `.polarlayer`,
    each with its own `.scatterlayer` numbered from one. The unscoped
    selector therefore matched *both* first traces -- one keypress outlining
    two charts -- while `nth-child(2)` matched nothing, because no subplot
    held a second. Scoped, each of these resolved to exactly one element,
    and the two to different ones.
    """
    figure = make_subplots(rows=1, cols=2, specs=[[{"type": "polar"}] * 2])
    figure.add_trace(go.Scatterpolar(r=[3, 9, 5], theta=SPOKES[:3]), row=1, col=1)
    figure.add_trace(go.Scatterpolar(r=[2, 6, 4], theta=SPOKES[:3]), row=1, col=2)

    first, second = _layers(figure)

    assert first["selectors"] == [
        ".polarlayer > g.polar .scatterlayer .trace:nth-child(1) path.js-line"
    ]
    assert second["selectors"] == [
        ".polarlayer > g.polar2 .scatterlayer .trace:nth-child(1) path.js-line"
    ]


def test_a_second_subplot_numbers_its_traces_from_one() -> None:
    """The position is a place in one `.scatterlayer`, not in the figure.

    A running counter across every polar trace gave the second subplot's
    only radar `nth-child(2)`, which resolves to nothing inside its own
    group. Measured on this figure: `g.polar2 ... nth-child(1)` and
    `nth-child(2)` are the two radars of that subplot, and the barpolar
    between them shifts neither -- it draws into `g.polar2`'s `.barlayer`.
    """
    figure = make_subplots(rows=1, cols=2, specs=[[{"type": "polar"}] * 2])
    figure.add_trace(go.Scatterpolar(r=[3, 9, 5], theta=SPOKES[:3]), row=1, col=1)
    figure.add_trace(go.Scatterpolar(r=[2, 6, 4], theta=SPOKES[:3]), row=1, col=2)
    figure.add_trace(go.Barpolar(r=[1, 4, 8], theta=SPOKES[:3]), row=1, col=2)
    figure.add_trace(go.Scatterpolar(r=[7, 8, 9], theta=SPOKES[:3]), row=1, col=2)

    left, right_first, _bars, right_second = _layers(figure)

    assert "g.polar .scatterlayer .trace:nth-child(1)" in left["selectors"][0]
    assert "g.polar2 .scatterlayer .trace:nth-child(1)" in right_first["selectors"][0]
    assert "g.polar2 .scatterlayer .trace:nth-child(2)" in right_second["selectors"][0]


def test_each_polar_subplot_is_named_from_its_own_layout_block() -> None:
    """`layout.polar2` is the second chart's, and only its own.

    The titles were read from `layout.polar` for every polar trace, so the
    second subplot announced the first one's radial name -- a wrong word
    rather than a missing one, which a reader has no way to catch.
    """
    figure = make_subplots(rows=1, cols=2, specs=[[{"type": "polar"}] * 2])
    figure.add_trace(go.Scatterpolar(r=[3, 9, 5], theta=SPOKES[:3]), row=1, col=1)
    figure.add_trace(go.Scatterpolar(r=[2, 6, 4], theta=SPOKES[:3]), row=1, col=2)
    figure.update_layout(
        polar={"radialaxis": {"title": "Left R"}},
        polar2={"radialaxis": {"title": "Right R"}},
    )

    first, second = _layers(figure)

    assert first["axes"]["y"]["label"] == "Left R"
    assert second["axes"]["y"]["label"] == "Right R"


def test_a_scatterpolargl_is_read_as_a_radar() -> None:
    """The WebGL twin draws the same spokes and was read as nothing (#668).

    `go.Scatterpolargl` carries the same `r` and `theta` as
    `go.Scatterpolar` and differs only in being painted by regl. The polar
    branch of `_extract_plots` listed two trace types by name and this was
    not one of them, so the figure produced no layers at all and took the
    static-image path.
    """
    (layer,) = _layers(go.Figure([go.Scatterpolargl(r=RADII, theta=SPOKES)]))

    assert layer["type"] == PlotType.RADAR
    assert _spokes(layer) == list(zip(SPOKES, RADII))


@pytest.mark.parametrize("mode", [None, "lines", "markers", "lines+markers"])
def test_a_scatterpolargl_is_read_but_not_addressed(mode) -> None:
    """It is painted to a canvas, so there is no element in any mode.

    Measured in Chromium on `r=[1, 2, 3]`, counting inside the polar
    subplot: a `scatterpolar` puts one `.trace` in the `.scatterlayer` and
    no canvas on the page, while a `scatterpolargl` puts none there and
    three canvases -- for `mode="lines"` and `mode="markers"` alike. So
    neither the outline nor the markers `PlotlyPolarPlot` names for an SVG
    radar exists here, and the layer ships without a highlight, keeping its
    audio, braille and text.
    """
    trace = go.Scatterpolargl(r=RADII, theta=SPOKES, mode=mode)
    (layer,) = _layers(go.Figure([trace]))

    assert layer["type"] == PlotType.RADAR
    assert "selectors" not in layer
    assert _spokes(layer) == list(zip(SPOKES, RADII))


@pytest.mark.parametrize("gl_first", [True, False])
def test_a_scatterpolargl_does_not_shift_a_radar_position(gl_first: bool) -> None:
    """It never enters the `.scatterlayer` the `nth-child` counts over.

    The trap the cartesian numbering already documents, in the polar
    subplot: counting a canvas trace would push its SVG sibling one place
    along, onto a selector matching nothing.

    Measured in Chromium on one polar subplot holding one of each --
    declared either way round, the `.scatterlayer` holds exactly one child
    and it is the SVG trace, at `nth-child(1)`.
    """
    gl = go.Scatterpolargl(r=[3, 9, 5], theta=["N", "E", "S"], name="gl")
    svg = go.Scatterpolar(r=[2, 6, 4], theta=["N", "E", "S"], name="svg")
    layers = _layers(go.Figure([gl, svg] if gl_first else [svg, gl]))

    named = [layer for layer in layers if "selectors" in layer]
    assert len(layers) == 2
    assert len(named) == 1
    assert "nth-child(1)" in named[0]["selectors"][0]


def test_a_scatterpolargl_still_reads_its_own_spokes_beside_an_svg_one() -> None:
    """Losing the highlight costs it nothing else.

    Both layers are emitted, in the order plotly declared them, and each
    announces the radii it was given -- which is the whole point of reading
    a canvas trace rather than declining it.
    """
    first, second = _layers(
        go.Figure(
            [
                go.Scatterpolargl(r=[3, 9, 5], theta=["N", "E", "S"], name="gl"),
                go.Scatterpolar(r=[2, 6, 4], theta=["N", "E", "S"], name="svg"),
            ]
        )
    )

    assert _spokes(first) == [("N", 3), ("E", 9), ("S", 5)]
    assert _spokes(second) == [("N", 2), ("E", 6), ("S", 4)]

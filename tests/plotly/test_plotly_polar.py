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
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

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


def test_a_radar_addresses_its_outline() -> None:
    """One selector for one series, which is what the contract wants.

    Measured: a scatterpolar draws exactly one `path.js-line` per trace.
    """
    (layer,) = _layers(go.Figure([go.Scatterpolar(r=RADII, theta=SPOKES)]))

    assert layer["selectors"] == [
        ".polarlayer .scatterlayer .trace:nth-child(1) path.js-line"
    ]


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

"""Seven plotly map traces registered no layer at all (#683).

`go.Choropleth` was read; every other trace plotly draws on a map was not.
Measured through `PlotlyMaidr(fig)._flatten_maidr()` on plotly 6.7.0, counting
the layers each figure produced::

    Scattergeo             n=0
    Scattermap             n=0
    Scattermapbox          n=0
    Densitymap             n=0
    Densitymapbox          n=0
    Choroplethmap          n=0
    Choroplethmapbox       n=0
    Choropleth (read)      n=1   choropleth pts=1

Zero layers means the whole figure falls back to a picture: a `go.Scattergeo`
of three cities was silent.

**A scatter of degrees, not a choropleth.** A placed marker has a position and
a name and no magnitude. `ChoroplethPoint.y` is required, and the only ways to
supply one are to invent a constant or to promote the array index -- both
announce a measurement the chart never made. The same reading the Highcharts
adapter gives `mappoint` (xability/maidr#1187).
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

LAT = [51.5, 48.9, 59.9]
LON = [-0.13, 2.35, 10.75]
NAMES = ["London", "Paris", "Oslo"]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _placed(layer: dict) -> list[tuple]:
    """Each marker as ``(longitude, latitude)``."""
    return [(point[MaidrKey.X], point[MaidrKey.Y]) for point in layer["data"]]


@pytest.mark.parametrize(
    "trace",
    [
        go.Scattergeo(lat=LAT, lon=LON, text=NAMES),
        go.Scattermap(lat=LAT, lon=LON, text=NAMES),
        go.Scattermapbox(lat=LAT, lon=LON, text=NAMES),
    ],
    ids=["scattergeo", "scattermap", "scattermapbox"],
)
def test_a_map_of_markers_is_read_rather_than_registering_nothing(trace) -> None:
    """The reproduction, across the three spellings of one chart.

    `scattermapbox` is deprecated in favour of `scattermap`, but plotly still
    draws it and figures in the wild still use it, so it is read too.
    """
    (layer,) = _layers(go.Figure([trace]))

    assert layer["type"] is PlotType.SCATTER
    assert _placed(layer) == [(-0.13, 51.5), (2.35, 48.9), (10.75, 59.9)]


def test_a_marker_is_placed_at_its_longitude_and_latitude_that_way_round() -> None:
    """Swapped, every place is announced somewhere it is not.

    London is 51.5 degrees north and 0.13 west. Read the other way it lands in
    the Indian Ocean, and nothing in the payload would say so.
    """
    (layer,) = _layers(go.Figure([go.Scattergeo(lat=LAT, lon=LON, text=NAMES)]))
    london = layer["data"][0]

    assert london[MaidrKey.X] == -0.13
    assert london[MaidrKey.Y] == 51.5
    assert london[MaidrKey.LABEL] == "London"


def test_the_two_coordinates_are_named_rather_than_left_as_x_and_y() -> None:
    """A map draws no cartesian axes, so `layout.xaxis` holds neither name."""
    (layer,) = _layers(go.Figure([go.Scattergeo(lat=LAT, lon=LON)]))

    assert layer["axes"][MaidrKey.X][MaidrKey.LABEL] == "Longitude"
    assert layer["axes"][MaidrKey.Y][MaidrKey.LABEL] == "Latitude"
    # No `z` on a trace that carries no magnitude: an axis announced with
    # nothing behind it is a reading of a field the chart never filled.
    assert MaidrKey.Z not in layer["axes"]


def test_a_marker_with_no_name_carries_no_label() -> None:
    """`ScatterPoint.label` says "this point is Oslo". An empty one says nothing."""
    (layer,) = _layers(go.Figure([go.Scattergeo(lat=LAT, lon=LON)]))

    assert all(MaidrKey.LABEL not in point for point in layer["data"])


def test_a_blank_name_is_not_announced_as_one() -> None:
    """A whitespace string is a name the reader would hear as silence."""
    (layer,) = _layers(
        go.Figure([go.Scattergeo(lat=LAT, lon=LON, text=["London", "  ", "Oslo"])])
    )

    assert [point.get(MaidrKey.LABEL) for point in layer["data"]] == [
        "London",
        None,
        "Oslo",
    ]


@pytest.mark.parametrize(
    "trace",
    [
        go.Densitymap(lat=LAT, lon=LON, z=[5, 6, 7]),
        go.Densitymapbox(lat=LAT, lon=LON, z=[5, 6, 7]),
    ],
    ids=["densitymap", "densitymapbox"],
)
def test_a_density_map_carries_its_magnitude(trace) -> None:
    """`z` is a real measurement here, so it travels where the core sounds it."""
    (layer,) = _layers(go.Figure([trace]))

    assert [point[MaidrKey.Z] for point in layer["data"]] == [5.0, 6.0, 7.0]
    assert layer["axes"][MaidrKey.Z][MaidrKey.LABEL] == "Density"


def test_a_density_map_takes_the_colour_bar_title_for_its_magnitude() -> None:
    """The one thing the author may have written about what the colour means."""
    (layer,) = _layers(
        go.Figure(
            [
                go.Densitymap(
                    lat=LAT,
                    lon=LON,
                    z=[5, 6, 7],
                    colorbar={"title": {"text": "Sightings"}},
                )
            ]
        )
    )

    assert layer["axes"][MaidrKey.Z][MaidrKey.LABEL] == "Sightings"


@pytest.mark.parametrize(
    "trace",
    [
        go.Choroplethmap(locations=["a", "b"], z=[1, 2]),
        go.Choroplethmapbox(locations=["a", "b"], z=[1, 2]),
    ],
    ids=["choroplethmap", "choroplethmapbox"],
)
def test_a_choropleth_on_a_tiled_map_reads_as_the_choropleth_it_is(trace) -> None:
    """The base map is drawing, not data.

    `choropleth`, `choroplethmap` and `choroplethmapbox` carry the same
    `locations` and `z`; only what is painted underneath differs. Two of the
    three registered nothing while the first was read.
    """
    (layer,) = _layers(go.Figure([trace]))

    assert layer["type"] is PlotType.CHOROPLETH
    assert [(point[MaidrKey.X], point[MaidrKey.Y]) for point in layer["data"]] == [
        ("a", 1),
        ("b", 2),
    ]


def test_a_trace_that_placed_no_marker_is_declined_rather_than_emitted_empty() -> None:
    """A layer of no points is the phantom row #421 describes.

    The reader can navigate into it and it can say nothing. Declining leaves
    the rest of the figure readable.
    """
    assert _layers(go.Figure([go.Scattergeo(text=NAMES)])) == []


def test_a_marker_with_a_non_finite_coordinate_is_dropped_not_announced() -> None:
    """`json.dumps` writes `NaN` as a bare token, which `JSON.parse` rejects.

    One such value stops the chart initialising at all (#427) -- and plotly
    draws nothing there either, so announcing it would put a place on the map
    the reader cannot be told anything about.
    """
    (layer,) = _layers(
        go.Figure(
            [go.Scattergeo(lat=[1, None, 3], lon=[4, 5, 6], text=["a", "b", "c"])]
        )
    )

    assert _placed(layer) == [(4.0, 1.0), (6.0, 3.0)]
    # The names travel with the markers that survived, not with their indices.
    assert [point[MaidrKey.LABEL] for point in layer["data"]] == ["a", "c"]


def test_a_map_ships_without_a_selector() -> None:
    """The limit `PlotlyChoroplethPlot` already documents, for the same reason.

    Plotly fetches a projection's land geometry, and a tiled map's tiles, from
    the network at render time, so what the markers are drawn as could not be
    measured here. A highlight that lands on the wrong marker is worse than
    none; the layer keeps its audio, braille and text (#640).
    """
    (layer,) = _layers(go.Figure([go.Scattergeo(lat=LAT, lon=LON)]))

    assert not layer.get("selectors")


def test_a_map_takes_its_own_cell_beside_a_cartesian_subplot() -> None:
    """Placed by the named block a choropleth is, not by an axis pair."""
    grid = make_subplots(
        rows=1, cols=2, specs=[[{"type": "scattergeo"}, {"type": "xy"}]]
    )
    grid.add_trace(go.Scattergeo(lat=LAT, lon=LON, text=NAMES), row=1, col=1)
    grid.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

    cells = PlotlyMaidr(grid)._flatten_maidr()["subplots"]

    assert [layer["type"] for layer in cells[0][0]["layers"]] == [PlotType.SCATTER]
    assert [layer["type"] for layer in cells[0][1]["layers"]] == [PlotType.BAR]


@pytest.mark.parametrize(
    ("block", "trace"),
    [
        ("map", go.Scattermap(lat=LAT, lon=LON, text=NAMES)),
        ("mapbox", go.Scattermapbox(lat=LAT, lon=LON, text=NAMES)),
        ("map", go.Choroplethmap(locations=["a"], z=[1])),
        ("mapbox", go.Choroplethmapbox(locations=["a"], z=[1])),
    ],
    ids=["scattermap", "scattermapbox", "choroplethmap", "choroplethmapbox"],
)
def test_a_tiled_map_takes_its_own_cell_too(block, trace) -> None:
    """The tiled family names its block under a different field than `geo`.

    Measured on plotly 6.7.0: ``go.Scattergeo(geo="geo2")`` writes ``geo``,
    while ``go.Scattermap(subplot="map2")`` writes ``subplot`` -- and the
    block it defaults to is ``map`` for a maplibre figure and ``mapbox`` for
    a mapbox one. Resolving every map through ``geo`` puts the layer in
    whichever cell ``layout.geo`` happens to describe, which on a figure with
    no ``geo`` block at all is the first one -- on top of whatever is there.
    """
    # The map goes in the SECOND column deliberately. A block name that
    # resolves to nothing lands the layer at domain start (0, 0) -- which is
    # cell [0][0], where a map drawn first would have been anyway. Only a map
    # that is not first can tell a resolved block from an unresolved one.
    grid = make_subplots(rows=1, cols=2, specs=[[{"type": "xy"}, {"type": block}]])
    grid.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
    grid.add_trace(trace, row=1, col=2)

    cells = PlotlyMaidr(grid)._flatten_maidr()["subplots"]

    assert len(cells[0]) == 2
    assert [layer["type"] for layer in cells[0][0]["layers"]] == [PlotType.BAR]
    assert [layer["type"] for layer in cells[0][1]["layers"]] in (
        [PlotType.SCATTER],
        [PlotType.CHOROPLETH],
    )


def test_markers_over_regions_land_on_the_same_map() -> None:
    """Two layers, one cell: they are drawn on one `geo` block.

    Splitting them across cells would tell the reader the capital is on a
    different map from the country it is in.
    """
    figure = go.Figure()
    figure.add_trace(go.Choropleth(locations=["USA"], z=[1]))
    figure.add_trace(go.Scattergeo(lat=[38.9], lon=[-77.0], text=["DC"]))

    cells = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert len(cells) == 1 and len(cells[0]) == 1
    assert [layer["type"] for layer in cells[0][0]["layers"]] == [
        PlotType.CHOROPLETH,
        PlotType.SCATTER,
    ]

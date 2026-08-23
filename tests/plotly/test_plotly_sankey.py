"""A plotly sankey produced a figure with no layers at all.

`go.Sankey` states weighted flow the way `FlowPoint` wants it -- one link,
two nodes, an amount -- except by **index**: `link.source` and `link.target`
point into `node.label`. Resolving those indices back to the names a reader
is told is the whole of the mapping. `maidr/plotly/` had none of it, so the
trace fell through `_extract_plots` to `PlotlyPlotFactory`, which returned
`None` (#627). The core has drawn sankeys since xability/maidr#810.

Two things measured in Chromium:

  * **the links are drawn in the trace's own order.** Read off the
    `__data__` d3 binds onto each ribbon, with values written out of order
    so a re-sort by magnitude would show: `value=[3, 9, 5, 1]` came back as
    indices 0, 1, 2, 3 in that order.
  * **two sankeys in one figure cannot be told apart.** Both `.sankey`
    groups are bare `<g class="sankey">` siblings under `main-svg` with no
    id and no data attribute; they differ only by a `transform`, which
    moves with the layout. `:nth-of-type` cannot separate them either --
    it counts *every* `<g>` sibling, and the two sankeys were the 15th and
    16th, so `.sankey:nth-of-type(1)` resolved to **0** elements.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Values written out of ascending order, so an emitted order that sorted
#: them could not pass by coincidence.
FLOW = {
    "node": {"label": ["a", "b", "c", "d"]},
    "link": {"source": [0, 0, 1, 2], "target": [1, 2, 3, 3], "value": [3, 9, 5, 1]},
}


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _links(layer: dict) -> list[tuple]:
    """Each link as ``(source, target, value)``, in the order emitted."""
    return [
        (point["source"], point["target"], point["value"]) for point in layer["data"]
    ]


def test_a_sankey_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing."""
    layers = _layers(go.Figure([go.Sankey(**FLOW)]))

    assert [layer["type"] for layer in layers] == [PlotType.SANKEY]


def test_the_endpoints_are_resolved_to_node_names() -> None:
    """Indices are what plotly states; names are what a reader is told.

    Passing the indices through would announce "0 to 1" -- true of the wire
    format and meaningless to anyone listening.
    """
    (layer,) = _layers(go.Figure([go.Sankey(**FLOW)]))

    assert _links(layer) == [
        ("a", "b", 3.0),
        ("a", "c", 9.0),
        ("b", "d", 5.0),
        ("c", "d", 1.0),
    ]


def test_the_links_keep_the_order_they_were_written_in() -> None:
    """Measured off the `__data__` on each drawn ribbon.

    The selector is positional, so a reordering here would land every later
    link on another ribbon -- and the reading would still sound plausible.
    """
    (layer,) = _layers(go.Figure([go.Sankey(**FLOW)]))

    assert [point["value"] for point in layer["data"]] == [3.0, 9.0, 5.0, 1.0]


def test_a_link_to_a_node_that_does_not_exist_is_skipped() -> None:
    """`FlowPoint` has no shape for a nameless end.

    Plotly draws nothing for an out-of-range index either, so passing one on
    would announce a ribbon that is not on the screen.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Sankey(
                    node={"label": ["a", "b"]},
                    link={"source": [0, 9], "target": [1, 0], "value": [5, 2]},
                )
            ]
        )
    )

    assert _links(layer) == [("a", "b", 5.0)]


def test_a_lone_sankey_addresses_its_ribbons() -> None:
    """Measured: `.sankey .sankey-link` resolved to one path per link."""
    (layer,) = _layers(go.Figure([go.Sankey(**FLOW)]))

    assert layer["selectors"] == ".sankey .sankey-link"


def test_two_sankeys_are_read_but_not_addressed() -> None:
    """A stated limit, not an oversight.

    The two `.sankey` groups cannot be separated by any stable selector, so
    a second sankey has no addressable geometry. Emitting a selector that
    matched both traces' ribbons would be worse than emitting none: the
    resolved count would equal neither layer's link count, so both
    highlights would be dropped anyway *and* the payload would claim an
    address it does not have.

    The layers still read -- audio, braille and text are unaffected -- which
    is the outcome #145 established for a layer with nothing to point at.
    """
    first, second = _layers(
        go.Figure(
            [
                go.Sankey(
                    node={"label": ["a", "b"]},
                    link={"source": [0], "target": [1], "value": [5]},
                    domain={"x": [0, 0.45]},
                ),
                go.Sankey(
                    node={"label": ["p", "q", "r"]},
                    link={"source": [0, 1], "target": [1, 2], "value": [2, 3]},
                    domain={"x": [0.55, 1]},
                ),
            ]
        )
    )

    assert "selectors" not in first
    assert "selectors" not in second
    assert _links(first) == [("a", "b", 5.0)]
    assert _links(second) == [("p", "q", 2.0), ("q", "r", 3.0)]


def test_a_sankey_names_its_two_dimensions() -> None:
    """It draws no axes, so the generic pair says what the two are."""
    (layer,) = _layers(go.Figure([go.Sankey(**FLOW)]))

    assert layer["axes"]["x"]["label"] == "Flow"
    assert layer["axes"]["y"]["label"] == "Value"


def test_a_sankey_takes_a_grid_cell_of_its_own() -> None:
    """It is placed by its own `domain`, as a pie is."""
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
    )
    figure.add_trace(go.Sankey(**FLOW), row=1, col=1)
    figure.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

    cells = [(plot.row_index, plot.col_index) for plot in PlotlyMaidr(figure)._plots]

    assert cells == [(0, 0), (0, 1)]

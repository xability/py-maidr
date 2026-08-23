"""A plotly parallel sets diagram produced a figure with no layers.

`go.Parcats` puts categorical dimensions side by side and draws a ribbon
between adjacent ones for every combination that occurs, at a width
proportional to how often it does. `maidr/plotly/` had no handling for it, so
it fell through `_extract_plots` to `PlotlyPlotFactory`, which returned
`None` (#627). The core has had `TraceType.ALLUVIAL` for this shape, sharing
`FlowTrace` with `SANKEY` and `CHORD`.

A `FlowPoint` is one weighted flow between two named nodes, so a ribbon
spanning several dimensions becomes one flow **per adjacent pair**. That is
what the grammar's unit is, and it is also the reading: a parallel sets
diagram shows how a population is re-divided at each step, and each step is
a pair.

Two things measured in Chromium decided the rest:

  * **Plotly merges duplicate combinations.** Five rows whose first and fifth
    share a combination drew *four* ribbons, the shared one at the summed
    count of 8.
  * **Plotly writes the ribbons in its own layout order.** The `key` values
    bound to the four paths, in document order, were `0, 2, 1, 3`, carrying
    counts `8, 2, 1, 4`. So the drawn order is not the declared order and is
    not computable offline, which is why the layer takes no selector.
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


def _flows(layer: dict) -> list[tuple]:
    """Each flow as ``(source, target, value)``."""
    return [(f["source"], f["target"], f["value"]) for f in layer["data"]]


TITANIC = go.Parcats(
    dimensions=[
        {"label": "Sex", "values": ["M", "F", "M", "F", "M"]},
        {"label": "Class", "values": ["1", "1", "2", "2", "1"]},
    ],
    counts=[3, 1, 2, 4, 5],
)


def test_a_parcats_is_read_as_an_alluvial_layer() -> None:
    """The reproduction, and the type it becomes."""
    (layer,) = _layers(go.Figure([TITANIC]))

    assert layer["type"] is PlotType.ALLUVIAL


def test_duplicate_combinations_are_one_flow_at_their_summed_weight() -> None:
    """Which is what plotly draws, not a tidying choice.

    Rows one and five are both `(M, 1)`, at counts 3 and 5. Measured, plotly
    drew four ribbons for the five rows and gave the shared one a count of 8.
    Emitting the rows unaggregated would announce two flows where the chart
    draws one, and each at the wrong width.
    """
    (layer,) = _layers(go.Figure([TITANIC]))

    assert _flows(layer) == [
        ("Sex: M", "Class: 1", 8.0),
        ("Sex: F", "Class: 1", 1.0),
        ("Sex: M", "Class: 2", 2.0),
        ("Sex: F", "Class: 2", 4.0),
    ]


def test_a_ribbon_across_three_dimensions_is_two_flows() -> None:
    """One flow per adjacent pair, which is the grammar's unit.

    `FlowTrace` reads a flow as two nodes and a weight, so a ribbon spanning
    three dimensions has no single pair to be. Splitting it at each step is
    also the reading: what the chart shows is the re-division, and each
    re-division happens between one pair of columns.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcats(
                    dimensions=[
                        {"label": "A", "values": ["x", "x"]},
                        {"label": "B", "values": ["p", "q"]},
                        {"label": "C", "values": ["1", "1"]},
                    ]
                )
            ]
        )
    )

    assert _flows(layer) == [
        ("A: x", "B: p", 1.0),
        ("A: x", "B: q", 1.0),
        ("B: p", "C: 1", 1.0),
        ("B: q", "C: 1", 1.0),
    ]


def test_a_level_name_shared_between_dimensions_stays_two_nodes() -> None:
    """The reason a node is named for its dimension.

    A parallel sets diagram routinely repeats a level across dimensions --
    "yes" under one question and "yes" under the next. The grammar derives
    its nodes *from the flows*, so two nodes named alike are one node: the
    chart's two columns would collapse into a single node with a flow to
    itself, which is not a thing the chart draws.

    It is also what the reader needs. "First: yes" says which question was
    answered; "yes" alone does not.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcats(
                    dimensions=[
                        {"label": "First", "values": ["yes", "no"]},
                        {"label": "Second", "values": ["yes", "yes"]},
                    ]
                )
            ]
        )
    )

    sources = {source for source, _, _ in _flows(layer)}
    targets = {target for _, target, _ in _flows(layer)}

    assert "First: yes" in sources
    assert "Second: yes" in targets
    assert not sources & targets


def test_a_hidden_dimension_is_not_a_step() -> None:
    """`visible: False` takes a dimension out of the drawing.

    A flow through it would join two nodes the chart never places side by
    side, and announce a re-division that is not drawn. The two visible
    columns become adjacent, which is what the reader sees.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcats(
                    dimensions=[
                        {"label": "A", "values": ["x", "y"]},
                        {"label": "H", "values": ["p", "q"], "visible": False},
                        {"label": "B", "values": ["1", "2"]},
                    ]
                )
            ]
        )
    )

    assert _flows(layer) == [("A: x", "B: 1", 1.0), ("A: y", "B: 2", 1.0)]


def test_a_row_weighs_one_when_the_trace_declares_no_counts() -> None:
    """Which is what plotly does with it.

    `counts` is optional; without it each row is one observation. Two
    identical rows are therefore one flow of weight two, not one of weight
    one.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Parcats(
                    dimensions=[
                        {"label": "A", "values": ["x", "x"]},
                        {"label": "B", "values": ["p", "p"]},
                    ]
                )
            ]
        )
    )

    assert _flows(layer) == [("A: x", "B: p", 2.0)]


def test_a_single_dimension_forms_no_layer() -> None:
    """One column has nothing to flow to, so the chart draws no ribbon.

    No guard here says so: there is no adjacent pair, so the extraction
    yields nothing and #636's payload guard drops the layer. The answer is
    arrived at once rather than twice, and this is what pins it.
    """
    assert (
        _layers(
            go.Figure([go.Parcats(dimensions=[{"label": "A", "values": ["x", "y"]}])])
        )
        == []
    )


def test_no_dimensions_at_all_does_not_take_the_render_down() -> None:
    """The one case that does need its own guard.

    With no columns there is nothing to take a minimum length over, and
    `min()` on an empty sequence raises -- measured, `ValueError: min() arg
    is an empty sequence`, which propagates out of `_flatten_maidr()` and
    takes the whole figure with it rather than costing one layer.
    """
    assert _layers(go.Figure([go.Parcats(dimensions=[])])) == []


def test_a_parcats_is_read_but_not_addressed() -> None:
    """A stated limit, and the third distinct reason for one.

    Measured in Chromium: the four `path` elements carry `key` values `0, 2,
    1, 3` in document order, with counts `8, 2, 1, 4`. Plotly lays its
    ribbons out in its own order, which is not the declaration order and is
    not computable from the trace offline.

    A positional selector list would therefore resolve to real elements and
    to the *wrong* ones -- a highlight that is confidently incorrect, which
    is worse than none. So the layer ships without one and keeps its audio,
    braille and text, the outcome #145 established.
    """
    (layer,) = _layers(go.Figure([TITANIC]))

    assert "selectors" not in layer


def test_a_flow_layer_names_no_axes() -> None:
    """`FlowTrace` announces a flow as its nodes and its weight.

    Each node carries its own dimension name, so there is no x or y for a
    reader to be told about -- and inventing a pair would put words in a
    chart that has neither.
    """
    (layer,) = _layers(go.Figure([TITANIC]))

    assert layer["axes"] == {}


def test_a_parcats_takes_its_own_grid_cell() -> None:
    """It is placed by its own `domain` rectangle, like a pie.

    Now that maidr renders it, that rectangle joins the figure's column
    universe -- otherwise a cartesian subplot beside it would sit in the
    wrong column.
    """
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
    )
    figure.add_trace(TITANIC, row=1, col=1)
    figure.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    assert [layer["type"] for layer in grid[0][0]["layers"]] == [PlotType.ALLUVIAL]
    assert [layer["type"] for layer in grid[0][1]["layers"]] == [PlotType.BAR]

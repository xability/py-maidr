"""A trace that draws nothing formed a layer anyway, for most families.

#421 established the rule -- a trace plotly draws nothing for forms no layer
-- and implemented it where it mattered then, by excluding an undrawn trace
from the line and area *groupings* with `draws_marks()`. Every other family's
build block appended unconditionally, so an empty pie, sankey, hierarchy,
polar or parcoords became a layer with an empty payload (#636).

Measured before the fix, layers per figure:

    empty pie          [[1]]
    empty sankey       [[1]]
    empty scatterpolar [[1]]
    empty parcoords    [[1]]
    empty scatter      [[0]]   <- the one that was filtered

That is not a harmless no-op. It is a cell the reader can tab into and find
nothing in, and for the line-family types it is worse: `LineTrace` throws on
an empty series and takes the whole render down (xability/maidr#905).
`ParallelTrace` and `RadarTrace` are both built on it.

The fix is one guard on the rendered payload, after the build blocks, so
every trace type reaches the same answer and a new one added later inherits
it. `draws_marks()` stays where it is: it does something a later filter
cannot, keeping the *positions* of the surviving series contiguous.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


EMPTY = [
    pytest.param(go.Pie(labels=[], values=[]), id="pie"),
    pytest.param(
        go.Sankey(
            node={"label": []},
            link={"source": [], "target": [], "value": []},
        ),
        id="sankey",
    ),
    pytest.param(go.Scatterpolar(r=[], theta=[]), id="scatterpolar"),
    pytest.param(go.Parcoords(dimensions=[]), id="parcoords"),
    pytest.param(go.Treemap(labels=[], parents=[]), id="treemap"),
    pytest.param(go.Bar(x=[], y=[]), id="bar"),
    pytest.param(go.Scatter(x=[], y=[]), id="scatter"),
    pytest.param(go.Histogram(), id="histogram"),
    pytest.param(go.Heatmap(z=[]), id="heatmap"),
]


@pytest.mark.parametrize("trace", EMPTY)
def test_a_trace_that_draws_nothing_forms_no_layer(trace) -> None:
    """The whole point, across every family that reaches the guard.

    `scatter` is in the list as the control: it was already filtered, by
    #421's `draws_marks()`, and has to stay filtered -- the new guard must
    not be the *only* thing keeping it out, or removing `draws_marks()` would
    look harmless when it is not.
    """
    assert _layers(go.Figure([trace])) == []


DRAWN = [
    pytest.param(go.Pie(labels=["a", "b"], values=[1, 2]), id="pie"),
    pytest.param(
        go.Sankey(
            node={"label": ["a", "b"]},
            link={"source": [0], "target": [1], "value": [5]},
        ),
        id="sankey",
    ),
    pytest.param(go.Scatterpolar(r=[1, 2], theta=[0, 90]), id="scatterpolar"),
    pytest.param(
        go.Parcoords(dimensions=[{"label": "A", "values": [1, 2]}]), id="parcoords"
    ),
    pytest.param(
        go.Treemap(labels=["r", "a"], parents=["", "r"], values=[3, 1]), id="treemap"
    ),
    pytest.param(go.Bar(x=["a"], y=[1]), id="bar"),
    pytest.param(go.Scatter(x=[1], y=[2]), id="scatter"),
    pytest.param(go.Heatmap(z=[[1, 2], [3, 4]]), id="heatmap"),
]


@pytest.mark.parametrize("trace", DRAWN)
def test_a_trace_that_draws_something_still_forms_a_layer(trace) -> None:
    """The controls. A guard this broad has to be shown not to overreach."""
    assert len(_layers(go.Figure([trace]))) == 1


def test_a_gauge_whose_every_number_is_zero_is_not_an_empty_payload() -> None:
    """The case a naive truthiness test gets wrong.

    A gauge's payload is a single *mapping* rather than a list, and every one
    of its three fields is a number. Measured, a dial declared
    `range=[0, 0]` with a reading of `0` emits
    `{"value": 0.0, "min": 0.0, "max": 0.0}` -- three fields, all falsy, and a
    complete reading of a chart the author asked for.

    `any(bool(v) for v in data.values())` drops it. That is why the mapping
    branch asks whether each field *holds something* rather than whether it is
    truthy: a zero is a number, and silencing a correct chart is the exact
    failure this guard exists to avoid causing.
    """
    figure = go.Figure(
        [go.Indicator(mode="gauge+number", value=0, gauge={"axis": {"range": [0, 0]}})]
    )

    (layer,) = _layers(figure)

    assert layer["data"]["value"] == 0


#: Every plot type maidr builds for a plotly figure, with a drawn example.
#: Kept exhaustive on purpose -- see the contract test below.
EVERY_TYPE = [
    pytest.param(go.Bar(x=["a"], y=[1]), id="bar"),
    pytest.param(go.Scatter(x=[1], y=[2]), id="scatter"),
    pytest.param(go.Pie(labels=["a"], values=[1]), id="pie"),
    pytest.param(go.Heatmap(z=[[1, 2], [3, 4]]), id="heatmap"),
    pytest.param(go.Histogram(x=[1, 2, 2, 3]), id="histogram"),
    pytest.param(go.Box(y=[1, 2, 3]), id="box"),
    pytest.param(go.Violin(y=[1, 2, 3]), id="violin"),
    pytest.param(
        go.Sankey(
            node={"label": ["a", "b"]},
            link={"source": [0], "target": [1], "value": [5]},
        ),
        id="sankey",
    ),
    pytest.param(
        go.Treemap(labels=["r", "a"], parents=["", "r"], values=[3, 1]), id="treemap"
    ),
    pytest.param(
        go.Indicator(mode="gauge+number", value=1, gauge={"axis": {"range": [0, 2]}}),
        id="gauge",
    ),
    pytest.param(go.Scatterpolar(r=[1], theta=[0]), id="scatterpolar"),
    pytest.param(
        go.Parcoords(dimensions=[{"label": "A", "values": [1, 2]}]), id="parcoords"
    ),
    pytest.param(go.Funnel(y=["a", "b"], x=[10, 5]), id="funnel"),
    pytest.param(go.Waterfall(x=["a"], y=[1]), id="waterfall"),
    pytest.param(
        go.Candlestick(x=[1], open=[1], high=[2], low=[0], close=[1.5]),
        id="candlestick",
    ),
]


@pytest.mark.parametrize("trace", EVERY_TYPE)
def test_a_payload_is_one_of_the_shapes_the_guard_knows(trace) -> None:
    """The contract the guard is written against, asserted rather than assumed.

    Measured across every plot type maidr builds, a payload is one of exactly
    three shapes: a list (thirteen of them), the gauge's
    `{value, min, max}` mapping of numbers, and the heatmap's
    `{points: [...]}`.

    The guard handles a list and a mapping and *keeps* anything else, on the
    grounds that an unfamiliar shape is not evidence of emptiness. That branch
    is unreachable today, which is exactly why this test exists: a fourth
    shape added later has to come with a decision about what empty means for
    it, and this is where that decision gets asked for.
    """
    for layer in _layers(go.Figure([trace])):
        data = layer["data"]
        assert isinstance(data, (list, dict)), type(data)
        if isinstance(data, dict):
            assert all(
                isinstance(value, (int, float, list)) for value in data.values()
            ), data


def test_a_heatmap_of_one_empty_row_is_kept() -> None:
    """Where the guard deliberately stops.

    `go.Heatmap(z=[[]])` renders as `{"points": [[]]}` -- a mapping whose one
    field holds a non-empty list whose one entry is empty. Recursing to decide
    that is "really" empty would be guessing at a shape rather than reading
    it, and dropping a layer that should have shipped is the more damaging of
    the two mistakes. One level, and this pins that boundary.
    """
    (layer,) = _layers(go.Figure([go.Heatmap(z=[[]])]))

    assert layer["data"] == {"points": [[]]}


def test_an_empty_trace_does_not_reserve_a_grid_cell() -> None:
    """The consequence for a figure that holds a drawn chart beside it.

    A dropped layer must not leave an empty cell behind for the reader to tab
    through, which is the other half of what #421 was about.
    """
    from plotly.subplots import make_subplots

    figure = make_subplots(rows=1, cols=2)
    figure.add_trace(go.Scatter(x=[], y=[]), row=1, col=1)
    figure.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [layer["type"] for row in grid for cell in row for layer in cell["layers"]]
    assert sum(len(cell.get("layers", [])) for row in grid for cell in row) == 1

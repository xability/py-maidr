"""A plotly candlestick chart produced a figure with no layers at all.

`maidr/plotly/` builds its MAIDR schema in Python, so it needs its own handling
per trace type, and it had none for `candlestick` or `ohlc`. Neither errored --
`_extract_plots` simply had no branch for them, so they fell through to
`PlotlyPlotFactory`, which returned `None`::

    go.Candlestick(...)   ->  layers: []
    go.Ohlc(...)          ->  layers: []

The HTML still rendered and MAIDR still loaded. What arrived was an empty
shell: a chart with nothing to navigate, no announcement, and no error saying
why (#343).

Nothing here is inferred. Both trace types state every number they draw --
`open`, `high`, `low` and `close` are arrays on the trace itself -- so this is
a transcription, not a reconstruction. The two differ only in how plotly draws
a bar, not in what it means, so both are read as `PlotType.CANDLESTICK`.

The selectors were measured in a browser rather than reasoned about, because
plotly puts a candlestick in the DOM in three ways that a plausible selector
gets wrong. Each is pinned by a test below with the measured counts.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Four candles, all four series distinct so a swapped pair cannot pass.
OHLC = {
    "x": ["d1", "d2", "d3", "d4"],
    "open": [1.0, 2.0, 3.0, 2.5],
    "high": [2.0, 3.0, 4.0, 3.2],
    "low": [0.0, 1.0, 2.0, 1.8],
    "close": [1.5, 2.5, 3.5, 2.0],
}

#: A second series, so two traces on one subplot can be told apart.
OTHER = {
    "x": ["d1", "d2", "d3", "d4"],
    "open": [5.0, 6.0, 7.0, 6.5],
    "high": [6.0, 7.0, 8.0, 7.2],
    "low": [4.0, 5.0, 6.0, 5.8],
    "close": [5.5, 6.5, 7.5, 6.0],
}


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _box(name: str, seed: int = 3) -> go.Box:
    """A box trace, which shares plotly's `boxlayer` with a candlestick."""
    return go.Box(y=list(np.random.default_rng(seed).normal(size=20)), name=name)


def test_a_candlestick_chart_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing.

    Not a crash and not a mislabel — `_extract_plots` had no branch for the
    type, so the figure arrived with an empty layer list and MAIDR had nothing
    to navigate.
    """
    layers = _layers(go.Figure([go.Candlestick(name="ACME", **OHLC)]))

    assert [layer["type"] for layer in layers] == [PlotType.CANDLESTICK]


def test_an_ohlc_chart_is_read_the_same_way() -> None:
    """`go.Ohlc` is the same numbers drawn differently.

    Plotly draws a body-and-wick for `candlestick` and a bar with ticks for
    `ohlc`. A reader is told open, high, low and close either way, so the two
    are one MAIDR type rather than two.
    """
    layers = _layers(go.Figure([go.Ohlc(name="ACME", **OHLC)]))

    assert [layer["type"] for layer in layers] == [PlotType.CANDLESTICK]


def test_the_numbers_are_the_traces_own() -> None:
    """Every value is transcribed, not derived.

    Each of the four series is distinct here, so a pair read in the wrong
    order — `high` for `close`, say — fails rather than passing on plausible
    numbers.
    """
    (layer,) = _layers(go.Figure([go.Candlestick(name="ACME", **OHLC)]))

    assert layer["data"] == [
        {"open": 1.0, "high": 2.0, "low": 0.0, "close": 1.5, "value": "d1"},
        {"open": 2.0, "high": 3.0, "low": 1.0, "close": 2.5, "value": "d2"},
        {"open": 3.0, "high": 4.0, "low": 2.0, "close": 3.5, "value": "d3"},
        {"open": 2.5, "high": 3.2, "low": 1.8, "close": 2.0, "value": "d4"},
    ]


def test_trend_and_volatility_are_left_to_the_core() -> None:
    """The core computes both from OHLC and overwrites what it is sent.

    `Candlestick`'s constructor in the MAIDR core maps every point to one
    carrying its own `trend` and `volatility`, so a copy emitted here could
    only ever be a second opinion that is discarded — and would rot silently
    if the core's rule ever changed. The matplotlib emitter omits them too.

    `volume` is absent for a different reason: no plotly OHLC trace carries
    one, and the core announces no volume section, so there is nothing to
    invent.
    """
    (layer,) = _layers(go.Figure([go.Candlestick(name="ACME", **OHLC)]))

    for candle in layer["data"]:
        assert set(candle) == {"open", "high", "low", "close", "value"}


def test_a_candle_without_an_x_is_named_by_its_index() -> None:
    """`x` is optional, and plotly labels the axis 0, 1, 2… without it.

    Naming the candles the same way keeps the announcement and the drawn axis
    saying the same thing.
    """
    figure = go.Figure(
        [
            go.Candlestick(
                open=[1.0, 2.0], high=[2.0, 3.0], low=[0.0, 1.0], close=[1.5, 2.5]
            )
        ]
    )

    (layer,) = _layers(figure)

    assert [candle["value"] for candle in layer["data"]] == ["0", "1"]


def test_a_gap_in_the_middle_drops_only_that_candle() -> None:
    """A missing number mid-series is a candle plotly leaves blank.

    The trailing case is covered by the ragged test below, but a `None` among
    otherwise equal-length arrays takes the other branch — the per-candle
    `except`, not the shortest-array count. Skipping keeps the announced
    candles aligned with the drawn ones; a placeholder would put a candle at
    a price nothing was traded at, and carrying the gap forward would shift
    every later candle onto the wrong date.
    """
    figure = go.Figure(
        [
            go.Candlestick(
                x=["d1", "d2", "d3"],
                open=[1.0, None, 3.0],
                high=[2.0, 3.0, 4.0],
                low=[0.0, 1.0, 2.0],
                close=[1.5, 2.5, 3.5],
            )
        ]
    )

    (layer,) = _layers(figure)

    assert [candle["value"] for candle in layer["data"]] == ["d1", "d3"]
    assert [candle["open"] for candle in layer["data"]] == [1.0, 3.0]


def test_a_ragged_trace_stops_at_the_shortest_series() -> None:
    """Plotly draws only the candles it has all four numbers for.

    Reading to the longest array instead would announce candles that were
    never drawn, filled from whichever series happened to be longer.
    """
    figure = go.Figure(
        [
            go.Candlestick(
                x=["d1", "d2", "d3"],
                open=[1.0, 2.0, 3.0],
                high=[2.0, 3.0, 4.0],
                low=[0.0, 1.0],  # one short
                close=[1.5, 2.5, 3.5],
            )
        ]
    )

    (layer,) = _layers(figure)

    assert [candle["value"] for candle in layer["data"]] == ["d1", "d2"]


# ---------------------------------------------------------------------------
# Selectors
#
# Pinned as exact strings because the failure they prevent is silent: a
# selector that matches the wrong elements highlights the wrong bar, and
# nothing in the schema says so. Each count below was measured in Chromium
# against real plotly output; the reasoning is in the docstrings so a future
# edit can tell an intentional change from a regression.
# ---------------------------------------------------------------------------


def test_the_selector_excludes_the_rangeslider() -> None:
    """Plotly gives a candlestick chart a rangeslider by **default**, and it
    holds a complete second copy of the plot.

    Measured for a 4-candle chart::

        .trace.boxes .box                                     8   ** the copy
        .subplot.xy .boxlayer > .trace.boxes:nth-child(1) …   4

    The duplicate lives at `g.infolayer > g.rangeslider-container >
    g.rangeslider-rangeplot.xy`, which carries the `xy` class but *not*
    `subplot` — so the `.subplot.<id>` prefix is what excludes it. Without
    that prefix a chart matches every mark twice, and the highlight for the
    second half of the candles lands in the thumbnail.

    This is asserted on the emitted string rather than the browser because the
    test suite has no DOM; the count above is the measurement it stands in for.
    """
    (layer,) = _layers(go.Figure([go.Candlestick(name="ACME", **OHLC)]))

    assert layer["selectors"] == (
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box"
    )


def test_an_ohlc_trace_has_a_layer_of_its_own() -> None:
    """`ohlc` does not share the box machinery — it draws into `g.ohlclayer`.

    Measured: `.subplot.xy .boxlayer …` matches 0 for an `ohlc` chart and
    `.subplot.xy .ohlclayer > .trace.ohlc:nth-child(1) > path` matches 4. The
    two types being one MAIDR layer type does not make them one DOM shape, so
    the selector is chosen per trace type rather than per layer type.
    """
    (layer,) = _layers(go.Figure([go.Ohlc(name="ACME", **OHLC)]))

    assert layer["selectors"] == (
        ".subplot.xy .ohlclayer > .trace.ohlc:nth-child(1) > path"
    )


def test_two_candlesticks_address_different_marks() -> None:
    """Two traces put two groups in one `boxlayer`.

    Without a position each selector matches all 8 marks, so every candle
    after the fourth highlights the other series — right count, wrong series,
    nothing raised.
    """
    figure = go.Figure(
        [go.Candlestick(name="A", **OHLC), go.Candlestick(name="B", **OTHER)]
    )

    positions = [layer["selectors"] for layer in _layers(figure)]

    assert positions == [
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box",
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(2) path.box",
    ]


def test_a_box_beside_a_candlestick_takes_a_slot() -> None:
    """A `go.Box` draws into the same `boxlayer`, and its own `path.box`.

    So the position is an index among *box-family* traces, not among
    candlesticks. Counting only candlesticks would put this one at
    `nth-child(1)` — the box's group — and every candle would highlight a
    box plot instead.
    """
    figure = go.Figure([_box("b"), go.Candlestick(name="A", **OHLC)])

    candle = next(
        layer for layer in _layers(figure) if layer["type"] is PlotType.CANDLESTICK
    )

    assert candle["selectors"] == (
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(2) path.box"
    )


def test_declaration_order_decides_the_slot() -> None:
    """Plotly appends one group per trace in the order they were declared.

    The mirror of the test above: the same two traces the other way round put
    the candlestick first. Measured rather than assumed, since a library that
    sorted by type instead would make both tests pass with one wrong.
    """
    figure = go.Figure([go.Candlestick(name="A", **OHLC), _box("b")])

    candle = next(
        layer for layer in _layers(figure) if layer["type"] is PlotType.CANDLESTICK
    )

    assert candle["selectors"] == (
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box"
    )


@pytest.mark.parametrize(
    "neighbour",
    [
        pytest.param(go.Violin(y=[1.0, 2.0, 3.0, 4.0], name="v"), id="violin"),
        pytest.param(go.Scatter(x=[1, 2], y=[1, 2], name="s"), id="scatter"),
    ],
)
def test_a_trace_in_another_layer_does_not_take_a_slot(neighbour) -> None:
    """Only `boxlayer` traces shift a candlestick's position.

    A violin draws into `g.violinlayer` and a scatter into `g.scatterlayer`,
    so neither appears among the candlestick's siblings. Counting every trace
    on the subplot instead would push this one to `nth-child(2)`, which does
    not exist — and a selector matching nothing loses the highlight silently,
    with the audio and text still working, so nothing else would report it.
    """
    figure = go.Figure([neighbour, go.Candlestick(name="A", **OHLC)])

    candle = next(
        layer for layer in _layers(figure) if layer["type"] is PlotType.CANDLESTICK
    )

    assert candle["selectors"] == (
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box"
    )


def test_a_candlestick_on_a_second_subplot_is_scoped_to_it() -> None:
    """The subplot prefix has to follow the trace, not default to `xy`.

    Two panels each holding one candlestick both sit at `nth-child(1)` of
    their own `boxlayer`, so the axis pair is the only thing telling them
    apart.
    """
    figure = go.Figure(
        [
            go.Candlestick(name="A", **OHLC),
            go.Candlestick(name="B", xaxis="x2", yaxis="y2", **OTHER),
        ]
    )
    figure.update_layout(
        xaxis={"domain": [0.0, 0.45]},
        xaxis2={"domain": [0.55, 1.0], "anchor": "y2"},
        yaxis2={"anchor": "x2"},
    )

    selectors = sorted(layer["selectors"] for layer in _layers(figure))

    assert selectors == [
        ".subplot.x2y2 .boxlayer > .trace.boxes:nth-child(1) path.box",
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box",
    ]


def test_a_figure_of_other_traces_is_unchanged() -> None:
    """The control: recognising a new type must cost the existing ones nothing.

    `_extract_plots` gained a branch ahead of the factory fallback, and a bar
    and a scatter both reach that fallback, so this drives the path the new
    branch sits in front of.
    """
    figure = go.Figure(
        [
            go.Bar(x=["a", "b"], y=[1.0, 2.0], name="bar"),
            go.Scatter(x=[1, 2], y=[3, 4], mode="markers", name="pts"),
        ]
    )

    assert [layer["type"] for layer in _layers(figure)] == [
        PlotType.BAR,
        PlotType.SCATTER,
    ]

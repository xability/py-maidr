"""A plotly waterfall chart produced a figure with no layers at all.

`maidr/plotly/` builds its MAIDR schema in Python and had no handling for
`waterfall`, so the trace fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None`::

    go.Waterfall(...)   ->  layers: []

The core has drawn waterfalls since xability/maidr#790 and the bundle shipped
in this wheel names the type, so nothing was missing downstream: a waterfall
written in plotly was silent only on the Python side (#627).

Plotly states a waterfall in *offsets* -- a `measure` array saying what each
`y` means -- while `WaterfallPoint` wants the two absolute running totals a
step sits between. The three measures were measured rather than read off the
documentation, by rendering each case in Chromium and inverting the drawn
rectangles back through plotly's own axis map. Every expectation below is one
of those measurements:

===========================  =================================================
input                        drawn (rounded off the 0.3px stroke bleed)
===========================  =================================================
`y=[10, -4, 7]`, no measure  `0->10`, `10->6`, `6->13`
the plotly docs' example     `0->60`, `60->140`, `0->140`, `140->100`,
                             `100->80`, `0->80`
`[relative, absolute,        `0->10`, `0->100`, `100->105`
 relative]` on `[10,100,5]`
`[.., .., total]` on         `0->10`, `10->15`, `0->15` -- the total's own
`[10, 5, 999]`               999 is ignored
`base=100` on `[10, 5, 0]`   `100->110`, `110->115`, `100->115`
===========================  =================================================
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: The example from plotly's own waterfall documentation, whose two `total`
#: steps are what separate a waterfall from a bar chart of deltas.
DOC = {
    "measure": ["relative", "relative", "total", "relative", "relative", "total"],
    "x": ["Sales", "Consulting", "Net revenue", "Purchases", "Other", "Profit"],
    "y": [60, 80, 0, -40, -20, 0],
}


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _spans(layer: dict) -> list[tuple[float, float]]:
    """Each step's `(start, end)` pair -- the bar's two ends."""
    return [(point["start"], point["end"]) for point in layer["data"]]


def test_a_waterfall_chart_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing.

    Not a crash and not a mislabel -- the figure arrived with an empty layer
    list and MAIDR had nothing to navigate.
    """
    layers = _layers(go.Figure([go.Waterfall(x=["a", "b", "c"], y=[10, -4, 7])]))

    assert [layer["type"] for layer in layers] == [PlotType.WATERFALL]


def test_a_measureless_waterfall_accumulates() -> None:
    """Every step is a contribution unless the author says otherwise.

    This is the whole difference from a bar chart: the same three numbers
    read as a bar layer would be `10`, `-4` and `7` at three independent
    positions, and the running total the chart is drawn to show would be
    nowhere in the payload.
    """
    (layer,) = _layers(go.Figure([go.Waterfall(x=["a", "b", "c"], y=[10, -4, 7])]))

    assert _spans(layer) == [(0, 10), (10, 6), (6, 13)]
    assert [point["delta"] for point in layer["data"]] == [10, -4, 7]


def test_a_total_step_restates_the_running_total() -> None:
    """A `total` draws from the base to wherever the chart has got to.

    The measured geometry of plotly's own example, step for step. A total
    read as a relative step would put `0` in `delta` and leave the reader
    with a bar the chart draws two hundred pixels tall and MAIDR calls
    nothing.
    """
    (layer,) = _layers(go.Figure([go.Waterfall(**DOC)]))

    assert _spans(layer) == [
        (0, 60),
        (60, 140),
        (0, 140),
        (140, 100),
        (100, 80),
        (0, 80),
    ]


def test_a_total_step_ignores_its_own_value() -> None:
    """`y` on a total is not drawn, so it must not be read.

    Measured: `y=999` on the third step drew `0->15`, the running total. The
    999 is what an author writes when they have not noticed plotly ignores
    it, and transcribing it would announce a number the chart never shows.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Waterfall(
                    measure=["relative", "relative", "total"],
                    x=["a", "b", "c"],
                    y=[10, 5, 999],
                )
            ]
        )
    )

    assert _spans(layer) == [(0, 10), (10, 15), (0, 15)]


def test_an_absolute_step_resets_the_running_total() -> None:
    """`absolute` sets the total rather than adding to it.

    Measured: after `[relative, absolute, relative]` on `[10, 100, 5]` the
    third step drew `100->105`, not `115->120`. Reading `absolute` as
    `relative` would leave every later step offset by the difference -- a
    whole chart wrong from the middle onwards, with nothing to say so.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Waterfall(
                    measure=["relative", "absolute", "relative"],
                    x=["a", "b", "c"],
                    y=[10, 100, 5],
                )
            ]
        )
    )

    assert _spans(layer) == [(0, 10), (0, 100), (100, 105)]


def test_base_moves_where_the_accumulation_starts() -> None:
    """`base` shifts the relative steps and the totals alike.

    Measured: `base=100` drew `100->110`, `110->115` and -- for the total --
    `100->115`, so the total's own floor is the base rather than zero.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Waterfall(
                    measure=["relative", "relative", "total"],
                    x=["a", "b", "c"],
                    y=[10, 5, 0],
                    base=100,
                )
            ]
        )
    )

    assert _spans(layer) == [(100, 110), (110, 115), (100, 115)]


def test_each_step_says_which_way_it_moved() -> None:
    """`kind` comes from the measure, not from the sign alone.

    The core excludes `total` steps from "largest contribution" and from the
    extrema targets, precisely so an opening or closing bar -- which restates
    the whole running value -- does not bury the answer the reader wanted. A
    total announced as an increase would do exactly that.
    """
    (layer,) = _layers(go.Figure([go.Waterfall(**DOC)]))

    assert [point["kind"] for point in layer["data"]] == [
        "increase",
        "increase",
        "total",
        "decrease",
        "decrease",
        "total",
    ]


def test_an_absolute_step_is_a_total_too() -> None:
    """`absolute` restates the running value, which is what `total` means.

    It is the measure an author uses for an opening balance, and the core's
    reason for excluding totals applies to it unchanged.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Waterfall(
                    measure=["absolute", "relative"], x=["open", "a"], y=[100, 5]
                )
            ]
        )
    )

    assert [point["kind"] for point in layer["data"]] == ["total", "increase"]


def test_a_step_that_nets_to_nothing_is_still_a_step() -> None:
    """A zero contribution is an increase, not a total.

    It is a step that happened to net to nothing, and calling it a total
    would take it out of the increase/decrease counts the description
    reports as well as out of the extrema search.
    """
    (layer,) = _layers(go.Figure([go.Waterfall(x=["a", "b"], y=[10, 0])]))

    assert [point["kind"] for point in layer["data"]] == ["increase", "increase"]


def test_a_horizontal_waterfall_keeps_its_categories_in_x() -> None:
    """The core fixes a waterfall's main axis, so the payload has to fit it.

    `IS_ORIENTED` marks `WATERFALL` false -- "a horizontal waterfall swaps
    nothing a reader would hear" -- and `WaterfallTrace` announces the step's
    label against `this.xAxis`. So the category belongs in `x` however the
    chart is drawn, and the values accumulate out of the trace's `x` array.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Waterfall(
                    orientation="h",
                    measure=["relative", "relative", "total"],
                    y=["a", "b", "c"],
                    x=[10, -4, 0],
                )
            ]
        )
    )

    assert [point["x"] for point in layer["data"]] == ["a", "b", "c"]
    assert _spans(layer) == [(0, 10), (10, 6), (0, 6)]


def test_a_horizontal_waterfall_carries_its_axis_titles_across() -> None:
    """The titles travel with the values they name.

    Left in plotly's arrangement they would announce the value axis's title
    beside the category name and the category axis's title beside the
    contribution -- both labels attached to the wrong number.
    """
    figure = go.Figure(
        [go.Waterfall(orientation="h", y=["a", "b"], x=[10, -4])]
    )
    figure.update_layout(
        xaxis={"title": {"text": "Amount"}}, yaxis={"title": {"text": "Stage"}}
    )

    (layer,) = _layers(figure)

    assert layer["axes"]["x"]["label"] == "Stage"
    assert layer["axes"]["y"]["label"] == "Amount"


def test_a_vertical_waterfall_leaves_its_axis_titles_alone() -> None:
    """The control for the swap above: it must not fire both ways."""
    figure = go.Figure([go.Waterfall(x=["a", "b"], y=[10, -4])])
    figure.update_layout(
        xaxis={"title": {"text": "Stage"}}, yaxis={"title": {"text": "Amount"}}
    )

    (layer,) = _layers(figure)

    assert layer["axes"]["x"]["label"] == "Stage"
    assert layer["axes"]["y"]["label"] == "Amount"


def test_the_selector_is_scoped_to_the_waterfall_layer() -> None:
    """`.trace.bars` alone is not unique to any one trace family.

    Measured in Chromium on a subplot holding one bar trace and one
    waterfall: `.subplot.xy .trace.bars .point > path` matched **7**
    elements -- the four bars and the three steps -- while
    `.subplot.xy .waterfalllayer .trace.bars .point > path` matched exactly
    the 3 steps.
    """
    (layer,) = _layers(go.Figure([go.Waterfall(x=["a", "b", "c"], y=[10, -4, 7])]))

    assert ".waterfalllayer" in layer["selectors"]


def test_two_waterfalls_on_one_subplot_address_their_own_steps() -> None:
    """Plotly appends one `.trace.bars` group per trace, in declaration order.

    Without the position each layer's selector would claim both groups, so
    every resolved count would be the sum of the two and both highlights
    would be dropped.
    """
    first, second = _layers(
        go.Figure(
            [
                go.Waterfall(x=["a", "b"], y=[1, 2]),
                go.Waterfall(x=["a", "b"], y=[3, 4]),
            ]
        )
    )

    assert "nth-of-type(1)" in first["selectors"]
    assert "nth-of-type(2)" in second["selectors"]


def test_a_bar_beside_a_waterfall_still_addresses_its_own_bars() -> None:
    """The other half of the same over-match (#628).

    The bar layer's selector was `.trace.bars` with no layer to scope it, so
    it matched the waterfall's steps too. `BarTrace.mapToSvgElements` needs
    the resolved count to equal the point count, so 7 against 4 dropped the
    highlight for the whole bar layer.

    The layer is found by type rather than by position: `_extract_plots`
    emits its merge blocks before the traces that fall through to the
    factory, so a waterfall precedes a bar declared ahead of it -- exactly
    as a box or a candlestick already does. That ordering is older than this
    change and is not what this test is about.
    """
    layers = _layers(
        go.Figure(
            [
                go.Bar(x=["a", "b", "c", "d"], y=[1, 2, 3, 4]),
                go.Waterfall(x=["a", "b", "c"], y=[10, -4, 7]),
            ]
        )
    )
    (bar,) = [layer for layer in layers if layer["type"] == PlotType.BAR]

    assert ".barlayer" in bar["selectors"]
    assert sorted(layer["type"] for layer in layers) == [
        PlotType.BAR,
        PlotType.WATERFALL,
    ]


def test_a_lone_bar_chart_is_unchanged_apart_from_the_scope() -> None:
    """The control: scoping must not disturb what the selector resolved to.

    `.barlayer` is the group plotly already put the bars in, so the added
    step narrows the match without moving it.
    """
    (layer,) = _layers(go.Figure([go.Bar(x=["a", "b"], y=[1, 2])]))

    assert layer["selectors"] == ".subplot.xy .barlayer .trace.bars .point > path"

"""MAIDR read plotly traces the chart does not draw.

`visible=False` and `visible="legendonly"` both tell plotly to draw nothing,
and plotly obeys completely: it renders **no group at all** for such a trace.
Measured in Chromium, two traces with one hidden produce a single group in the
layer, for bar, scatter, pie, box and violin alike.

`_extract_plots` read `fig.to_dict()["data"]` without asking, so every hidden
trace became a layer:

    hidden bar + shown bar     ['stacked_bar']   ** and merged into a stack
    hidden scatter             ['point']
    hidden box                 ['box']
    hidden pie                 ['pie']
    hidden histogram           ['hist']

Nothing errored. A reader was told about series that are not on the chart —
their values, their categories, their names — with nothing saying the series
is switched off. The bar row is the worst of them: the hidden trace was merged
with the visible one into a `stacked_bar`, so a plain one-series bar chart was
announced as a stack of two, and every bar's meaning changed.

There is a second failure underneath. Selectors scoped by a trace's position
among its layer-mates — candlestick, violin, pie — counted the hidden trace as
occupying a slot it does not have, so the drawn trace's selector pointed at a
group that does not exist and matched nothing. The audio, braille and text
stayed correct, so only a sighted reader could tell the highlight had stopped.

Clicking a legend entry sets `visible="legendonly"` and re-renders, so this is
reached by ordinary use rather than an exotic figure.

The fix is one filter where the traces enter, rather than a guard in each
branch: every downstream reader — bar merging, line grouping, pie and
candlestick positions, the subplot grid — then sees only what was drawn, and
none of them has to remember to ask.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Both spellings of "not drawn". `False` hides a trace outright;
#: `"legendonly"` is what a legend click leaves behind.
HIDDEN = pytest.mark.parametrize(
    "hidden", [False, "legendonly"], ids=["false", "legendonly"]
)

VALUES = [1.0, 2.0, 3.0, 4.0]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _types(figure: go.Figure) -> list[str]:
    """The emitted layer types."""
    return [layer["type"].value for layer in _layers(figure)]


@HIDDEN
@pytest.mark.parametrize(
    "trace_of",
    [
        pytest.param(lambda v: go.Bar(x=["a", "b"], y=[1.0, 2.0], **v), id="bar"),
        pytest.param(
            lambda v: go.Scatter(x=[1, 2], y=[3, 4], mode="markers", **v), id="scatter"
        ),
        pytest.param(lambda v: go.Box(y=VALUES, **v), id="box"),
        pytest.param(lambda v: go.Violin(y=VALUES, **v), id="violin"),
        pytest.param(lambda v: go.Histogram(x=VALUES, **v), id="histogram"),
        pytest.param(
            lambda v: go.Pie(labels=["a", "b"], values=[1.0, 2.0], **v), id="pie"
        ),
        pytest.param(
            lambda v: go.Candlestick(
                x=["d1"], open=[1.0], high=[2.0], low=[0.0], close=[1.5], **v
            ),
            id="candlestick",
        ),
        # `ohlc` is the other half of the OHLC family and draws into a layer
        # of its own, so it is named here rather than left to the candlestick
        # case -- the point of this parametrization is that no type is assumed
        # to be covered by a neighbour.
        pytest.param(
            lambda v: go.Ohlc(
                x=["d1"], open=[1.0], high=[2.0], low=[0.0], close=[1.5], **v
            ),
            id="ohlc",
        ),
    ],
)
def test_a_hidden_trace_is_not_read(trace_of, hidden) -> None:
    """Whatever its type, a trace plotly drew nothing for is not a layer.

    Parametrized across the types rather than left to one representative,
    because the filter is meant to be type-blind and a per-type guard is
    exactly what it replaced -- a guard that was easy to add for one type and
    forget for the next six.
    """
    figure = go.Figure([trace_of({"visible": hidden})])

    assert _layers(figure) == []


@HIDDEN
def test_a_hidden_bar_does_not_become_half_a_stack(hidden) -> None:
    """The worst row, stated on its own.

    Plotly's default `barmode` stacks, so a hidden bar trace beside a visible
    one was merged into a `stacked_bar` -- announcing a one-series chart as a
    stack of two, with the invisible series contributing segments a reader
    could not see and totals that do not exist. Not a lost relationship but an
    invented one.
    """
    figure = go.Figure(
        [
            go.Bar(x=["a", "b"], y=[1.0, 2.0], name="hidden", visible=hidden),
            go.Bar(x=["a", "b"], y=[3.0, 4.0], name="shown"),
        ]
    )

    (layer,) = _layers(figure)

    assert layer["type"] is PlotType.BAR
    assert [point["y"] for point in layer["data"]] == [3.0, 4.0]


@HIDDEN
def test_a_hidden_trace_takes_no_position(hidden) -> None:
    """The second failure: a slot the hidden trace does not occupy.

    Plotly renders one group per *drawn* trace, so a selector scoped by
    position must count only those. With the hidden box counted, the
    candlestick took `nth-child(2)` of a layer holding one child and its
    selector matched nothing -- the highlight silently stopping while
    everything else stayed right.
    """
    figure = go.Figure(
        [
            go.Box(y=VALUES, name="hidden", visible=hidden),
            go.Candlestick(
                x=["d1"], open=[1.0], high=[2.0], low=[0.0], close=[1.5], name="A"
            ),
        ]
    )

    (layer,) = _layers(figure)

    assert layer["selectors"] == (
        ".subplot.xy .boxlayer > .trace.boxes:nth-child(1) path.box"
    )


@HIDDEN
def test_a_hidden_pie_does_not_shift_the_one_beside_it(hidden) -> None:
    """A pie is positioned within the figure's `pielayer`, so it counts too.

    Its selector is scoped by position among the *drawn* pies -- which is
    also what the browser-side adapter's `isDrawnPie` decides, so the two
    agree on what counts.

    Pinned exactly rather than by substring, matching the candlestick and
    violin cases beside it: a `nth-child(1) in str(...)` check can pass on a
    coincidence elsewhere in the string, which is precisely the kind of test
    that looks like coverage and is not.
    """
    figure = go.Figure(
        [
            go.Pie(labels=["a"], values=[1.0], visible=hidden),
            go.Pie(labels=["b", "c"], values=[2.0, 3.0]),
        ]
    )

    (layer,) = _layers(figure)

    assert layer["type"] is PlotType.PIE
    assert layer["selectors"] == (
        ".pielayer > .trace:nth-child(1) > .slice > path.surface"
    )


@HIDDEN
def test_a_hidden_violin_takes_no_group(hidden) -> None:
    """The violin pair is built from the drawn traces alone.

    Worse here than elsewhere, because a violin that is not drawn was
    announced with its name, its quartiles and its whole density curve.
    """
    figure = go.Figure(
        [
            go.Violin(y=VALUES, name="hidden", visible=hidden),
            go.Violin(y=[10.0, 20.0, 30.0, 40.0], name="shown"),
        ]
    )

    box = next(
        layer for layer in _layers(figure) if layer["type"] is PlotType.VIOLIN_BOX
    )
    kde = next(
        layer for layer in _layers(figure) if layer["type"] is PlotType.VIOLIN_KDE
    )

    assert [row["z"] for row in box["data"]] == ["shown"]
    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)"
    ]


def test_a_figure_of_only_hidden_traces_has_no_layers() -> None:
    """Nothing drawn is nothing to read, and that must not raise.

    An empty layer list is the honest answer, and the paths that assume at
    least one trace -- the barmode merge, the subplot grid -- have to survive
    reaching none.
    """
    figure = go.Figure(
        [
            go.Bar(x=["a"], y=[1.0], visible=False),
            go.Scatter(x=[1], y=[1], mode="markers", visible="legendonly"),
        ]
    )

    assert _layers(figure) == []
    assert PlotlyMaidr(figure).render() is not None


def test_an_explicitly_visible_trace_is_read() -> None:
    """`visible=True` is the same as not saying so.

    The control for reading the value rather than testing for the key: a
    figure that sets `visible` explicitly must not be mistaken for one that
    hid something.
    """
    figure = go.Figure([go.Bar(x=["a", "b"], y=[1.0, 2.0], visible=True)])

    assert _types(figure) == ["bar"]


def test_a_figure_that_hides_nothing_is_unchanged() -> None:
    """The control: the filter must cost an ordinary figure nothing.

    Every trace here reaches a different branch of `_extract_plots`, so this
    drives the paths the filter now sits in front of -- including the order
    those branches emit in, which is the line group before the bar group and
    is not something the filter should disturb.
    """
    figure = go.Figure(
        [
            go.Bar(x=["a", "b"], y=[1.0, 2.0], name="bar"),
            go.Scatter(x=[1, 2], y=[3, 4], mode="markers", name="pts"),
            go.Scatter(x=[1, 2], y=[5, 6], mode="lines", name="line"),
        ]
    )

    assert _types(figure) == ["line", "bar", "point"]

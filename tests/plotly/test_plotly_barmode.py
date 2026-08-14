"""A stacked plotly bar chart was announced as a grouped one.

`PlotlyMaidr._extract_plots` classifies multi-trace bar figures from
`layout.barmode`::

    barmode = layout.get("barmode", "group")
    ...
    if len(bar_traces) > 1 and barmode in ("group", "stack"):
        plot_type = PlotType.DODGED if barmode == "group" else PlotType.STACKED

Plotly's default `barmode` is **`relative`**, which stacks. That line defaulted
to `group`, which dodges — and `relative` was missing from the tuple besides:

                             plotly draws          maidr said
    no barmode               relative (default)    ['dodged_bar']
    barmode=relative         relative              ['bar', 'bar']
    barmode=stack            stack                 ['stacked_bar']
    barmode=group            group                 ['dodged_bar']
    barmode=overlay          overlay               ['bar', 'bar']

Row 1 is the severe one: not a lost relationship but an inverted one. A reader
was told the bars sit side by side when plotly drew them on top of each other,
so every segment means something other than what was announced and the totals
a stack is read for are absent entirely. Nothing errored (#390).

Row 2 is how `px.bar(color=...)` — the ordinary way to draw a stacked bar
chart in plotly express — arrives.

Unlike the matplotlib side, where stacking is inferred from a `bottom=`
argument, plotly *states* this in the layout. It was a lookup table missing a
row and carrying the wrong fallback, so every barmode is enumerated below.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pytest

from maidr.plotly.plotly_maidr import PlotlyMaidr

#: Every value plotly accepts, with the layer types MAIDR should emit.
#: `relative` and `stack` both combine; `group` dodges; `overlay` draws the
#: bars over one another rather than joining them, so they stay separate.
BARMODES = [
    (None, ["stacked_bar"]),
    ("relative", ["stacked_bar"]),
    ("stack", ["stacked_bar"]),
    ("group", ["dodged_bar"]),
    ("overlay", ["bar", "bar"]),
]


def _two_bar_traces(barmode: str | None) -> go.Figure:
    """Two bar traces over one category axis, at *barmode*."""
    figure = go.Figure(
        [
            go.Bar(x=["a", "b", "c"], y=[1.0, 2.0, 3.0], name="lower"),
            go.Bar(x=["a", "b", "c"], y=[3.0, 2.0, 1.0], name="upper"),
        ]
    )
    if barmode is not None:
        figure.update_layout(barmode=barmode)
    return figure


def _types(figure: go.Figure) -> list[str]:
    """The layer types MAIDR extracts from a plotly figure."""
    return [plot.type.value for plot in PlotlyMaidr(figure)._plots]


@pytest.mark.parametrize("barmode,expected", BARMODES)
def test_every_barmode_is_read_the_way_plotly_draws_it(barmode, expected) -> None:
    """The whole table, because the failure is a silent mislabel.

    The set is small and enumerable, and three of these five rows were wrong
    in a way nothing downstream could detect — so each is named rather than
    left to a representative case.
    """
    assert _types(_two_bar_traces(barmode)) == expected


def test_the_default_matches_plotly_rather_than_the_old_guess() -> None:
    """The row that inverted the relationship, stated on its own.

    A figure that sets no `barmode` is drawn stacked by plotly. It was
    announced as dodged — bars side by side where plotly put them on top of
    one another. This asserts against plotly's own reported default rather
    than a literal, so the two cannot drift apart silently.
    """
    figure = _two_bar_traces(None)

    assert figure.layout.barmode is None, "plotly leaves it unset"
    assert _types(figure) == ["stacked_bar"]


def test_a_plotly_express_stacked_bar_is_stacked() -> None:
    """`px.bar(color=...)` is the ordinary way to draw one, and it sets
    `relative` — the value that used to fall through to two plain layers."""
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "g": list("abc") * 10,
            "h": ["x", "y"] * 15,
            "v": rng.normal(10, 3, size=30),
        }
    )

    figure = px.bar(frame, x="g", y="v", color="h")

    assert figure.layout.barmode == "relative"
    assert _types(figure) == ["stacked_bar"]


def test_a_single_bar_trace_is_not_merged() -> None:
    """The control: merging needs more than one trace, whatever the barmode.

    A one-trace figure carries plotly's stacking default too, so reading the
    barmode alone would turn every plain bar chart into a stack of one.
    """
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({"g": list("abc") * 10, "v": rng.normal(10, 3, size=30)})

    assert _types(px.bar(frame, x="g", y="v")) == ["bar"]

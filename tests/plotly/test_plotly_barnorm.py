"""A 100% stacked bar chart was announced as an ordinary stacked one.

`layout.barnorm` is plotly's own switch for normalising each stack to a common
total — `'percent'` scales to 100, `'fraction'` to 1. Either way the segment
values are *shares of their category* rather than counts. MAIDR did not read
it, so such a chart arrived as `stacked_bar` (#338).

What a reader loses is not the numbers, which are announced either way, but
what they *are*. A `stacked_bar` invites the reading that each segment is a
count and that the categories happen to total the same; `stacked_normalized_bar`
says the totals are equal by construction and the parts are proportions. The
MAIDR core has carried `TraceType.NORMALIZED = 'stacked_normalized_bar'` for
some time; `PlotType` simply had no member to emit it with, so the type was
unreachable from Python.

This is a lookup rather than a heuristic, and deliberately so. matplotlib and
seaborn have no equivalent declaration — a user normalises the data themselves
and calls `ax.bar(bottom=...)` — so inferring "every category totals 1.0, so
this must be normalised" would name a chart from a coincidence in its data.
Plotly states it, so plotly is where this can be read honestly.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Every combination that decides the layer type. `barnorm` normalises a stack
#: whatever spelling of stacking got it there, and means nothing to a dodge.
CASES = [
    (None, None, "stacked_bar"),
    ("stack", None, "stacked_bar"),
    ("stack", "percent", "stacked_normalized_bar"),
    ("stack", "fraction", "stacked_normalized_bar"),
    ("relative", "percent", "stacked_normalized_bar"),
    (None, "percent", "stacked_normalized_bar"),
    ("group", "percent", "dodged_bar"),
    ("group", None, "dodged_bar"),
]


def _figure(barmode: str | None, barnorm: str | None) -> go.Figure:
    """Two bar traces over one category axis, at *barmode* and *barnorm*."""
    figure = go.Figure(
        [
            go.Bar(x=["a", "b", "c"], y=[1.0, 2.0, 3.0], name="lower"),
            go.Bar(x=["a", "b", "c"], y=[3.0, 2.0, 1.0], name="upper"),
        ]
    )
    layout = {}
    if barmode is not None:
        layout["barmode"] = barmode
    if barnorm is not None:
        layout["barnorm"] = barnorm
    if layout:
        figure.update_layout(**layout)
    return figure


def _types(figure: go.Figure) -> list[str]:
    """The layer types MAIDR extracts from a plotly figure."""
    return [plot.type.value for plot in PlotlyMaidr(figure)._plots]


@pytest.mark.parametrize("barmode,barnorm,expected", CASES)
def test_barnorm_decides_only_what_it_should(barmode, barnorm, expected) -> None:
    """The whole table, since the failure is a silent mislabel.

    Two axes of a small closed set, so every combination is named rather than
    left to a representative case — including the two rows where `barnorm` is
    set and must *not* change the answer.
    """
    assert _types(_figure(barmode, barnorm)) == [expected]


def test_a_dodge_is_not_normalised_by_barnorm() -> None:
    """`barnorm` normalises a *stack*, and a dodge has none to normalise.

    Stated on its own because it is the row a "barnorm means normalised"
    shortcut would get wrong, and the answer would look plausible: side-by-side
    bars announced as shares of a total that the chart never draws.
    """
    assert _types(_figure("group", "percent")) == ["dodged_bar"]


def test_an_empty_barnorm_is_not_normalisation() -> None:
    """Plotly's own "off" value is the empty string, not absence.

    `barnorm=""` is how a figure says *not* normalised after something set it,
    so membership of the normalising set is the test rather than truthiness of
    the key.
    """
    assert _types(_figure("stack", "")) == ["stacked_bar"]


def test_the_type_is_the_one_the_maidr_core_already_carries() -> None:
    """The wire value has to match the core, or the bundle cannot draw it.

    `TraceType.NORMALIZED = 'stacked_normalized_bar'` has existed in the JS
    grammar for some time; what was missing was a `PlotType` member to emit
    it. A mismatch here would render an unknown trace rather than a chart, so
    the string is pinned rather than left to a constructor.
    """
    assert PlotType.NORMALIZED.value == "stacked_normalized_bar"
    assert PlotType.NORMALIZED.display_name == "100% stacked bar"

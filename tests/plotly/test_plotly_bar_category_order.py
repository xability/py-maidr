"""
A plotly bar chart with ``categoryorder`` was read in the data's order (#495).

`categoryorder` sorts the category axis and leaves the trace's own `x` and `y`
exactly as the author wrote them, so the arrays alone do not say what the chart
shows:

    go.Bar(x=['charlie', 'alpha', 'bravo'], y=[3, 1, 2])
    xaxis.categoryorder = 'category ascending'

    emitted   charlie, alpha, bravo        <- the trace's order
    drawn     alpha, bravo, charlie        <- left to right

Every label still carried its own value and the highlight still landed on the
right bar, so nothing read as *broken*. What was wrong is everything that
treats the index as a **position**: which way arrowing travels, the stereo pan,
the braille line, and the autoplay sweep.

The heatmap half of this is #489, and `_drawn_category_order` and the three
axis-type helpers it needs now live on `PlotlyPlot` rather than on the heatmap,
because each of them is about an *axis*. Their limits carry over unchanged:
only `"array"` with a `categoryarray` and the two `"category"` sorts can be
answered offline, and a numeric or ISO-date axis resolves as linear or date and
ignores `categoryorder` outright.

**The selectors have to move with the data.** Measured in Chromium on the chart
above, the three `.point` groups sit at x = 773, 37 and 405 -- the *trace's*
order -- so the single selector this layer used to emit resolves in the order
the points used to be in. Reordering the points alone would leave every
highlight one place out. `.point:nth-of-type(k)` addresses them one at a time:
measured on the same page it matches exactly one element, and it is the kth in
document order, for every k.

Verified end to end in Chromium against the emitted selector list:

    drawn 0  'alpha'    matched 1  left  37
    drawn 1  'bravo'    matched 1  left 405
    drawn 2  'charlie'  matched 1  left 773

Left-to-right position ascends with the announced order, so the two agree and
both agree with the chart.
"""

from __future__ import annotations

import warnings

import plotly.graph_objects as go
import pytest

from maidr.plotly.plotly_maidr import PlotlyMaidr

warnings.filterwarnings("ignore")

#: Written out of order on purpose: sorted, reversed and declared each give a
#: different permutation, so no two expectations below agree by accident.
CATEGORIES = ["charlie", "alpha", "bravo"]
VALUES = [3, 1, 2]


def _layer(fig) -> dict:
    """The first emitted layer, keyed by raw strings."""
    schema = PlotlyMaidr(fig)._flatten_maidr()
    layer = schema["subplots"][0][0]["layers"][0]
    return {str(getattr(key, "value", key)): value for key, value in layer.items()}


def _pairs(fig) -> list[tuple]:
    """Each announced point as ``(x, y)``, in the order it is emitted."""
    return [(point.get("x"), point.get("y")) for point in _layer(fig)["data"]]


def _bar(order: str | None = None, **axis) -> go.Figure:
    fig = go.Figure(data=[go.Bar(x=CATEGORIES, y=VALUES)])
    if order is not None:
        axis["categoryorder"] = order
    if axis:
        fig.update_layout(xaxis=axis)
    return fig


def test_an_unsorted_bar_chart_is_untouched():
    """The order the trace is in *is* the drawn order, so nothing moves --
    and the selector stays the single string it has always been."""
    fig = _bar()

    assert _pairs(fig) == [("charlie", 3), ("alpha", 1), ("bravo", 2)]
    assert _layer(fig)["selectors"] == ".subplot.xy .trace.bars .point > path"


def test_an_ascending_sort_is_emitted_in_the_drawn_order():
    assert _pairs(_bar("category ascending")) == [
        ("alpha", 1),
        ("bravo", 2),
        ("charlie", 3),
    ]


def test_a_descending_sort_is_emitted_in_the_drawn_order():
    """Not merely the reverse of the trace's order: `charlie, bravo, alpha`
    is the reverse of the *sorted* order, and the trace's own is
    `charlie, alpha, bravo`."""
    assert _pairs(_bar("category descending")) == [
        ("charlie", 3),
        ("bravo", 2),
        ("alpha", 1),
    ]


def test_a_declared_array_is_emitted_in_its_own_order():
    """`categoryarray` is what plotly express's `category_orders` compiles to,
    and it is neither sorted nor reversed."""
    fig = _bar("array", categoryarray=["bravo", "charlie", "alpha"])

    assert _pairs(fig) == [("bravo", 2), ("charlie", 3), ("alpha", 1)]


def test_each_selector_names_the_bar_whose_point_it_carries():
    """The half that a check on the data alone would not catch.

    A permuted list of points with an unpermuted selector is worse than
    either alone: the reading is right and the highlight is one place out,
    which is the blind spot xability/maidr#814 names. Asserted against the
    positions measured in Chromium -- `alpha` is the trace's second entry, so
    it is `nth-of-type(2)`.
    """
    prefix = ".subplot.xy .trace.bars"

    assert _layer(_bar("category ascending"))["selectors"] == [
        f"{prefix} .point:nth-of-type(2) > path",
        f"{prefix} .point:nth-of-type(3) > path",
        f"{prefix} .point:nth-of-type(1) > path",
    ]


def test_a_horizontal_bar_is_sorted_along_the_axis_it_is_named_on():
    """A horizontal bar's categories are on `y`, and `paired_axes` is
    symmetric rather than swapping them -- so reading the sort off `xaxis`
    would find nothing and leave the chart as it was."""
    fig = go.Figure(data=[go.Bar(y=CATEGORIES, x=VALUES, orientation="h")])
    fig.update_layout(yaxis={"categoryorder": "category ascending"})

    assert _pairs(fig) == [(1, "alpha"), (2, "bravo"), (3, "charlie")]


@pytest.mark.parametrize(
    "order",
    ["total ascending", "total descending", "sum ascending", "mean descending"],
)
def test_an_aggregate_order_is_declined(order):
    """Resolving one means reimplementing plotly's aggregation and
    tie-breaking offline, and a sort that is subtly not plotly's would leave
    the chart confidently wrong in the same way reading the trace's order
    does. Leaving it unapplied is the smaller error -- and the selector stays
    a single string, so the highlight is exactly what it was."""
    fig = _bar(order)

    assert _pairs(fig) == [("charlie", 3), ("alpha", 1), ("bravo", 2)]
    assert isinstance(_layer(fig)["selectors"], str)


def test_a_numeric_axis_ignores_a_declared_order_here_too():
    """Plotly infers the axis *type* first, and a linear axis ignores
    `categoryorder` outright -- so applying one would reorder a chart plotly
    does not."""
    fig = go.Figure(data=[go.Bar(x=[3, 1, 2], y=[3, 1, 2])])
    fig.update_layout(xaxis={"categoryorder": "category ascending"})

    assert _pairs(fig) == [(3, 3), (1, 1), (2, 2)]


def test_a_numeric_axis_declared_categorical_is_sorted():
    """`type: "category"` is what makes it categorical again, and then the
    order is honoured -- the other side of the guard above."""
    fig = go.Figure(data=[go.Bar(x=[3, 1, 2], y=[30, 10, 20])])
    fig.update_layout(xaxis={"type": "category", "categoryorder": "category ascending"})

    assert _pairs(fig) == [(1, 10), (2, 20), (3, 30)]


def test_an_array_naming_a_category_the_trace_lacks_is_declined():
    """Plotly draws an empty column for it, which `points` has no way to say.
    Inventing or dropping one would be worse than leaving the sort
    unapplied."""
    fig = _bar("array", categoryarray=["alpha", "bravo", "charlie", "delta"])

    assert _pairs(fig) == [("charlie", 3), ("alpha", 1), ("bravo", 2)]

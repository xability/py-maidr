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
    assert _layer(fig)["selectors"] == ".subplot.xy .barlayer .trace.bars .point > path"


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
    prefix = ".subplot.xy .barlayer .trace.bars"

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


def test_a_horizontal_bar_is_announced_from_the_bottom_lane_up():
    """Which end of a vertical axis the announcement starts from, pinned by
    a sort that is not its own reverse.

    An alphabetical sort cannot catch an inverted mapping -- ascending looks
    the same read from either end -- so this declares `bravo, charlie, alpha`,
    which is neither sorted nor reversed.

    Bottom-up rather than top-down, and measured rather than assumed by
    analogy with the heatmap (which does flip, via `_axis_runs_backwards`,
    so that row 0 is visually up). The *unsorted* horizontal chart already
    ships bottom-up: written `['charlie', 'alpha', 'bravo']` it draws its
    tick labels top to bottom as `bravo, alpha, charlie`, so the trace order
    py-maidr has always emitted for it runs from the bottom lane. A sorted
    chart matching that is consistent; flipping it would put two spellings of
    one chart in opposite orders.
    """
    fig = go.Figure(data=[go.Bar(y=CATEGORIES, x=VALUES, orientation="h")])
    fig.update_layout(
        yaxis={"categoryorder": "array", "categoryarray": ["bravo", "charlie", "alpha"]}
    )

    # `categoryarray` runs from the axis origin, which on y is the bottom.
    assert _pairs(fig) == [(2, "bravo"), (3, "charlie"), (1, "alpha")]


@pytest.mark.parametrize(
    ("order", "axis", "positions"),
    [
        ("category descending", {}, (1, 3, 2)),
        ("array", {"categoryarray": ["bravo", "charlie", "alpha"]}, (3, 1, 2)),
    ],
)
def test_every_resolved_sort_permutes_the_selectors_too(order, axis, positions):
    """Not only the ascending one. Each sort is its own permutation, and a
    path that reordered the data while leaving the selectors alone would read
    correctly and outline the wrong bar."""
    prefix = ".subplot.xy .barlayer .trace.bars"

    assert _layer(_bar(order, **axis))["selectors"] == [
        f"{prefix} .point:nth-of-type({index}) > path" for index in positions
    ]


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


# --- The grouped, stacked and normalized paths -------------------------------
#
# They walk the same arrays and had the same gap. What differs is the shape a
# sorted layer's selectors need: a segmented layer addresses its cells by row
# and column, `selectors[group][category]`, which is the shape `data` already
# has.
#
# Measured in Chromium, two traces over three categories, in both barmodes:
#
#     grouped   traceGroups 2   perGroup [[767, 37, 402], [913, 183, 548]]
#     stacked   traceGroups 2   perGroup [[767, 37, 402], [767, 37, 402]]
#
# Two sibling `.trace.bars` groups under `g.barlayer.mlayer`, one per trace and
# in the traces' own order, each holding its categories in that trace's order.
# `.trace.bars:nth-of-type(t) .point:nth-of-type(c)` matched exactly one
# element for all six pairs, and the coordinates say which: dodged puts the two
# traces side by side at one category, stacked puts them one above the other.

SECOND = [1, 4, 2]


def _group(barmode: str, order: str | None = None, **layout) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Bar(name="A", x=CATEGORIES, y=VALUES),
            go.Bar(name="B", x=CATEGORIES, y=SECOND),
        ]
    )
    if order is not None:
        layout["xaxis"] = {"categoryorder": order}
    fig.update_layout(barmode=barmode, **layout)
    return fig


def _groups(fig) -> list[list[tuple]]:
    """Each group's points as ``(x, y)``, in the order they are emitted."""
    return [
        [(point.get("x"), point.get("y")) for point in group]
        for group in _layer(fig)["data"]
    ]


@pytest.mark.parametrize("barmode", ["group", "stack"])
def test_an_unsorted_group_is_untouched(barmode):
    fig = _group(barmode)

    assert _groups(fig) == [
        [("charlie", 3), ("alpha", 1), ("bravo", 2)],
        [("charlie", 1), ("alpha", 4), ("bravo", 2)],
    ]
    assert _layer(fig)["selectors"] == ".subplot.xy .barlayer .trace.bars .point > path"


@pytest.mark.parametrize("barmode", ["group", "stack"])
def test_every_group_is_emitted_in_the_drawn_order(barmode):
    """One order for all of them: the traces of a group share the category
    axis by construction, which is what makes them one chart."""
    assert _groups(_group(barmode, "category ascending")) == [
        [("alpha", 1), ("bravo", 2), ("charlie", 3)],
        [("alpha", 4), ("bravo", 2), ("charlie", 1)],
    ]


def test_a_sorted_group_addresses_each_cell_by_trace_and_category():
    """A grid rather than a flat list, keyed the way `data` is.

    Row 1 is trace A and row 2 trace B; within a row the categories are in
    the drawn order, pointing at the position each holds in *that trace's*
    own arrays.
    """
    prefix = ".subplot.xy .barlayer .trace.bars"
    expected = [
        [
            f"{prefix}:nth-of-type({group}) .point:nth-of-type({index}) > path"
            for index in (2, 3, 1)
        ]
        for group in (1, 2)
    ]

    assert _layer(_group("group", "category ascending"))["selectors"] == expected


def test_a_normalized_stack_keeps_each_share_with_its_own_category():
    """The shares are computed per category and must travel with it.

    `stack_shares` matches by category rather than by index, so the two
    changes are independent -- but a reordering applied to one and not the
    other would put `alpha`'s share on `charlie` while both looked
    plausible. The raw values are 1 and 4 at alpha, so its shares are 0.2 and
    0.8, and no other category shares that pair.
    """
    fig = _group("stack", "category ascending", barnorm="fraction")

    assert _groups(fig) == [
        [("alpha", 0.2), ("bravo", 0.5), ("charlie", 0.75)],
        [("alpha", 0.8), ("bravo", 0.5), ("charlie", 0.25)],
    ]


def test_traces_written_in_different_orders_each_get_their_own_permutation():
    """The correctness of resolving per trace rather than once for the group.

    The traces share the axis -- which is what makes them one chart -- so
    they share the drawn sequence of category *names*. They do not share the
    positions those names sit at: `px.bar(df, x=..., color=...)` builds one
    trace per colour from a filtered slice, and unless the frame is sorted
    the same way in every slice their arrays disagree.

    Here A is written `charlie, alpha, bravo` and B `alpha, bravo, charlie`.
    Resolving from A alone gives `[1, 2, 0]`; applying that to B pulls
    `bravo(20), charlie(30), alpha(10)` -- every point still carrying its own
    label while the *column* it lands in belongs to another category, which
    is this issue's own defect one level up.
    """
    fig = go.Figure(
        data=[
            go.Bar(name="A", x=["charlie", "alpha", "bravo"], y=[3, 1, 2]),
            go.Bar(name="B", x=["alpha", "bravo", "charlie"], y=[10, 20, 30]),
        ]
    )
    fig.update_layout(barmode="group", xaxis={"categoryorder": "category ascending"})

    # Column j is the same category in both groups.
    assert _groups(fig) == [
        [("alpha", 1), ("bravo", 2), ("charlie", 3)],
        [("alpha", 10), ("bravo", 20), ("charlie", 30)],
    ]

    # And each group's selectors point into its own arrays: A is written out
    # of order and permutes, B is already sorted and does not.
    prefix = ".subplot.xy .barlayer .trace.bars"
    assert _layer(fig)["selectors"] == [
        [
            f"{prefix}:nth-of-type(1) .point:nth-of-type({index}) > path"
            for index in (2, 3, 1)
        ],
        [
            f"{prefix}:nth-of-type(2) .point:nth-of-type({index}) > path"
            for index in (1, 2, 3)
        ],
    ]


def test_traces_carrying_different_categories_are_declined():
    """A grid's column has to mean one category in every group, and traces
    that carry different category *sets* -- rather than the same set
    differently ordered -- cannot give it one."""
    fig = go.Figure(
        data=[
            go.Bar(name="A", x=["charlie", "alpha", "bravo"], y=[3, 1, 2]),
            go.Bar(name="B", x=["alpha", "bravo", "delta"], y=[10, 20, 30]),
        ]
    )
    fig.update_layout(barmode="group", xaxis={"categoryorder": "category ascending"})

    assert _groups(fig) == [
        [("charlie", 3), ("alpha", 1), ("bravo", 2)],
        [("alpha", 10), ("bravo", 20), ("delta", 30)],
    ]
    assert isinstance(_layer(fig)["selectors"], str)


def test_a_group_whose_traces_disagree_about_length_is_declined():
    """Reordering some groups and not others is worse than reordering none,
    and indexing a shorter trace by the first's positions would raise. A
    trace that carries fewer categories is a legitimate chart -- plotly draws
    it with a gap -- so this declines rather than fails."""
    fig = go.Figure(
        data=[
            go.Bar(name="A", x=CATEGORIES, y=VALUES),
            go.Bar(name="B", x=CATEGORIES[:2], y=SECOND[:2]),
        ]
    )
    fig.update_layout(barmode="group", xaxis={"categoryorder": "category ascending"})

    assert _groups(fig) == [
        [("charlie", 3), ("alpha", 1), ("bravo", 2)],
        [("charlie", 1), ("alpha", 4)],
    ]
    assert isinstance(_layer(fig)["selectors"], str)

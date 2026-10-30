"""A plotly box layer is read in the order its boxes are drawn.

Plotly stands boxes along the axis that places them from its origin, left on x
and bottom on y, and draws each trace's ``path.box`` elements in that order.
The box readers took each trace's own order instead. A ``categoryorder``, a
numeric axis written out of order, or a category another trace introduced
first therefore paired a category's numbers with another category's box, as
an audit that drove every example with the keyboard found. Several traces
grouped at one category were read trace by trace, and each of their boxes was
named by the category alone.

Every expected order below was measured in Chromium: the medians of each
trace group's ``path.box`` elements were read from plotly's calcdata and
compared with the order of the elements. Each box is found in its group by
its key, the first of its samples in the trace's arrays (``s7``), which the
init script reads off the data plotly bound to the element it drew -- also
measured -- or, for a precomputed box, by its place.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _layer(fig: go.Figure) -> dict:
    (layer,) = [plot.schema for plot in PlotlyMaidr(fig)._plots]
    assert layer[MaidrKey.TYPE] == PlotType.BOX
    return layer


def _read(fig: go.Figure) -> list[tuple[str, float, tuple[int, str]]]:
    """Each box as read: its name, its median, and its trace group and key."""
    layer = _layer(fig)
    read = []
    for box, selector in zip(layer[MaidrKey.DATA], layer[MaidrKey.SELECTOR]):
        found = re.search(
            r'g:nth-child\((\d+)\) > \[data-maidr-box-part="(\w+) q2"\]',
            selector["q2"],
        )
        assert found, selector["q2"]
        drawn = (int(found.group(1)), found.group(2))
        read.append((box[MaidrKey.Z.value], box[MaidrKey.Q2.value], drawn))
    return read


def _samples(base: float) -> list[float]:
    """Seven samples whose median is ``base + 3``."""
    return [base + step for step in range(7)]


def _at(categories: list, bases: list[float]) -> dict[str, list]:
    """A trace's positions and samples, seven samples per position."""
    return {
        "positions": [category for category in categories for _ in range(7)],
        "samples": [value for base in bases for value in _samples(base)],
    }


def _box(categories: list, bases: list[float], horizontal=False, **trace) -> go.Box:
    data = _at(categories, bases)
    if horizontal:
        return go.Box(
            y=data["positions"], x=data["samples"], orientation="h", **trace
        )
    return go.Box(x=data["positions"], y=data["samples"], **trace)


def test_a_sorted_category_axis_is_read_in_its_order():
    # Written c, a, b (samples from 0, 7 and 14) and drawn a, b, c.
    fig = go.Figure(
        _box(["c", "a", "b"], [30, 10, 20], name="T"),
        layout={"xaxis": {"categoryorder": "category ascending"}},
    )

    assert _read(fig) == [
        ("a", 13.0, (1, "s7")),
        ("b", 23.0, (1, "s14")),
        ("c", 33.0, (1, "s0")),
    ]


def test_a_category_array_puts_what_it_names_first():
    # Measured: "z" has no box and leaves a gap; "b", which the array does
    # not name, is drawn after the ones it does.
    fig = go.Figure(
        _box(["a", "b", "c"], [10, 20, 30], name="T"),
        layout={"xaxis": {"categoryorder": "array", "categoryarray": ["c", "z", "a"]}},
    )

    assert _read(fig) == [
        ("c", 33.0, (1, "s14")),
        ("a", 13.0, (1, "s0")),
        ("b", 23.0, (1, "s7")),
    ]


def test_a_sorted_horizontal_axis_is_read_top_first():
    # "a" is drawn at the bottom; a horizontal layer is handed to maidr.js
    # top first.
    fig = go.Figure(
        _box(["c", "a", "b"], [30, 10, 20], horizontal=True, name="T"),
        layout={"yaxis": {"categoryorder": "category ascending"}},
    )

    assert _read(fig) == [
        ("c", 33.0, (1, "s0")),
        ("b", 23.0, (1, "s14")),
        ("a", 13.0, (1, "s7")),
    ]


@pytest.mark.parametrize("horizontal", [False, True])
def test_numeric_positions_are_read_in_numeric_order(horizontal):
    fig = go.Figure(_box([3, 1, 2], [30, 10, 20], horizontal=horizontal))

    read = _read(fig)
    if horizontal:
        read.reverse()

    assert read == [
        ("1", 13.0, (1, "s7")),
        ("2", 23.0, (1, "s14")),
        ("3", 33.0, (1, "s0")),
    ]


def test_grouped_traces_are_read_category_by_category():
    # Measured: at each category the first trace's box is drawn left of the
    # second's.
    fig = go.Figure(
        [
            _box(["Thu", "Fri"], [10, 20], name="Male"),
            _box(["Thu", "Fri"], [15, 25], name="Female"),
        ],
        layout={"boxmode": "group"},
    )

    assert _read(fig) == [
        ("Thu, Male", 13.0, (1, "s0")),
        ("Thu, Female", 18.0, (2, "s0")),
        ("Fri, Male", 23.0, (1, "s7")),
        ("Fri, Female", 28.0, (2, "s7")),
    ]


def test_grouped_horizontal_traces_are_read_top_first():
    # Measured: Thu is drawn at the bottom, and at each category the first
    # trace's box below the second's.
    fig = go.Figure(
        [
            _box(["Thu", "Fri"], [10, 20], horizontal=True, name="Male"),
            _box(["Thu", "Fri"], [15, 25], horizontal=True, name="Female"),
        ],
        layout={"boxmode": "group"},
    )

    assert _read(fig) == [
        ("Fri, Female", 28.0, (2, "s7")),
        ("Fri, Male", 23.0, (1, "s7")),
        ("Thu, Female", 18.0, (2, "s0")),
        ("Thu, Male", 13.0, (1, "s0")),
    ]


def test_grouped_traces_follow_a_category_array_each_in_its_own_order():
    # The second trace lists Sat, Thu, Fri; plotly draws both Sat, Fri, Thu.
    fig = go.Figure(
        [
            _box(["Thu", "Fri", "Sat"], [10, 20, 30], name="Male"),
            _box(["Sat", "Thu", "Fri"], [35, 15, 25], name="Female"),
        ],
        layout={
            "boxmode": "group",
            "xaxis": {"categoryorder": "array", "categoryarray": ["Sat", "Fri", "Thu"]},
        },
    )

    assert _read(fig) == [
        ("Sat, Male", 33.0, (1, "s14")),
        ("Sat, Female", 38.0, (2, "s0")),
        ("Fri, Male", 23.0, (1, "s7")),
        ("Fri, Female", 28.0, (2, "s14")),
        ("Thu, Male", 13.0, (1, "s0")),
        ("Thu, Female", 18.0, (2, "s7")),
    ]


def test_a_category_another_trace_introduced_is_drawn_where_that_one_put_it():
    # The axis takes b and c from A, then a from B, so B draws b before a.
    fig = go.Figure(
        [
            _box(["b", "c"], [20, 30], name="A"),
            _box(["a", "b"], [10, 25], name="B"),
        ]
    )

    assert _read(fig) == [
        ("b, A", 23.0, (1, "s0")),
        ("b, B", 28.0, (2, "s7")),
        ("c, A", 33.0, (1, "s7")),
        ("a, B", 13.0, (2, "s0")),
    ]


def test_precomputed_boxes_keep_the_places_they_are_drawn_in():
    # A precomputed trace draws its boxes in the order it lists them,
    # wherever they stand: c first, at the right.
    fig = go.Figure(
        go.Box(
            x=["c", "a", "b"],
            q1=[30, 10, 20],
            median=[32, 12, 22],
            q3=[34, 14, 24],
            name="P",
        ),
        layout={"xaxis": {"categoryorder": "category ascending"}},
    )

    assert _read(fig) == [
        ("a", 12, (1, "2")),
        ("b", 22, (1, "3")),
        ("c", 32, (1, "1")),
    ]


def test_a_trace_named_as_its_category_is_not_named_twice():
    # What `px.box(df, x="day", color="day")` draws: a trace per category,
    # each named as the category it stands at.
    fig = go.Figure(
        [_box(["Thu"], [10], name="Thu"), _box(["Fri"], [20], name="Fri")]
    )

    assert [name for name, _, _ in _read(fig)] == ["Thu", "Fri"]


def test_traces_without_positions_keep_their_names():
    fig = go.Figure(
        [go.Box(y=_samples(10), name="Group 1"), go.Box(y=_samples(20), name="Group 2")]
    )

    assert _read(fig) == [("Group 1", 13.0, (1, "s0")), ("Group 2", 23.0, (2, "s0"))]


def test_dates_are_read_in_time_order():
    # Measured: plotly draws a date axis in time order, whatever order the
    # trace writes the dates in.
    fig = go.Figure(_box(["2024-03-01", "2024-01-01", "2024-02-01"], [30, 10, 20]))

    assert _read(fig) == [
        ("2024-01-01", 13.0, (1, "s7")),
        ("2024-02-01", 23.0, (1, "s14")),
        ("2024-03-01", 33.0, (1, "s0")),
    ]


def test_an_aggregate_sort_still_finds_each_box_by_its_samples(caplog):
    # Measured: under "median ascending" plotly draws a, b, c. That order is
    # not read, so the walk keeps the trace's own, c, a, b, and says so; but
    # each box is still found by its own samples, so it outlines its own box.
    fig = go.Figure(
        _box(["c", "a", "b"], [30, 10, 20], name="T"),
        layout={"xaxis": {"categoryorder": "median ascending"}},
    )

    with caplog.at_level("WARNING", logger="maidr.plotly.box"):
        read = _read(fig)

    assert read == [
        ("c", 33.0, (1, "s0")),
        ("a", 13.0, (1, "s7")),
        ("b", 23.0, (1, "s14")),
    ]
    assert "categoryorder='median ascending'" in caplog.text


def test_a_box_whose_first_samples_are_missing_is_found_by_its_first_number():
    # Plotly keeps only the samples that are numbers, so the first of the box
    # it draws is the first number.
    fig = go.Figure(go.Box(x=["a", "a", "a", "b", "b"], y=[None, 1, 2, 3, 4]))

    assert [drawn for _, _, drawn in _read(fig)] == [(1, "s1"), (1, "s3")]


@pytest.mark.parametrize(
    ("q1", "median", "q3"),
    [
        ([1, None, 21, 31], [2, None, 22, 32], [3, None, 23, 33]),
        ([1, 15, 21, 31], [2, 12, 22, 32], [3, 13, 23, 33]),
    ],
    ids=["missing", "out-of-order"],
)
def test_the_boxes_after_a_dropped_precomputed_box_keep_their_places(q1, median, q3):
    # Measured: plotly still draws b, as a flat line, so c and d are its
    # third and fourth boxes. Counted among the boxes read, they named the
    # second and third: c was outlined on b's line and d on c's box.
    fig = go.Figure(
        go.Box(x=["a", "b", "c", "d"], q1=q1, median=median, q3=q3, name="P")
    )

    assert _read(fig) == [
        ("a", 2, (1, "1")),
        ("c", 22, (1, "3")),
        ("d", 32, (1, "4")),
    ]


def test_a_layer_of_precomputed_and_sampled_traces_names_both():
    fig = go.Figure(
        [
            go.Box(
                x=["Thu", "Fri"],
                q1=[11, 21],
                median=[13, 23],
                q3=[15, 25],
                name="Male",
            ),
            _box(["Thu", "Fri"], [15, 25], name="Female"),
        ],
        layout={"boxmode": "group"},
    )

    assert _read(fig) == [
        ("Thu, Male", 13, (1, "1")),
        ("Thu, Female", 18.0, (2, "s0")),
        ("Fri, Male", 23, (1, "2")),
        ("Fri, Female", 28.0, (2, "s7")),
    ]

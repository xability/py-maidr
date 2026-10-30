"""A plotly box layer is read in the order its boxes are drawn.

Plotly stands boxes along the axis that places them from its origin, left on x
and bottom on y, and draws each trace's ``path.box`` elements in that order.
The box readers took each trace's own order instead. A ``categoryorder``, a
numeric axis written out of order, or a category another trace introduced
first therefore paired a category's numbers with another category's box, as
an audit that drove every example with the keyboard found. Several traces
grouped at one category were read trace by trace, and each of their boxes was
named by the category alone.

Every expected order and place below was measured in Chromium. The medians
of each trace group's ``path.box`` elements were read from plotly's calcdata
and compared with the order of the elements.
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


def _read(fig: go.Figure) -> list[tuple[str, float, tuple[int, int]]]:
    """Each box as read: its name, its median, and the drawn box it names."""
    layer = _layer(fig)
    read = []
    for box, selector in zip(layer[MaidrKey.DATA], layer[MaidrKey.SELECTOR]):
        found = re.search(
            r'g:nth-child\((\d+)\) > \[data-maidr-box-part="(\d+) q2"\]',
            selector["q2"],
        )
        assert found, selector["q2"]
        drawn = (int(found.group(1)), int(found.group(2)))
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
    # Written c, a, b and drawn a, b, c: each box names the box drawn at its
    # category, where it named the first, second and third drawn in the
    # trace's own order.
    fig = go.Figure(
        _box(["c", "a", "b"], [30, 10, 20], name="T"),
        layout={"xaxis": {"categoryorder": "category ascending"}},
    )

    assert _read(fig) == [
        ("a", 13.0, (1, 1)),
        ("b", 23.0, (1, 2)),
        ("c", 33.0, (1, 3)),
    ]


def test_a_category_array_puts_what_it_names_first():
    # Measured: "z" has no box and leaves a gap; "b", which the array does
    # not name, is drawn after the ones it does.
    fig = go.Figure(
        _box(["a", "b", "c"], [10, 20, 30], name="T"),
        layout={"xaxis": {"categoryorder": "array", "categoryarray": ["c", "z", "a"]}},
    )

    assert _read(fig) == [
        ("c", 33.0, (1, 1)),
        ("a", 13.0, (1, 2)),
        ("b", 23.0, (1, 3)),
    ]


def test_a_sorted_horizontal_axis_is_read_top_first():
    # "a" is drawn at the bottom; a horizontal layer is handed to maidr.js
    # top first.
    fig = go.Figure(
        _box(["c", "a", "b"], [30, 10, 20], horizontal=True, name="T"),
        layout={"yaxis": {"categoryorder": "category ascending"}},
    )

    assert _read(fig) == [
        ("c", 33.0, (1, 3)),
        ("b", 23.0, (1, 2)),
        ("a", 13.0, (1, 1)),
    ]


@pytest.mark.parametrize("horizontal", [False, True])
def test_numeric_positions_are_read_in_numeric_order(horizontal):
    fig = go.Figure(_box([3, 1, 2], [30, 10, 20], horizontal=horizontal))

    read = _read(fig)
    if horizontal:
        read.reverse()

    assert read == [("1", 13.0, (1, 1)), ("2", 23.0, (1, 2)), ("3", 33.0, (1, 3))]


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
        ("Thu, Male", 13.0, (1, 1)),
        ("Thu, Female", 18.0, (2, 1)),
        ("Fri, Male", 23.0, (1, 2)),
        ("Fri, Female", 28.0, (2, 2)),
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
        ("Fri, Female", 28.0, (2, 2)),
        ("Fri, Male", 23.0, (1, 2)),
        ("Thu, Female", 18.0, (2, 1)),
        ("Thu, Male", 13.0, (1, 1)),
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
        ("Sat, Male", 33.0, (1, 1)),
        ("Sat, Female", 38.0, (2, 1)),
        ("Fri, Male", 23.0, (1, 2)),
        ("Fri, Female", 28.0, (2, 2)),
        ("Thu, Male", 13.0, (1, 3)),
        ("Thu, Female", 18.0, (2, 3)),
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
        ("b, A", 23.0, (1, 1)),
        ("b, B", 28.0, (2, 1)),
        ("c, A", 33.0, (1, 2)),
        ("a, B", 13.0, (2, 2)),
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
        ("a", 12, (1, 2)),
        ("b", 22, (1, 3)),
        ("c", 32, (1, 1)),
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

    assert _read(fig) == [("Group 1", 13.0, (1, 1)), ("Group 2", 23.0, (2, 1))]

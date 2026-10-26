"""A horizontal plotly box layer lists its boxes top first.

maidr.js reverses a horizontal box layer so the reader starts on the bottom box
and Up moves up the page, and it expects the boxes top to bottom for that.
Plotly draws a horizontal layer's boxes from the bottom up in the order the
traces list them, and that order was emitted as it was: on the gallery's
horizontal box plot the reader started on Group 3, drawn at the top, and Up
moved down to Group 2 and Group 1, the reverse of the matplotlib, seaborn and
Altair box pages, as an audit that drove every example with the keyboard
found. matplotlib's reader reverses its rows for the same reason.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("plotly")
np = pytest.importorskip("numpy")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

GROUPS = ["Group 1", "Group 2", "Group 3"]


def _layer(fig: go.Figure) -> dict:
    (layer,) = [plot.schema for plot in PlotlyMaidr(fig)._plots]
    assert layer[MaidrKey.TYPE] == PlotType.BOX
    return layer


def _names(layer: dict) -> list[str]:
    return [box[MaidrKey.Z.value] for box in layer[MaidrKey.DATA]]


def _drawn_box(selector: dict) -> tuple[int, int]:
    """The trace group and the box within it that a box's selector names."""
    found = re.search(
        r'g:nth-child\((\d+)\) > \[data-maidr-box-part="(\d+) q2"\]', selector["q2"]
    )
    assert found, selector["q2"]
    return int(found.group(1)), int(found.group(2))


def _boxes(orientation: str, **layout) -> go.Figure:
    """The gallery's three-box figure, one trace per group."""
    rng = np.random.default_rng(42)
    samples = "x" if orientation == "h" else "y"
    fig = go.Figure(
        [
            go.Box(**{samples: rng.normal(100, 10, 50).tolist()}, name=name)
            for name in GROUPS
        ]
    )
    fig.update_layout(**layout)
    return fig


def test_a_horizontal_layer_starts_from_the_top_box():
    layer = _layer(_boxes("h"))

    assert layer[MaidrKey.ORIENTATION] == "horz"
    assert _names(layer) == ["Group 3", "Group 2", "Group 1"]


def test_each_box_keeps_its_own_marks():
    # Group 3 is the third trace, so the third group in the box layer.
    layer = _layer(_boxes("h"))

    assert [_drawn_box(s) for s in layer[MaidrKey.SELECTOR]] == [(3, 1), (2, 1), (1, 1)]


@pytest.mark.parametrize(
    "yaxis",
    [{"autorange": "reversed"}, {"range": [2.5, -0.5]}],
    ids=["autorange", "range"],
)
def test_a_y_axis_that_runs_backwards_already_draws_the_first_box_on_top(yaxis):
    layer = _layer(_boxes("h", yaxis=yaxis))

    assert _names(layer) == GROUPS
    assert [_drawn_box(s) for s in layer[MaidrKey.SELECTOR]] == [(1, 1), (2, 1), (3, 1)]


def test_a_vertical_layer_keeps_the_order_left_to_right():
    layer = _layer(_boxes("v"))

    assert _names(layer) == GROUPS


def test_one_trace_of_several_horizontal_boxes_is_reversed_too():
    # Precomputed boxes placed up a categorical y axis, all in one trace.
    fig = go.Figure(
        go.Box(
            y=["low", "mid", "high"],
            q1=[1, 2, 3],
            median=[2, 3, 4],
            q3=[3, 4, 5],
            lowerfence=[0, 1, 2],
            upperfence=[4, 5, 6],
        )
    )
    layer = _layer(fig)

    assert layer[MaidrKey.ORIENTATION] == "horz"
    assert _names(layer) == ["high", "mid", "low"]
    assert [_drawn_box(s) for s in layer[MaidrKey.SELECTOR]] == [(1, 3), (1, 2), (1, 1)]

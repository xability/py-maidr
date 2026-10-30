"""A horizontal plotly box trace with its categories on y is read, not a crash.

``go.Box(x=values, y=categories, orientation="h")`` -- what ``px.box`` draws
for a numeric ``x`` and a categorical ``y`` -- stands its boxes along ``y`` and
reads its samples from ``x``. Both box readers grouped every trace with both
arrays by ``x``, so a horizontal one took its category names for samples,
``float()`` of the first one raised ``ValueError``, and the whole figure
failed to render, every other layer with it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

LOW = [1, 2, 3, 4, 5]
HIGH = [10, 20, 30, 40, 50]


def _layers(fig) -> list[dict]:
    grid = PlotlyMaidr(fig)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _box_layer(fig) -> dict:
    (layer,) = [layer for layer in _layers(fig) if layer["type"] is PlotType.BOX]
    return layer


def _medians(layer: dict) -> dict[str, float]:
    return {box[MaidrKey.Z.value]: box[MaidrKey.Q2.value] for box in layer["data"]}


def test_one_horizontal_trace_reads_a_box_per_category():
    fig = go.Figure(
        go.Box(x=LOW + HIGH, y=["a"] * 5 + ["b"] * 5, orientation="h", name="t")
    )

    layer = _box_layer(fig)

    assert layer[MaidrKey.ORIENTATION] == "horz"
    assert _medians(layer) == {"a": 3.0, "b": 30.0}
    # Top first, as maidr.js takes a horizontal layer: "b" is drawn above "a".
    assert [box["z"] for box in layer["data"]] == ["b", "a"]


def test_plotly_express_draws_the_same_trace():
    fig = px.box(x=LOW + HIGH, y=["a"] * 5 + ["b"] * 5)

    assert fig.data[0].orientation == "h"
    assert _medians(_box_layer(fig)) == {"a": 3.0, "b": 30.0}


def test_several_horizontal_traces_are_read_together():
    fig = go.Figure(
        [
            go.Box(x=LOW + HIGH, y=["a"] * 5 + ["b"] * 5, orientation="h", name="t1"),
            go.Box(x=HIGH + LOW, y=["a"] * 5 + ["b"] * 5, orientation="h", name="t2"),
        ]
    )

    layer = _box_layer(fig)

    assert layer[MaidrKey.ORIENTATION] == "horz"
    assert sorted(box["q2"] for box in layer["data"]) == [3.0, 3.0, 30.0, 30.0]
    assert len(layer[MaidrKey.SELECTOR]) == 4


def test_the_rest_of_the_figure_still_renders():
    fig = go.Figure(
        [
            go.Bar(x=["p", "q"], y=[1, 2], xaxis="x", yaxis="y"),
            go.Box(
                x=LOW + HIGH,
                y=["a"] * 5 + ["b"] * 5,
                orientation="h",
                xaxis="x2",
                yaxis="y2",
            ),
        ]
    )
    fig.update_layout(
        xaxis={"domain": [0, 0.45]},
        xaxis2={"domain": [0.55, 1]},
        yaxis2={"anchor": "x2"},
    )

    assert sorted(layer["type"].value for layer in _layers(fig)) == ["bar", "box"]


def test_a_vertical_trace_is_still_grouped_by_x():
    fig = go.Figure(go.Box(x=["a"] * 5 + ["b"] * 5, y=LOW + HIGH, name="t"))

    layer = _box_layer(fig)

    assert layer[MaidrKey.ORIENTATION] == "vert"
    assert [box["z"] for box in layer["data"]] == ["a", "b"]
    assert _medians(layer) == {"a": 3.0, "b": 30.0}

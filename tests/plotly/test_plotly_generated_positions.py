"""A plotly trace written without `x` announced nothing (#418).

`x` is optional in plotly. Omit it and the trace is drawn at `0, 1, 2, ...`,
which is how most quick plots are written:

    go.Figure([go.Bar(y=[3, 1, 2])])

py-maidr paired the two arrays with `zip(as_list(x), as_list(y))`, and
`as_list(None)` is `[]`, so the zip yielded nothing. Every such trace produced
a layer of the right *type* carrying no data at all -- the chart drawn, the
layer present, and nothing to navigate.

Measured in Chromium rather than assumed. `gd.calcdata[0]` for
`go.Scatter(y=[1, 2, 3], mode="lines")` comes back with x `[0, 1, 2]` and one
drawn `path.js-line`; for `go.Bar(y=[3, 1, 2])`, the same x and three drawn
bars. So plotly supplies the positions and draws normally, and generating
`range(len(values))` is reproducing what it does rather than inventing a
convention.
"""

from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import paired_axes  # noqa: E402

Y = [1, 2, 3]


def only_layer(fig) -> dict:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]


def points(fig) -> list[dict]:
    """Flatten a layer's data, whether it is one series or several."""
    data = only_layer(fig)["data"]
    if not data:
        return []
    return data if isinstance(data[0], dict) else [p for s in data for p in s]


def xs(fig) -> list:
    return [point["x"] for point in points(fig)]


def ys(fig) -> list:
    return [point["y"] for point in points(fig)]


class TestTheHelper:
    def test_a_missing_position_array_is_generated(self):
        positions, values = paired_axes({"y": [5, 6, 7]})
        assert positions == [0, 1, 2]
        assert values == [5, 6, 7]

    def test_a_present_position_array_is_left_alone(self):
        positions, _ = paired_axes({"x": [10, 20, 30], "y": [1, 2, 3]})
        assert positions == [10, 20, 30]

    def test_an_empty_value_array_generates_nothing(self):
        positions, values = paired_axes({})
        assert positions == []
        assert values == []

    def test_a_short_position_array_is_left_short(self):
        # Plotly pairs the two positionally and draws only as far as the
        # shorter reaches. Truncating is its behaviour, not damage to repair
        # here -- padding would invent points it never drew.
        positions, values = paired_axes({"x": [1], "y": [1, 2, 3]})
        assert positions == [1]
        assert len(list(zip(positions, values))) == 1

    def test_the_value_axis_can_be_x(self):
        # A horizontal trace carries its magnitudes on `x`, so the generated
        # array is `y`.
        positions, values = paired_axes(
            {"x": [4, 5, 6]}, value_key="x", position_key="y"
        )
        assert positions == [0, 1, 2]
        assert values == [4, 5, 6]

    def test_an_explicit_zero_position_is_not_treated_as_missing(self):
        # `[0]` is falsy-adjacent only if someone tests the first element;
        # the list itself is truthy, so it must survive.
        positions, _ = paired_axes({"x": [0, 0, 0], "y": [1, 2, 3]})
        assert positions == [0, 0, 0]


class TestTheTraceTypesThatWentSilent:
    @pytest.mark.parametrize(
        ("fig", "expected_type"),
        [
            (
                go.Figure([go.Scatter(y=Y, mode="lines", name="a")]),
                PlotType.LINE,
            ),
            (
                go.Figure([go.Scatter(y=Y, mode="markers", name="a")]),
                PlotType.SCATTER,
            ),
            (go.Figure([go.Bar(y=[3, 1, 2], name="a")]), PlotType.BAR),
        ],
    )
    def test_the_layer_now_carries_its_points(self, fig, expected_type):
        assert only_layer(fig)["type"] is expected_type
        assert len(points(fig)) == 3

    def test_the_generated_positions_start_at_zero(self):
        # Matching plotly's own calcdata, which is `[0, 1, 2]` -- not 1-based
        # and not the data's own index.
        assert xs(go.Figure([go.Bar(y=[3, 1, 2], name="a")])) == [0, 1, 2]

    def test_the_values_are_untouched(self):
        assert ys(go.Figure([go.Bar(y=[3, 1, 2], name="a")])) == [3, 1, 2]

    def test_a_line_keeps_its_name(self):
        fig = go.Figure([go.Scatter(y=Y, mode="lines", name="a")])
        assert points(fig)[0]["z"] == "a"


class TestATraceWithoutXNoLongerHidesItsNeighbours:
    def fig(self) -> go.Figure:
        return go.Figure(
            [
                go.Scatter(y=Y, mode="lines", name="a"),
                go.Scatter(x=[1, 2, 3], y=[4, 5, 6], mode="lines", name="b"),
            ]
        )

    def test_both_lines_are_announced(self):
        assert len(only_layer(self.fig())["data"]) == 2

    def test_both_lines_get_a_selector(self):
        assert len(only_layer(self.fig())["selectors"]) == 2

    def test_each_line_keeps_its_own_positions(self):
        series = only_layer(self.fig())["data"]
        assert [point["x"] for point in series[0]] == [0, 1, 2]
        assert [point["x"] for point in series[1]] == [1, 2, 3]


class TestExplicitPositionsStillWin:
    """The fix must not overwrite what an author supplied."""

    def test_a_categorical_x_survives(self):
        fig = go.Figure([go.Bar(x=["a", "b", "c"], y=[3, 1, 2], name="t")])
        assert xs(fig) == ["a", "b", "c"]

    def test_a_numeric_x_survives(self):
        fig = go.Figure(
            [go.Scatter(x=[10, 20, 30], y=Y, mode="lines", name="t")]
        )
        assert xs(fig) == [10, 20, 30]

    def test_a_grouped_bar_with_explicit_x_survives(self):
        fig = go.Figure(
            [
                go.Bar(x=["a", "b"], y=[1, 2], name="x"),
                go.Bar(x=["a", "b"], y=[3, 4], name="y"),
            ]
        ).update_layout(barmode="stack")
        assert xs(fig) == ["a", "b", "a", "b"]

    def test_a_grouped_bar_without_x_is_generated_per_trace(self):
        fig = go.Figure(
            [go.Bar(y=[1, 2], name="x"), go.Bar(y=[3, 4], name="y")]
        ).update_layout(barmode="stack")
        assert xs(fig) == [0, 1, 0, 1]

"""A plotly box addressed the wrong element, or none at all (#395).

A box needs *two* indices and was given one. Plotly puts one ``<g>`` in the
``boxlayer`` per trace and draws that trace's boxes as direct ``path.box``
children of it, so a categorical `go.Box` puts all of its boxes inside a
single group. Numbering boxes as though each were its own group made box 1
match every box in the trace and boxes 2..n match nothing.

Three separate failures, all measured in Chromium before the fix:

1. **One trace, several categories.** Emitted ``g:nth-child(1..3)`` where the
   DOM holds one group of three boxes.
2. **A candlestick sharing the layer.** `go.Candlestick` draws its own
   ``path.box`` group into the same ``boxlayer``, so a box declared after one
   is not in the first group. ``layer_position`` widened its search to
   boxlayer-mates only when the trace *was* a candlestick, so a candlestick
   counted the boxes beside it while a box ignored the candlestick and
   claimed the group it had already taken.
3. **Multi-box with categories.** Two traces of two categories produced four
   boxes of data and only *two* selectors, because the loop ran over traces
   rather than over boxes. Half the boxes addressed nothing at all, and the
   frontend pairs selector *i* with box *i*.

Every selector asserted below was resolved against real Plotly.js output in
Chromium: 15 of 15 matched exactly one element, and the outlier selectors
matched the categories that actually have outliers.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")
np = pytest.importorskip("numpy")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.candlestick import layer_position  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

VALUES = list(np.random.default_rng(0).normal(0, 1, 45))


def box_layer(fig) -> dict:
    layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
    return next(layer for layer in layers if layer["type"] is PlotType.BOX)


def box_selectors(fig) -> list[str]:
    return [selector["q1"] for selector in box_layer(fig)["selectors"]]


def candle() -> go.Candlestick:
    return go.Candlestick(
        x=[1, 2], open=[1, 2], high=[2, 3], low=[0, 1], close=[1.5, 2.5]
    )


def categorical(name: str, values: list) -> go.Box:
    half = len(values) // 2
    return go.Box(x=["a"] * half + ["b"] * (len(values) - half), y=values, name=name)


class TestOneTraceManyCategories:
    """The boxes share a group and differ by their position inside it."""

    def fig(self) -> go.Figure:
        return go.Figure(
            [go.Box(x=["a"] * 15 + ["b"] * 15 + ["c"] * 15, y=VALUES, name="t")]
        )

    def test_a_selector_per_box(self):
        assert len(box_selectors(self.fig())) == 3

    def test_every_box_is_in_the_same_group(self):
        assert all(
            "g:nth-child(1)" in selector for selector in box_selectors(self.fig())
        )

    def test_the_boxes_are_told_apart_within_that_group(self):
        selectors = box_selectors(self.fig())
        assert "(1 of path.box)" in selectors[0]
        assert "(2 of path.box)" in selectors[1]
        assert "(3 of path.box)" in selectors[2]

    def test_no_two_boxes_share_a_selector(self):
        selectors = box_selectors(self.fig())
        assert len(set(selectors)) == len(selectors)

    def test_the_selector_count_matches_the_data(self):
        layer = box_layer(self.fig())
        assert len(layer["selectors"]) == len(layer["data"])


class TestACandlestickSharesTheLayer:
    """`go.Candlestick` draws `path.box` into the same `boxlayer`."""

    def test_a_box_after_a_candlestick_is_in_the_second_group(self):
        fig = go.Figure([candle(), go.Box(y=VALUES[:15], name="b")])
        assert "g:nth-child(2)" in box_selectors(fig)[0]

    def test_a_box_before_a_candlestick_stays_first(self):
        fig = go.Figure([go.Box(y=VALUES[:15], name="b"), candle()])
        assert "g:nth-child(1)" in box_selectors(fig)[0]

    def test_layer_position_counts_both_directions(self):
        # The asymmetry that caused it: a candlestick counted boxes, a box
        # did not count candlesticks. Both share `g.boxlayer`, so each shifts
        # the other.
        traces = [{"type": "candlestick"}, {"type": "box"}]
        assert layer_position(traces, traces[0]) == 0
        assert layer_position(traces, traces[1]) == 1

    def test_a_violin_does_not_shift_a_box(self):
        # `go.Violin` draws into `g.violinlayer`, so it is not a layer-mate
        # and must not be counted.
        traces = [{"type": "violin"}, {"type": "box"}]
        assert layer_position(traces, traces[1]) == 0

    def test_a_scatter_does_not_shift_a_box(self):
        traces = [{"type": "scatter"}, {"type": "box"}]
        assert layer_position(traces, traces[1]) == 0


class TestSeveralTracesWithCategories:
    """The case that emitted fewer selectors than boxes."""

    def fig(self) -> go.Figure:
        return go.Figure(
            [
                categorical("t1", VALUES[:15]),
                categorical("t2", VALUES[15:30]),
            ]
        )

    def test_every_box_gets_a_selector(self):
        layer = box_layer(self.fig())
        assert len(layer["data"]) == 4
        assert len(layer["selectors"]) == 4

    def test_the_boxes_are_grouped_by_their_trace(self):
        selectors = box_selectors(self.fig())
        assert "g:nth-child(1)" in selectors[0]
        assert "g:nth-child(1)" in selectors[1]
        assert "g:nth-child(2)" in selectors[2]
        assert "g:nth-child(2)" in selectors[3]

    def test_the_order_is_trace_major_like_the_dom(self):
        # Measured: two groups of two, and the data comes back a, b, a, b.
        labels = [record["z"] for record in box_layer(self.fig())["data"]]
        assert labels == ["a", "b", "a", "b"]

    def test_no_two_boxes_share_a_selector(self):
        selectors = box_selectors(self.fig())
        assert len(set(selectors)) == len(selectors)

    def test_one_box_per_trace_still_works(self):
        fig = go.Figure(
            [
                go.Box(y=VALUES[:15], name="a"),
                go.Box(y=VALUES[15:30], name="b"),
                go.Box(y=VALUES[30:], name="c"),
            ]
        )
        selectors = box_selectors(fig)
        assert len(selectors) == 3
        assert all(
            f"g:nth-child({n})" in selectors[n - 1] for n in (1, 2, 3)
        )


class TestTheLoneBoxIsBuiltOnce:
    """Guards the fall-through the two-branch structure makes possible.

    A lone box is built in `_extract_plots` so it can be told its real group.
    If that branch forgot to mark the trace merged, the trace would reach the
    "remaining traces" loop and `PlotlyPlotFactory` would build a *second*
    box for it -- with `layer_position` left at its default 0, which is
    exactly #395 again for the one figure this fix is about.

    Cheap to assert and invisible otherwise: the duplicate would announce the
    same boxes twice and the wrong one might win.
    """

    def test_a_candlestick_and_a_box_make_exactly_one_box_layer(self):
        fig = go.Figure([candle(), go.Box(y=VALUES[:15], name="b")])
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        assert sum(1 for layer in layers if layer["type"] is PlotType.BOX) == 1

    def test_the_surviving_layer_is_the_one_that_knows_its_group(self):
        # The factory-built fallback would carry `layer_position=0`, so this
        # distinguishes "built once, correctly" from "built twice, wrong one
        # kept".
        fig = go.Figure([candle(), go.Box(y=VALUES[:15], name="b")])
        assert "g:nth-child(2)" in box_selectors(fig)[0]

    def test_a_lone_box_alone_is_also_built_once(self):
        fig = go.Figure([go.Box(y=VALUES[:15], name="b")])
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        assert sum(1 for layer in layers if layer["type"] is PlotType.BOX) == 1


class TestTheDomContractTheSelectorsAssume:
    """The measured facts the selector shape depends on, named so a change
    to plotly's DOM has somewhere to fail.

    These assert the emitted strings, not a rendered document -- the Python
    suite has no browser. The resolution check (15 of 15 selectors matching
    exactly one element) was run separately against real Plotly.js in
    Chromium, and is what the shape below was derived from rather than
    guessed at. What these can still catch is the shape drifting back.
    """

    def test_a_box_is_addressed_inside_its_group_not_as_a_group(self):
        # The regression that started #395: `> path.box` with no index
        # matches every box the trace drew.
        for selector in box_selectors(
            go.Figure([go.Box(x=["a"] * 10 + ["b"] * 10, y=VALUES[:20], name="t")])
        ):
            assert "of path.box)" in selector
            assert not selector.endswith("> path.box")

    def test_outliers_are_scoped_to_one_points_group(self):
        fig = go.Figure(
            [go.Box(y=[-100, 1, 2, 3, 4, 5, 6, 7, 8, 100], name="o")]
        )
        selector = box_layer(fig)["selectors"][0]
        for found in selector["lowerOutliers"] + selector["upperOutliers"]:
            # `.points` as a descendant would reach every box's outliers in
            # the trace; the indexed child reaches one box's.
            assert "of g.points)" in found
            assert " .points" not in found


class TestOutliersFollowTheirBox:
    """The outlier groups are per box and positionally aligned."""

    def fig(self) -> go.Figure:
        return go.Figure(
            [
                go.Box(
                    x=["a"] * 11 + ["b"] * 10 + ["c"] * 12,
                    y=(
                        [-50]
                        + [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                        + [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                        + [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 90, 95]
                    ),
                    name="t",
                    boxpoints="outliers",
                )
            ]
        )

    def test_only_the_categories_with_outliers_get_outlier_selectors(self):
        # Measured: 'a' has one low, 'b' none, 'c' two high. Plotly still
        # emits an empty `g.points` for 'b', which is what keeps the pairing
        # positional rather than a count of which categories have any.
        selectors = box_layer(self.fig())["selectors"]
        assert len(selectors[0]["lowerOutliers"]) == 1
        assert selectors[1]["lowerOutliers"] == []
        assert selectors[1]["upperOutliers"] == []
        assert len(selectors[2]["upperOutliers"]) == 1

    def test_an_outlier_selector_is_scoped_to_its_own_box(self):
        selectors = box_layer(self.fig())["selectors"]
        assert "(1 of g.points)" in selectors[0]["lowerOutliers"][0]
        assert "(3 of g.points)" in selectors[2]["upperOutliers"][0]

    def test_the_outlier_group_shares_its_box_s_trace_group(self):
        selectors = box_layer(self.fig())["selectors"]
        assert "g:nth-child(1)" in selectors[0]["lowerOutliers"][0]

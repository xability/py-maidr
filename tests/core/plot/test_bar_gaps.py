"""A bar drawn with no height announced one anyway (#429).

matplotlib draws a rectangle for a ``NaN`` height, so a gap in the data
survives as a bar with no magnitude rather than being dropped. Emitting it as
it stood went wrong twice over:

* ``json.dumps`` writes ``NaN`` as a bare token, which is legal JavaScript and
  invalid JSON. The core parses the SVG's ``maidr`` attribute with
  ``JSON.parse``, so one of them stops the chart initialising at all -- audio,
  text, braille and highlight all absent, with a ``console.error`` as the only
  trace (#427).
* Even reaching the model, ``NaN`` is not a reading a listener wants.

``None`` serialises to ``null``, which the core's ``toBarValue`` has read as a
gap since the bar family gained the concept: it becomes ``NaN`` inside the
model, stays out of the range, sounds as the empty tone rather than a floor
tone, and announces as "missing". No release dependency -- that helper is in
the currently published core.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def bar_points(ax) -> list[dict]:
    record = FigureManager.get_maidr(ax.get_figure())
    return record._plots[0].schema["data"]


def stacked_points(ax) -> list[list[dict]]:
    # The layer `maidr.stacked(ax)` registered, which is the last one: the
    # second `ax.bar(bottom=)` already auto-typed a STACKED layer beside the
    # first call's BAR one, and the explicit call adds its own after both.
    record = FigureManager.get_maidr(ax.get_figure())
    return record._plots[-1].schema["data"]


def parses_as_strict_json(ax) -> None:
    """Assert the payload survives what the core actually runs on it.

    ``json.loads`` accepts the bare tokens by default, exactly as
    ``json.dumps`` emits them, so a plain round trip passes while the browser
    fails. ``parse_constant`` is what lets this fail.
    """
    schema = FigureManager.get_maidr(ax.get_figure())._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


class TestABarWithNoHeight:
    def test_it_is_emitted_as_null_rather_than_nan(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes

        assert bar_points(ax)[1]["y"] is None

    def test_the_payload_is_loadable(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes

        parses_as_strict_json(ax)

    def test_it_keeps_its_category(self):
        # The bar is kept rather than dropped, which is the difference between
        # "no reading for c" and "c was never in this chart". A category that
        # vanishes cannot be navigated to and cannot be asked about.
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert len(points) == 3
        assert [point["x"] for point in points] == ["a", "b", "c"]

    def test_the_measured_bars_are_untouched(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert points[0]["y"] == 1.0
        assert points[2]["y"] == 3.0

    def test_a_horizontal_bar_is_covered_too(self):
        # A horizontal bar's magnitude is its *width*, read on the other
        # branch of the same method, so it needs its own case rather than
        # inheriting the vertical one's.
        #
        # And the gap lands on **x**, not y. I first asserted `y` here and it
        # failed with `assert 'b' is None`: a horizontal layer emits the
        # magnitude as x and the category as y, which is the layout the
        # renderer reads. The code was right and the expectation was wrong.
        ax = plt.barh(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert points[1]["x"] is None
        assert points[1]["y"] == "b"
        parses_as_strict_json(ax)


class TestWhatMustNotChange:
    def test_a_bar_measured_at_zero_is_still_a_reading(self):
        # The distinction the whole change exists to preserve. A zero-height
        # bar was measured; a gap was not.
        ax = plt.bar(["a", "b"], [0.0, 2.0])[0].axes

        assert bar_points(ax)[0]["y"] == 0.0
        assert bar_points(ax)[0]["y"] is not None

    def test_numpy_integer_heights_still_serialise(self):
        # Pinned because it broke. The `float()` cast in the extractor was
        # doing two jobs, and a first version of this fix kept only the
        # finiteness test -- which left matplotlib's numpy types in the
        # payload and raised `TypeError: Object of type int64 is not JSON
        # serializable` on 28 tests. That is the whole render, not one bar.
        ax = plt.bar(["a", "b"], np.array([1, 2], dtype=np.int64))[0].axes

        parses_as_strict_json(ax)
        assert bar_points(ax)[0]["y"] == 1.0

    def test_a_chart_with_no_gaps_is_unchanged(self):
        ax = plt.bar(["a", "b", "c"], [1.0, 2.0, 3.0])[0].axes

        assert [point["y"] for point in bar_points(ax)] == [1.0, 2.0, 3.0]


class TestAStackedBarWithNoHeight:
    # `BarPlot` routed its bars through `_magnitude` for #429, and the
    # segmented layer read the same rectangles through a bare `float()`. Its
    # reach is matplotlib's own stacking idiom -- `ax.bar(..., bottom=a)`
    # over data with a gap -- which types the layer STACKED and then emitted
    # a bare `NaN` token for the whole figure (#696).

    @staticmethod
    def _stacked():
        fig, ax = plt.subplots()
        first = [1.0, np.nan, 3.0]
        ax.bar(["x", "y", "z"], first, label="first")
        ax.bar(["x", "y", "z"], [4.0, 5.0, 6.0], bottom=first, label="second")
        maidr.stacked(ax)
        return ax

    def test_it_is_emitted_as_null_rather_than_nan(self):
        ax = self._stacked()

        assert stacked_points(ax)[0][1]["y"] is None

    def test_the_payload_is_loadable(self):
        ax = self._stacked()

        parses_as_strict_json(ax)

    def test_the_measured_bars_are_untouched(self):
        ax = self._stacked()
        points = stacked_points(ax)

        assert [point["y"] for point in points[0]] == [1.0, None, 3.0]
        assert [point["y"] for point in points[1]] == [4.0, 5.0, 6.0]
        assert [point["x"] for point in points[0]] == ["x", "y", "z"]

    def test_a_horizontal_bar_is_covered_too(self):
        # The gap lands on **x** for a horizontal layer, as it does for the
        # plain bar above: the magnitude is the width, read on the other
        # branch of the same method.
        fig, ax = plt.subplots()
        first = [1.0, np.nan, 3.0]
        ax.barh(["x", "y", "z"], first, label="first")
        ax.barh(["x", "y", "z"], [4.0, 5.0, 6.0], left=first, label="second")
        maidr.stacked(ax)
        points = stacked_points(ax)

        assert points[0][1]["x"] is None
        assert points[0][1]["y"] == "y"
        assert [point["x"] for point in points[1]] == [4.0, 5.0, 6.0]
        parses_as_strict_json(ax)


class TestADodgedBarWithNoHeight:
    # The other layer `GroupedBarPlot` reads. A dodged chart shares the
    # stacked one's extractor and so its gap, and is reached by matplotlib's
    # own grouping idiom: numeric positions offset by a fraction, with a
    # narrow width. Seaborn's `hue=` cannot put a NaN bar here -- it drops
    # the row before drawing, which is the next class's subject -- so the
    # chart is drawn by hand.

    @staticmethod
    def _dodged():
        fig, ax = plt.subplots()
        x = np.arange(3)
        ax.bar(x - 0.2, [1.0, np.nan, 3.0], width=0.4, label="p")
        ax.bar(x + 0.2, [4.0, 5.0, 6.0], width=0.4, label="q")
        ax.set_xticks(x, ["a", "b", "c"])
        ax.legend()
        return ax

    def test_it_is_a_dodged_layer(self):
        # Pinned so the case cannot quietly become a plain bar chart and
        # pass on the other extractor.
        ax = self._dodged()
        record = FigureManager.get_maidr(ax.get_figure())

        assert record._plots[-1].type is PlotType.DODGED

    def test_it_is_emitted_as_null_rather_than_nan(self):
        ax = self._dodged()

        assert stacked_points(ax)[0][1]["y"] is None

    def test_the_payload_is_loadable(self):
        ax = self._dodged()

        parses_as_strict_json(ax)

    def test_the_measured_bars_are_untouched(self):
        ax = self._dodged()
        points = stacked_points(ax)

        assert [point["y"] for point in points[0]] == [1.0, None, 3.0]
        assert [point["y"] for point in points[1]] == [4.0, 5.0, 6.0]
        assert [point["x"] for point in points[0]] == ["a", "b", "c"]

    def test_a_horizontal_bar_is_covered_too(self):
        # `barh` says its bar thickness with `height`, which the grouping
        # test does not read, so the sideways chart is drawn edge-aligned
        # instead -- the other idiom that test recognises. The gap lands on
        # x, as it does for every horizontal layer.
        fig, ax = plt.subplots()
        y = np.arange(3)
        ax.barh(y - 0.4, [1.0, np.nan, 3.0], height=0.4, align="edge", label="p")
        ax.barh(y, [4.0, 5.0, 6.0], height=0.4, align="edge", label="q")
        ax.set_yticks(y, ["a", "b", "c"])
        ax.legend()
        record = FigureManager.get_maidr(fig)
        points = stacked_points(ax)

        assert record._plots[-1].type is PlotType.DODGED
        assert points[0][1]["x"] is None
        assert points[0][1]["y"] == "b"
        assert [point["x"] for point in points[1]] == [4.0, 5.0, 6.0]
        parses_as_strict_json(ax)


class TestASeabornHueMissingACategory:
    # `sns.barplot(hue=)` cannot draw a NaN bar: it drops the row before
    # drawing, so the hue level that lacks one category comes out a bar
    # short and the containers are ragged. The grouped extractor paired bars
    # with labels by position alone and gave that layer up, and the patch
    # fell back to a plain bar layer whose labels were the bars' fractional
    # positions -- "-0.2", "0.8" -- so a reader heard numbers where the
    # chart shows groups (#752). The bar seaborn never drew is the same gap
    # the hand-drawn chart above emits for a NaN height.

    @staticmethod
    def _frame(missing: str = "b") -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "cat": ["a", "b", "c"] * 2,
                "grp": ["g1"] * 3 + ["g2"] * 3,
                "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            }
        )
        frame.loc[(frame["cat"] == missing) & (frame["grp"] == "g2"), "val"] = np.nan
        return frame

    @classmethod
    def _hued(cls, missing: str = "b"):
        fig, ax = plt.subplots()
        sns.barplot(data=cls._frame(missing), x="cat", y="val", hue="grp", ax=ax)
        # The premise: seaborn dropped the bar rather than drawing a gap.
        assert [len(c.patches) for c in ax.containers] == [3, 2]
        return ax

    def test_it_is_a_dodged_layer(self):
        ax = self._hued()
        record = FigureManager.get_maidr(ax.get_figure())

        assert record._plots[-1].type is PlotType.DODGED

    def test_it_names_the_categories_and_the_groups(self):
        # The whole of the complaint: "a", "b", "c" and "g1", "g2", which
        # are what the chart shows, and not "-0.2", which is where the
        # first bar happened to be drawn.
        ax = self._hued()
        points = stacked_points(ax)

        assert [[point["x"] for point in series] for series in points] == [
            ["a", "b", "c"],
            ["a", "b", "c"],
        ]
        assert [[point["z"] for point in series] for series in points] == [
            ["g1"] * 3,
            ["g2"] * 3,
        ]

    def test_the_missing_bar_is_emitted_as_null(self):
        ax = self._hued()

        assert stacked_points(ax)[1][1]["y"] is None

    def test_the_payload_is_loadable(self):
        ax = self._hued()

        parses_as_strict_json(ax)

    def test_the_measured_bars_are_untouched(self):
        ax = self._hued()
        points = stacked_points(ax)

        assert [point["y"] for point in points[0]] == [1.0, 2.0, 3.0]
        assert [point["y"] for point in points[1]] == [4.0, None, 6.0]

    @pytest.mark.parametrize("missing", ["a", "c"])
    def test_a_gap_at_either_end_lands_on_its_own_category(self, missing: str):
        # The bars are placed by the tick nearest each one rather than
        # counted from the start, so a gap at the first or last category
        # does not shift every bar after it by one.
        ax = self._hued(missing)
        points = stacked_points(ax)

        assert [point["x"] for point in points[1]] == ["a", "b", "c"]
        assert points[1][["a", "b", "c"].index(missing)]["y"] is None
        assert sum(point["y"] is None for point in points[1]) == 1

    def test_a_horizontal_layer_is_covered_too(self):
        # The gap lands on x for a horizontal layer, as it does for every
        # other one, and the bars are placed by their y centres.
        fig, ax = plt.subplots()
        sns.barplot(data=self._frame(), y="cat", x="val", hue="grp", ax=ax)
        record = FigureManager.get_maidr(fig)
        points = stacked_points(ax)

        assert record._plots[-1].type is PlotType.DODGED
        assert [point["y"] for point in points[1]] == ["a", "b", "c"]
        assert [point["x"] for point in points[1]] == [4.0, None, 6.0]
        parses_as_strict_json(ax)

    # Two hue levels each missing a *different* category -- containers of
    # [2, 2] bars over 3 ticks -- are equal in length and short of the
    # axis, which raggedness cannot see: the layer was still a plain bar
    # labelled by position, "1.2" for g2's "b".
    # It is the shape the hue that repeats the category draws as well, one
    # container per bar, so the two are told apart by whether a category
    # holds bars of two containers -- side by side is what dodged means.

    @staticmethod
    def _frame_short_everywhere(g1_lacks: str = "c", g2_lacks: str = "a"):
        # Containers of two bars over three ticks. With the defaults they
        # meet only at "b".
        frame = pd.DataFrame(
            {
                "cat": ["a", "b", "c"] * 2,
                "grp": ["g1"] * 3 + ["g2"] * 3,
                "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            }
        )
        frame.loc[(frame["cat"] == g1_lacks) & (frame["grp"] == "g1"), "val"] = np.nan
        frame.loc[(frame["cat"] == g2_lacks) & (frame["grp"] == "g2"), "val"] = np.nan
        return frame

    @pytest.mark.parametrize(
        "g1_lacks, g2_lacks",
        [
            pytest.param("c", "a", id="meet-at-b"),
            # The first category's only bar is g2's, dodged to +0.2 and 0.4
            # wide, so its left edge is `0.2 - 0.2` -- a float hair past
            # the tick at 0. The tick filter used to drop that category as
            # outside the data, which left two labels for two bars and let
            # the layer pair by position: g2's "a" was announced as "b".
            pytest.param("a", "b", id="edge-a-hair-past-the-tick"),
        ],
    )
    def test_two_levels_each_missing_a_different_category_are_grouped(
        self, g1_lacks: str, g2_lacks: str
    ):
        fig, ax = plt.subplots()
        sns.barplot(
            data=self._frame_short_everywhere(g1_lacks, g2_lacks),
            x="cat",
            y="val",
            hue="grp",
            ax=ax,
        )
        # The premise: [2, 2] bars over three ticks, equal and both short.
        assert [len(c.patches) for c in ax.containers] == [2, 2]
        assert [t.get_text() for t in ax.get_xticklabels()] == ["a", "b", "c"]
        record = FigureManager.get_maidr(fig)
        points = stacked_points(ax)

        assert record._plots[-1].type is PlotType.DODGED
        heights = {"a": [1.0, 4.0], "b": [2.0, 5.0], "c": [3.0, 6.0]}
        assert points == [
            [
                {
                    "x": cat,
                    "z": "g1",
                    "y": None if cat == g1_lacks else heights[cat][0],
                }
                for cat in ["a", "b", "c"]
            ],
            [
                {
                    "x": cat,
                    "z": "g2",
                    "y": None if cat == g2_lacks else heights[cat][1],
                }
                for cat in ["a", "b", "c"]
            ],
        ]
        parses_as_strict_json(ax)

    def test_two_levels_each_missing_a_different_category_sideways(self):
        fig, ax = plt.subplots()
        sns.barplot(
            data=self._frame_short_everywhere(), y="cat", x="val", hue="grp", ax=ax
        )
        record = FigureManager.get_maidr(fig)
        points = stacked_points(ax)

        assert record._plots[-1].type is PlotType.DODGED
        assert [point["y"] for point in points[1]] == ["a", "b", "c"]
        assert [point["x"] for point in points[0]] == [1.0, 2.0, None]
        assert [point["x"] for point in points[1]] == [None, 5.0, 6.0]

    def test_a_hue_that_repeats_the_category_stays_a_plain_bar(self):
        # The control. Seaborn draws this one container per bar, all the
        # same length and short of the axis -- the shape above -- but no
        # category holds two bars, so nothing about it is grouped, and the
        # plain bar layer names the categories as it always did.
        frame = pd.DataFrame({"cat": ["a", "b", "c"], "val": [1.0, 2.0, 3.0]})
        fig, ax = plt.subplots()
        sns.barplot(data=frame, x="cat", y="val", hue="cat", ax=ax)
        record = FigureManager.get_maidr(fig)

        assert [len(c.patches) for c in ax.containers] == [1, 1, 1]
        assert record._plots[-1].type is PlotType.BAR
        assert bar_points(ax) == [
            {"x": "a", "y": 1.0},
            {"x": "b", "y": 2.0},
            {"x": "c", "y": 3.0},
        ]

    def test_a_numeric_axis_is_not_placed_against_its_breaks(self):
        # The guard the placement needs. A stacked chart over
        # `np.arange(3)` has more ticks in view than bars, all chosen by the
        # locator; those are breaks, not categories, and the layer keeps
        # announcing the positions its bars were drawn at (#384).
        fig, ax = plt.subplots()
        positions = np.arange(3)
        ax.bar(positions, [1.0, 2.0, 3.0], label="lower")
        ax.bar(positions, [4.0, 5.0, 6.0], bottom=[1.0, 2.0, 3.0], label="upper")
        maidr.stacked(ax)
        points = stacked_points(ax)

        assert [point["x"] for point in points[0]] == ["0", "1", "2"]
        assert [point["y"] for point in points[1]] == [4.0, 5.0, 6.0]

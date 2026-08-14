"""A plotly histogram's ``histfunc`` was ignored, so an aggregate read as a
count (#405).

`histfunc` selects what a histogram bar *measures*. `_extract_plot_data`
called `np.histogram`, which returns bin populations, and never read the
attribute -- so every aggregating mode was announced as a count. Only
`count`, the default, was right, and only because it is what we already
computed.

Two things widened this beyond how it was first raised in review, and both are
pinned below:

* **It is not only `sum`.** `avg`, `min` and `max` are ignored too.
* **It is not only the categorical path.** Numeric binning has it as well,
  and that case is worse: a reader gets `2` where the chart draws `30`, inside
  a layer whose bin bounds are all correct, so nothing else in the
  announcement looks wrong.

The empty-bin behaviour is the part that could not be reasoned out. `count`
and `sum` announce a zero for a bin nothing landed in; `avg`, `min` and `max`
have no answer and plotly emits no point at all -- interior bins included, not
just the edges #402 trims. But setting **any** `histnorm` brings them back as
zeros: measured over a sample with a two-bin gap, `avg` alone gives four
points and `avg` with any of the four norms gives six. So the two attributes
do not compose as one step after the other, and a fix that applied them in
sequence would be wrong for exactly the figures that use both.

Every expectation is `gd.calcdata[0][i].s` after `Plotly.newPlot` in Chromium.
All 50 figure shapes measured that way now agree elementwise, on both
orientations.
"""

from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.histogram import aggregate_bins, value_array  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Categories a/b/c holding 1,4,7 / 2,5,8 / 3,6,9.
CATS = list("abcabcabc")
CAT_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9]

#: Four values either side of a two-bin gap, on an explicit 0..12 grid of 2.
GAP_X = [0.5, 1.2, 2.4, 3.1, 9.0, 9.6, 10.8, 11.2]
GAP_Y = [10, 20, 30, 40, 50, 60, 70, 80]
GRID = dict(start=0, end=12, size=2)


def pairs(fig) -> list[tuple]:
    """``(bin, value)`` per emitted point, off whichever axis holds which."""
    layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
    horizontal = layer.get("orientation") == "horz"
    binned, measured = ("y", "x") if horizontal else ("x", "y")
    return [(d[binned], d[measured]) for d in layer["data"]]


def values(fig) -> list:
    return [value for _, value in pairs(fig)]


class TestValueArray:
    """Which array supplies the values, and when there is one at all."""

    def test_a_counting_trace_has_no_value_array(self):
        assert value_array({"type": "histogram", "x": CATS}, "x") is None

    def test_an_explicit_count_has_none_either(self):
        trace = {"type": "histogram", "x": CATS, "y": CAT_VALUES, "histfunc": "count"}
        assert value_array(trace, "x") is None

    @pytest.mark.parametrize("histfunc", ["sum", "avg", "min", "max"])
    def test_an_aggregating_trace_takes_the_other_axis(self, histfunc):
        trace = {"type": "histogram", "x": CATS, "y": CAT_VALUES, "histfunc": histfunc}
        assert value_array(trace, "x") == CAT_VALUES

    def test_it_is_the_other_axis_rather_than_the_numeric_one(self):
        # `go.Histogram(y=cats, x=vals, histfunc="sum")` resolves to
        # `orientation: v` in Plotly.js -- plotly bins `x` in *both* spellings
        # -- so "whichever array is not categorical" is not the rule. The
        # binned axis decides and this is simply the other.
        trace = {"type": "histogram", "y": CATS, "x": CAT_VALUES, "histfunc": "sum"}
        assert value_array(trace, "x") == CATS

    def test_an_aggregating_trace_with_only_one_array_has_nothing_to_reduce(self):
        trace = {"type": "histogram", "x": CATS, "histfunc": "sum"}
        assert value_array(trace, "x") is None


class TestAggregateBins:
    """The reduction in isolation."""

    ASSIGNMENT = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2])
    VALUES = np.array(CAT_VALUES, dtype=float)

    @pytest.mark.parametrize(
        ("histfunc", "expected"),
        [
            ("sum", [12.0, 15.0, 18.0]),
            ("avg", [4.0, 5.0, 6.0]),
            ("min", [1.0, 2.0, 3.0]),
            ("max", [7.0, 8.0, 9.0]),
        ],
    )
    def test_reduces_each_bin(self, histfunc, expected):
        got, present = aggregate_bins(self.ASSIGNMENT, self.VALUES, 3, histfunc)
        assert list(got) == pytest.approx(expected)
        assert list(present) == [True, True, True]

    def test_an_empty_bin_is_marked_rather_than_guessed(self):
        got, present = aggregate_bins(
            np.array([0, 0, 2]), np.array([1.0, 3.0, 9.0]), 3, "avg"
        )
        assert list(present) == [True, False, True]
        # The caller decides what an unmarked bin becomes; the value here is
        # only a placeholder, never an announced average of nothing.
        assert got[0] == pytest.approx(2.0)
        assert got[2] == pytest.approx(9.0)

    def test_observations_outside_every_bin_are_discarded(self):
        # `-1` is what `_bin_assignment` gives a value beyond the grid, and
        # plotly drops those rather than clipping them into an edge bin.
        got, present = aggregate_bins(
            np.array([-1, 0, -1]), np.array([100.0, 5.0, 200.0]), 2, "max"
        )
        assert got[0] == pytest.approx(5.0)
        assert list(present) == [True, False]


class TestCategoricalAggregation:
    """Plotly draws string data as a count bar chart; `histfunc` still applies."""

    @pytest.mark.parametrize(
        ("histfunc", "expected"),
        [
            ("count", [3, 3, 3]),
            ("sum", [12, 15, 18]),
            ("avg", [4, 5, 6]),
            ("min", [1, 2, 3]),
            ("max", [7, 8, 9]),
        ],
    )
    def test_every_mode_matches_plotly(self, histfunc, expected):
        fig = go.Figure([go.Histogram(x=CATS, y=CAT_VALUES, histfunc=histfunc)])
        assert values(fig) == expected

    def test_the_labels_survive_aggregation(self):
        fig = go.Figure([go.Histogram(x=CATS, y=CAT_VALUES, histfunc="sum")])
        assert [category for category, _ in pairs(fig)] == ["a", "b", "c"]

    def test_a_horizontal_categorical_trace_aggregates_the_same_way(self):
        # `orientation="h"` is required, not decorative. With both arrays
        # present plotly resolves to `v` whichever way round they are given,
        # so swapping them alone does not make a horizontal chart -- see
        # `TestSwappedArraysIsNotHorizontal` for what it does make.
        upright = values(
            go.Figure([go.Histogram(x=CATS, y=CAT_VALUES, histfunc="sum")])
        )
        sideways = values(
            go.Figure(
                [go.Histogram(y=CATS, x=CAT_VALUES, histfunc="sum", orientation="h")]
            )
        )
        assert sideways == upright


class TestNumericAggregation:
    """The path the review's framing did not cover."""

    @pytest.mark.parametrize(
        ("histfunc", "expected"),
        [
            ("count", [2, 2, 0, 0, 2, 2]),
            ("sum", [30, 70, 0, 0, 110, 150]),
        ],
    )
    def test_count_and_sum_keep_an_empty_bin_as_zero(self, histfunc, expected):
        fig = go.Figure([go.Histogram(x=GAP_X, y=GAP_Y, histfunc=histfunc, xbins=GRID)])
        assert values(fig) == expected

    @pytest.mark.parametrize(
        ("histfunc", "expected"),
        [
            ("avg", [(1.0, 15), (3.0, 35), (9.0, 55), (11.0, 75)]),
            ("min", [(1.0, 10), (3.0, 30), (9.0, 50), (11.0, 70)]),
            ("max", [(1.0, 20), (3.0, 40), (9.0, 60), (11.0, 80)]),
        ],
    )
    def test_the_undefined_modes_drop_an_empty_bin_entirely(self, histfunc, expected):
        # Four points, not six, and the two dropped are *interior* -- so this
        # is not #402's edge trim reaching further. There is no average of
        # nothing to announce.
        fig = go.Figure([go.Histogram(x=GAP_X, y=GAP_Y, histfunc=histfunc, xbins=GRID)])
        assert pairs(fig) == expected

    def test_a_horizontal_numeric_trace_aggregates_the_same_way(self):
        upright = values(
            go.Figure([go.Histogram(x=GAP_X, y=GAP_Y, histfunc="sum", xbins=GRID)])
        )
        sideways = values(
            go.Figure(
                [
                    go.Histogram(
                        y=GAP_X,
                        x=GAP_Y,
                        histfunc="sum",
                        ybins=GRID,
                        orientation="h",
                    )
                ]
            )
        )
        assert sideways == upright

    def test_the_bin_bounds_are_untouched_by_aggregating(self):
        counted = [
            b for b, _ in pairs(go.Figure([go.Histogram(x=GAP_X, y=GAP_Y, xbins=GRID)]))
        ]
        summed = [
            b
            for b, _ in pairs(
                go.Figure([go.Histogram(x=GAP_X, y=GAP_Y, histfunc="sum", xbins=GRID)])
            )
        ]
        assert summed == counted


class TestNonNumericValues:
    """The value array is not guaranteed numeric, and plotly does not error."""

    #: `b` holds two strings and one number.
    MIXED = [1, "z", 3, 4, "w", 6, 7, 8, 9]

    @pytest.mark.parametrize(
        ("histfunc", "expected"),
        [
            # `b` reduces over `[8]` alone in every mode.
            ("sum", [12, 8, 18]),
            ("avg", [4, 8, 6]),
            ("min", [1, 8, 3]),
            ("max", [7, 8, 9]),
        ],
    )
    def test_a_string_is_dropped_rather_than_counted_as_zero(self, histfunc, expected):
        # The distinction the `avg` row settles: `b` averages to **8**, not
        # 8/3. Treating a non-number as an observation of zero would give
        # 2.667 here and 0 for `min`, and both would look plausible.
        fig = go.Figure([go.Histogram(x=CATS, y=self.MIXED, histfunc=histfunc)])
        assert values(fig) == expected

    def test_count_is_unaffected_by_an_unreadable_value(self):
        # `count` counts observations on the *binned* axis, so what sits in
        # the value array cannot change it.
        fig = go.Figure([go.Histogram(x=CATS, y=self.MIXED, histfunc="count")])
        assert values(fig) == [3, 3, 3]

    def test_a_wholly_non_numeric_value_array_does_not_raise(self):
        # `go.Histogram(y=cats, x=vals, histfunc="sum")` bins `x` and hands
        # the *category strings* to the aggregate. A plain float conversion
        # raised here, on a figure plotly renders without complaint.
        fig = go.Figure([go.Histogram(y=CATS, x=CAT_VALUES, histfunc="sum")])
        assert all(value == 0 for value in values(fig))


class TestSwappedArraysIsNotHorizontal:
    """Swapping the arrays makes a different chart, not a rotated one."""

    def test_plotly_still_bins_x_and_maidr_follows(self):
        # `go.Histogram(y=cats, x=vals, histfunc="sum")` reads as vertical:
        # plotly bins `x` -- the *numeric* array here -- and sums `y`, which
        # is the category strings and contributes nothing. Plotly draws two
        # bars of zero. That is a chart nobody wants, and it is the chart the
        # call describes, so it is announced rather than second-guessed.
        fig = go.Figure([go.Histogram(y=CATS, x=CAT_VALUES, histfunc="sum")])
        layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]

        assert layer["orientation"] == "vert"
        assert all(point["y"] == 0 for point in layer["data"])


class TestHistfuncAndHistnormTogether:
    """They do not compose as one step after the other."""

    @pytest.mark.parametrize("histfunc", ["avg", "min", "max"])
    @pytest.mark.parametrize(
        "histnorm", ["percent", "probability", "density", "probability density"]
    )
    def test_any_histnorm_brings_the_empty_bins_back(self, histfunc, histnorm):
        # The interaction that cannot be reasoned out: alone these three drop
        # an empty bin, and with *any* histnorm plotly emits it as a zero.
        # Rescaling evidently runs over the whole bin array without carrying
        # the "no answer" marker through.
        alone = go.Figure(
            [go.Histogram(x=GAP_X, y=GAP_Y, histfunc=histfunc, xbins=GRID)]
        )
        rescaled = go.Figure(
            [
                go.Histogram(
                    x=GAP_X,
                    y=GAP_Y,
                    histfunc=histfunc,
                    histnorm=histnorm,
                    xbins=GRID,
                )
            ]
        )
        assert len(values(alone)) == 4
        assert len(values(rescaled)) == 6
        assert values(rescaled)[2:4] == [0, 0]

    def test_sum_and_avg_normalise_to_the_same_shares(self):
        # The measurement that settles `histnorm`'s denominator: dividing
        # every value by a constant leaves the shares alone, so the total
        # cannot be the sample size.
        summed = values(
            go.Figure(
                [go.Histogram(x=CATS, y=CAT_VALUES, histfunc="sum", histnorm="percent")]
            )
        )
        averaged = values(
            go.Figure(
                [go.Histogram(x=CATS, y=CAT_VALUES, histfunc="avg", histnorm="percent")]
            )
        )
        assert averaged == pytest.approx(summed)
        assert sum(summed) == pytest.approx(100.0)

    def test_min_normalises_to_a_different_shape(self):
        # And a mode that is not a constant multiple of `sum` must not, or
        # the test above would pass on an implementation that ignored
        # `histfunc` entirely.
        summed = values(
            go.Figure(
                [go.Histogram(x=CATS, y=CAT_VALUES, histfunc="sum", histnorm="percent")]
            )
        )
        smallest = values(
            go.Figure(
                [go.Histogram(x=CATS, y=CAT_VALUES, histfunc="min", histnorm="percent")]
            )
        )
        assert smallest != pytest.approx(summed)
        assert smallest == pytest.approx([100 / 6, 200 / 6, 300 / 6])

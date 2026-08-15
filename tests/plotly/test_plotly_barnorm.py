"""A 100% stacked bar chart was announced as an ordinary stacked one.

`layout.barnorm` is plotly's own switch for normalising each stack to a common
total — `'percent'` scales to 100, `'fraction'` to 1. Either way the segment
values are *shares of their category* rather than counts. MAIDR did not read
it, so such a chart arrived as `stacked_bar` (#338).

What a reader loses is not the numbers, which are announced either way, but
what they *are*. A `stacked_bar` invites the reading that each segment is a
count and that the categories happen to total the same; `stacked_normalized_bar`
says the totals are equal by construction and the parts are proportions. The
MAIDR core has carried `TraceType.NORMALIZED = 'stacked_normalized_bar'` for
some time; `PlotType` simply had no member to emit it with, so the type was
unreachable from Python.

This is a lookup rather than a heuristic, and deliberately so. matplotlib and
seaborn have no equivalent declaration — a user normalises the data themselves
and calls `ax.bar(bottom=...)` — so inferring "every category totals 1.0, so
this must be normalised" would name a chart from a coincidence in its data.
Plotly states it, so plotly is where this can be read honestly.


A second defect in the same setting, fixed later: the layer was typed
`stacked_normalized_bar` correctly, and the values under it stayed the raw
counts (#409). The type said the bars are shares of their category; the
numbers were the tallies. Everything below the `TestTheScale` class covers
that half, and every number in it was measured against `gd.calcdata[i][j].s`
after `Plotly.newPlot` in Chromium rather than read from the documentation --
including two rules the documentation does not spell out: the denominator
depends on `barmode`, and under `stack` it is the *absolute value* of the
signed sum.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.barnorm import (  # noqa: E402
    barnorm_scale,
    stack_shares,
    stack_totals,
)
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Every combination that decides the layer type. `barnorm` normalises a stack
#: whatever spelling of stacking got it there, and means nothing to a dodge.
CASES = [
    (None, None, "stacked_bar"),
    ("stack", None, "stacked_bar"),
    ("stack", "percent", "stacked_normalized_bar"),
    ("stack", "fraction", "stacked_normalized_bar"),
    ("relative", "percent", "stacked_normalized_bar"),
    (None, "percent", "stacked_normalized_bar"),
    ("group", "percent", "dodged_bar"),
    ("group", None, "dodged_bar"),
]


def _figure(barmode: str | None, barnorm: str | None) -> go.Figure:
    """Two bar traces over one category axis, at *barmode* and *barnorm*."""
    figure = go.Figure(
        [
            go.Bar(x=["a", "b", "c"], y=[1.0, 2.0, 3.0], name="lower"),
            go.Bar(x=["a", "b", "c"], y=[3.0, 2.0, 1.0], name="upper"),
        ]
    )
    layout = {}
    if barmode is not None:
        layout["barmode"] = barmode
    if barnorm is not None:
        layout["barnorm"] = barnorm
    if layout:
        figure.update_layout(**layout)
    return figure


def _types(figure: go.Figure) -> list[str]:
    """The layer types MAIDR extracts from a plotly figure."""
    return [plot.type.value for plot in PlotlyMaidr(figure)._plots]


@pytest.mark.parametrize("barmode,barnorm,expected", CASES)
def test_barnorm_decides_only_what_it_should(barmode, barnorm, expected) -> None:
    """The whole table, since the failure is a silent mislabel.

    Two axes of a small closed set, so every combination is named rather than
    left to a representative case — including the two rows where `barnorm` is
    set and must *not* change the answer.
    """
    assert _types(_figure(barmode, barnorm)) == [expected]


def test_a_dodge_is_not_normalised_by_barnorm() -> None:
    """`barnorm` normalises a *stack*, and a dodge has none to normalise.

    Stated on its own because it is the row a "barnorm means normalised"
    shortcut would get wrong, and the answer would look plausible: side-by-side
    bars announced as shares of a total that the chart never draws.
    """
    assert _types(_figure("group", "percent")) == ["dodged_bar"]


def test_an_empty_barnorm_is_not_normalisation() -> None:
    """Plotly's own "off" value is the empty string, not absence.

    `barnorm=""` is how a figure says *not* normalised after something set it,
    so membership of the normalising set is the test rather than truthiness of
    the key.
    """
    assert _types(_figure("stack", "")) == ["stacked_bar"]


def test_the_express_spelling_reaches_the_same_answer() -> None:
    """How a user actually writes one, rather than a hand-built layout.

    `px.bar` takes no `barnorm` argument -- unlike `px.histogram`, which does
    -- so the express route to a 100% stacked bar is `update_layout`. That
    still has to arrive as `relative` + `percent` in `to_dict()` for the
    lookup above to fire, which is the part worth driving rather than assuming
    from the `go.Figure` cases.
    """
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    import plotly.express as px

    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "g": list("abc") * 10,
            "h": ["x", "y"] * 15,
            "v": rng.normal(10, 3, size=30),
        }
    )

    figure = px.bar(frame, x="g", y="v", color="h").update_layout(barnorm="percent")

    assert figure.layout.barmode == "relative"
    assert _types(figure) == ["stacked_normalized_bar"]


def test_the_type_is_the_one_the_maidr_core_already_carries() -> None:
    """The wire value has to match the core, or the bundle cannot draw it.

    `TraceType.NORMALIZED = 'stacked_normalized_bar'` has existed in the JS
    grammar for some time; what was missing was a `PlotType` member to emit
    it. A mismatch here would render an unknown trace rather than a chart, so
    the string is pinned rather than left to a constructor.
    """
    assert PlotType.NORMALIZED.value == "stacked_normalized_bar"
    assert PlotType.NORMALIZED.display_name == "100% stacked bar"


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"c": ["a", "a", "b", "b"], "g": ["x", "y", "x", "y"], "v": [3, 1, 2, 6]}
    )


def only_layer(fig) -> dict:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]


def values(fig, key: str = "y") -> list[list]:
    return [[point[key] for point in series] for series in only_layer(fig)["data"]]


def one_position(vals: list, barmode: str, scale: float = 100.0) -> list:
    """Run every value through one shared stack position."""
    series = [[("a", v)] for v in vals]
    return [row[0] for row in stack_shares(series, barmode, scale)]


class TestTheScale:
    @pytest.mark.parametrize(
        ("barnorm", "expected"), [("percent", 100.0), ("fraction", 1.0)]
    )
    def test_the_two_normalising_settings(self, barnorm, expected):
        assert barnorm_scale(barnorm) == expected

    @pytest.mark.parametrize("barnorm", [None, "", "nonsense", 5, True])
    def test_everything_else_normalises_nothing(self, barnorm):
        # `None` rather than 1.0, so the caller emits the values untouched
        # instead of multiplying them by a no-op and turning ints into floats.
        assert barnorm_scale(barnorm) is None


class TestTheDenominatorFollowsTheBarmode:
    """The rule the documentation does not spell out."""

    def test_relative_normalises_each_sign_against_its_own_total(self):
        # Measured: [3, -1] comes back 100, -100 -- not 75, -25. `relative`
        # draws the positive and negative bars as two stacks growing away
        # from the baseline and normalises each against its own total.
        assert one_position([3, -1], "relative") == [100.0, -100.0]

    def test_stack_pools_both_signs_into_one_total(self):
        # Measured: the same input under `stack` comes back 150, -50 --
        # a denominator of 2, the signed sum.
        assert one_position([3, -1], "stack") == [150.0, -50.0]

    def test_the_pooled_denominator_is_the_absolute_signed_sum(self):
        # The measurement that refutes reading it as a plain signed sum:
        # [0, -4] comes back 0, -100. A denominator of -4 would have made
        # the second bar +100.
        assert one_position([0, -4], "stack") == [0.0, -100.0]

    def test_three_values_pooled(self):
        assert one_position([3, -1, 6], "stack") == [37.5, -12.5, 75.0]

    def test_three_values_by_sign(self):
        got = one_position([3, -1, 6], "relative")
        assert got == pytest.approx([100 / 3, -100.0, 200 / 3])

    def test_a_zero_does_not_change_the_pooled_total(self):
        assert one_position([0, 4, -2], "stack") == [0.0, 200.0, -100.0]

    def test_two_negatives_share_their_own_total(self):
        assert one_position([-3, -1], "relative") == [-75.0, -25.0]

    def test_an_unset_barmode_behaves_as_relative(self):
        # Plotly's default is `relative`, and it is what `px.bar` leaves
        # behind, so an absent barmode must not fall into the pooled rule.
        assert one_position([3, -1], None) == [100.0, -100.0]


class TestUndefinedShares:
    def test_a_position_totalling_zero_is_a_gap(self):
        # Measured: a category whose every segment is zero comes back with
        # its `x` intact and `s` null. The share would be 0/0.
        assert one_position([0, 0], "relative") == [None, None]

    def test_a_pooled_stack_that_cancels_is_a_gap(self):
        # [3, -3] sums to zero under `stack`, so nothing can be a share of
        # it -- measured as null for both.
        assert one_position([3, -3], "stack") == [None, None]

    def test_the_same_input_is_defined_under_relative(self):
        # Same numbers, different rule: each sign has a non-zero total of
        # its own, so both bars are full shares of their side.
        assert one_position([3, -3], "relative") == [100.0, -100.0]

    def test_a_zero_alone_in_its_sign_group_is_a_gap(self):
        # Measured under `relative`: [0, -4] gives null, -100. Zero counts
        # as positive, its group totals zero, so its share is undefined --
        # where the pooled rule gives it a defined 0.
        assert one_position([0, -4], "relative") == [None, -100.0]

    def test_a_null_stays_null_and_leaves_the_total_alone(self):
        # Measured: [None, 4] comes back null, 100 -- so the null neither
        # contributed to the denominator nor became a zero share.
        assert one_position([None, 4], "relative") == [None, 100.0]

    def test_a_gap_keeps_its_position(self):
        # The count of points never changes: plotly blanks the value and
        # keeps the `x`, so the category is still reachable by a cursor.
        series = [[("a", 0), ("b", 3)], [("a", 0), ("b", 1)]]
        assert stack_shares(series, "relative", 100.0) == [
            [None, 75.0],
            [None, 25.0],
        ]


class TestPositionsAreMatchedByValue:
    def test_a_series_that_skips_a_position_contributes_nothing_there(self):
        # Ragged input: measured with one trace covering both categories and
        # the other only the first, the lone bar at the second came back 100.
        series = [[("a", 3), ("b", 2)], [("a", 1)]]
        assert stack_shares(series, "relative", 100.0) == [[75.0, 100.0], [25.0]]

    def test_totals_are_keyed_by_position_not_index(self):
        # Declared in opposite orders, so an index-keyed total would pair
        # 'a' with 'b'.
        series = [[("a", 3), ("b", 2)], [("b", 6), ("a", 1)]]
        assert stack_shares(series, "relative", 100.0) == [
            [75.0, 25.0],
            [75.0, 25.0],
        ]

    def test_stack_totals_reports_one_bucket_per_sign(self):
        totals = stack_totals([[("a", 3)], [("a", -1)]], "relative")
        assert totals["a"] == {False: 3.0, True: 1.0}

    def test_stack_totals_pools_into_one_bucket(self):
        totals = stack_totals([[("a", 3)], [("a", -1)]], "stack")
        assert totals["a"] == {False: 2.0}


class TestTheEmittedBarLayer:
    def test_percent_reaches_the_layer(self):
        fig = px.bar(frame(), x="c", y="v", color="g").update_layout(
            barnorm="percent"
        )
        assert values(fig) == [[75.0, 25.0], [25.0, 75.0]]

    def test_fraction_reaches_the_layer(self):
        fig = px.bar(frame(), x="c", y="v", color="g").update_layout(
            barnorm="fraction"
        )
        assert values(fig) == [[0.75, 0.25], [0.25, 0.75]]

    def test_the_type_and_the_values_now_agree(self):
        fig = px.bar(frame(), x="c", y="v", color="g").update_layout(
            barnorm="percent"
        )
        layer = only_layer(fig)
        assert layer["type"] == PlotType.NORMALIZED.value
        assert sum(point["y"] for point in layer["data"][0][:1]) == 75.0

    def test_without_barnorm_the_counts_are_untouched(self):
        fig = px.bar(frame(), x="c", y="v", color="g")
        assert only_layer(fig)["type"] == PlotType.STACKED.value
        assert values(fig) == [[3, 2], [1, 6]]

    def test_a_horizontal_bar_normalises_the_value_axis(self):
        # The category and the magnitude swap axes, so normalising `y` would
        # rescale the categories. Measured: the shares come back on `x`.
        fig = px.bar(
            frame(), y="c", x="v", color="g", orientation="h"
        ).update_layout(barnorm="percent")
        assert values(fig, "x") == [[75.0, 25.0], [25.0, 75.0]]

    def test_a_horizontal_bar_leaves_its_categories_alone(self):
        fig = px.bar(
            frame(), y="c", x="v", color="g", orientation="h"
        ).update_layout(barnorm="percent")
        assert values(fig, "y") == [["a", "b"], ["a", "b"]]

    def test_an_unrecognised_barnorm_changes_nothing(self):
        fig = px.bar(frame(), x="c", y="v", color="g").update_layout(barnorm="")
        assert values(fig) == [[3, 2], [1, 6]]


class TestDodgedIsLeftAlone:
    """A degenerate combination, pinned rather than half-handled."""

    def test_a_dodged_barnorm_keeps_its_counts(self):
        # `barmode="group"` makes every bar its own stack, so plotly draws
        # all four at 100% -- measured, every `s` came back 100. The layer
        # is typed `dodged_bar`, which claims no normalisation, so the type
        # and the values do not contradict each other the way #409 describes.
        #
        # Emitting four 100s would be faithful to the drawn geometry and
        # useless to a reader; emitting the counts keeps the information and
        # matches the announced type. Neither is fully right, which is why
        # this is pinned rather than fixed here.
        fig = px.bar(
            frame(), x="c", y="v", color="g", barmode="group"
        ).update_layout(barnorm="percent")
        assert only_layer(fig)["type"] == PlotType.DODGED.value
        assert values(fig) == [[3, 2], [1, 6]]


class TestTheEmittedHistogramLayer:
    def bins(self, **layout):
        fig = go.Figure(
            [
                go.Histogram(
                    x=[1, 1, 1, 2, 2], name="x", xbins=dict(start=0, end=4, size=1)
                ),
                go.Histogram(
                    x=[1, 2, 2, 2, 2], name="y", xbins=dict(start=0, end=4, size=1)
                ),
            ]
        )
        return fig.update_layout(barmode="stack", **layout)

    def test_the_shares_match_the_drawn_bars(self):
        got = values(self.bins(barnorm="percent"))
        assert got[0] == pytest.approx([75.0, 100 / 3])
        assert got[1] == pytest.approx([25.0, 200 / 3])

    def test_without_barnorm_the_counts_stay(self):
        assert values(self.bins()) == [[3, 2], [1, 4]]

    def test_an_empty_bin_between_two_full_ones_is_a_gap(self):
        # Measured: plotly keeps the bin's `x` and leaves `s` null, because
        # the share would be 0/0. The bin count does not change.
        fig = go.Figure(
            [
                go.Histogram(
                    x=[1, 1, 3], name="x", xbins=dict(start=0, end=5, size=1)
                ),
                go.Histogram(
                    x=[1, 3, 3], name="y", xbins=dict(start=0, end=5, size=1)
                ),
            ]
        ).update_layout(barmode="stack", barnorm="percent")
        got = values(fig)
        assert [len(series) for series in got] == [3, 3]
        assert got[0][1] is None and got[1][1] is None
        assert got[0] == pytest.approx([200 / 3, None, 100 / 3], nan_ok=True)

    def uneven(self, histnorm=None, barnorm="percent"):
        """Series of six and three observations, so `histnorm` scales them by
        different factors and the composition order is actually visible.

        With two equal-sized series it is not: `percent` divides each by its
        own total, those totals agree, and the shares come out the same
        whichever order the two are applied in. That degenerate case is why
        this needs its own figure.
        """
        kw = dict(xbins=dict(start=0, end=4, size=1))
        low = go.Histogram(x=[1, 1, 1, 1, 2, 2], name="x", **kw)
        high = go.Histogram(x=[1, 2, 2], name="y", **kw)
        if histnorm:
            low.histnorm = histnorm
            high.histnorm = histnorm
        figure = go.Figure([low, high]).update_layout(barmode="stack")
        return figure.update_layout(barnorm=barnorm) if barnorm else figure

    def test_barnorm_rescales_the_histnormed_values_not_the_raw_counts(self):
        # Measured. Raw counts are 4,2 and 1,2, so `barnorm` alone gives
        # 80/20 and 50/50. Under `histnorm="percent"` the same figure draws
        # 66.7/33.3 and 33.3/66.7 -- which is `barnorm` applied to the
        # histnormed values. Were it applied to the counts, `histnorm` could
        # not change the answer at all.
        assert values(self.uneven())[0] == pytest.approx([80.0, 50.0])

        composed = values(self.uneven(histnorm="percent"))
        assert composed[0] == pytest.approx([200 / 3, 100 / 3])
        assert composed[1] == pytest.approx([100 / 3, 200 / 3])

    @pytest.mark.parametrize("histnorm", ["percent", "probability"])
    def test_the_share_does_not_depend_on_which_histnorm(self, histnorm):
        # Both scale a series by its own total, differing only in the factor,
        # so once each position is rescaled to a common total the shares
        # coincide. Measured for both.
        got = values(self.uneven(histnorm=histnorm))
        assert got[0] == pytest.approx([200 / 3, 100 / 3])

    def test_the_bar_and_histogram_paths_agree(self):
        # #409 covers both together because `PlotlyGroupedHistogramPlot`
        # matched `PlotlyGroupedBarPlot` on purpose. Same underlying tallies
        # drawn both ways must produce the same shares.
        as_bars = px.bar(
            pd.DataFrame(
                {
                    "c": [1.5, 1.5, 2.5, 2.5],
                    "g": ["x", "y", "x", "y"],
                    "v": [3, 1, 2, 4],
                }
            ),
            x="c",
            y="v",
            color="g",
        ).update_layout(barnorm="percent")
        from_bins = values(self.bins(barnorm="percent"))
        for bar_series, bin_series in zip(values(as_bars), from_bins):
            assert bar_series == pytest.approx(bin_series)

"""Stacked plotly histograms were read as independent distributions (#394).

`_extract_plots` collected `bar` traces for merging and left `histogram`
traces to the factory, one layer each. So every multi-series histogram --
`px.histogram(color=...)` is the ordinary way to draw one, and plotly's
default `barmode` stacks -- was announced as several separate distributions,
with nothing saying the bars stack or that `barnorm` had rescaled them.

The bins were wrong as well, which the issue did not cover and which is worse
than the missing relationship. Plotly bins a group **jointly**: one grid from
every trace's values together. Binned per trace, `px.histogram(frame, x="v",
color="h")` over two well-separated samples announced the first series as 13
bins of width 0.2 where the chart draws 4 of width 1.

The joint grid needed no new arithmetic. Feeding the existing `autoBin` port
the union returns plotly's own `size=1, start=-2, end=12` for that figure --
so what the issue called "inference rather than transcription" was
transcription with the wrong input.

Merging also settles the highlight. Left separate, every histogram in a
subplot emitted the identical selector -- `.trace.bars .point > path` matches
every bar in the panel -- so each layer highlighted its neighbours' bars too.
One layer holding every series is what that selector already described.

Values under `barnorm` stay raw here, matching what the merged bar path has
emitted since #338/#393. Plotly draws shares, and both paths diverge from it
identically; that is #409, filed to cover the two together rather than fixed
for histograms alone.

Every expectation is `gd.calcdata[i][j]` after `Plotly.newPlot` in Chromium,
compared per series.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.grouped_histogram import group_bin_spec  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Two well-separated samples: binned apart they get very different widths,
#: binned together they get plotly's shared grid.
NARROW = [
    -0.1391, -0.7975, 0.5219, 0.2044, -0.1122, -0.2371, 0.1016, -0.4166,
    0.3011, -0.0559, 0.6082, -0.3141, 0.0776, -0.2404, 0.4448, 0.1958,
]  # fmt: skip
WIDE = [
    7.2, 4.9, 6.1, 8.8, 5.4, 9.6, 3.7, 6.8,
    5.1, 7.9, 4.2, 8.1, 6.4, 5.8, 9.1, 3.3,
]  # fmt: skip

SMALL_A = [0.1, 0.5, 1.2, 1.8, 2.4]
SMALL_B = [2.1, 2.9, 3.5, 4.2, 4.8]


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"v": NARROW + WIDE, "h": ["x"] * len(NARROW) + ["y"] * len(WIDE)}
    )


def only_layer(fig) -> dict:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]


def layers(fig) -> list[dict]:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


def stacked(*samples, **layout) -> go.Figure:
    fig = go.Figure([go.Histogram(x=list(s)) for s in samples])
    return fig.update_layout(barmode="stack", **layout)


class TestTheGroupIsOneLayer:
    def test_a_default_multi_series_histogram_stacks(self):
        # Plotly's default `barmode` is `relative`, so this is what
        # `px.histogram(color=...)` produces without asking for anything.
        layer = only_layer(px.histogram(frame(), x="v", color="h"))
        assert layer["type"] == PlotType.STACKED.value
        assert len(layer["data"]) == 2

    def test_barnorm_says_the_stack_is_normalised(self):
        layer = only_layer(px.histogram(frame(), x="v", color="h", barnorm="percent"))
        assert layer["type"] == PlotType.NORMALIZED.value

    def test_barmode_group_dodges(self):
        layer = only_layer(px.histogram(frame(), x="v", color="h", barmode="group"))
        assert layer["type"] == PlotType.DODGED.value

    def test_overlay_stays_separate_layers(self):
        # Plotly draws overlaid bars over one another rather than joining
        # them, so separate layers is the honest reading -- the same rule the
        # bar path follows.
        emitted = layers(px.histogram(frame(), x="v", color="h", barmode="overlay"))
        assert [layer["type"] for layer in emitted] == [
            PlotType.HIST.value,
            PlotType.HIST.value,
        ]

    def test_a_lone_histogram_is_untouched(self):
        layer = only_layer(px.histogram(frame(), x="v"))
        assert layer["type"] == PlotType.HIST.value

    def test_each_series_carries_its_own_name(self):
        layer = only_layer(px.histogram(frame(), x="v", color="h"))
        names = [{point["z"] for point in series} for series in layer["data"]]
        assert names == [{"x"}, {"y"}]


class TestJointBinning:
    def test_the_group_shares_one_grid(self):
        # The defect the issue did not name. Binned separately these two get
        # widths of 0.2 and 1; plotly bins them together at width 1.
        layer = only_layer(px.histogram(frame(), x="v", color="h"))
        centres = sorted({point["x"] for series in layer["data"] for point in series})
        # Every bin centre from *either* series sits on one lattice. Asserted
        # as a lattice rather than a fixed width so the test says "one grid"
        # rather than pinning whichever width autobin happens to pick.
        width = min(round(b - a, 9) for a, b in zip(centres, centres[1:]))
        offsets = {round((c - centres[0]) % width, 6) for c in centres}
        assert offsets == {0.0}

    def test_a_separately_binned_series_would_have_more_bins(self):
        # Guards the assertion above against passing for the wrong reason: on
        # its own the narrow sample really does get a much finer grid, so the
        # joint grid is doing work rather than coinciding.
        alone = only_layer(px.histogram(pd.DataFrame({"v": NARROW}), x="v"))
        grouped = only_layer(px.histogram(frame(), x="v", color="h"))
        assert len(alone["data"]) > len(grouped["data"][0])

    def test_every_series_is_binned_on_the_same_edges(self):
        layer = only_layer(stacked(SMALL_A, SMALL_B))
        first, second = layer["data"]
        # The two series overlap at one bin centre, which they can only do if
        # they were binned on a shared grid.
        assert {p["x"] for p in first} & {p["x"] for p in second}

    def test_a_third_trace_joins_the_same_grid(self):
        layer = only_layer(stacked(SMALL_A, SMALL_B, [1.1, 3.3]))
        assert len(layer["data"]) == 3

    def test_a_trace_with_nothing_in_it_keeps_its_place(self):
        # The series' names have to stay paired with their data, so an empty
        # trace holds its slot rather than shifting every later series' name
        # onto the wrong values.
        layer = only_layer(stacked(SMALL_A, []))
        assert len(layer["data"]) == 2
        assert layer["data"][1] == []


class TestTheGroupCountsTheWayASingleTraceDoes:
    """Both counting paths in this file read the bins the same way.

    A grouped layer counts with `bincount` over the shared assignment rather
    than with `np.histogram`, which closes its final bin. The two disagreed
    about a value sitting exactly on a shared window's `end`: `np.histogram`
    folded it into the last bin and the assignment dropped it, and which one
    applied was decided by the `histfunc` -- the default `count` took one path
    and an `avg` the other, in the same layer.
    """

    WINDOW = dict(start=0, end=6, size=2)

    def test_a_value_on_the_shared_end_is_dropped(self):
        """Measured: plotly draws the top bin holding two, not three.

        The six samples run 1 .. 6 and the window closes at 6, so the sample
        *at* 6 is outside every bin plotly made -- the same reading a single
        trace has had since #650.
        """
        figure = go.Figure(
            [
                go.Histogram(x=[1, 2, 3, 4, 5, 6], xbins=self.WINDOW),
                go.Histogram(x=[1, 2]),
            ]
        )

        first, second = only_layer(figure)["data"]

        assert [point["y"] for point in first] == [1, 2, 2]
        assert [point["y"] for point in second] == [1, 1]

    def test_an_aggregating_histfunc_agrees_with_the_count(self):
        """The path that was already right, asserted beside the one that was not.

        `avg` has always gone through the shared assignment, so it dropped the
        boundary sample while the count folded it in. Both drop it now, and
        this says so rather than leaving the pairing to be re-derived.
        """
        figure = go.Figure(
            [
                go.Histogram(
                    x=[1, 2, 3, 4, 5, 6],
                    y=[1, 1, 1, 1, 1, 99],
                    histfunc="avg",
                    xbins=self.WINDOW,
                ),
                go.Histogram(x=[1, 2], y=[1, 1], histfunc="avg"),
            ]
        )

        first, _ = only_layer(figure)["data"]

        # The 99 rides on the sample at 6, so an average that folded it in
        # would be 50 rather than 1.
        assert [point["y"] for point in first] == [1, 1, 1]


class TestGroupBinSpec:
    def test_a_spec_on_any_trace_governs_the_group(self):
        # Not "the first trace's spec". Plotly resolves a `size` given on the
        # *second* trace onto both, and the pair bins at that width rather
        # than the one they would autobin to.
        traces = [
            {"type": "histogram", "x": SMALL_A},
            {"type": "histogram", "x": SMALL_B, "xbins": {"size": 3}},
        ]
        bins, nbins = group_bin_spec(traces, "x")
        assert bins == {"size": 3}
        assert nbins is None

    def test_the_first_supplied_spec_wins(self):
        traces = [
            {"type": "histogram", "x": SMALL_A, "xbins": {"size": 2}},
            {"type": "histogram", "x": SMALL_B, "xbins": {"size": 3}},
        ]
        assert group_bin_spec(traces, "x")[0] == {"size": 2}

    def test_no_spec_anywhere_yields_nothing(self):
        traces = [
            {"type": "histogram", "x": SMALL_A},
            {"type": "histogram", "x": SMALL_B},
        ]
        assert group_bin_spec(traces, "x") == (None, None)

    def test_it_reads_the_binned_axis(self):
        traces = [{"type": "histogram", "y": SMALL_A, "ybins": {"size": 3}}]
        assert group_bin_spec(traces, "y")[0] == {"size": 3}
        assert group_bin_spec(traces, "x")[0] is None

    def test_the_spec_reaches_the_emitted_bins(self):
        wide = only_layer(
            go.Figure(
                [
                    go.Histogram(x=SMALL_A),
                    go.Histogram(x=SMALL_B, xbins=dict(size=3)),
                ]
            ).update_layout(barmode="stack")
        )
        autobinned = only_layer(stacked(SMALL_A, SMALL_B))
        assert len(wide["data"][0]) < len(autobinned["data"][0])


class TestOrientation:
    def test_a_horizontal_group_says_so(self):
        layer = only_layer(px.histogram(frame(), y="v", color="h"))
        assert layer["orientation"] == "horz"
        assert layer["type"] == PlotType.STACKED.value

    def test_a_vertical_group_says_so(self):
        layer = only_layer(px.histogram(frame(), x="v", color="h"))
        assert layer["orientation"] == "vert"

    def test_both_orientations_describe_the_same_sample(self):
        upright = only_layer(px.histogram(frame(), x="v", color="h"))
        sideways = only_layer(px.histogram(frame(), y="v", color="h"))
        assert [len(series) for series in sideways["data"]] == [
            len(series) for series in upright["data"]
        ]


class TestCategoricalGroupDeclines:
    def test_it_is_left_to_the_factory_one_trace_at_a_time(self):
        # Plotly draws a categorical histogram as a count bar chart rather
        # than binning it, which is a different layer shape. Half-describing
        # it as a binned stack would be worse than the separate layers.
        cats = pd.DataFrame(
            {"g": list("abc") * 6, "h": ["x", "y"] * 9},
        )
        emitted = layers(px.histogram(cats, x="g", color="h"))
        assert len(emitted) == 2
        assert all(layer["type"] == PlotType.BAR.value for layer in emitted)


class TestBarnormValuesStayRaw:
    """Now the shares, matching the bar path -- #409, which this pinned."""

    def test_the_values_are_the_shares_rather_than_the_counts(self):
        layer = only_layer(stacked(SMALL_A, SMALL_B, barnorm="percent"))
        first = [point["y"] for point in layer["data"][0]]
        # Plotly draws 100 and 25 for these; the counts were 4 and 1. This
        # test previously asserted the counts, to pin the divergence until
        # #409 was taken.
        assert first == [100.0, 25.0]

    def test_the_type_still_reports_the_normalisation(self):
        layer = only_layer(stacked(SMALL_A, SMALL_B, barnorm="percent"))
        assert layer["type"] == PlotType.NORMALIZED.value

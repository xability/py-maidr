"""A plotly histogram's ``histnorm`` was ignored, so a percent axis read in
counts (#404).

`histnorm` decides what a bar *measures*. `_extract_plot_data` called
`np.histogram`, which returns counts, and never read the attribute -- so a
`px.histogram(histnorm="percent")` layer carried an axis labelled **percent**
and a first value of **2**, where plotly draws **3.33**.

The label was right: it comes from `layout`, which plotly express fills in
from `histnorm`. Only the values were untransformed, so the two halves of one
layer disagreed with nothing marking which to trust. A reader working from the
announced numbers concludes the first bin holds 2% where it holds 3.33%, and
finds the bars do not sum to 100 either.

The denominator is the part worth being careful about. It is the total of the
**bars' own values**, not the number of observations. Those coincide under the
default `histfunc="count"` -- the counts sum to `n` -- which is exactly why
the wrong reading survives the obvious test. `histfunc="sum"` and
`histfunc="avg"` over the same data return *identical* output under
`histnorm="percent"`, which is impossible if the denominator is the sample
size and required if it is their own total. `apply_histnorm` therefore takes
the values it is handed rather than recomputing from the sample, so the
aggregate flows through unchanged when #405 lands.

Every expectation is `gd.calcdata[0][i].s` after `Plotly.newPlot` in Chromium.
All 38 figure shapes measured that way now agree elementwise, on both
orientations.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.histogram import apply_histnorm  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: 60 values in [-1.2, 1.2]-ish, autobinned by plotly to width 0.2.
SAMPLE = [
    0.8164, -1.0223, 0.1672, -0.2271, -0.1810, -0.0862,
    -0.8080, -0.0928, -0.3461, 1.3292, 0.0903, -0.1410,
    -0.1125, -0.2672, -0.4221, -0.1563, 0.1928, -0.0954,
    0.3831, -0.0799, 0.0097, 0.6183, 0.2180, -0.2021,
    -0.0731, 0.2162, 0.7740, -0.1078, -0.0974, 0.4009,
    -0.3546, -0.1167, 0.3530, 0.2322, 0.0366, 0.2680,
    -1.1313, 0.4085, -0.3838, -0.6674, 0.1106, 0.2802,
    -0.1779, -0.4306, 0.0104, -0.0211, 0.5622, 0.2990,
    0.0775, 0.4446, -0.0822, -0.3704, 0.2336, 0.2330,
    -0.0859, -0.3131, 0.0917, -0.9976, 0.2760, 0.1966,
]  # fmt: skip


def values_of(fig) -> list[float]:
    """The announced bar value per bin, off whichever axis holds it."""
    layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
    key = "x" if layer.get("orientation") == "horz" else "y"
    return [round(float(d[key]), 6) for d in layer["data"]]


class TestApplyHistnorm:
    """The transform in isolation, against the closed forms."""

    VALUES = np.array([2.0, 3.0, 5.0])
    WIDTHS = np.array([0.5, 0.5, 0.5])

    @pytest.mark.parametrize(
        ("histnorm", "expected"),
        [
            (None, [2.0, 3.0, 5.0]),
            ("", [2.0, 3.0, 5.0]),
            ("percent", [20.0, 30.0, 50.0]),
            ("probability", [0.2, 0.3, 0.5]),
            ("density", [4.0, 6.0, 10.0]),
            ("probability density", [0.4, 0.6, 1.0]),
            # Plotly leaves an attribute it does not recognise alone rather
            # than erroring, and a layer that quietly rescaled by some other
            # rule would be worse than one that did not rescale at all.
            ("nonsense", [2.0, 3.0, 5.0]),
        ],
    )
    def test_matches_the_closed_form(self, histnorm, expected):
        got = apply_histnorm(self.VALUES.copy(), self.WIDTHS, histnorm)
        assert list(got) == pytest.approx(expected)

    def test_the_denominator_is_the_values_own_total(self):
        # The distinction the default `histfunc` hides. Scaling every value by
        # a constant must leave `percent` unchanged, because the total scales
        # with it -- which is what makes `sum` and `avg` agree in plotly, and
        # what a sample-size denominator could not do.
        base = apply_histnorm(self.VALUES.copy(), self.WIDTHS, "percent")
        tripled = apply_histnorm(self.VALUES * 3, self.WIDTHS, "percent")
        assert list(tripled) == pytest.approx(list(base))

    def test_density_ignores_the_total_and_reads_the_width(self):
        # `density` is the one form with no total in it, so the same check
        # must come out the other way round.
        base = apply_histnorm(self.VALUES.copy(), self.WIDTHS, "density")
        tripled = apply_histnorm(self.VALUES * 3, self.WIDTHS, "density")
        assert list(tripled) == pytest.approx([v * 3 for v in base])

        wider = apply_histnorm(self.VALUES.copy(), self.WIDTHS * 2, "density")
        assert list(wider) == pytest.approx([v / 2 for v in base])

    def test_an_all_empty_trace_does_not_divide_by_zero(self):
        empty = np.zeros(3)
        got = apply_histnorm(empty, self.WIDTHS, "percent")
        assert list(got) == [0.0, 0.0, 0.0]


class TestEmittedValues:
    """End to end, against what Plotly.js drew for the same figure."""

    @pytest.mark.parametrize(
        ("histnorm", "first_five"),
        [
            (None, [2, 2, 1, 2, 8]),
            ("percent", [3.333333, 3.333333, 1.666667, 3.333333, 13.333333]),
            ("probability", [0.033333, 0.033333, 0.016667, 0.033333, 0.133333]),
            ("density", [10.0, 10.0, 5.0, 10.0, 40.0]),
            (
                "probability density",
                [0.166667, 0.166667, 0.083333, 0.166667, 0.666667],
            ),
        ],
    )
    def test_every_mode_matches_plotly(self, histnorm, first_five):
        got = values_of(go.Figure([go.Histogram(x=SAMPLE, histnorm=histnorm)]))
        assert got[:5] == pytest.approx(first_five, abs=1e-6)

    def test_percent_sums_to_a_hundred(self):
        # Not a plotly comparison but a property the announcement has to have:
        # a reader told these are percentages will add them up.
        got = values_of(go.Figure([go.Histogram(x=SAMPLE, histnorm="percent")]))
        assert sum(got) == pytest.approx(100.0)

    def test_probability_sums_to_one(self):
        got = values_of(go.Figure([go.Histogram(x=SAMPLE, histnorm="probability")]))
        assert sum(got) == pytest.approx(1.0)

    def test_the_bar_extent_moves_with_the_value(self):
        # `yMax` carries the bar's height, so leaving it on the raw count
        # would have the announced extent disagree with the announced value
        # inside one point.
        fig = go.Figure([go.Histogram(x=SAMPLE, histnorm="percent")])
        layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
        for point in layer["data"]:
            assert point["yMax"] == point["y"]
            assert point["yMin"] == 0

    def test_a_horizontal_trace_is_rescaled_the_same_way(self):
        upright = values_of(go.Figure([go.Histogram(x=SAMPLE, histnorm="percent")]))
        sideways = values_of(go.Figure([go.Histogram(y=SAMPLE, histnorm="percent")]))
        assert sideways == pytest.approx(upright)

    def test_density_follows_a_wider_explicit_bin(self):
        # `density` divides by the bin width, so it is the one mode an
        # explicit `xbins` changes the answer for. Both of these are plotly's.
        narrow = values_of(go.Figure([go.Histogram(x=SAMPLE, histnorm="density")]))
        wide = values_of(
            go.Figure([go.Histogram(x=SAMPLE, xbins=dict(size=2), histnorm="density")])
        )
        assert max(wide) < max(narrow)

    def test_an_unset_histnorm_still_announces_whole_counts(self):
        # A count is an integer and reads as one. Turning every bar into a
        # float to accommodate the rescaled modes would change every existing
        # histogram's announcement for nothing.
        fig = go.Figure([go.Histogram(x=SAMPLE)])
        layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
        assert all(isinstance(d["y"], int) for d in layer["data"])

    def test_a_rescaled_value_is_not_rounded_to_look_like_a_count(self):
        fig = go.Figure([go.Histogram(x=SAMPLE, histnorm="percent")])
        layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
        assert any(not float(d["y"]).is_integer() for d in layer["data"])


class TestTrimmingIsUnaffected:
    """#402's trim and this rescaling have to stay independent."""

    def test_an_empty_edge_bin_is_still_trimmed_under_histnorm(self):
        fig = go.Figure(
            [
                go.Histogram(
                    x=[-2.8, -1.2, 0.3, 1.1, 2.4, 3.3],
                    xbins=dict(start=-10, end=10, size=1),
                    histnorm="percent",
                )
            ]
        )
        # Seven bins, as without the rescaling: every mode maps zero to zero,
        # so which bins exist cannot depend on it.
        assert len(values_of(fig)) == 7

    def test_an_interior_empty_bin_survives_as_a_zero(self):
        fig = go.Figure(
            [
                go.Histogram(
                    x=[0.2, 0.6, 1.4, 2.9, 9.1, 9.8, 10.4, 11.7],
                    xbins=dict(size=2),
                    histnorm="percent",
                )
            ]
        )
        got = values_of(fig)
        assert 0.0 in got[1:-1]

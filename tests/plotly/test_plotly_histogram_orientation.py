"""A plotly histogram binned on y announced nothing at all (#401).

A histogram bins one axis and counts into the other. ``PlotlyHistogramPlot``
read the sample from ``x`` and gave up when it was absent, so every horizontal
histogram emitted a layer with an empty ``data`` list -- correctly typed, both
axes correctly named from ``layout``, and nothing in it to navigate. Nothing
errored, and nothing in the schema's metadata showed the emptiness, so it read
as a histogram of nothing rather than a histogram that failed to read.

Which axis is binned is not always stated. ``px.histogram(y=...)`` writes
``orientation`` onto the trace; ``go.Histogram(y=...)`` writes nothing and
leaves Plotly.js to infer it. The rule in ``binned_axis`` is plotly's own,
taken from ``gd._fullData[i].orientation`` read back out of Chromium rather
than from the documentation, and the case that fixes the precedence is
``go.Histogram(x=v, orientation="h")``: plotly honours the attribute and bins
the *absent* ``y``, drawing an empty trace rather than falling back to ``x``.

The bin spec follows the binned axis too, and plotly discards the other axis's
spec outright rather than falling back to it. Measured both ways: a horizontal
trace given ``xbins`` autobins exactly as if none were given, and a vertical
one given ``ybins`` does the same.

Every expectation below was checked against what Plotly.js drew for the same
figure -- ``gd.calcdata[0]`` after ``Plotly.newPlot`` in Chromium, where a bin
is ``[p - size/2, p + size/2)`` with ``size`` from ``gd._fullData[0]``. Across
eighteen figure shapes the emitted bins now agree elementwise, bin bounds and
counts alike, on both orientations. Four shapes still disagree, all of them on
the explicit-bin-size path and all of them identically on ``x`` and ``y``: see
#402, which is orientation-independent and predates this.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.histogram import binned_axis  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: A fixed normal sample. Rounded so the figure JSON handed to the browser and
#: the array handed to numpy hold the same values to the last bit.
SAMPLE = [round(float(v), 4) for v in np.random.default_rng(3).normal(0, 1, 60)]


def only_layer(fig) -> dict:
    """The single layer of a single-subplot figure."""
    schema = PlotlyMaidr(fig)._flatten_maidr()
    return schema["subplots"][0][0]["layers"][0]


def bins(layer: dict) -> list[tuple[float, float, int]]:
    """``(low, high, count)`` per bin, read off whichever axis was binned."""
    horizontal = layer.get("orientation") == "horz"
    low, high, count = (
        ("yMin", "yMax", "x") if horizontal else ("xMin", "xMax", "y")
    )
    return [(d[low], d[high], d[count]) for d in layer["data"]]


class TestBinnedAxis:
    """The x-or-y decision, against Plotly.js's own resolved orientation."""

    @pytest.mark.parametrize(
        ("trace", "expected"),
        [
            ({"type": "histogram", "x": SAMPLE}, "x"),
            ({"type": "histogram", "y": SAMPLE}, "y"),
            ({"type": "histogram", "y": SAMPLE, "orientation": "h"}, "y"),
            ({"type": "histogram", "x": SAMPLE, "orientation": "v"}, "x"),
            # Both arrays present: plotly bins x and aggregates y, whichever
            # of the two happens to be the categorical one.
            ({"type": "histogram", "x": SAMPLE, "y": SAMPLE}, "x"),
            # An explicit orientation wins over the arrays. Plotly bins the
            # absent axis and draws an empty trace rather than falling back.
            ({"type": "histogram", "x": SAMPLE, "orientation": "h"}, "y"),
        ],
    )
    def test_matches_plotlys_resolved_orientation(self, trace, expected):
        assert binned_axis(trace) == expected


class TestHorizontalHistogram:
    """The defect itself: bins on y, counts on x."""

    def test_a_horizontal_histogram_is_no_longer_empty(self):
        fig = go.Figure([go.Histogram(y=SAMPLE)])
        layer = only_layer(fig)

        # The count is what plotly's calcdata holds for the same figure. An
        # assertion on `len(data) > 0` alone would pass on any binning at all,
        # including the per-trace one #394 is about.
        assert len(layer["data"]) == 13
        assert layer["orientation"] == "horz"

    def test_the_bins_run_along_the_axis_they_are_drawn_on(self):
        fig = go.Figure([go.Histogram(y=SAMPLE)])
        layer = only_layer(fig)
        first = layer["data"][0]

        # `yMin`/`yMax` bound the bin and `x` carries the count -- the reverse
        # of the vertical case. Emitting the bin on `x` would have the reader
        # told the count where the range belongs, which the core cannot detect
        # because both are numbers.
        assert (first["yMin"], first["yMax"]) == (-3.0, -2.5)
        assert first["x"] == first["xMax"] == 2
        assert first["xMin"] == 0

    def test_the_two_orientations_describe_the_same_sample(self):
        # Same numbers, same bins, transposed. Anything that read one axis for
        # part of the work and the other for the rest would show up here.
        vertical = bins(only_layer(go.Figure([go.Histogram(x=SAMPLE)])))
        horizontal = bins(only_layer(go.Figure([go.Histogram(y=SAMPLE)])))
        assert horizontal == vertical

    def test_plotly_express_horizontal_is_read_too(self):
        import pandas as pd

        fig = px.histogram(pd.DataFrame({"v": SAMPLE}), y="v")
        layer = only_layer(fig)

        assert layer["orientation"] == "horz"
        assert bins(layer) == bins(
            only_layer(go.Figure([go.Histogram(x=SAMPLE)]))
        )

    def test_a_vertical_histogram_still_says_so(self):
        # `orientation` is emitted either way rather than left off for the
        # default, so a reader of the schema never has to infer it.
        assert only_layer(go.Figure([go.Histogram(x=SAMPLE)]))["orientation"] == (
            "vert"
        )


class TestBinSpecFollowsTheBinnedAxis:
    """``ybins``/``nbinsy`` govern a horizontal trace; ``xbins``/``nbinsx`` do not."""

    def test_ybins_is_honoured_on_a_horizontal_trace(self):
        fig = go.Figure([go.Histogram(y=SAMPLE, ybins=dict(size=2))])
        # plotly's own bins for this figure, its trailing empty bin aside
        # (#402): four bins of width 2 starting at -4.
        assert bins(only_layer(fig))[:4] == [
            (-4.0, -2.0, 4),
            (-2.0, 0.0, 27),
            (0.0, 2.0, 27),
            (2.0, 4.0, 2),
        ]

    def test_nbinsy_is_honoured_on_a_horizontal_trace(self):
        fig = go.Figure([go.Histogram(y=SAMPLE, nbinsy=4)])
        assert bins(only_layer(fig)) == [
            (-4.0, -2.0, 4),
            (-2.0, 0.0, 27),
            (0.0, 2.0, 27),
            (2.0, 4.0, 2),
        ]

    @pytest.mark.parametrize(
        "ignored",
        [
            pytest.param({"xbins": dict(size=2)}, id="xbins"),
            pytest.param({"nbinsx": 4}, id="nbinsx"),
        ],
    )
    def test_the_other_axiss_spec_is_discarded_the_way_plotly_discards_it(
        self, ignored
    ):
        # Plotly does not fall back to the other axis: it autobins. Honouring
        # the spec here would announce four wide bins for a chart drawn with
        # thirteen narrow ones.
        autobinned = bins(only_layer(go.Figure([go.Histogram(y=SAMPLE)])))
        with_spec = bins(only_layer(go.Figure([go.Histogram(y=SAMPLE, **ignored)])))

        assert with_spec == autobinned
        assert len(autobinned) == 13

    def test_ybins_on_a_vertical_trace_is_discarded_too(self):
        autobinned = bins(only_layer(go.Figure([go.Histogram(x=SAMPLE)])))
        with_spec = bins(
            only_layer(go.Figure([go.Histogram(x=SAMPLE, ybins=dict(size=2))]))
        )
        assert with_spec == autobinned


class TestCategoricalHorizontal:
    """A horizontal count bar chart keeps its labels on the binned axis."""

    def test_categories_land_on_the_axis_they_are_drawn_on(self):
        labels = list("abcabca")
        layer = only_layer(go.Figure([go.Histogram(y=labels)]))

        # Plotly draws string data as a count bar chart, and the extractor
        # switches the schema type to match. The categories still belong on
        # the binned axis: on `x` they would be announced as counts, and the
        # counts as labels.
        assert layer["type"] == PlotType.BAR.value
        assert layer["orientation"] == "horz"
        assert layer["data"] == [
            {"y": "a", "x": 3},
            {"y": "b", "x": 2},
            {"y": "c", "x": 2},
        ]

    def test_a_vertical_count_chart_is_unchanged(self):
        labels = list("abcabca")
        layer = only_layer(go.Figure([go.Histogram(x=labels)]))
        assert layer["data"] == [
            {"x": "a", "y": 3},
            {"x": "b", "y": 2},
            {"x": "c", "y": 2},
        ]


class TestEmptyTrace:
    """An orientation with nothing on it still declines rather than guessing."""

    def test_a_trace_with_neither_array_yields_no_data(self):
        assert only_layer(go.Figure([go.Histogram()]))["data"] == []

    def test_an_explicit_orientation_pointing_at_an_absent_axis_yields_no_data(
        self,
    ):
        # Plotly draws essentially nothing for this figure -- one empty entry
        # in calcdata -- so announcing the `x` sample instead would describe a
        # distribution the chart does not show.
        fig = go.Figure([go.Histogram(x=SAMPLE, orientation="h")])
        assert only_layer(fig)["data"] == []

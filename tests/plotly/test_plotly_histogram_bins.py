"""A plotly histogram announced bins the chart never drew (#402).

Three defects, all on the explicit-bin-size path, all identical on both
orientations. An empty bin is not a harmless extra row: plotly draws no
``.point`` element for one, and the layer's selector resolves positionally, so
a phantom bin shifts the highlight of every bin after it. A leading phantom
shifts all of them.

1. **Empty edge bins were emitted.** Plotly emits bins from the first that
   holds an observation to the last, and keeps every empty bin between them.
   It does not emit the empty ones outside that span.

2. **The end fallback overshot by a bin.** ``ceil(max / size) * size + size``
   put an extra bin past the data, where plotly stops at the data. The trim in
   (1) subsumes it, but the arithmetic was also describing a grid plotly does
   not use, and the boundary case below needs it stated correctly.

3. **The bin start skipped plotly's anti-clustering shift.** Only the autobin
   path ran ``_auto_shift_bins``; an explicit ``size`` took a bare round
   multiple. So ``go.Histogram(x=[0, 1, 2, 3, 4], xbins=dict(size=2))`` was
   announced from 0 where plotly draws from -0.5.

The rule behind (1) took a figure narrower than its data on *both* sides to
pin down. The reading it replaced -- "span the data, clamped to the caller's
``[start, end)``" -- fits every wider window and predicts one bin too many
there, because clamping keeps a leading bin that nothing landed in. Plotly
discards the out-of-window values rather than piling them into the edge bin.

Every expectation here is what Plotly.js drew for the same figure:
``gd.calcdata[0]`` after ``Plotly.newPlot`` in Chromium, a bin being
``[p - size/2, p + size/2)`` with ``size`` from ``gd._fullData[0]``. With
these fixes all 29 shapes measured that way agree elementwise, bin bounds and
counts alike, on both orientations -- up from 16 of 29.

That 16 is worth stating precisely, because the count of bins hides most of
it. Six of the thirteen disagreements emitted the *right number* of bins on
the *wrong grid*, so anything checking only the length would have called them
equal. The comparison is elementwise for that reason.
"""

from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.histogram import _auto_shift_bins, _occupied_span  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Spans a window given below in one test and above it in another.
NARROW = [-2.8, -1.2, 0.3, 1.1, 2.4, 3.3]

#: Two clusters with a hole between them, so interior empties have somewhere
#: to appear.
BIMODAL = [0.2, 0.6, 1.4, 2.9, 9.1, 9.8, 10.4, 11.7]


def bins(fig) -> list[tuple[float, float, int]]:
    """``(low, high, count)`` per emitted bin, off whichever axis was binned."""
    layer = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"][0]
    horizontal = layer.get("orientation") == "horz"
    low, high, count = ("yMin", "yMax", "x") if horizontal else ("xMin", "xMax", "y")
    return [(d[low], d[high], d[count]) for d in layer["data"]]


def layers(fig) -> list[dict]:
    """Every layer of a single-subplot figure, which may now be none."""
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


class TestOccupiedSpan:
    """The helper, in isolation."""

    @pytest.mark.parametrize(
        ("counts", "expected"),
        [
            ([1, 2, 3], (0, 2)),
            ([0, 2, 3], (1, 2)),
            ([1, 2, 0], (0, 1)),
            ([0, 0, 5, 0, 0], (2, 2)),
            # An interior run of empties is inside the span, not trimmed.
            ([4, 0, 0, 7], (0, 3)),
            ([0, 0, 0], (None, None)),
            ([], (None, None)),
        ],
    )
    def test_finds_the_first_and_last_occupied_bin(self, counts, expected):
        assert _occupied_span(np.array(counts, dtype=int)) == expected


class TestEmptyEdgeBinsAreTrimmed:
    def test_a_window_wider_than_the_data_emits_only_the_data(self):
        # Plotly's resolved spec keeps start=-10 and end=10, and draws seven
        # bins from -3 to 4. Emitting all twenty put thirteen phantom bins in
        # the layer, thirteen of them before the first real one.
        fig = go.Figure([go.Histogram(x=NARROW, xbins=dict(start=-10, end=10, size=1))])
        assert bins(fig) == [
            (-3.0, -2.0, 1),
            (-2.0, -1.0, 1),
            (-1.0, 0.0, 0),
            (0.0, 1.0, 1),
            (1.0, 2.0, 1),
            (2.0, 3.0, 1),
            (3.0, 4.0, 1),
        ]

    def test_a_window_narrower_on_both_sides_still_trims_its_leading_empty(self):
        # The case that settled the rule. Data exists below `start`, so
        # "clamp the span to the window" keeps bin (-1, 0); plotly drops it
        # because nothing landed *in* it -- the values below `start` are
        # discarded rather than piled into the first bin.
        fig = go.Figure([go.Histogram(x=NARROW, xbins=dict(start=-1, end=2, size=1))])
        assert bins(fig) == [(0.0, 1.0, 1), (1.0, 2.0, 1)]

    def test_an_interior_empty_bin_is_kept(self):
        # Trimming is not "drop every empty bin". A gap in the middle of the
        # distribution is a fact about the data and plotly draws the axis
        # across it, so it stays.
        fig = go.Figure([go.Histogram(x=BIMODAL, xbins=dict(size=2))])
        counts = [count for _, _, count in bins(fig)]
        assert 0 in counts[1:-1]
        assert counts[0] > 0 and counts[-1] > 0

    def test_the_same_trimming_happens_on_a_horizontal_trace(self):
        upright = bins(
            go.Figure([go.Histogram(x=NARROW, xbins=dict(start=-1, end=2, size=1))])
        )
        sideways = bins(
            go.Figure([go.Histogram(y=NARROW, ybins=dict(start=-1, end=2, size=1))])
        )
        assert sideways == upright


class TestDataOutsideAnExplicitWindow:
    """Already correct before this, and easy to break while fixing the rest."""

    @pytest.mark.parametrize(
        ("spec", "expected_span"),
        [
            # Data reaches 3.3, the window stops at 1: the values above are
            # dropped, not clipped into the last bin.
            (dict(start=-3, end=1, size=1), (-3.0, 1.0)),
            # ... and the same below.
            (dict(start=0, end=4, size=1), (0.0, 4.0)),
        ],
    )
    def test_values_beyond_the_window_are_dropped_rather_than_clipped(
        self, spec, expected_span
    ):
        emitted = bins(go.Figure([go.Histogram(x=NARROW, xbins=spec)]))
        assert (emitted[0][0], emitted[-1][1]) == expected_span
        # Nothing piled up: no bin holds more than the two values that fall in
        # it, so the discarded values did not land anywhere.
        assert sum(count for _, _, count in emitted) < len(NARROW)


class TestBinStartShift:
    """Plotly runs its anti-clustering shift for an explicit size too."""

    def test_integer_data_is_shifted_off_the_bin_edges(self):
        # Every value is an integer and would otherwise sit exactly on an
        # edge, so plotly moves the grid half a unit down. Announced from 0,
        # each value lands in a different bin than the one drawn around it.
        fig = go.Figure([go.Histogram(x=[0, 1, 2, 3, 4], xbins=dict(size=2))])
        assert bins(fig) == [(-0.5, 1.5, 2), (1.5, 3.5, 2), (3.5, 5.5, 1)]

    def test_the_shift_can_go_the_other_way(self):
        fig = go.Figure([go.Histogram(x=[-4, -3, 0, 1], xbins=dict(size=2))])
        assert bins(fig) == [(-4.5, -2.5, 2), (-2.5, -0.5, 0), (-0.5, 1.5, 2)]

    def test_a_value_clustering_on_an_edge_shifts_without_all_being_integers(self):
        # The other branch of the shift: not every value is an integer, but
        # one sits on an edge, which is enough for plotly to move the grid.
        fig = go.Figure([go.Histogram(x=[0.5, 1.5, 4.0], xbins=dict(size=2))])
        assert bins(fig) == [(-1.0, 1.0, 1), (1.0, 3.0, 1), (3.0, 5.0, 1)]

    def test_an_explicit_start_is_honoured_rather_than_shifted(self):
        # The shift only chooses a start; given one, plotly uses it verbatim.
        fig = go.Figure(
            [go.Histogram(x=[0, 1, 2, 3, 4], xbins=dict(start=0, end=6, size=2))]
        )
        assert bins(fig)[0][0] == 0.0

    def test_the_shift_applies_on_a_horizontal_trace_too(self):
        fig = go.Figure([go.Histogram(y=[0, 1, 2, 3, 4], ybins=dict(size=2))])
        assert bins(fig) == [(-0.5, 1.5, 2), (1.5, 3.5, 2), (3.5, 5.5, 1)]


class TestBothCallersSeedTheShiftEquivalently:
    """``_auto_shift_bins`` has two callers that seed it differently.

    The autobin path passes ``ceil(data_min / dtick) * dtick - dtick``; the
    explicit-size path passes ``floor(data_min / size) * size``. Those agree
    except when ``data_min`` is itself a multiple of the width, where they
    differ by exactly one bin — and the branches inside then correct both to
    the same start.

    That is a property of those branches, not of the seed arithmetic, so a
    refactor of the shift could break the coupling with nothing failing. This
    pins it instead of leaving it to be re-derived by hand.
    """

    SAMPLES = {
        "integers from zero": [0, 1, 2, 3, 4],
        "integers spanning zero": [-4, -3, 0, 1],
        "one value on an edge": [0.5, 1.5, 4.0],
        "min on a multiple": [2.0, 3.7, 5.1, 8.9],
        "every value a multiple": [0.0, 2.0, 4.0, 6.0],
        "negative multiples": [-6.0, -4.0, -2.0, 0.0],
        "barely any spread": [1.0, 1.0000001],
        "sub-unit": [0.001, 0.002, 0.004],
    }

    @pytest.mark.parametrize("label", sorted(SAMPLES))
    @pytest.mark.parametrize("width", [0.001, 0.5, 1, 2, 3, 5])
    def test_the_two_seeds_land_on_the_same_start(self, label, width):
        import math

        arr = np.array(self.SAMPLES[label], dtype=float)
        low, high = float(arr.min()), float(arr.max())

        from_explicit = _auto_shift_bins(
            math.floor(low / width) * width, arr, width, low, high
        )
        from_autobin = _auto_shift_bins(
            math.ceil(low / width) * width - width, arr, width, low, high
        )

        assert from_explicit == pytest.approx(from_autobin, abs=1e-12)


class TestNothingToAnnounce:
    def test_a_window_holding_no_data_forms_no_layer(self):
        # Every bin empty. Emitting them would announce a distribution made
        # entirely of gaps, none of which the chart draws an element for.
        #
        # This asserted `bins(fig) == []` until #636 -- an empty payload on a
        # layer that still shipped. The layer is now dropped outright, which
        # is the same judgement one step further: a cell holding no bins is a
        # cell the reader can tab into and find nothing in.
        fig = go.Figure([go.Histogram(x=NARROW, xbins=dict(start=20, end=24, size=1))])
        assert layers(fig) == []

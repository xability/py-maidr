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

import math
import warnings

import pytest

pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.histogram import (  # noqa: E402
    _auto_shift_bins,
    _occupied_span,
    _plotly_default_size0,
)
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
    """``_auto_shift_bins`` can be seeded two ways, and they agree.

    The seed can be written ``ceil(data_min / width) * width - width`` or
    ``floor(data_min / width) * width``. Those differ by exactly one bin when
    ``data_min`` is itself a multiple of the width — and the branches inside
    then correct both to the same start.

    That agreement is what let #650 fold the explicit-size and automatic
    paths into one, which had been the two callers seeding it differently.
    It is a property of those branches rather than of the seed arithmetic, so
    a refactor of the shift could break it with nothing else failing; this
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


def _shift_by_plotly_loop(
    bin_start: float,
    data: np.ndarray,
    dtick: float,
    data_min: float,
    data_max: float,
) -> float:
    """``_auto_shift_bins`` as it was before #701: plotly's loop, verbatim.

    Kept as the reference because it is the port that was measured against
    the browser. The numpy form is only right insofar as it agrees with this
    on every sample, so the comparison is exact rather than approximate.
    """
    edge_count = 0
    mid_count = 0
    int_count = 0

    def near_edge(v: float) -> bool:
        return (1 + (v - bin_start) * 100 / dtick) % 100 < 2

    for v in data:
        if v % 1 == 0:
            int_count += 1
        if near_edge(v):
            edge_count += 1
        if near_edge(v + dtick / 2):
            mid_count += 1

    n = len(data)
    if n == 0:
        return bin_start

    if int_count == n:
        if dtick < 1:
            return data_min - 0.5 * dtick
        else:
            shifted = bin_start - 0.5
            if shifted + dtick < data_min:
                shifted += dtick
            return shifted

    if mid_count < n * 0.1:
        if edge_count > n * 0.3 or near_edge(data_min) or near_edge(data_max):
            binshift = dtick / 2
            if bin_start + binshift < data_min:
                return bin_start + binshift
            else:
                return bin_start - binshift

    return bin_start


class TestTheCountsAreTakenInNumpy:
    """``_auto_shift_bins`` counts its samples elementwise, and exactly.

    The per-sample loop was most of a histogram's render at 50k samples
    (#701), so the three counts the branches consume are now numpy
    reductions. They are the same IEEE operations the loop performed, on
    the same ``np.float64`` values, so the start they choose is bit-identical
    -- which this pins, rather than approximates, against a copy of that
    loop over seeded samples of every shape the predicates react to: whole
    numbers, values rounded to a decimal or two, values sitting at an offset,
    values far below the width, and a ``nan``.
    """

    #: One draw of a few hundred samples per kind, seeded so a mismatch is
    #: reproducible.
    KINDS = {
        "normal": lambda rng: rng.normal(size=300),
        "integer": lambda rng: rng.integers(-20, 20, size=300).astype(float),
        "one decimal": lambda rng: np.round(rng.normal(size=300) * 5, 1),
        "two decimals": lambda rng: np.round(rng.normal(size=300) * 5, 2),
        "offset uniform": lambda rng: rng.uniform(0.25, 9.25, size=300),
        "sub-milli": lambda rng: rng.normal(size=300) * 1e-3,
        "with a nan": lambda rng: np.append(rng.normal(size=300), np.nan),
    }

    #: Both seeds the callers pass -- see the class above.
    SEEDS = {
        "autobin": lambda low, width: math.ceil(low / width) * width - width,
        "explicit": lambda low, width: math.floor(low / width) * width,
    }

    @pytest.mark.parametrize("kind", sorted(KINDS))
    @pytest.mark.parametrize("width", [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10])
    @pytest.mark.parametrize("seed", sorted(SEEDS))
    def test_the_vectorised_counts_match_the_plotly_loop(self, kind, width, seed):
        arr = self.KINDS[kind](np.random.default_rng(701))
        low, high = float(np.nanmin(arr)), float(np.nanmax(arr))
        start = self.SEEDS[seed](low, width)

        # The loop is the one that may warn, on the `nan` sample; the numpy
        # form must not, because a render is not the place for one.
        with np.errstate(invalid="ignore"):
            expected = _shift_by_plotly_loop(start, arr, width, low, high)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            actual = _auto_shift_bins(start, arr, width, low, high)

        assert float(actual) == float(expected)


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


class TestTheRoundUpIsStrict:
    """A rough width landing exactly on a nice number takes the next one up.

    `Lib.roundUp` binary-searches with ``arrayIn[mid] <= val``, so it returns
    the first element **strictly greater** than the value. py-maidr read it as
    "greater than or equal", which agrees everywhere except on the boundary --
    and there it picked the width *below* the one plotly draws: twice as many
    bins, half as wide, every count wrong to match (#646).

    ``nbins`` is what makes the ratio exact on demand, since the rough width
    is then ``range / nbins`` rather than something derived from the spread.

    The same comparison decides a contour's automatic levels, which run
    through the same ``autoTicks`` -- a field spanning 0 .. 3 gives a rough
    step of exactly 0.2 and plotly draws 0.5 (#642).
    """

    @pytest.mark.parametrize(
        ("high", "points", "width"),
        [
            # 30 / 15 = 2 exactly. The loose reading gives 2; plotly gives 5.
            pytest.param(30, 61, 5, id="exactly-two"),
            # 75 / 15 = 5 exactly.
            pytest.param(75, 76, 10, id="exactly-five"),
            # Controls a hair either side, where the two readings agree.
            pytest.param(28.5, 58, 2, id="just-below-two"),
            pytest.param(31.5, 64, 5, id="just-above-two"),
        ],
    )
    def test_the_width_is_the_one_plotly_draws(self, high, points, width):
        values = list(np.linspace(0, high, points))

        drawn = bins(go.Figure(go.Histogram(x=values, nbinsx=15)))

        assert {round(hi - lo, 9) for lo, hi, _ in drawn} == {width}

    def test_a_two_dimensional_histogram_rounds_the_same_way(self):
        """It shares `_plotly_dtick`, so the boundary reaches it too.

        Its automatic width divides by a different power of the sample count,
        but the round-up afterwards is the same one -- so an `nbins` hint that
        lands on the boundary lands there for both. Measured: plotly resolves
        this figure to ``xbins`` of ``size 5, start -2.5, end 32.5``, where
        the loose reading would have given a width of 2.
        """
        values = list(np.linspace(0, 30, 61))
        figure = go.Figure(go.Histogram2d(x=values, y=values, nbinsx=15, nbinsy=15))

        layer = PlotlyMaidr(figure)._flatten_maidr()["subplots"][0][0]["layers"][0]

        assert layer["data"]["x"] == [
            "-2.5 – 2.5",
            "2.5 – 7.5",
            "7.5 – 12.5",
            "12.5 – 17.5",
            "17.5 – 22.5",
            "22.5 – 27.5",
            "27.5 – 32.5",
        ]


class TestABinSpecWithoutASize:
    """#650: a ``start`` or an ``end`` was read only alongside a ``size``.

    Every one of these was measured against plotly 6.7.0 in Chromium, on the
    sample below -- twenty integers from 1 to 10, whose automatic bins run
    from -0.5 in steps of 2.
    """

    SAMPLE = [1, 1, 2, 2, 2, 3, 3, 4, 5, 5, 5, 5, 6, 6, 7, 8, 8, 9, 9, 10]

    def test_a_start_alone_moves_every_bin(self):
        """The case that shows what it cost: five bars announced as six.

        With the start discarded, this was binned from the automatic -0.5 and
        announced as six bins of ``[2, 5, 5, 3, 4, 1]`` -- for a chart drawing
        five bars of ``[5, 3, 6, 3, 3]``. Not one of the six numbers is a
        number on the chart, and not one of the six labels names a bar.
        """
        drawn = bins(go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(start=0.5))))

        assert [count for _, _, count in drawn] == [5, 3, 6, 3, 3]
        assert [low for low, _, _ in drawn] == [0.5, 2.5, 4.5, 6.5, 8.5]

    def test_an_end_alone_stops_the_bins_short(self):
        """And drops the samples past it, which is what plotly draws.

        Measured: three bars, holding twelve of the twenty samples. The eight
        at 6 and above are outside every bin and are not counted anywhere --
        the same reading an explicit window already had (#402).
        """
        drawn = bins(go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(end=5))))

        assert drawn == [(-0.5, 1.5, 2), (1.5, 3.5, 5), (3.5, 5.5, 5)]

    def test_both_ends_without_a_width_get_one_derived_for_them(self):
        """The width is still the automatic one; only the window is theirs."""
        drawn = bins(go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(start=2, end=6))))

        assert drawn == [(2.0, 4.0, 5), (4.0, 6.0, 5)]

    @pytest.mark.parametrize(
        "size",
        [pytest.param(None, id="width-derived"), pytest.param(2, id="width-named")],
    )
    def test_a_window_that_is_not_whole_bins_keeps_its_part_bin(self, size):
        """Plotly steps while the *bin's own* start is below ``end``.

        ``start=0.5, end=9`` is four and a quarter bins of 2. Measured: five
        bars, the last of them ``[8.5, 10.5)`` -- reaching past the ``end``
        that admitted it. Rounding the span to whole bins gives four and
        loses the three samples at 9, 9 and 10.

        Written both ways round because the old code had two paths here and
        only one of them was ever reached with a derived width.
        """
        spec = dict(start=0.5, end=9)
        if size is not None:
            spec["size"] = size

        drawn = bins(go.Figure(go.Histogram(x=self.SAMPLE, xbins=spec)))

        assert len(drawn) == 5
        assert drawn[-1] == (8.5, 10.5, 3)

    def test_a_width_of_zero_is_an_absence_and_takes_nbins_with_it(self):
        """Measured, and the second half is the surprising half.

        ``size=0`` is not a width plotly can use, so it bins automatically --
        and writing ``size`` at all, even as that zero, discards an ``nbins``
        hint too. Measured: ``nbinsx`` of 4 and of 12 both draw the same six
        automatic bars. Reading the hint anyway would announce twelve.

        This also used to be a crash rather than a reading: a zero width
        reached a division by it.
        """
        for hint in (None, 4, 12):
            extra = {} if hint is None else {"nbinsx": hint}
            drawn = bins(
                go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(size=0), **extra))
            )

            assert [count for _, _, count in drawn] == [2, 5, 5, 3, 4, 1]

    def test_a_sample_with_no_spread_is_one_wide_wherever_it_starts(self):
        """A width of 1, not the 2 that rounding one up gives.

        Measured: a run of 3s is binned from 2.5 to 3.5, and with
        ``start=0`` from 3 to 4 -- one wide either way. The automatic width
        for a sample with no spread falls back to 1 *before* the round-up
        rather than through it.
        """
        flat = [3, 3, 3, 3, 3]

        assert bins(go.Figure(go.Histogram(x=flat))) == [(2.5, 3.5, 5)]
        assert bins(go.Figure(go.Histogram(x=flat, xbins=dict(start=0)))) == [
            (3.0, 4.0, 5)
        ]

    def test_a_window_a_hair_over_whole_bins_is_still_whole_bins(self):
        """``(-2.8 - -3.0) / 0.1`` is 2.0000000000000018 in binary.

        Two bins, and the arithmetic says a shade more than two -- so a
        ceiling taken at face value adds a third, ``[-2.8, -2.7)``, and puts
        the two samples past the author's window into it. Measured: plotly
        draws two bars and drops those samples, which are outside every bin
        it made.

        Reached with data past the ``end`` on purpose. An empty extra bin
        would be trimmed back off before anyone heard it, so only a bin with
        something in it shows the difference.
        """
        inside_and_beyond = [-2.99, -2.95, -2.92, -2.85, -2.83, -2.75, -2.74]

        drawn = bins(
            go.Figure(
                go.Histogram(
                    x=inside_and_beyond,
                    xbins=dict(start=-3.0, end=-2.8, size=0.1),
                )
            )
        )

        assert [count for _, _, count in drawn] == [3, 2]

    def test_a_value_that_is_not_a_number_is_in_no_bin(self):
        """It is not an observation rather than an observation of zero (#405).

        Said where the bins are assigned rather than left to the comparisons
        there: NaN answers False to both of them, while ``searchsorted`` sorts
        it past the last edge -- so it came back as a bin one past the end,
        and the counts were then one longer than the grid they belong to.
        """
        from maidr.plotly.histogram import PlotlyHistogramPlot

        edges = np.array([0.0, 2.0, 4.0, 6.0])
        with_a_gap = np.array([1.0, np.nan, 3.0, 5.0])

        assert list(PlotlyHistogramPlot._bin_assignment(with_a_gap, edges)) == [
            0,
            -1,
            1,
            2,
        ]
        assert list(PlotlyHistogramPlot._bin_counts(with_a_gap, edges)) == [1, 1, 1]

    def test_a_negative_width_forms_no_layer(self):
        """Not a width, and not a chart this can read.

        Plotly draws *something* for it -- measured, a width of -2 over these
        twenty integers draws ten bars, one per distinct value -- by a route
        worth neither guessing at nor reproducing. Declining costs the layer;
        the one bin holding everything that the arithmetic would otherwise
        produce would misreport a chart drawing ten (#636).
        """
        figure = go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(size=-2)))

        assert layers(figure) == []

    def test_a_start_past_the_last_value_forms_no_layer(self):
        """There is no bin at all, which is what plotly draws: nothing.

        A layer of no bins would announce a distribution the chart does not
        draw, which is what #636 settled for every other empty reading.
        """
        figure = go.Figure(go.Histogram(x=self.SAMPLE, xbins=dict(start=20)))

        assert layers(figure) == []


class TestABlankIsNoObservation:
    """A ``None`` or a ``NaN`` in the sample raised out of the figure (#699).

    ``_bin_assignment`` already put a blank in no bin; the grid was still
    worked out from the whole array, so its minimum was ``NaN`` and the first
    ``ceil`` of it raised ``ValueError`` -- out of ``maidr.render``, taking
    every other layer of the figure down with the histogram. Plotly draws
    around a blank: ``min``/``max``, ``distinctVals`` and ``stdev`` all skip
    it, and only the ``data.length`` under the automatic width's exponent
    still counts it.
    """

    WITH_BLANKS = BIMODAL[:3] + [None, float("nan")] + BIMODAL[3:]

    def test_the_finite_values_are_binned_as_they_would_be_alone(self):
        with_blanks = go.Figure(go.Histogram(x=self.WITH_BLANKS))
        finite = go.Figure(go.Histogram(x=BIMODAL))

        assert bins(with_blanks) == bins(finite)
        assert bins(finite) == [(0.0, 5.0, 4), (5.0, 10.0, 2), (10.0, 15.0, 2)]

    def test_on_a_horizontal_trace_too(self):
        with_blanks = go.Figure(go.Histogram(y=self.WITH_BLANKS))
        finite = go.Figure(go.Histogram(y=BIMODAL))

        assert bins(with_blanks) == bins(finite)

    def test_from_a_frame_column(self):
        # The ordinary way to meet one: a column with a missing entry, which
        # `to_dict` hands over as an array holding a `nan`.
        column = px.histogram(pd.DataFrame({"v": self.WITH_BLANKS}), x="v")

        assert bins(column) == bins(go.Figure(go.Histogram(x=BIMODAL)))

    @pytest.mark.parametrize(
        "spec",
        [
            dict(xbins=dict(size=2)),
            dict(xbins=dict(start=0.5)),
            dict(nbinsx=3),
        ],
        ids=["size", "start", "nbins"],
    )
    def test_under_every_spelling_of_the_spec(self, spec):
        # Each spelling read the minimum or the maximum on a path of its own,
        # and every one of them raised.
        with_blanks = go.Figure(go.Histogram(x=self.WITH_BLANKS, **spec))
        finite = go.Figure(go.Histogram(x=BIMODAL, **spec))

        assert bins(with_blanks) == bins(finite)

    def test_a_sample_of_nothing_but_blanks_forms_no_layer(self):
        # Plotly draws no bars for it, and a layer of no bins would announce a
        # distribution the chart does not draw (#636).
        assert layers(go.Figure(go.Histogram(x=[None, float("nan")]))) == []

    def test_the_shift_counts_the_sample_without_its_blanks(self):
        """``autoShiftNumericBins`` subtracts the blanks from its length.

        The bundle tallies them alongside the integers
        (``t[c]%1===0?s++:zh(t[c])||l++``), takes ``f=t.length-l``, and tests
        ``s===f``, ``f*.1`` and ``f*.3`` against that ``f``. Forty integers
        and thirty blanks pin which length is meant: over the finite sample
        every value is an integer and the grid shifts half a step off them,
        to ``-0.5``. Counted over the whole array, ``s`` would be 40 against
        an ``f`` of 70, the integer branch would not fire, and the sample's
        minimum sitting on an edge would send it half a *bin* down instead,
        to ``-2.5`` -- a start the chart does not draw.

        The width is named so that only the shift is under test: the
        automatic one does read the whole length, through its exponent.
        """
        integers = list(range(40))
        with_blanks = integers + [None] * 30

        finite = bins(go.Figure(go.Histogram(x=integers, xbins=dict(size=5))))
        blanked = bins(go.Figure(go.Histogram(x=with_blanks, xbins=dict(size=5))))

        assert blanked == finite
        assert finite[0][0] == -0.5

    def test_a_blank_still_counts_toward_the_width_exponent(self):
        """The one term plotly reads off the whole array, blanks included.

        ``autoBin`` divides ``2 * stdev`` by ``data.length ** 0.4``, and that
        length is the array as given, where the standard deviation beside it
        is over the numeric entries alone. So the finite values do **not**
        always bin as they would on their own: two blanks make this sample
        two longer, the rough width smaller by ``(6 / 8) ** 0.4``, and that is
        enough to carry it across the 2 the nice rounding turns on.
        """
        sample = np.array(NARROW, dtype=float)
        alone = _plotly_default_size0(sample)
        with_two_blanks = _plotly_default_size0(sample, sample_size=len(NARROW) + 2)

        assert with_two_blanks == pytest.approx(alone * (6 / 8) ** 0.4)

        two_blanks = NARROW[:3] + [None, float("nan")] + NARROW[3:]
        assert bins(go.Figure(go.Histogram(x=NARROW))) == [
            (-5.0, 0.0, 2),
            (0.0, 5.0, 4),
        ]
        assert bins(go.Figure(go.Histogram(x=two_blanks))) == [
            (-4.0, -2.0, 1),
            (-2.0, 0.0, 1),
            (0.0, 2.0, 2),
            (2.0, 4.0, 2),
        ]

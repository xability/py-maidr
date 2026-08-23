"""A plotly `histogram2dcontour` produced a figure with no layers.

The last of #627's fifteen, and the one that is two readings at once: it bins
samples the way a `histogram2d` does and then draws the curves along which
those *counts* are constant, the way a `contour` does. Both halves already
exist, so what is new here is where they meet.

Three things differ from either half alone, all measured against plotly 6.7.0
in Chromium:

- **The grid is one bin wider at each automatic edge**, so the curves have
  somewhere to close. Which edges move is per-side and not simply "the
  automatic ones" -- see `histogram2d.extended_edges`.
- **The curves run through the bin centres**, not the edges. Plotly's own
  `calcdata` for this trace carries five coordinates for five bins where a
  `histogram2d` carries four edges for three bins.
- **A cell nothing landed in traces as zero.** The heatmap reading of the
  same binning announces it as `None` -- there is no average of nothing --
  but the contour reading cannot, because plotly hands the grid to a tracer
  written in JavaScript where a `null` compares as below every level. The
  *levels*, though, are still chosen from the real values: plotly reports a
  sparse `histfunc="avg"` grid as running 3.5 to 19, not 0 to 19.

Read end to end against the browser on 13 figures -- automatic bins, an
`nbins` hint, four spellings of `xbins`, three `histfunc`s, a `histnorm`, an
`ncontours` and an explicit level spec. Eleven agree curve for curve. The two
that do not are levels whose curves reach the grid's own edge, where plotly's
`<path>` elements are the outlines of the filled regions rather than the
curves themselves; every one of those levels has more than one curve, so the
layer declines its selectors there anyway. Measured separately: a level whose
single curve ends on the grid edge *does* match its drawn path exactly, in
every `coloring` mode.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.histogram2d import extended_edges  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Twenty samples along a diagonal band. Plotly bins them into a 5x5 grid of
#: counts running 0 .. 10 -- the ring of zeros being the widening -- and picks
#: levels 1 .. 9 for it. Measured.
X = [1, 1, 2, 2, 2, 3, 3, 4, 5, 5, 5, 5, 6, 6, 7, 8, 8, 9, 9, 10]
Y = [1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10]

#: A value per sample, for the aggregating `histfunc`s.
Z = list(range(20))


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _levels(layer: dict) -> list[float]:
    """The distinct levels the layer's series run at, in order."""
    return sorted({series[0][MaidrKey.LEVEL.value] for series in layer["data"]})


def test_a_binned_contour_is_read_as_a_contour_layer() -> None:
    """The counts are the field, and the curves are of the counts.

    Twelve curves across nine levels, which is what plotly draws: three of the
    levels cross the diagonal band twice and get two curves each.
    """
    (layer,) = _layers(go.Figure(go.Histogram2dContour(x=X, y=Y)))

    assert layer["type"] is PlotType.CONTOUR
    assert _levels(layer) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert len(layer["data"]) == 12


def test_the_curves_run_through_the_bin_centres() -> None:
    """Not the edges, which is where a `histogram2d` reads its grid.

    Plotly bins these into five bins from -5.5 in steps of 5 and traces the
    contour through their centres, -3 .. 17 -- measured off its own
    `calcdata`, which carries five coordinates here where a `histogram2d`
    carries six edges. Every vertex therefore lies within that span, and the
    curves of the outermost level touch it.
    """
    (layer,) = _layers(go.Figure(go.Histogram2dContour(x=X, y=Y)))

    xs = [point[MaidrKey.X.value] for series in layer["data"] for point in series]
    ys = [point[MaidrKey.Y.value] for series in layer["data"] for point in series]

    assert min(xs) >= -3.0 and max(xs) <= 17.0
    assert min(ys) >= -3.0 and max(ys) <= 17.0


class TestTheGridIsWidened:
    """Which edges plotly moves, and which it leaves where the author put them.

    From the bundle this wheel ships, where ``l`` is what the author wrote::

        l.size || (P.start = tickIncrement(P.start, P.size, true)),
        l.end === void 0 && (P.end = tickIncrement(P.end, P.size, false))

    So the low edge moves unless a ``size`` was named -- not unless a
    ``start`` was -- and the high edge moves unless an ``end`` was. An
    author's own ``start`` still stands, because it replaces the automatic one
    either way. Measured across nine spellings of ``xbins`` on five samples.
    """

    EDGES = np.array([0.0, 2.0, 4.0, 6.0])

    @pytest.mark.parametrize(
        ("bins", "expected"),
        [
            pytest.param(None, [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0], id="nothing-named"),
            pytest.param({}, [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0], id="an-empty-block"),
            pytest.param(
                {"size": 2}, [0.0, 2.0, 4.0, 6.0, 8.0], id="a-size-holds-the-low-edge"
            ),
            pytest.param(
                {"start": 0}, [0.0, 2.0, 4.0, 6.0, 8.0], id="a-start-holds-it-too"
            ),
            pytest.param(
                {"end": 6},
                [-2.0, 0.0, 2.0, 4.0, 6.0],
                id="an-end-holds-the-high-edge",
            ),
            pytest.param(
                {"start": 0, "end": 6},
                [0.0, 2.0, 4.0, 6.0],
                id="both-ends-hold-both",
            ),
        ],
    )
    def test_only_the_edges_plotly_moves_move(self, bins: dict, expected: list) -> None:
        assert list(extended_edges(self.EDGES, bins)) == pytest.approx(expected)

    def test_a_grid_of_one_edge_is_left_alone(self) -> None:
        """There is no width to widen it by."""
        lonely = np.array([1.0])

        assert list(extended_edges(lonely, None)) == [1.0]


class TestACellWithNoAnswer:
    """An aggregating `histfunc` leaves gaps, and the two halves read them apart.

    Measured on this grid, whose four filled cells run 3.5 .. 19: plotly draws
    ten curves across levels 4 .. 18. Read as a field with holes in it,
    `contourpy` finds five curves and misses the top three levels entirely --
    the gaps are traced as zeros, not as holes.

    The levels are the other half of it. They come from the values that are
    there, so the range is 3.5 .. 19 rather than the 0 .. 19 the filled grid
    would give. Taking the filled grid's range instead draws levels 2 .. 16,
    none of which is a level on the chart.
    """

    def test_the_gaps_trace_as_zeros(self) -> None:
        (layer,) = _layers(
            go.Figure(go.Histogram2dContour(x=X, y=Y, z=Z, histfunc="avg"))
        )

        assert _levels(layer) == [4, 6, 8, 10, 12, 14, 16, 18]
        assert len(layer["data"]) == 10

    def test_a_histfunc_that_fills_every_cell_needs_none_of_that(self) -> None:
        """`sum` puts a 0 in an empty cell rather than leaving it empty.

        The same twenty values, summed instead of averaged: thirteen levels,
        one curve each, and a highlight for every one of them.
        """
        (layer,) = _layers(
            go.Figure(go.Histogram2dContour(x=X, y=Y, z=Z, histfunc="sum"))
        )

        assert _levels(layer) == [10 * step for step in range(1, 14)]
        assert len(layer["selectors"]) == 13


def test_a_normalisation_reaches_the_levels() -> None:
    """The cells are normalised before the levels are picked, as plotly does.

    Twenty samples under ``probability`` put the fullest cell at 0.5, and the
    levels follow at every twentieth -- measured, nine of them and twelve
    curves.

    The twelve is the sharper half. One cell here holds exactly 0.4, and the
    level that grazes it arrives as ``0.39999999999999997`` -- so the curve
    `contourpy` returns there is five copies of one point that differ in
    their last bits, spanning 1.6e-15 on a grid whose cells are 5 wide.
    Testing that span for zero rather than against the grid keeps it, and
    announces a thirteenth curve the chart does not draw.
    """
    (layer,) = _layers(
        go.Figure(go.Histogram2dContour(x=X, y=Y, histnorm="probability"))
    )

    assert _levels(layer) == pytest.approx([0.05 * step for step in range(1, 10)])
    assert len(layer["data"]) == 12


def test_an_explicit_level_spec_is_the_author_s() -> None:
    """The binning is plotly's, the levels are theirs, and both are read.

    Four levels, each drawing a single ring around the band, so the layer
    keeps its highlight and each series points at its own group.
    """
    (layer,) = _layers(
        go.Figure(
            go.Histogram2dContour(x=X, y=Y, contours=dict(start=1, end=4, size=1))
        )
    )

    assert _levels(layer) == [1, 2, 3, 4]
    assert [selector.split("contourlevel:")[1] for selector in layer["selectors"]] == [
        f"nth-of-type({group}) path:nth-of-type(1)" for group in range(1, 5)
    ]


def test_ncontours_reaches_the_binned_counts() -> None:
    """The level rule runs over the counts, so `ncontours` divides their range.

    Measured: over counts of 0 .. 10, an `ncontours` of 4 rounds a step of 2.5
    up to 5, and the first multiple above the floor is already past the last
    below the ceiling -- so plotly draws one level, at their midpoint.
    """
    (layer,) = _layers(go.Figure(go.Histogram2dContour(x=X, y=Y, ncontours=4)))

    assert _levels(layer) == [5]


class TestTheThirdAxisIsNamed:
    """A `contour`'s levels are the author's numbers; these are computed here.

    So their name is known, and leaving it unsaid would announce a chart of
    bare numbers with no word for what they count. The same reading a
    `histogram2d` settled for its cells, and the same order of precedence.
    """

    @pytest.mark.parametrize(
        ("extra", "expected"),
        [
            pytest.param({}, "Count", id="counted"),
            pytest.param({"z": Z, "histfunc": "avg"}, "Average", id="averaged"),
            pytest.param({"z": Z, "histfunc": "max"}, "Maximum", id="reduced"),
            pytest.param(
                {"histnorm": "percent"}, "Percent", id="normalised-wins-over-the-rest"
            ),
        ],
    )
    def test_the_levels_are_named_for_what_they_measure(
        self, extra: dict, expected: str
    ) -> None:
        (layer,) = _layers(go.Figure(go.Histogram2dContour(x=X, y=Y, **extra)))

        assert layer["axes"][MaidrKey.Z][MaidrKey.LABEL] == expected

    def test_the_author_s_colour_bar_title_wins(self) -> None:
        (layer,) = _layers(
            go.Figure(
                go.Histogram2dContour(x=X, y=Y, colorbar=dict(title="Sightings"))
            )
        )

        assert layer["axes"][MaidrKey.Z][MaidrKey.LABEL] == "Sightings"


class TestNothingToRead:
    """Declining, rather than emitting a layer for a chart with nothing in it."""

    def test_a_trace_with_no_samples_forms_no_layer(self) -> None:
        assert _layers(go.Figure(go.Histogram2dContour(x=[], y=[]))) == []

    def test_one_sample_is_still_a_chart(self) -> None:
        """And the widening is what makes it one.

        A single sample bins to one cell, which on its own is a grid too small
        to trace -- marching squares needs a cell, which needs two rows and
        two columns. The empty bin plotly puts outside each edge makes it a
        3x3, and the field then runs 0 to 1 with nine levels across it.

        Measured: plotly draws exactly that -- nine groups at 0.1 .. 0.9, one
        ring each around the one filled cell -- so every one of them is
        addressable.
        """
        (layer,) = _layers(go.Figure(go.Histogram2dContour(x=[3], y=[4])))

        assert _levels(layer) == pytest.approx([0.1 * step for step in range(1, 10)])
        assert len(layer["selectors"]) == 9

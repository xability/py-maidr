"""A plotly 2-D histogram produced a figure with no layers.

`go.Histogram2d` carries raw samples and lets plotly bin them into a grid in
the browser. `maidr/plotly/` had no handling for it, so it fell through
`_extract_plots` to `PlotlyPlotFactory`, which returned `None` (#627).

**It is a heatmap.** A rectangular grid of cells each carrying a number is
exactly that, and plotly agrees: measured in Chromium, a `histogram2d` draws a
single `<image>` into its subplot's `heatmaplayer`, the same element a
`go.Heatmap` draws. So the layer extends `PlotlyHeatmapPlot` and shares its
selector.

What differs is where the grid comes from, and that turned out to be a small
question with a measured answer. Plotly bins a 2-D axis on the rule py-maidr
already matches for a 1-D histogram, with **one** change: the sample-size
exponent is `0.25` rather than `0.4` -- `autoBin`'s own `is2d` flag. The same
thirty values are binned five wide by `go.Histogram` and ten wide by
`go.Histogram2d`, which is what `test_a_two_dimensional_axis_is_binned_more_coarsely`
pins.

Every emitted cell and bin label was then checked against `gd.calcdata` in
Chromium across 16 figures -- auto widths, `nbins` hints, explicit bins, all
four `histnorm` forms, three `histfunc` aggregates, a reversed x axis, a
reversed y axis, and a subplot. 0 disagreements.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Two bins on each axis, so a grid can be read by eye. Samples at (1, 1),
#: (1, 3) and (3, 1) fill three of the four cells and leave the fourth empty.
BINS = {
    "xbins": {"start": 0, "end": 4, "size": 2},
    "ybins": {"start": 0, "end": 4, "size": 2},
}
CORNER = {"x": [1, 1, 3], "y": [1, 3, 1]}

#: The grid those three samples make, **top row first** -- the schema's order,
#: which the core turns over again so its own row 0 is the bottom of the
#: drawing.
CORNER_GRID = [[1.0, 0.0], [1.0, 1.0]]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _histogram2d(**kwargs: object) -> go.Figure:
    """One 2-D histogram, with its colour bar out of the way."""
    return go.Figure(go.Histogram2d(showscale=False, **kwargs))


def test_a_histogram2d_is_read_as_a_heatmap_layer() -> None:
    """The reproduction, and the type it becomes.

    A rectangular grid of cells each carrying a number is a heatmap, and
    plotly draws it with the same element -- measured, one `<image>` in the
    subplot's `heatmaplayer`.
    """
    (layer,) = _layers(_histogram2d(**CORNER, **BINS))

    assert layer["type"] is PlotType.HEAT
    assert layer["selectors"] == ".subplot.xy .heatmaplayer image"


def test_the_grid_is_the_counts_the_samples_make() -> None:
    """Read top row first, which is the schema's order."""
    (layer,) = _layers(_histogram2d(**CORNER, **BINS))

    assert layer["data"]["points"] == CORNER_GRID


def test_a_cell_is_named_by_the_range_it_covers() -> None:
    """Not by its index and not by its centre.

    "A count of 4" says nothing without "between 0 and 2", and the range is
    what a sighted reader takes off the axis. r-maidr settled the same
    question the same way for `geom_bin_2d` (xability/r-maidr#136).
    """
    (layer,) = _layers(_histogram2d(**CORNER, **BINS))

    assert layer["data"]["x"] == ["0 – 2", "2 – 4"]
    assert layer["data"]["y"] == ["2 – 4", "0 – 2"]


def test_a_two_dimensional_axis_is_binned_more_coarsely() -> None:
    """The one thing that differs from the 1-D rule, and the whole of it.

    Plotly's `autoBin` divides by ``n ** 0.25`` for a 2-D histogram and
    ``n ** 0.4`` for a 1-D one. Measured in Chromium on exactly these thirty
    values: `go.Histogram` bins them **five** wide and `go.Histogram2d` bins
    them **ten** wide, both starting at -0.5. Reusing the 1-D exponent would
    announce six columns where the chart draws three.
    """
    values = list(range(30))

    (layer,) = _layers(_histogram2d(x=values, y=values))

    assert layer["data"]["x"] == ["-0.5 – 9.5", "9.5 – 19.5", "19.5 – 29.5"]


def test_an_nbins_hint_is_honoured() -> None:
    """Plotly rounds it to a nice width rather than obeying it exactly.

    Which is the 1-D behaviour unchanged: only the *automatic* width differs
    between one dimension and two, so the hint path needed nothing.
    """
    values = list(range(30))

    (layer,) = _layers(_histogram2d(x=values, y=values, nbinsx=6, nbinsy=6))

    assert layer["data"]["x"] == [
        "-0.5 – 4.5",
        "4.5 – 9.5",
        "9.5 – 14.5",
        "14.5 – 19.5",
        "19.5 – 24.5",
        "24.5 – 29.5",
    ]


def test_a_sample_missing_a_coordinate_is_not_on_the_chart() -> None:
    """Measured: plotly drops the pair rather than placing it anywhere.

    Counting it would announce a cell one fuller than the one drawn.
    """
    (layer,) = _layers(_histogram2d(x=[1, None, 3], y=[1, 3, 1], **BINS))

    assert layer["data"]["points"] == [[0.0, 0.0], [1.0, 1.0]]


def test_a_sample_outside_every_bin_is_dropped_rather_than_clipped() -> None:
    """Measured on an explicit ``xbins`` with a value past its ``end``.

    Folding it into the edge bin would put a sample in a cell the chart shows
    as holding one fewer.
    """
    (layer,) = _layers(_histogram2d(x=[1, 9, 3], y=[1, 1, 1], **BINS))

    assert layer["data"]["points"] == [[0.0, 0.0], [1.0, 1.0]]


def test_a_histfunc_reduces_the_z_values_rather_than_counting_rows() -> None:
    """What a cell *measures* is the author's choice, not the population.

    The bottom-left cell holds **two** samples on purpose: with one apiece
    every reduction agrees, and a sum would pass for an average.
    """
    (layer,) = _layers(
        _histogram2d(
            x=[1, 1, 1, 3],
            y=[1, 1, 3, 1],
            z=[10, 30, 20, 40],
            histfunc="avg",
            **BINS,
        )
    )

    assert layer["data"]["points"] == [[20.0, None], [20.0, 40.0]]


def test_a_cell_nothing_landed_in_is_a_zero_or_a_blank_by_histfunc() -> None:
    """Measured: `count` and `sum` paint a 0 there, `avg`/`min`/`max` do not.

    An average of nothing is not zero, and announcing one would put a number
    on a cell the chart leaves unpainted.
    """
    counted = _layers(_histogram2d(**CORNER, **BINS))[0]
    averaged = _layers(
        _histogram2d(**CORNER, z=[10, 20, 30], histfunc="avg", **BINS)
    )[0]

    assert counted["data"]["points"][0][1] == 0.0
    assert averaged["data"]["points"][0][1] is None


def test_an_aggregating_histfunc_with_nothing_to_reduce_counts_instead() -> None:
    """Which is what plotly does with it -- measured.

    `histfunc="sum"` and no `z` draws the same grid as the default, so
    declining it would leave a readable chart unread.
    """
    (layer,) = _layers(_histogram2d(**CORNER, histfunc="sum", **BINS))

    assert layer["data"]["points"] == CORNER_GRID


@pytest.mark.parametrize(
    ("histnorm", "expected"),
    [
        pytest.param(None, [[1.0, 0.0], [1.0, 1.0]], id="count"),
        pytest.param(
            "percent",
            [[100 / 3, 0.0], [100 / 3, 100 / 3]],
            id="percent-of-the-grand-total",
        ),
        pytest.param(
            "probability", [[1 / 3, 0.0], [1 / 3, 1 / 3]], id="share-of-the-total"
        ),
        pytest.param(
            "density", [[0.25, 0.0], [0.25, 0.25]], id="per-unit-of-cell-area"
        ),
        pytest.param(
            "probability density",
            [[1 / 12, 0.0], [1 / 12, 1 / 12]],
            id="share-per-unit-of-area",
        ),
    ],
)
def test_histnorm_rescales_a_cell_the_way_plotly_does(
    histnorm: str | None, expected: list
) -> None:
    """The 1-D rule with the cell's **area** where it uses the bin's width.

    Measured against the browser for all four forms on a grid of unequal x
    and y widths. Here every cell is 2 x 2, so a density is a quarter of a
    count.
    """
    figure = _histogram2d(**CORNER, **BINS)
    if histnorm is not None:
        figure.data[0].histnorm = histnorm

    (layer,) = _layers(figure)

    # Flattened because `pytest.approx` does not take a nested sequence, and
    # the shape is already pinned by the tests above.
    flat = [value for row in layer["data"]["points"] for value in row]
    assert flat == pytest.approx([value for row in expected for value in row])


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({}, "Count", id="the-default"),
        pytest.param({"histnorm": "percent"}, "Percent", id="a-normalisation"),
        pytest.param(
            {"z": [1, 2, 3], "histfunc": "max"}, "Maximum", id="an-aggregate"
        ),
        pytest.param(
            {"z": [1, 2, 3], "histfunc": "sum", "histnorm": "density"},
            "Density",
            id="the-normalisation-wins-over-the-aggregate",
        ),
        pytest.param({"histfunc": "sum"}, "Count", id="an-aggregate-with-no-z"),
    ],
)
def test_the_third_axis_is_named_for_what_a_cell_holds(
    kwargs: dict, expected: str
) -> None:
    """A heatmap's numbers are the author's; these are computed.

    So their name is known here, and leaving it unsaid would announce a grid
    of bare numbers with no word for what they count. The normalisation wins
    over the aggregate because it is what decides the units -- measured, a
    ``sum`` under ``histnorm="percent"`` still totals 100.
    """
    (layer,) = _layers(_histogram2d(**CORNER, **BINS, **kwargs))

    assert layer["axes"]["z"]["label"] == expected


def test_a_colour_bar_the_author_titled_wins() -> None:
    """It is the one thing they may have written about the cells."""
    (layer,) = _layers(
        _histogram2d(
            **CORNER, **BINS, colorbar={"title": {"text": "Sightings"}}
        )
    )

    assert layer["axes"]["z"]["label"] == "Sightings"


def test_a_reversed_y_axis_already_counts_from_the_top() -> None:
    """So the rows are not turned over again (#487).

    The schema's rows run top-first and the core reverses them, which is what
    makes ArrowUp move visually up. A y axis drawn reversed has the drawing's
    top at its low end already.
    """
    figure = _histogram2d(**CORNER, **BINS)
    figure.update_layout(yaxis={"autorange": "reversed"})

    (layer,) = _layers(figure)

    assert layer["data"]["points"] == [[1.0, 1.0], [1.0, 0.0]]
    assert layer["data"]["y"] == ["0 – 2", "2 – 4"]


def test_a_reversed_x_axis_turns_the_columns_over() -> None:
    """The columns start at the left, so only a reversed x axis moves them."""
    figure = _histogram2d(**CORNER, **BINS)
    figure.update_layout(xaxis={"autorange": "reversed"})

    (layer,) = _layers(figure)

    assert layer["data"]["points"] == [[0.0, 1.0], [1.0, 1.0]]
    assert layer["data"]["x"] == ["2 – 4", "0 – 2"]


def test_a_histogram2d_on_a_second_subplot_is_scoped_to_it() -> None:
    """Each subplot holds a `heatmaplayer` of its own."""
    from plotly.subplots import make_subplots

    figure = make_subplots(rows=1, cols=2)
    figure.add_trace(go.Bar(x=["a"], y=[1]), row=1, col=1)
    figure.add_trace(
        go.Histogram2d(showscale=False, **CORNER, **BINS), row=1, col=2
    )

    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

    assert [len(row) for row in grid] == [2]
    (heat,) = grid[0][1]["layers"]
    assert heat["selectors"] == ".subplot.x2y2 .heatmaplayer image"


def test_a_histogram2d_with_no_samples_forms_no_layer() -> None:
    """Nothing is binned, so nothing is drawn (#636).

    Measured: plotly's `calcdata` entry for such a trace carries no `z` at
    all, so there is no grid to read.
    """
    assert _layers(_histogram2d(x=[], y=[], **BINS)) == []


def test_a_histogram2d_whose_samples_are_all_unusable_forms_no_layer() -> None:
    """Same answer, reached with values rather than an empty array."""
    assert _layers(_histogram2d(x=[None, None], y=[1, 2], **BINS)) == []


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        pytest.param([1, 4], [[0.0, 0.0], [1.0, 0.0]], id="the-last-edge-is-outside"),
        pytest.param([1, 2], [[0.0, 0.0], [1.0, 1.0]], id="an-interior-edge-goes-up"),
        pytest.param([0, 1], [[0.0, 0.0], [2.0, 0.0]], id="the-opening-edge-is-inside"),
    ],
)
def test_every_bin_is_half_open_including_the_last(x: list, expected: list) -> None:
    """Measured, because the obliging answer is the wrong one.

    Folding a sample that sits exactly on the closing edge into the bin below
    it is what a reader of the code would expect, and plotly drops it: with
    ``xbins`` running to 4, a sample at 4 is not on the chart. Announcing it
    would make that cell one fuller than the one drawn.
    """
    (layer,) = _layers(_histogram2d(x=x, y=[1, 1], **BINS))

    assert layer["data"]["points"] == expected


def test_a_z_shorter_than_the_samples_shortens_the_pairing() -> None:
    """A sample is an x, a y **and** a z when a `histfunc` reduces them.

    Measured: with `histfunc="avg"` and a `z` two long against four x and y,
    plotly uses two samples and leaves the rest of the grid unpainted. Before
    the pairing folded `z` in, this raised `ValueError: operands could not be
    broadcast together with shapes (4,) (2,)` out of the extraction and took
    the **whole figure** with it -- the failure `paired_arrays` documents for
    the 1-D path, arrived at again.
    """
    (layer,) = _layers(
        _histogram2d(
            x=[1, 1, 1, 3], y=[1, 1, 3, 1], z=[10, 30], histfunc="avg", **BINS
        )
    )

    assert layer["data"]["points"] == [[None, None], [20.0, None]]


def test_a_short_z_leaves_a_counting_trace_alone() -> None:
    """It shortens the pairing only where it is read.

    Measured: the same two-long `z` under the default `count` changes nothing
    and all four samples are counted, exactly as if no `z` were there. Folding
    it into the pairing unconditionally would drop two samples the chart draws.
    """
    (layer,) = _layers(_histogram2d(x=[1, 1, 1, 3], y=[1, 1, 3, 1], z=[10, 30], **BINS))

    assert layer["data"]["points"] == [[1.0, 0.0], [2.0, 1.0]]


def test_a_grid_of_one_cell_is_still_a_grid() -> None:
    """The smallest chart there is, and the one an off-by-one shows up in."""
    (layer,) = _layers(
        _histogram2d(
            x=[1.0, 1.5],
            y=[1.0, 1.5],
            xbins={"start": 0, "end": 2, "size": 2},
            ybins={"start": 0, "end": 2, "size": 2},
        )
    )

    assert layer["data"]["points"] == [[2.0]]
    assert layer["data"]["x"] == ["0 – 2"]
    assert layer["data"]["y"] == ["0 – 2"]


@pytest.mark.parametrize("histfunc", ["avg", "min", "max"])
@pytest.mark.parametrize(
    "histnorm", ["percent", "probability", "density", "probability density"]
)
def test_a_histnorm_brings_an_empty_cell_back_as_a_zero(
    histfunc: str, histnorm: str
) -> None:
    """Which is not the composition of the two rules, and is what plotly does.

    An `avg` of nothing has no answer, so plotly leaves that cell `NaN` --
    until any `histnorm` is set, and then it is a **0**. Measured across all
    three of these functions and all four norms. Rescaling evidently runs over
    the whole grid without carrying the "no answer" marker through.

    The one-dimensional path found exactly this and says so; deciding from
    `histfunc` alone would announce "no value" on a cell the chart paints.
    """
    (layer,) = _layers(
        _histogram2d(
            x=[1, 1, 1, 3],
            y=[1, 1, 3, 1],
            z=[10, 30, 20, 40],
            histfunc=histfunc,
            histnorm=histnorm,
            **BINS,
        )
    )

    assert layer["data"]["points"][0][1] == 0.0


def test_an_aggregate_without_a_histnorm_still_leaves_the_cell_unpainted() -> None:
    """The control for the pair above: the norm is what changes it."""
    (layer,) = _layers(
        _histogram2d(
            x=[1, 1, 1, 3], y=[1, 1, 3, 1], z=[10, 30, 20, 40], histfunc="avg", **BINS
        )
    )

    assert layer["data"]["points"][0][1] is None


def test_mismatched_x_and_y_pair_down_to_the_shorter() -> None:
    """A sample needs both coordinates, `histfunc` or no `histfunc`.

    The `z` tests above cover the aggregating path; this is the same question
    on the counting one, where `z` is not read at all.
    """
    (layer,) = _layers(_histogram2d(x=[1, 1], y=[1, 3, 1, 3], **BINS))

    assert layer["data"]["points"] == [[1.0, 0.0], [1.0, 0.0]]

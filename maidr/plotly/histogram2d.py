from __future__ import annotations

import math
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.heatmap import PlotlyHeatmapPlot
from maidr.plotly.histogram import (
    apply_histnorm,
    as_numeric,
    compute_bin_edges,
)
from maidr.plotly.plotly_plot import as_list

#: What separates a bin's two edges when it is named.
#:
#: A bin's label is its coordinate *range*, not its index or its centre: "a
#: count of 4" says nothing without "between -2.2 and -1.1", and the range is
#: what a sighted reader takes off the axis. r-maidr settled the same question
#: the same way for `geom_bin_2d` (xability/r-maidr#136).
_RANGE_SEPARATOR = " – "

#: How many significant figures a bin edge is named to. Plotly's automatic
#: widths are 1/2/5x10ⁿ, so an edge is usually short already; this only keeps
#: an explicit ``size`` of 0.1 from reaching the reader as
#: ``0.30000000000000004``.
_EDGE_FIGURES = 6

#: What the cells hold, said plainly, when the author named no colour bar.
#: ``histnorm`` decides the units when it is set -- measured, a ``histfunc``
#: of ``sum`` under ``histnorm="percent"`` still totals 100 -- so it wins over
#: the aggregate, and the aggregate wins over the default count.
_HISTNORM_NAMES = {
    "percent": "Percent",
    "probability": "Probability",
    "density": "Density",
    "probability density": "Probability density",
}
_HISTFUNC_NAMES = {
    "sum": "Sum",
    "avg": "Average",
    "min": "Minimum",
    "max": "Maximum",
}

#: ``histfunc`` values that reduce a second array rather than counting rows.
_AGGREGATING = frozenset(_HISTFUNC_NAMES)

#: Of those, the ones with no answer for a cell nothing landed in. Measured:
#: ``count`` and ``sum`` put a **0** there and plotly paints the cell, while
#: ``avg``/``min``/``max`` put ``NaN`` and plotly leaves it unpainted. So an
#: empty cell is emitted as ``None`` under these three -- there is no number
#: to announce -- and as ``0`` under the other two, which is what the chart
#: shows.
_UNDEFINED_WHEN_EMPTY = frozenset({"avg", "min", "max"})


class PlotlyHistogram2dPlot(PlotlyHeatmapPlot):
    """Extract data from a Plotly ``histogram2d`` trace.

    A two-dimensional histogram **is** a heatmap -- a rectangular grid of
    cells, each carrying a number -- which is why this extends
    :class:`~maidr.plotly.heatmap.PlotlyHeatmapPlot` and why the two share a
    selector: measured in Chromium, a ``histogram2d`` draws a single
    ``<image>`` into its subplot's ``heatmaplayer``, exactly as a
    ``go.Heatmap`` does.

    What differs is where the grid comes from. A heatmap is handed one; a
    ``histogram2d`` carries raw samples and lets plotly bin them in the
    browser, so reading it means binning them here on the same rule. That
    rule is the one py-maidr already matches for a one-dimensional histogram,
    with a single change: plotly bins a 2-D axis more coarsely, dividing by
    ``n**0.25`` rather than ``n**0.4``. Measured against the browser on eight
    axes across four figures, ``0.4`` matched none and ``0.25`` matched all
    eight.

    Sharing the selector shares its one limit: `.heatmaplayer image` names the
    first image on the subplot rather than this trace's, so a subplot holding
    two of them -- a `go.Heatmap` beside a `histogram2d`, or two of either --
    has both layers pointing at the first. That predates this class and
    applies to two heatmaps today; reading a second trace type into the same
    layer is what makes it reachable a second way. See #647.
    """

    def _extract_plot_data(self) -> dict:
        """Bin the samples and read the grid as a heatmap's.

        Returns
        -------
        dict
            ``{"points": [[...]], "x": [...], "y": [...]}`` with the rows
            top-first, which is the schema's order and what the core turns
            over again so its own row 0 is the bottom of the drawing.
            Empty when there is nothing to bin, which leaves the figure with
            no layer rather than an empty one (#636).
        """
        grid = _binned_grid(self._trace)
        if grid is None:
            return {}

        counts, x_labels, y_labels = grid

        # The schema's rows run top-first and the core reverses them, so the
        # bottom-first grid built above turns over -- unless the y axis is
        # drawn reversed and already counts from the top (#487). The columns
        # start at the left and turn over only when the x axis does (#489).
        # Both mirror `PlotlyHeatmapPlot`, whose grid this becomes.
        if not self._axis_runs_backwards(self._yaxis_name):
            counts.reverse()
            y_labels = list(reversed(y_labels))
        if self._axis_runs_backwards(self._xaxis_name):
            counts = [list(reversed(row)) for row in counts]
            x_labels = list(reversed(x_labels))

        return {
            MaidrKey.POINTS: counts,
            MaidrKey.X: x_labels,
            MaidrKey.Y: y_labels,
        }

    def _extract_axes_data(self) -> dict:
        """Name the third axis for what the cells actually hold.

        The parent emits a ``z`` only when the author titled the colour bar,
        which is right for a heatmap: its numbers are the author's and only
        they can say what they are. A ``histogram2d``'s numbers are computed,
        so their name is known here -- and leaving it unsaid would announce
        a grid of bare numbers with no word for what they count.

        The author's colour bar title still wins where there is one.
        """
        axes = super()._extract_axes_data()
        axes.setdefault(MaidrKey.Z, self._axis_config(label=self._cell_name()))
        return axes

    def _cell_name(self) -> str:
        """What one cell measures: the normalisation, the aggregate, or a count."""
        histnorm = self._trace.get("histnorm")
        if histnorm in _HISTNORM_NAMES:
            return _HISTNORM_NAMES[histnorm]
        if _reduces_values(self._trace):
            return _HISTFUNC_NAMES[str(self._trace.get("histfunc"))]
        return "Count"


def is_histogram2d_trace(trace: dict) -> bool:
    """Report whether a trace is a two-dimensional histogram."""
    return trace.get("type") == "histogram2d"


def _binned_grid(trace: dict) -> tuple[list[list], list[str], list[str]] | None:
    """Bin a trace's samples into the grid plotly draws.

    Returns
    -------
    tuple or None
        ``(counts, x_labels, y_labels)`` with ``counts`` **bottom-first**,
        matching plotly's own ``calcdata``. None when there is nothing to
        bin: a trace with no samples draws no grid at all -- measured, its
        ``calcdata`` entry carries no ``z`` -- so there is nothing to read.
    """
    x = as_numeric(as_list(trace.get("x")))
    y = as_numeric(as_list(trace.get("y")))

    # A sample is an x, a y, and -- when a `histfunc` reduces them -- a z, so
    # the shortest of those decides how many samples there are. Measured both
    # ways: with `histfunc="avg"` and a `z` two long against four x and y,
    # plotly uses **two** samples and leaves the rest of the grid unpainted;
    # with the default `count`, the same short `z` changes nothing and all
    # four are counted. So `z` shortens the pairing only when it is read.
    #
    # Truncating here rather than at the point of use, which is the mistake
    # `paired_arrays` in `histogram.py` documents for the 1-D path: a late
    # truncation raised out of a rendering path for a figure plotly draws
    # without complaint. Here it was a `ValueError` from numpy broadcasting
    # a mask of four against an array of two, which took the whole figure.
    values = _values(trace)
    aggregating = _reduces_values(trace)

    paired = min(x.size, y.size)
    if aggregating and values is not None:
        paired = min(paired, values.size)
        values = values[:paired]
    x, y = x[:paired], y[:paired]
    # A sample missing either coordinate is not on the chart. Measured: one
    # `None` among three x values drops that pair rather than placing it
    # anywhere, so counting it would announce a cell one fuller than drawn.
    #
    # This is also what answers a trace with no samples at all: nothing is
    # usable, so nothing is binned. Said once rather than twice, since an
    # empty array and an array of nothing usable are the same chart -- one
    # plotly draws no grid for, its `calcdata` entry carrying no `z`.
    inside = np.isfinite(x) & np.isfinite(y)
    if not inside.any():
        return None

    x_edges = compute_bin_edges(
        x[inside], trace.get("xbins"), trace.get("nbinsx"), is_2d=True
    )
    y_edges = compute_bin_edges(
        y[inside], trace.get("ybins"), trace.get("nbinsy"), is_2d=True
    )
    if len(x_edges) < 2 or len(y_edges) < 2:
        return None

    columns, rows = len(x_edges) - 1, len(y_edges) - 1
    column_of = _bin_of(x, x_edges)
    row_of = _bin_of(y, y_edges)
    # A sample outside every bin is dropped rather than clipped into an edge
    # one -- measured on an explicit `xbins` with a value past its `end`.
    placed = inside & (column_of >= 0) & (row_of >= 0)

    histfunc = trace.get("histfunc")
    if aggregating and values is not None:
        cells = _aggregate(
            row_of, column_of, placed, values, rows, columns, str(histfunc)
        )
    else:
        # Plotly falls back to counting when an aggregating `histfunc` has no
        # `z` to reduce -- measured, `histfunc="sum"` without one draws the
        # same grid as the default.
        cells = _count(row_of, column_of, placed, rows, columns)
        histfunc = "count"

    histnorm = trace.get("histnorm")
    cells = _normalised(cells, histnorm, x_edges, y_edges)
    counts = _as_payload(cells, histfunc, histnorm)

    return (
        counts,
        [_bin_label(x_edges, index) for index in range(columns)],
        [_bin_label(y_edges, index) for index in range(rows)],
    )


def _values(trace: dict) -> np.ndarray | None:
    """The ``z`` array an aggregating ``histfunc`` reduces, or None."""
    declared = as_list(trace.get("z"))
    return as_numeric(declared) if declared else None


def _reduces_values(trace: dict) -> bool:
    """Whether this trace's ``histfunc`` has a ``z`` to reduce.

    Asked in two places -- to decide what a cell measures and to decide
    whether ``z`` shortens the sample pairing -- so it is one rule rather
    than two that could drift apart.
    """
    return trace.get("histfunc") in _AGGREGATING and bool(as_list(trace.get("z")))


def _bin_of(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Which bin each value falls in, or ``-1`` for one outside every bin.

    Every bin is half-open, ``[lo, hi)``, **including the last** -- measured
    rather than assumed, because the obliging thing to do is fold a value
    sitting exactly on the final edge into the bin below it, and plotly does
    not: with ``xbins`` running to 4, a sample at 4 is dropped, while one at
    an interior edge of 2 counts in ``[2, 4)`` and one at the opening edge of
    0 counts in ``[0, 2)``. Folding it in would announce a cell one fuller
    than the chart draws.
    """
    with np.errstate(invalid="ignore"):
        index = np.digitize(values, edges) - 1
    return np.where((index < 0) | (index >= len(edges) - 1), -1, index)


def _count(
    row_of: np.ndarray,
    column_of: np.ndarray,
    placed: np.ndarray,
    rows: int,
    columns: int,
) -> list[list[float | None]]:
    """How many samples landed in each cell, bottom row first.

    Counted with ``bincount`` over the flattened cell index rather than a
    Python loop over the samples, so the work scales with the *grid* rather
    than with the sample count -- which is the shape the one-dimensional
    `aggregate_bins` already has, and the one that matters on a scatter of a
    hundred thousand points.
    """
    flat = row_of[placed] * columns + column_of[placed]
    tally = np.bincount(flat.astype(int), minlength=rows * columns)
    return [
        [float(tally[row * columns + column]) for column in range(columns)]
        for row in range(rows)
    ]


def _aggregate(
    row_of: np.ndarray,
    column_of: np.ndarray,
    placed: np.ndarray,
    values: np.ndarray,
    rows: int,
    columns: int,
    histfunc: str,
) -> list[list[float | None]]:
    """Reduce each cell's values the way ``histfunc`` does.

    A value that is not a number is not an observation rather than an
    observation of zero, which is what :func:`~maidr.plotly.histogram.as_numeric`
    turns it into and what is dropped here -- the same reading the
    one-dimensional path settled (#405).
    """
    # `values` arrives the same length as `placed`, paired down by the caller.
    usable = placed & np.isfinite(values)
    gathered: dict[tuple[int, int], list[float]] = {}
    for row, column, value in zip(row_of[usable], column_of[usable], values[usable]):
        gathered.setdefault((int(row), int(column)), []).append(float(value))

    reduce = {
        "sum": sum,
        "avg": lambda held: sum(held) / len(held),
        "min": min,
        "max": max,
    }[histfunc]

    cells: list[list[float | None]] = [[None] * columns for _ in range(rows)]
    for (row, column), held in gathered.items():
        cells[row][column] = float(reduce(held))
    return cells


def _normalised(
    cells: list[list[float | None]],
    histnorm: str | None,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
) -> list[list[float | None]]:
    """Rescale the cells the way ``histnorm`` does.

    The one-dimensional rule with the bin's **area** where it uses the bin's
    width -- measured against the browser for all four forms on a grid of
    unequal x and y widths: ``percent`` and ``probability`` divide by the
    grand total, ``density`` by the cell's area, and ``probability density``
    by both.
    """
    if not histnorm:
        return cells

    rows, columns = len(cells), len(cells[0]) if cells else 0
    widths = np.array(
        [
            [
                (x_edges[column + 1] - x_edges[column])
                * (y_edges[row + 1] - y_edges[row])
                for column in range(columns)
            ]
            for row in range(rows)
        ],
        dtype=float,
    )
    held = np.array(
        [[0.0 if value is None else value for value in row] for row in cells],
        dtype=float,
    )
    scaled = apply_histnorm(held.reshape(-1), widths.reshape(-1), histnorm)
    scaled = scaled.reshape(held.shape)

    return [
        [None if cells[row][column] is None else float(scaled[row][column])
         for column in range(columns)]
        for row in range(rows)
    ]


def _as_payload(
    cells: list[list[float | None]], histfunc: str, histnorm: str | None
) -> list[list[float | None]]:
    """Turn a cell nothing landed in into what plotly shows there.

    ``count`` and ``sum`` paint a zero; ``avg``, ``min`` and ``max`` leave the
    cell unpainted, and there is no number to announce for it.

    **Unless a ``histnorm`` is set, which brings the empty cells back as
    zeros.** Measured across all three of those functions and all four norms:
    ``avg`` alone leaves the cell ``NaN``, and ``avg`` with any ``histnorm``
    puts a **0** there. Rescaling evidently runs over the whole grid and does
    not carry the "no answer" marker through, so the composition is not simply
    one step after the other. The one-dimensional path found exactly this and
    says so in `PlotlyHistogramPlot._extract_plot_data`; the same rule, on a
    grid.
    """
    undefined = histfunc in _UNDEFINED_WHEN_EMPTY and not histnorm
    empty: float | None = None if undefined else 0.0
    return [[empty if value is None else value for value in row] for row in cells]


def _bin_label(edges: np.ndarray, index: int) -> str:
    """Name one bin by the range it covers."""
    return (
        f"{_edge(edges[index])}{_RANGE_SEPARATOR}{_edge(edges[index + 1])}"
    )


def _edge(value: Any) -> str:
    """Write one edge without the floating-point tail an exact width leaves."""
    number = float(value)
    if not math.isfinite(number):
        return str(value)
    rounded = float(f"{number:.{_EDGE_FIGURES}g}")
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)

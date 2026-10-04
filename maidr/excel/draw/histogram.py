"""Histograms and Pareto charts, binned as Excel bins them.

The part keeps the values a histogram is drawn from, not its bins, so the bins
are worked out here: Scott's rule from the smallest value, or the width or
count the chart sets, each bin holding its right end.
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from maidr.excel.draw.common import (
    category_labels,
    draw_grid,
    legend_place,
    name_axis,
    plain_axes,
)
from maidr.excel.spec import Binning, ChartSpec, Group, Series, sums_categories

#: The most bins a histogram is drawn with, whatever its bin width says.
_MAX_BINS = 1_000


def excel_bins(values: list[float], binning: Binning) -> tuple[np.ndarray, list[int]]:
    """
    Bin values as an Excel histogram does.

    Parameters
    ----------
    values : list of float
        The values, blanks left out.
    binning : Binning
        What the chart says about its bins.

    Returns
    -------
    edges : numpy.ndarray
        The bin edges, the underflow and overflow bins included when the chart
        has them; the underflow bin starts at the smallest value and the
        overflow bin ends at the largest.
    counts : list of int
        How many values each bin holds.

    Notes
    -----
    Bins start at the smallest value, or at the underflow, and are as wide as
    the chart says, as many as it says, or, by default, as Scott's normal
    reference rule says: ``3.5 * stdev / n ** (1/3)``. A bin includes its
    right end, ``(a, b]``, and the first its left end too, unless the chart
    closes them on the left.
    """
    data = np.sort(np.asarray(values, dtype=float))
    low, high = float(data[0]), float(data[-1])
    start = binning.underflow if binning.underflow is not None else low
    stop = binning.overflow if binning.overflow is not None else high
    if binning.size is not None:
        width = binning.size
    elif binning.count is not None:
        width = (stop - start) / binning.count
    else:
        spread = float(np.std(data, ddof=1)) if len(data) > 1 else 0.0
        width = 3.5 * spread / len(data) ** (1 / 3)
    if not math.isfinite(width) or width <= 0:
        width = 1.0
    span = stop - start
    if span > 0 and not span / width <= _MAX_BINS:
        # More bins than are ever drawn: as many as are, each wider.
        width = span / _MAX_BINS
    count = max(1, min(_MAX_BINS, math.ceil(span / width - 1e-9))) if span > 0 else 1
    edges = start + width * np.arange(count + 1)
    if binning.overflow is None:
        # Rounding must not leave the largest value past the last edge.
        edges[-1] = max(edges[-1], stop)
    else:
        # The bins end where the overflow begins.
        edges[-1] = stop

    right = binning.closed != "l"
    inner = list(np.histogram(data, bins=edges)[0]) if not right else []
    if right:
        # (a, b], with the first bin taking its left end as well.
        upper = np.searchsorted(data, edges, side="right")
        inner = [int(upper[1] - np.searchsorted(data, edges[0], side="left"))]
        inner += [int(upper[i + 1] - upper[i]) for i in range(1, count)]
    counts = [int(c) for c in inner]
    if binning.underflow is not None:
        below = int(np.sum(data <= start)) if right else int(np.sum(data < start))
        if right:
            # The first bin no longer takes its left end: that is underflow.
            counts[0] -= int(np.sum(data == start))
        edges = np.concatenate([[low if low < start else start - width], edges])
        counts = [below] + counts
    if binning.overflow is not None:
        above = int(np.sum(data > stop)) if right else int(np.sum(data >= stop))
        if not right:
            counts[-1] -= int(np.sum(data == stop))
        edges = np.concatenate([edges, [high if high > stop else stop + width]])
        counts = counts + [above]
    return edges, counts


def bin_labels(edges: np.ndarray, binning: Binning, places: int) -> list[str]:
    """
    The bins as Excel labels them: ``[1, 5]``, ``(5, 9]``, ``≤1``, ``>9``.

    Parameters
    ----------
    edges : numpy.ndarray
        The bin edges, as :func:`excel_bins` returns them.
    binning : Binning
        What the chart says about its bins.
    places : int
        The most decimals an edge is written with.

    Returns
    -------
    list of str
        One label per bin. A bracket says whether a bin holds its end: the
        first of right-closed bins holds its left end unless an underflow bin
        took it, and the last of left-closed ones its right end unless an
        overflow bin did.
    """
    right = binning.closed != "l"
    under = binning.underflow is not None
    over = binning.overflow is not None
    first = 1 if under else 0
    last = len(edges) - 2 if over else len(edges) - 1
    labels = []
    for i in range(len(edges) - 1):
        a, b = _edge(edges[i], places), _edge(edges[i + 1], places)
        if i < first:
            labels.append(f"≤{b}" if right else f"<{b}")
        elif i >= last:
            labels.append(f">{a}" if right else f"≥{a}")
        elif right:
            held = i == first and not under
            labels.append(f"[{a}, {b}]" if held else f"({a}, {b}]")
        else:
            held = i == last - 1 and not over
            labels.append(f"[{a}, {b}]" if held else f"[{a}, {b})")
    return labels


def _rounded(edges: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Bin edges to three significant figures of the bins' width, as they are
    drawn and read, and how many decimals that is; the values were counted
    against the exact edges.
    """
    widths = np.diff(edges)
    positive = widths[widths > 0]
    width = float(np.min(positive)) if positive.size else 1.0
    places = min(12, max(0, 2 - math.floor(math.log10(width))))
    return np.round(edges, places), places


def _edge(value: float, places: int) -> str:
    """A bin edge as its label writes it: no more decimals than it has."""
    text = f"{value:.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _by_category(s: Series) -> tuple[list[str], list[float]]:
    """Each category once, in the order it first appears, its values summed."""
    totals: dict[str, float] = {}
    for label, value in zip(category_labels(s.categories, unique=False), s.values):
        if value is not None:
            totals[label] = totals.get(label, 0.0) + value
    return list(totals), list(totals.values())


def draw_histogram(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """A histogram's first series, binned as Excel bins it, or summed by
    category where the chart says so."""
    ax = plain_axes(fig)
    s = group.series[0]
    binning = group.binning or Binning()
    values = [v for v in s.values if v is not None]
    if sums_categories(group.binning, s):
        names, totals = _by_category(s)
        ax.bar(names, totals, 0.95, color=s.color, label=s.name)
    elif values:
        edges, counts = excel_bins(values, binning)
        edges, places = _rounded(edges)
        centers = (edges[:-1] + edges[1:]) / 2
        _, _, bars = ax.hist(
            centers,
            bins=edges,
            weights=counts,
            color=s.color,
            edgecolor="white",
            label=s.name,
        )
        # matplotlib places each bar by its center, which leaves rounding in
        # the edges a reader is told; the bars are put back on them.
        for bar, start, stop in zip(bars, edges[:-1], edges[1:]):
            bar.set_x(start)
            bar.set_width(stop - start)
        ax.set_xticks(centers, bin_labels(edges, binning, places))
        if len(centers) > 6:
            ax.tick_params(axis="x", labelrotation=45)
    x, y = group.x_axis, group.y_axis
    name_axis(ax.xaxis, x.label if x else None, s.name or "Bin", bool(x and x.title))
    name_axis(ax.yaxis, y.label if y else None, "Count", bool(y and y.title))
    draw_grid(ax)
    return ax


def draw_pareto(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A Pareto chart: the bins, or the categories with their values summed,
    largest first, and the running share of the total on a second axis.
    """
    ax = plain_axes(fig)
    s = group.series[0]
    binning = group.binning or Binning()
    if sums_categories(group.binning, s):
        names, totals = _by_category(s)
    else:
        values = [v for v in s.values if v is not None]
        if not values:
            return ax
        edges, counts = excel_bins(values, binning)
        rounded, places = _rounded(edges)
        names = bin_labels(rounded, binning, places)
        totals = [float(c) for c in counts]
    if not totals:
        return ax
    order = sorted(range(len(totals)), key=lambda i: -totals[i])
    names = [names[i] for i in order]
    totals = [totals[i] for i in order]
    ax.bar(names, totals, color=s.color, label=s.name)
    whole = sum(totals) or 1.0
    shares = list(np.cumsum(totals) / whole)
    twin = ax.twinx()
    twin.spines["top"].set_visible(False)
    # Unlabelled, so the reader is not told the line's name twice over: as
    # its value and as its group.
    line = twin.plot(names, shares, color=_second_color(group), marker="o")[0]
    twin.set_ylim(0, 1.05)
    twin.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    x, y = group.x_axis, group.y_axis
    name_axis(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    name_axis(ax.yaxis, y.label if y else None, s.name or "Value", bool(y and y.title))
    name_axis(twin.xaxis, x.label if x else None, "Category", False)
    name_axis(twin.yaxis, _SHARE, _SHARE, False)
    if len(names) > 6:
        ax.tick_params(axis="x", labelrotation=45)
    draw_grid(ax)
    if spec.legend is not None:
        bars = ax.get_legend_handles_labels()
        ax.legend(
            bars[0] + [line],
            bars[1] + [_SHARE],
            frameon=False,
            **legend_place(spec),
        )
    return ax


def _second_color(group: Group) -> str:
    """The Pareto line's color, which the reader keeps as a second series."""
    if len(group.series) > 1 and group.series[1].color:
        return group.series[1].color
    return "#ED7D31"


#: What the reader hears a Pareto chart's line called.
_SHARE = "Cumulative percentage"

"""Draw an Excel 2016 chart with matplotlib.

A histogram, a Pareto chart and a box and whisker chart are drawn through the
``Axes`` calls py-maidr reads -- ``hist``, ``bar`` and ``plot``, ``bxp`` --
with the bins and the quartiles worked out as Excel works them out, since the
part keeps only the values they are worked from. A waterfall, a funnel, a
treemap, a sunburst and a map have no such call; they are drawn from plain
artists and described by the layers of :mod:`maidr.excel.layers`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle, Wedge
from matplotlib.ticker import PercentFormatter

from maidr.core.enum import PlotType
from maidr.excel.chartxml import Binning, ChartSpec, Group, Series, sums_categories
from maidr.excel.draw import (
    _GRID,
    _LEGEND,
    BLANK,
    _label,
    _labels,
    new_figure,
    number_formatter,
)
from maidr.excel.layers import each_mark, register
from maidr.util.caller_warning import warn_at_caller

#: What a reader is told each Excel 2016 chart type is called.
NAMES = {
    "histogram": "histogram",
    "pareto": "Pareto",
    "box": "box and whisker",
    "waterfall": "waterfall",
    "funnel": "funnel",
    "treemap": "treemap",
    "sunburst": "sunburst",
    "region": "map",
}

#: The most bins a histogram is drawn with, whatever its bin width says.
_MAX_BINS = 1_000


def draw_ex(spec: ChartSpec, *, aspect: float | None, where: str) -> Figure:
    """
    Draw an Excel 2016 chart.

    Parameters
    ----------
    spec : ChartSpec
        The chart, as :func:`maidr.excel.chartex.read_chartex` read it.
    aspect : float or None
        The chart's height over its width on the sheet, if known.
    where : str
        How warnings name the chart.

    Returns
    -------
    matplotlib.figure.Figure
        A figure not managed by pyplot, with its layers registered with maidr.
    """
    fig = new_figure(aspect)
    group = spec.groups[0]
    if group.kind not in ("box", "pareto") and len(group.series) > 1:
        warn_at_caller(
            f"maidr reads the first series of the {NAMES[group.kind]} chart "
            f"{where}; the other {len(group.series) - 1} are left out."
        )
    ax = _DRAW[group.kind](fig, group, spec, where)
    if spec.title:
        ax.set_title(spec.title)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------
# Histogram and Pareto
# --------------------------------------------------------------------------


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


def _number(value: float) -> str:
    return f"{value:.4g}" if not float(value).is_integer() else str(int(value))


def _by_category(s: Series) -> tuple[list[str], list[float]]:
    """Each category once, in the order it first appears, its values summed."""
    totals: dict[str, float] = {}
    for label, value in zip(_labels(s.categories, unique=False), s.values):
        if value is not None:
            totals[label] = totals.get(label, 0.0) + value
    return list(totals), list(totals.values())


def _histogram(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    ax = _plain_axes(fig)
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
    _label(ax.xaxis, x.label if x else None, s.name or "Bin", bool(x and x.title))
    _label(ax.yaxis, y.label if y else None, "Count", bool(y and y.title))
    _grid(ax)
    return ax


def _pareto(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A Pareto chart: the bins, or the categories with their values summed,
    largest first, and the running share of the total on a second axis.
    """
    ax = _plain_axes(fig)
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
    _label(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    _label(ax.yaxis, y.label if y else None, s.name or "Value", bool(y and y.title))
    _label(twin.xaxis, x.label if x else None, "Category", False)
    _label(twin.yaxis, _SHARE, _SHARE, False)
    if len(names) > 6:
        ax.tick_params(axis="x", labelrotation=45)
    _grid(ax)
    if spec.legend is not None:
        bars = ax.get_legend_handles_labels()
        ax.legend(
            bars[0] + [line],
            bars[1] + [_SHARE],
            frameon=False,
            **_legend_place(spec),
        )
    return ax


# --------------------------------------------------------------------------
# Box and whisker
# --------------------------------------------------------------------------


def quartile(values: list[float], fraction: float, method: str) -> float:
    """
    A quartile as Excel's ``QUARTILE.EXC`` or ``QUARTILE.INC`` finds it.

    Parameters
    ----------
    values : list of float
        The values, sorted.
    fraction : float
        ``0.25``, ``0.5`` or ``0.75``.
    method : str
        ``"exclusive"`` or ``"inclusive"`` of the median.

    Returns
    -------
    float
        The value at that rank, interpolated between its neighbors.
    """
    n = len(values)
    rank = (n - 1) * fraction if method == "inclusive" else (n + 1) * fraction - 1
    rank = min(max(rank, 0.0), n - 1.0)
    low = int(math.floor(rank))
    high = min(low + 1, n - 1)
    return values[low] + (rank - low) * (values[high] - values[low])


def box_stats(values: list[float], method: str, label: str) -> dict[str, Any]:
    """
    A box's statistics as Excel draws them: its quartiles, whiskers reaching
    the furthest values within one and a half interquartile ranges of the
    box, the values beyond them as outliers, and the mean.
    """
    data = sorted(values)
    q1 = quartile(data, 0.25, method)
    q3 = quartile(data, 0.75, method)
    reach = 1.5 * (q3 - q1)
    inside = [v for v in data if q1 - reach <= v <= q3 + reach]
    return {
        "label": label,
        "q1": q1,
        "med": quartile(data, 0.5, method),
        "q3": q3,
        "whislo": inside[0] if inside else q1,
        "whishi": inside[-1] if inside else q3,
        "fliers": [v for v in data if v < q1 - reach or v > q3 + reach],
        "mean": sum(data) / len(data),
    }


def _box(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    One box per category and series, clustered by category as Excel draws
    them, each series a layer named after it.
    """
    ax = _plain_axes(fig)
    series = group.series
    # Each series' values by category, and the categories in the order they
    # first appear in any series.
    grouped = []
    for s in series:
        found: dict[str, list[float]] = {}
        for c, v in zip(s.categories, s.values):
            if v is not None and c is not None:
                found.setdefault(c, []).append(v)
        grouped.append(found)
    categories = list(dict.fromkeys(c for found in grouped for c in found))
    by_category = bool(categories)
    if not by_category:
        categories = [s.name or f"Series {i + 1}" for i, s in enumerate(series)]
    width = 0.8 / (len(series) if by_category else 1)
    handles = []
    for k, (s, found) in enumerate(zip(series, grouped)):
        stats, positions = [], []
        for j, category in enumerate(categories):
            if by_category:
                values = found.get(category, [])
                position = j + (k - (len(series) - 1) / 2) * width
            else:
                values = [v for v in s.values if v is not None] if j == k else []
                position = j
            if values:
                stats.append(box_stats(values, group.quartiles, category))
                positions.append(position)
        if not stats:
            continue
        color = s.color or f"C{k}"
        ax.bxp(
            stats,
            positions=positions,
            widths=width * 0.8,
            patch_artist=True,
            showmeans=group.mean_marker,
            boxprops={"facecolor": color, "edgecolor": "#404040"},
            medianprops={"color": "#404040"},
            whiskerprops={"color": "#404040"},
            capprops={"color": "#404040"},
            meanprops={
                "marker": "x",
                "markeredgecolor": "#404040",
                "markerfacecolor": "#404040",
            },
            flierprops={
                "marker": "o",
                "markerfacecolor": "none",
                "markeredgecolor": color,
            },
        )
        if s.name:
            handles.append(Patch(facecolor=color, edgecolor="#404040", label=s.name))
    ax.set_xticks(range(len(categories)), categories)
    ax.set_xlim(-0.6, len(categories) - 0.4)
    x, y = group.x_axis, group.y_axis
    _label(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    _label(ax.yaxis, y.label if y else None, "Value", bool(y and y.title))
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    _grid(ax)
    if by_category and len(handles) > 1:
        # The legend is also what names each series' layer: a box layer is
        # named by the legend entry of its color.
        ax.legend(handles=handles, frameon=False, **_legend_place(spec))
    return ax


# --------------------------------------------------------------------------
# Waterfall and funnel
# --------------------------------------------------------------------------


def _waterfall(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A waterfall: each step from the running total to the next, and each
    point set as a total from zero to its own value, which the steps after it
    carry on from.
    """
    ax = _plain_axes(fig)
    s = group.series[0]
    labels = _labels(s.categories, unique=False)
    colors = dict(s.point_colors)
    totals = set(group.totals)
    steps = []
    running = 0.0
    for index, (label, value) in enumerate(zip(labels, s.values)):
        if value is None:
            continue
        if index in totals:
            start, end, kind = 0.0, value, "total"
        else:
            start, end = running, running + value
            kind = "decrease" if value < 0 else "increase"
        running = end
        steps.append((index, label, start, end, kind))
    positions = np.arange(len(steps), dtype=float)
    bars = PatchCollection(
        [
            Rectangle((x - 0.35, min(start, end)), 0.7, abs(end - start))
            for x, (_, _, start, end, _) in zip(positions, steps)
        ],
        facecolor=[colors.get(index) or s.color or "C0" for index, *_ in steps],
        edgecolor="none",
        zorder=3,
    )
    ax.add_collection(bars)
    ax.add_collection(
        LineCollection(
            [
                [(x + 0.35, step[3]), (x + 0.65, step[3])]
                for x, step in zip(positions[:-1], steps[:-1])
            ],
            colors="#7F7F7F",
            linewidths=0.8,
            zorder=2,
        )
    )
    ax.set_xticks(positions, [label for _, label, *_ in steps])
    ax.set_xlim(-0.6, len(steps) - 0.4)
    ax.autoscale_view(scalex=False)
    ax.axhline(0, color="#7F7F7F", linewidth=0.8, zorder=1)
    y = group.y_axis
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    x = group.x_axis
    _label(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    _label(ax.yaxis, y.label if y else None, s.name or "Value", bool(y and y.title))
    _grid(ax)
    if spec.legend is not None:
        kinds = {kind: colors.get(index) for index, *_, kind in steps}
        handles = [
            Patch(facecolor=kinds[kind] or s.color or "C0", label=kind.capitalize())
            for kind in ("increase", "decrease", "total")
            if kind in kinds
        ]
        ax.legend(handles=handles, frameon=False, **_legend_place(spec))
    register(
        ax,
        PlotType.WATERFALL,
        labels={"x": None, "y": None},
        data=[
            {"x": label, "start": start, "end": end, "delta": end - start, "kind": kind}
            for _, label, start, end, kind in steps
        ],
        selectors=each_mark(bars),
        formats={"y": "y"},
    )
    return ax


def _funnel(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """A funnel: one bar per stage, centered, the first at the top."""
    ax = fig.add_subplot()
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    s = group.series[0]
    stages = [
        (label, value)
        for label, value in zip(_labels(s.categories, unique=False), s.values)
        if value is not None
    ]
    widest = max((abs(v) for _, v in stages), default=1.0) or 1.0
    colors = dict(s.point_colors)
    bars = PatchCollection(
        [
            Rectangle((-abs(v) / 2, -k - 0.4), abs(v), 0.8)
            for k, (_, v) in enumerate(stages)
        ],
        facecolor=[colors.get(k) or s.color or "C0" for k in range(len(stages))],
        edgecolor="none",
    )
    ax.add_collection(bars)
    y = group.y_axis
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.xaxis.set_major_formatter(formatter)
    for k, (_, value) in enumerate(stages):
        ax.text(
            0,
            -k,
            formatter(value) if formatter is not None else _number(value),
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
        )
    ax.set_yticks(-np.arange(len(stages), dtype=float), [n for n, _ in stages])
    ax.set_xlim(-widest * 0.55, widest * 0.55)
    ax.set_ylim(-len(stages) + 0.4, 0.6)
    ax.xaxis.set_visible(False)
    value_name = (y.label if y else None) or s.name or "Value"
    category_name = group.category_name or "Stage"
    _label(ax.xaxis, value_name, "Value", False)
    _label(ax.yaxis, category_name, "Stage", False)
    register(
        ax,
        PlotType.FUNNEL,
        labels={"x": value_name, "y": category_name},
        data=[{"x": value, "y": label} for label, value in stages],
        selectors=each_mark(bars),
        formats={"x": "x"},
        extra={"orientation": "horz"},
    )
    return ax


# --------------------------------------------------------------------------
# Treemap and sunburst
# --------------------------------------------------------------------------


@dataclass
class _Node:
    """One node of a treemap's or a sunburst's hierarchy."""

    name: str
    path: tuple[str, ...]
    declared: float | None = None
    color: str | None = None
    children: dict[str, _Node] = field(default_factory=dict)

    @property
    def size(self) -> float:
        """Its area: its own value, or its children's, whichever is larger."""
        below = sum(child.size for child in self.children.values())
        own = self.declared if self.declared is not None and self.declared > 0 else 0
        return max(own, below)

    def walk(self) -> list[_Node]:
        """It and every node below it, each before its children."""
        out = [self]
        for child in self.children.values():
            out.extend(child.walk())
        return out


def _tree(s: Series) -> list[_Node]:
    """The hierarchy a series' paths and values make, its top level first."""
    top: dict[str, _Node] = {}
    colors = dict(s.point_colors)
    for index, (path, value) in enumerate(zip(s.paths, s.values)):
        if not path:
            continue
        level = top
        node = None
        for depth, name in enumerate(path):
            node = level.get(name)
            if node is None:
                node = level[name] = _Node(name, tuple(path[:depth]))
            node.color = node.color or colors.get(index) or s.color
            level = node.children
        if node is not None and value is not None:
            node.declared = (node.declared or 0.0) + value
    return list(top.values())


def _hierarchy_points(nodes: list[_Node]) -> list[dict[str, Any]]:
    """Every node, each before its children, as a hierarchy layer reads it."""
    points = []
    for node in (n for root in nodes for n in root.walk()):
        point: dict[str, Any] = {"x": node.name}
        if node.declared is not None:
            point["y"] = node.declared
        if node.path:
            point["path"] = list(node.path)
        points.append(point)
    return points


def squarify(
    sizes: list[float], x: float, y: float, width: float, height: float
) -> list[tuple[float, float, float, float]]:
    """
    Lay sizes out in a rectangle as near-square tiles, the squarified way.

    Parameters
    ----------
    sizes : list of float
        The tiles' sizes, largest first.
    x, y, width, height : float
        The rectangle, ``(x, y)`` its lower left corner.

    Returns
    -------
    list of tuple
        ``(x, y, width, height)`` of each tile, in the order of ``sizes``,
        laid out from the top left.
    """
    total = sum(sizes)
    if total <= 0 or width <= 0 or height <= 0:
        return [(x, y, 0.0, 0.0) for _ in sizes]
    scale = width * height / total
    areas = [s * scale for s in sizes]
    tiles = []
    top = y + height
    while areas:
        if areas[0] <= 0:
            # Sorted largest first: what is left has no area to lay out.
            tiles.extend((x, top, 0.0, 0.0) for _ in areas)
            break
        side = min(width, height)
        row = [areas[0]]
        while len(row) < len(areas) and _worst(row + [areas[len(row)]], side) <= _worst(
            row, side
        ):
            row.append(areas[len(row)])
        areas = areas[len(row) :]
        thickness = sum(row) / side
        if width >= height:
            # A column down the left edge.
            down = top
            for area in row:
                tall = area / thickness
                tiles.append((x, down - tall, thickness, tall))
                down -= tall
            x += thickness
            width -= thickness
        else:
            # A row along the top edge.
            across = x
            for area in row:
                wide = area / thickness
                tiles.append((across, top - thickness, wide, thickness))
                across += wide
            top -= thickness
            height -= thickness
    return tiles


def _worst(row: list[float], side: float) -> float:
    total = sum(row)
    if total <= 0 or min(row) <= 0:
        return math.inf
    return max(side * side * max(row) / total**2, total**2 / (side * side * min(row)))


def _treemap(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A treemap: every node a rectangle sized by its value, its children tiled
    inside it, each branch in its own color.
    """
    ax = fig.add_subplot()
    ax.set_axis_off()
    s = group.series[0]
    roots = _tree(s)
    places: dict[int, tuple[float, float, float, float]] = {}

    def lay_out(nodes: list[_Node], box: tuple[float, float, float, float]) -> None:
        ranked = sorted(nodes, key=lambda n: -n.size)
        for node, tile in zip(ranked, squarify([n.size for n in ranked], *box)):
            places[id(node)] = tile
            if node.children:
                x, y, w, h = tile
                pad = min(w, h) * 0.02
                lay_out(
                    list(node.children.values()),
                    (x + pad, y + pad, w - 2 * pad, h - 2 * pad),
                )

    lay_out(roots, (0.0, 0.0, 1.0, 1.0))
    nodes = [n for root in roots for n in root.walk()]
    tiles = PatchCollection(
        [Rectangle(places[id(n)][:2], *places[id(n)][2:]) for n in nodes],
        facecolor=["none" if n.children else (n.color or "C0") for n in nodes],
        edgecolor="white",
        linewidth=[2.5 if n.children else 1.0 for n in nodes],
    )
    ax.add_collection(tiles)
    for n in nodes:
        x, y, w, h = places[id(n)]
        if n.children and not n.path:
            ax.text(
                x + 0.01,
                y + h - 0.01,
                n.name,
                ha="left",
                va="top",
                fontweight="bold",
                color="white",
                fontsize=9,
            )
        elif not n.children and w > 0.06 and h > 0.04:
            ax.text(
                x + w / 2,
                y + h / 2,
                n.name,
                ha="center",
                va="center",
                color="white",
                fontsize=8,
                clip_on=True,
            )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _hierarchy_layer(ax, PlotType.TREEMAP, group, s, roots, tiles)
    return ax


def _sunburst(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A sunburst: the top level of the hierarchy in the inner ring, each level
    below it in the next ring out, clockwise from the top, each node's arc in
    proportion to its value.
    """
    ax = fig.add_subplot()
    ax.set_aspect("equal")
    ax.set_axis_off()
    s = group.series[0]
    roots = _tree(s)
    depth = max((len(n.path) + 1 for r in roots for n in r.walk()), default=1)
    hole, ring = 0.2, 0.8 / depth
    arcs: dict[int, tuple[float, float]] = {}

    def lay_out(nodes: list[_Node], start: float, sweep: float) -> None:
        total = sum(n.size for n in nodes) or 1.0
        for node in nodes:
            share = sweep * node.size / total
            arcs[id(node)] = (start - share, start)
            lay_out(list(node.children.values()), start, share)
            start -= share

    lay_out(roots, 90.0, 360.0)
    nodes = [n for root in roots for n in root.walk()]
    wedges = PatchCollection(
        [
            Wedge(
                (0, 0),
                hole + ring * (len(n.path) + 1),
                *arcs[id(n)],
                width=ring,
            )
            for n in nodes
        ],
        facecolor=[_tint(n.color or "C0", len(n.path)) for n in nodes],
        edgecolor="white",
        linewidth=1.0,
    )
    ax.add_collection(wedges)
    for n in nodes:
        low, high = arcs[id(n)]
        if high - low < 12:
            continue
        middle = math.radians((low + high) / 2)
        radius = hole + ring * (len(n.path) + 0.5)
        ax.text(
            radius * math.cos(middle),
            radius * math.sin(middle),
            n.name,
            ha="center",
            va="center",
            color="white",
            fontsize=8,
        )
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    _hierarchy_layer(ax, PlotType.SUNBURST, group, s, roots, wedges)
    return ax


def _hierarchy_layer(
    ax: Axes,
    plot_type: PlotType,
    group: Group,
    s: Series,
    roots: list[_Node],
    marks: PatchCollection,
) -> None:
    if all(n.declared is None for root in roots for n in root.walk()):
        # No value to size anything by: nothing to read.
        return
    y = group.y_axis
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    register(
        ax,
        plot_type,
        labels={
            "x": group.category_name or "Category",
            "y": (y.label if y else None) or s.name or "Value",
        },
        data=_hierarchy_points(roots),
        selectors=each_mark(marks),
        formats={"y": "y"},
    )


def _tint(color: str, depth: int) -> str:
    """A branch's color, lighter for each level below the top."""
    r, g, b = to_rgb(color)
    mix = min(0.15 * depth, 0.6)
    return "#{:02X}{:02X}{:02X}".format(
        *(round(255 * (c + (1 - c) * mix)) for c in (r, g, b))
    )


# --------------------------------------------------------------------------
# Map
# --------------------------------------------------------------------------


def _region(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A filled map, read as the list of its regions and drawn as one bar each,
    shaded by value as the map shades them.
    """
    warn_at_caller(
        f"maidr reads the map {where} as a list of its regions and their "
        "values, drawn as bars: it does not draw the map's shapes."
    )
    ax = _plain_axes(fig)
    s = group.series[0]
    regions = [
        (label, value)
        for label, value in zip(_labels(s.categories, unique=False), s.values)
        if value is not None and label != BLANK
    ]
    values = [v for _, v in regions]
    low, high = min(values, default=0.0), max(values, default=1.0)
    base = to_rgb(s.color or "#4472C4")

    def shade(value: float) -> tuple[float, float, float]:
        share = (value - low) / (high - low) if high > low else 1.0
        mix = 0.85 * (1 - share)
        return tuple(c + (1 - c) * mix for c in base)  # type: ignore[return-value]

    bars = PatchCollection(
        [
            Rectangle((min(0, v), -k - 0.4), abs(v), 0.8)
            for k, (_, v) in enumerate(regions)
        ],
        facecolor=[shade(v) for v in values],
        edgecolor="#7F7F7F",
        linewidth=0.5,
    )
    ax.add_collection(bars)
    ax.set_yticks(-np.arange(len(regions), dtype=float), [n for n, _ in regions])
    ax.set_ylim(-len(regions) + 0.4, 0.6)
    ax.autoscale_view(scaley=False)
    y = group.y_axis
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.xaxis.set_major_formatter(formatter)
    region_name = group.category_name or "Region"
    value_name = (y.label if y else None) or s.name or "Value"
    _label(ax.yaxis, region_name, "Region", False)
    _label(ax.xaxis, value_name, "Value", False)
    ax.grid(axis="x", color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    register(
        ax,
        PlotType.CHOROPLETH,
        labels={"x": region_name, "y": value_name},
        data=[{"x": label, "y": value} for label, value in regions],
        selectors=each_mark(bars),
        formats={"y": "x"},
    )
    return ax


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def _plain_axes(fig: Figure) -> Axes:
    ax = fig.add_subplot()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return ax


def _grid(ax: Axes) -> None:
    ax.grid(axis="y", color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _legend_place(spec: ChartSpec) -> dict[str, Any]:
    return dict(_LEGEND.get(spec.legend or "r", _LEGEND["r"]))


def _second_color(group: Group) -> str:
    """The Pareto line's color, which the reader keeps as a second series."""
    if len(group.series) > 1 and group.series[1].color:
        return group.series[1].color
    return "#ED7D31"


#: What the reader hears a Pareto chart's line called.
_SHARE = "Cumulative percentage"

_DRAW: dict[str, Callable[[Figure, Group, ChartSpec, str], Axes]] = {
    "histogram": _histogram,
    "pareto": _pareto,
    "box": _box,
    "waterfall": _waterfall,
    "funnel": _funnel,
    "treemap": _treemap,
    "sunburst": _sunburst,
    "region": _region,
}

"""Box and whisker charts, with Excel's quartiles."""

from __future__ import annotations

import math
from typing import Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from maidr.excel.draw.common import draw_grid, legend_place, name_axis, plain_axes
from maidr.excel.formats import number_formatter
from maidr.excel.spec import ChartSpec, Group


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


def draw_box(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    One box per category and series, clustered by category as Excel draws
    them, each series a layer named after it.
    """
    ax = plain_axes(fig)
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
    name_axis(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    name_axis(ax.yaxis, y.label if y else None, "Value", bool(y and y.title))
    formatter = number_formatter(y.number_format) if y else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    draw_grid(ax)
    if by_category and len(handles) > 1:
        # The legend is also what names each series' layer: a box layer is
        # named by the legend entry of its color.
        ax.legend(handles=handles, frameon=False, **legend_place(spec))
    return ax

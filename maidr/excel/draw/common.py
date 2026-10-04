"""What every chart is drawn with: its figure, axes, grid and legend."""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from maidr.excel.formats import number_formatter
from maidr.excel.spec import ChartSpec, Group

#: How a category with no label is read.
BLANK = "(blank)"

#: Figure width in inches. The height follows the chart's own proportions.
_WIDTH = 7.0
GRID = "#D9D9D9"

#: Legend position codes, as matplotlib ``legend`` arguments outside the axes.
_LEGEND = {
    "r": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
    "l": {"loc": "center right", "bbox_to_anchor": (-0.12, 0.5)},
    "t": {"loc": "lower center", "bbox_to_anchor": (0.5, 1.08)},
    "b": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.14)},
    "tr": {"loc": "upper left", "bbox_to_anchor": (1.02, 1.0)},
}

#: What a reader is told each kind of chart is called.
NAMES = {
    "bar": "bar",
    "line": "line",
    "area": "area",
    "scatter": "scatter",
    "bubble": "bubble",
    "pie": "pie",
    "doughnut": "doughnut",
    "radar": "radar",
    "stock": "stock",
    "surface": "surface",
    "histogram": "histogram",
    "pareto": "Pareto",
    "box": "box and whisker",
    "waterfall": "waterfall",
    "funnel": "funnel",
    "treemap": "treemap",
    "sunburst": "sunburst",
    "region": "map",
}


def chart_name(group: Group) -> str:
    """What a reader is told the group's kind of chart is called."""
    if group.kind == "ofpie":
        return f"{group.style or 'pie'}-of-pie"
    return NAMES.get(group.kind, group.kind)


def new_figure(aspect: float | None) -> Figure:
    """
    A figure as wide as every chart is drawn, as tall as the chart's own
    proportions on the sheet say, within bounds.
    """
    height = min(_WIDTH, max(3.5, _WIDTH * aspect)) if aspect else 4.5
    return Figure(figsize=(_WIDTH, height))


def style_axes(ax: Axes, group: Group, spec: ChartSpec) -> None:
    """Name, format and scale a group's axes as Excel does."""
    category_axis, value_axis = (
        (ax.yaxis, ax.xaxis) if group.horizontal else (ax.xaxis, ax.yaxis)
    )
    x, y = group.x_axis, group.y_axis
    if x is not None:
        name_axis(
            category_axis,
            x.label,
            "X" if group.kind in ("scatter", "bubble") else "Category",
            x.title is not None,
        )
        if x.hidden:
            category_axis.set_visible(False)
        if group.kind in ("scatter", "bubble"):
            _scale(ax, "x", x.minimum, x.maximum, x.reversed)
            formatter = number_formatter(x.number_format)
            if formatter is not None:
                ax.xaxis.set_major_formatter(formatter)
        elif x.reversed:
            if group.horizontal:
                ax.invert_yaxis()
            else:
                ax.invert_xaxis()
    if y is not None:
        name_axis(
            value_axis,
            y.label or value_name(spec, group),
            "Y" if group.kind in ("scatter", "bubble") else "Value",
            y.title is not None,
        )
        if y.hidden:
            value_axis.set_visible(False)
        if group.grouping == "percentStacked":
            value_axis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        else:
            formatter = number_formatter(y.number_format)
            if formatter is not None:
                value_axis.set_major_formatter(formatter)
        _scale(ax, "x" if group.horizontal else "y", y.minimum, y.maximum, y.reversed)
    ax.grid(axis="x" if group.horizontal else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def value_name(spec: ChartSpec, group: Group) -> str | None:
    """An untitled value axis is named after the only series drawn against it."""
    shared = [
        s for g in spec.groups if g.secondary == group.secondary for s in g.series
    ]
    if len(shared) == 1 and shared[0].name:
        return shared[0].name
    return None


def name_axis(axis: Any, label: str | None, fallback: str, drawn: bool) -> None:
    """
    Name an axis for the reader, and draw the name only where Excel does.

    A name found for an untitled axis -- the header above its range -- is read
    out but not drawn, so the picture keeps Excel's layout.
    """
    axis.set_label_text(label or fallback)
    axis.label.set_visible(drawn)


def _scale(
    ax: Axes, which: str, low: float | None, high: float | None, flip: bool
) -> None:
    if low is not None or high is not None:
        (ax.set_xlim if which == "x" else ax.set_ylim)(low, high)
    if flip:
        (ax.invert_xaxis if which == "x" else ax.invert_yaxis)()


def show_legend(ax: Axes, twin: Axes | None, position: str) -> None:
    """The legend of every named series on both axes, where Excel puts it."""
    handles, labels = ax.get_legend_handles_labels()
    if twin is not None:
        more = twin.get_legend_handles_labels()
        handles, labels = handles + more[0], labels + more[1]
    kept = [
        (h, text)
        for h, text in zip(handles, labels)
        if text and not text.startswith("_")
    ]
    if not kept:
        return
    place = _LEGEND.get(position, _LEGEND["r"])
    extra = {"ncol": len(kept)} if position in ("t", "b") else {}
    ax.legend(*zip(*kept), frameon=False, **place, **extra)


def legend_place(spec: ChartSpec) -> dict[str, Any]:
    """The ``legend`` arguments that put a legend where the chart does."""
    return dict(_LEGEND.get(spec.legend or "r", _LEGEND["r"]))


def plain_axes(fig: Figure) -> Axes:
    """Axes without the top and right spines, as Excel draws a chart."""
    ax = fig.add_subplot()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return ax


def draw_grid(ax: Axes) -> None:
    """Excel's horizontal gridlines, behind the marks."""
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def category_labels(categories: tuple[Any, ...], *, unique: bool) -> list[str]:
    """
    Category labels to draw and read: a missing one reads ``(blank)``, and
    where the axis needs them distinct, a repeated one gets its occurrence
    number, ``Q1 (2)``.
    """
    out, seen = [], {}
    for category in categories:
        label = str(category) if category not in (None, "") else BLANK
        if unique:
            count = seen.get(label, 0) + 1
            seen[label] = count
            if count > 1:
                label = f"{label} ({count})"
        out.append(label)
    return out


def as_floats(values: tuple[Any, ...]) -> np.ndarray:
    """Values as floats, a blank as ``nan``."""
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)

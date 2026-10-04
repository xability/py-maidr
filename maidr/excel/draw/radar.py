"""Radar charts: a spoke per category and a closed outline per series."""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
from matplotlib.ticker import MaxNLocator

from maidr.core.enum import PlotType
from maidr.excel.draw.common import (
    GRID,
    as_floats,
    category_labels,
    show_legend,
    value_name,
)
from maidr.excel.formats import number_formatter
from maidr.excel.layers import each_path, register
from maidr.excel.spec import ChartSpec, Group


def draw_radar(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A radar: one spoke per category, clockwise from the top, and one closed
    outline per series, on a web of the value axis' gridlines.

    Each series is read from its own line, drawn open; the edge that closes
    it is drawn apart, so the line holds one vertex per category.
    """
    ax = fig.add_subplot()
    ax.set_aspect("equal")
    ax.set_axis_off()
    series = group.series
    labels = category_labels(series[0].categories, unique=False)
    count = len(labels)
    values = [as_floats(s.values) for s in series]
    found = np.concatenate(values) if values else np.array([])
    found = found[np.isfinite(found)]
    axis = group.y_axis
    low = axis.minimum if axis is not None and axis.minimum is not None else None
    high = axis.maximum if axis is not None and axis.maximum is not None else None
    ticks = MaxNLocator(nbins=5).tick_values(
        low if low is not None else min(0.0, found.min(initial=0.0)),
        high if high is not None else found.max(initial=1.0),
    )
    low = low if low is not None else float(ticks[0])
    high = high if high is not None else float(ticks[-1])
    ticks = [t for t in ticks if low <= t <= high]
    span = (high - low) or 1.0
    angles = np.pi / 2 - 2 * np.pi * np.arange(count) / max(count, 1)
    cos, sin = np.cos(angles), np.sin(angles)

    for tick in ticks:
        ring = (tick - low) / span
        ax.add_line(
            Line2D(
                np.append(cos, cos[:1]) * ring,
                np.append(sin, sin[:1]) * ring,
                color=GRID,
                linewidth=0.8,
            )
        )
    for x, y, label in zip(cos, sin, labels):
        ax.add_line(Line2D([0, x], [0, y], color=GRID, linewidth=0.8))
        ax.text(
            1.1 * x,
            1.1 * y,
            label,
            ha="center" if abs(x) < 0.3 else ("left" if x > 0 else "right"),
            va="center" if abs(y) < 0.3 else ("bottom" if y > 0 else "top"),
        )
    formatter = number_formatter(axis.number_format) if axis is not None else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    for tick in ticks:
        ring = (tick - low) / span
        ax.text(
            0.03,
            ring,
            formatter(tick) if formatter is not None else f"{tick:g}",
            fontsize=8,
            color="#595959",
            va="center",
        )

    data, selectors = [], []
    for s, vals in zip(series, values):
        radius = (vals - low) / span
        xs, ys = radius * cos, radius * sin
        drawn = np.isfinite(radius)
        if group.style == "filled" and drawn.any():
            ax.add_patch(
                Polygon(
                    np.column_stack([xs[drawn], ys[drawn]]),
                    closed=True,
                    facecolor=s.color or "C0",
                    edgecolor="none",
                    alpha=0.6,
                )
            )
        line = Line2D(
            xs,
            ys,
            color=s.color,
            linewidth=1.5 if group.style == "filled" else 2,
            marker="o" if s.marker else None,
            label=s.name,
            zorder=3,
        )
        ax.add_line(line)
        if count > 2 and drawn[0] and drawn[-1]:
            ax.add_line(
                Line2D(
                    [xs[-1], xs[0]],
                    [ys[-1], ys[0]],
                    color=s.color,
                    linewidth=line.get_linewidth(),
                    zorder=3,
                )
            )
        selectors.append(each_path(line))
        points = []
        for label, value in zip(labels, s.values):
            point: dict[str, Any] = {"x": label, "y": value}
            if s.name:
                point["z"] = s.name
            points.append(point)
        data.append(points)
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.3, 1.3)
    if not found.size:
        # Every value blank: nothing to read, and the chart is left out.
        return ax
    register(
        ax,
        PlotType.RADAR,
        labels={
            "x": group.category_name or "Category",
            "y": (axis.label if axis is not None else None)
            or value_name(spec, group)
            or "Value",
        },
        data=data,
        selectors=selectors,
        formats={"y": "y"},
    )
    if spec.legend is not None and any(s.name for s in series):
        show_legend(ax, None, spec.legend)
    return ax

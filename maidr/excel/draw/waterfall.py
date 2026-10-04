"""Waterfall charts.

Each step is drawn from the running total, and each point set as a total
from zero.
"""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

from maidr.core.enum import PlotType
from maidr.excel.draw.common import (
    category_labels,
    draw_grid,
    legend_place,
    name_axis,
    plain_axes,
)
from maidr.excel.formats import number_formatter
from maidr.excel.layers import each_mark, register
from maidr.excel.spec import ChartSpec, Group


def draw_waterfall(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A waterfall: each step from the running total to the next, and each
    point set as a total from zero to its own value, which the steps after it
    carry on from.
    """
    ax = plain_axes(fig)
    s = group.series[0]
    labels = category_labels(s.categories, unique=False)
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
    name_axis(ax.xaxis, x.label if x else None, "Category", bool(x and x.title))
    name_axis(ax.yaxis, y.label if y else None, s.name or "Value", bool(y and y.title))
    draw_grid(ax)
    if spec.legend is not None:
        kinds = {kind: colors.get(index) for index, *_, kind in steps}
        handles = [
            Patch(facecolor=kinds[kind] or s.color or "C0", label=kind.capitalize())
            for kind in ("increase", "decrease", "total")
            if kind in kinds
        ]
        ax.legend(handles=handles, frameon=False, **legend_place(spec))
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

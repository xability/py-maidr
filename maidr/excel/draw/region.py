"""Filled maps, read as the list of their regions and drawn as bars."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PatchCollection
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from maidr.core.enum import PlotType
from maidr.excel.draw.common import (
    BLANK,
    GRID,
    category_labels,
    name_axis,
    plain_axes,
)
from maidr.excel.formats import number_formatter
from maidr.excel.layers import each_mark, register
from maidr.excel.spec import ChartSpec, Group
from maidr.util.caller_warning import warn_at_caller


def draw_region(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A filled map, read as the list of its regions and drawn as one bar each,
    shaded by value as the map shades them.
    """
    warn_at_caller(
        f"maidr reads the map {where} as a list of its regions and their "
        "values, drawn as bars: it does not draw the map's shapes."
    )
    ax = plain_axes(fig)
    s = group.series[0]
    regions = [
        (label, value)
        for label, value in zip(category_labels(s.categories, unique=False), s.values)
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
    name_axis(ax.yaxis, region_name, "Region", False)
    name_axis(ax.xaxis, value_name, "Value", False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
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

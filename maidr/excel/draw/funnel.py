"""Funnel charts: one bar per stage, centered, the first at the top."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from maidr.core.enum import PlotType
from maidr.excel.draw.common import category_labels, name_axis
from maidr.excel.formats import number_formatter
from maidr.excel.layers import each_mark, register
from maidr.excel.spec import ChartSpec, Group


def draw_funnel(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """A funnel: one bar per stage, centered, the first at the top."""
    ax = fig.add_subplot()
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    s = group.series[0]
    stages = [
        (label, value)
        for label, value in zip(category_labels(s.categories, unique=False), s.values)
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
    name_axis(ax.xaxis, value_name, "Value", False)
    name_axis(ax.yaxis, category_name, "Stage", False)
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


def _number(value: float) -> str:
    return f"{value:.4g}" if not float(value).is_integer() else str(int(value))

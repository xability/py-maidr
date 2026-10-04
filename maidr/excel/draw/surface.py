"""Surface charts, drawn as Excel's contour view shows them: a heatmap."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from maidr.excel.draw.common import as_floats, category_labels, name_axis
from maidr.excel.formats import number_formatter
from maidr.excel.spec import ChartSpec, Group


def draw_surface(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A surface, seen from above as Excel's contour chart shows it: a cell per
    category and series, shaded by its value, read as a heatmap whose rows are
    the series, the first at the bottom.
    """
    ax = fig.add_subplot()
    # A heatmap is read from its top row down, so the rows are drawn that
    # way, the last series first, which leaves the first at the bottom.
    series = group.series[::-1]
    columns = category_labels(series[0].categories, unique=False)
    rows = [s.name or f"Series {len(series) - i}" for i, s in enumerate(series)]
    grid = np.array([as_floats(s.values) for s in series])
    value = group.y_axis
    value_name = (value.label if value is not None else None) or "Value"
    accent = group.series[0].color or "#4472C4"
    shades = LinearSegmentedColormap.from_list("excel", ["#FFFFFF", accent])
    mesh = ax.pcolormesh(
        grid, cmap=shades, edgecolors="white", linewidth=0.5, z_label=value_name
    )
    ax.set_xticks(np.arange(len(columns)) + 0.5, columns)
    ax.set_yticks(np.arange(len(rows)) + 0.5, rows)
    ax.invert_yaxis()
    bar = fig.colorbar(mesh, ax=ax)
    bar.set_label(value_name)
    formatter = number_formatter(value.number_format) if value is not None else None
    if formatter is not None:
        bar.formatter = formatter
        bar.update_ticks()
    titled = group.x_axis is not None and group.x_axis.title is not None
    name_axis(ax.xaxis, group.category_name, "Category", titled)
    name_axis(ax.yaxis, group.series_name, "Series", group.series_name is not None)
    return ax

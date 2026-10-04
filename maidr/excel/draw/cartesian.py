"""Column, bar, line, area, scatter and bubble charts.

These are the kinds drawn on shared axes, any of them with the others.
"""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle

from maidr.core.enum import PlotType
from maidr.excel.draw.common import as_floats, category_labels
from maidr.excel.layers import gid, register
from maidr.excel.spec import Group


def draw_bar(ax: Axes, group: Group) -> None:
    """A column or bar group: clustered, stacked or 100% stacked."""
    series = group.series
    labels = category_labels(series[0].categories, unique=False)
    positions = np.arange(len(labels), dtype=float)
    bar = ax.barh if group.horizontal else ax.bar
    stacked = group.grouping in ("stacked", "percentStacked") and len(series) > 1
    if stacked:
        values = [as_floats(s.values) for s in series]
        if group.grouping == "percentStacked":
            totals = np.nansum(np.abs(values), axis=0)
            totals[totals == 0] = np.nan
            values = [100 * v / totals for v in values]
        above = np.zeros(len(labels))
        below = np.zeros(len(labels))
        for s, vals in zip(series, values):
            base = np.where(np.nan_to_num(vals) < 0, below, above)
            kwargs = (
                {"left" if group.horizontal else "bottom": base} if base.any() else {}
            )
            bar(positions, vals, label=s.name, color=s.color, **kwargs)
            above = above + np.where(vals > 0, vals, 0)
            below = below + np.where(vals < 0, vals, 0)
    elif len(series) == 1:
        s = series[0]
        bar(positions, as_floats(s.values), label=s.name, color=s.color)
    else:
        width = 0.8 / len(series)
        for i, s in enumerate(series):
            offset = (i - (len(series) - 1) / 2) * width
            bar(
                positions + offset,
                as_floats(s.values),
                width,
                label=s.name,
                color=s.color,
            )
    if group.horizontal:
        ax.set_yticks(positions, labels)
    else:
        ax.set_xticks(positions, labels)


def draw_line(ax: Axes, group: Group) -> None:
    """A line group, its series stacked where the chart stacks them."""
    labels = category_labels(group.series[0].categories, unique=True)
    if group.grouping in ("stacked", "percentStacked") and len(group.series) > 1:
        _stacked_lines(ax, group, labels)
        return
    for s in group.series:
        ax.plot(
            labels,
            as_floats(s.values),
            label=s.name,
            color=s.color,
            marker="o" if s.marker else None,
            zorder=3,
        )


def _stacked_lines(ax: Axes, group: Group, labels: list[str]) -> None:
    """
    Each line drawn at the running total, read as a stacked area.

    The bands are what py-maidr reads, each series' own values with the
    stacking it took; they are left unpainted, and the lines Excel draws are
    drawn over them.
    """
    series = group.series
    values = _stacked_values(group)
    bands = ax.stackplot(labels, *values, labels=[s.name or "" for s in series])
    positions = np.arange(len(labels), dtype=float)
    top = np.zeros(len(labels))
    for band, s, vals in zip(bands, series, values):
        band.set_facecolor("none")
        band.set_edgecolor("none")
        band.set_label("_nolegend_")
        top = top + np.nan_to_num(vals)
        ax.add_line(
            Line2D(
                positions,
                np.where(np.isnan(vals), np.nan, top),
                color=s.color,
                marker="o" if s.marker else None,
                linewidth=2,
                label=s.name,
                zorder=3,
            )
        )


def _stacked_values(group: Group) -> list[np.ndarray]:
    """Each series' values, as shares of their category's total for 100%."""
    values = [as_floats(s.values) for s in group.series]
    if group.grouping == "percentStacked":
        totals = np.nansum(np.abs(values), axis=0)
        totals[totals == 0] = np.nan
        values = [100 * v / totals for v in values]
    return values


def draw_area(ax: Axes, group: Group) -> None:
    """An area group: each band from zero, or stacked."""
    labels = category_labels(group.series[0].categories, unique=True)
    series = group.series
    values = _stacked_values(group)
    if group.grouping in ("stacked", "percentStacked") and len(series) > 1:
        ax.stackplot(
            labels,
            *values,
            labels=[s.name or "" for s in series],
            colors=[s.color for s in series] if all(s.color for s in series) else None,
        )
        return
    # Excel draws each band of a plain area chart from zero, the later ones in
    # front; one stack per band is the same picture.
    for s, vals in zip(series, values):
        ax.stackplot(
            labels,
            vals,
            labels=[s.name or ""],
            colors=[s.color] if s.color else None,
            alpha=0.85 if len(series) > 1 else 1.0,
        )


def draw_scatter(ax: Axes, group: Group) -> None:
    """A scatter group: points, or lines where Excel joins them."""
    for s in group.series:
        xs, ys = as_floats(s.categories), as_floats(s.values)
        if s.line:
            ax.plot(
                xs, ys, label=s.name, color=s.color, marker="o" if s.marker else None
            )
        else:
            ax.scatter(xs, ys, label=s.name, color=s.color)


def draw_bubble(ax: Axes, group: Group) -> None:
    """
    Each series' bubbles, read as points whose ``z`` is the bubble's size.

    Excel sizes a bubble by its area unless told to by its width, and draws
    the largest at a quarter of the plot's height, scaled by the chart's
    bubble scale.
    """
    marker = MarkerStyle("o")
    path = marker.get_path().transformed(marker.get_transform())
    sizes = [abs(v) for s in group.series for v in s.sizes if v is not None]
    largest = max(sizes, default=0.0) or 1.0
    # matplotlib sizes a marker by its area in points squared.
    biggest = (0.25 * 72 * ax.figure.get_figheight() * group.bubble_scale / 100) ** 2
    for s in group.series:
        xs, ys = as_floats(s.categories), as_floats(s.values)
        size = as_floats(s.sizes) if s.sizes else np.full(len(xs), largest)
        keep = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(size) & (size > 0)
        share = size[keep] / largest
        if group.style == "w":
            share = share**2
        bubbles = PathCollection(
            [path],
            sizes=biggest * share,
            offsets=np.column_stack([xs[keep], ys[keep]]),
            offset_transform=ax.transData,
            facecolors=s.color or "C0",
            edgecolors="white",
            alpha=0.85,
            label=s.name,
            zorder=3,
        )
        ax.add_collection(bubbles)
        mark = f"g[id='{gid(bubbles)}']"
        register(
            ax,
            PlotType.SCATTER,
            labels={"x": None, "y": None, "z": group.size_name or "Size"},
            data=[
                {"x": float(x), "y": float(y), "z": float(z)}
                for x, y, z in zip(xs[keep], ys[keep], size[keep])
            ],
            selectors=f"{mark} > g > use, {mark} > path",
            formats={"x": "x", "y": "y"},
        )
    ax.autoscale_view()
    # A bubble's radius reaches past its center; leave room for the largest.
    ax.margins(0.12)

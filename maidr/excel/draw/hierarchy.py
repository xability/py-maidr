"""Treemaps and sunbursts.

Every node of the hierarchy is read, each before its children, and drawn
sized by its value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from matplotlib.axes import Axes
from matplotlib.collections import PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Wedge

from maidr.core.enum import PlotType
from maidr.excel.colors import tint
from maidr.excel.formats import number_formatter
from maidr.excel.layers import each_mark, register
from maidr.excel.spec import ChartSpec, Group, Series


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


def draw_treemap(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
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


def draw_sunburst(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
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
        facecolor=[tint(n.color or "C0", len(n.path)) for n in nodes],
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

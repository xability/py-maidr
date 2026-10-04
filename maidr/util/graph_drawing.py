"""Draw a directed graph with matplotlib and register it as a maidr layer.

The graph is laid out top to bottom in rows, a node one row below the
deepest node feeding it (its longest path from an input), so every arrow
points down. Within a row the nodes sit under the nodes feeding them, as
near as the row allows. Each node is a rounded box with its label and a
caption, each scope a dashed frame round the nodes in it, and each edge an
arrow; only the boxes are named in the layer, as the directed graph trace
highlights a node, not an edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path

from maidr.core.figure_manager import FigureManager
from maidr.core.plot.directed_graph import DirectedGraphPlot

__all__ = ["draw_directed_graph", "layout"]

#: Sizes in inches: the axes are drawn one data unit to the inch.
_BOX_HEIGHT = 0.5
_ROW_GAP = 0.85
_COLUMN_GAP = 0.3
_CHAR_WIDTH = 0.075
_MIN_BOX_WIDTH = 1.2
_MARGIN = 0.35
_TITLE_HEIGHT = 0.45
#: How far an edge that skips rows runs out past the side of the boxes, how
#: far apart two such edges run, and how round their corners are.
_DETOUR = 0.3
_LANE_GAP = 0.12
_CORNER = 0.1
#: A label longer than this is cut short in the box; it is read out whole.
_MAX_DRAWN_CHARS = 26

_FILL = "#E3F2FD"
_EDGE = "#1565C0"
_TEXT = "#0D1B2A"
_CAPTION = "#455A64"
_ARROW = "#546E7A"
_SCOPE = "#78909C"


def layout(nodes: Sequence[Mapping[str, object]]) -> list[tuple[int, float]]:
    """
    Where each node is drawn: its row, and its place along the row.

    Parameters
    ----------
    nodes : sequence of mapping
        The nodes, each with an ``id`` and optional ``inputs``. An input that
        names no node, or the node itself, is ignored, as maidr.js ignores it.

    Returns
    -------
    list of tuple of (int, float)
        Per node, in the same order: the row, counted from 0 at the top, which
        is the longest path to it from a node with no inputs; and its column,
        centered on 0, in box widths. A cycle, which no model graph has, is
        broken where it is found so that every node still gets a row.
    """
    index = {node["id"]: i for i, node in enumerate(nodes)}
    feeding = [_inputs(node, index, i) for i, node in enumerate(nodes)]
    rows = [-1] * len(nodes)
    # Kahn's order, so a long chain needs no recursion; a node left over is on
    # a cycle, and takes its row from whichever of its inputs have one.
    waiting = [len(sources) for sources in feeding]
    feeds: list[list[int]] = [[] for _ in nodes]
    for i, sources in enumerate(feeding):
        for source in sources:
            feeds[source].append(i)
    ready = [i for i, count in enumerate(waiting) if count == 0]
    while ready or -1 in rows:
        if not ready:
            ready = [rows.index(-1)]
        i = ready.pop(0)
        if rows[i] >= 0:
            continue
        rows[i] = 1 + max((rows[s] for s in feeding[i] if rows[s] >= 0), default=-1)
        for target in feeds[i]:
            waiting[target] -= 1
            if waiting[target] == 0:
                ready.append(target)
    columns = [0.0] * len(nodes)
    for row in range(max(rows, default=-1) + 1):
        members = [i for i in range(len(nodes)) if rows[i] == row]

        def under(i: int) -> float:
            above = [columns[s] for s in feeding[i] if rows[s] < row]
            return sum(above) / len(above) if above else float("inf")

        wanted = {i: under(i) for i in members}
        members.sort(key=lambda i: (wanted[i], i))
        start = -(len(members) - 1) / 2
        for place, i in enumerate(members):
            columns[i] = start + place
    return list(zip(rows, columns))


def draw_directed_graph(
    nodes: Sequence[Mapping[str, object]],
    *,
    title: str,
    node_label: str,
    caption: str | None = None,
) -> Figure:
    """
    Draw a directed graph and register it as a ``directed_graph`` layer.

    Parameters
    ----------
    nodes : sequence of mapping
        The nodes, as :class:`~maidr.core.plot.directed_graph.DirectedGraphPlot`
        takes them: ``id``, and optionally ``label``, ``path``, ``inputs`` and
        ``attributes``.
    title : str
        The chart's title.
    node_label : str
        What a node is, such as ``"Layer"``.
    caption : str, optional
        The attribute written under each node's label in its box, such as
        ``"Layer type"``. Every attribute is read out either way.

    Returns
    -------
    matplotlib.figure.Figure
        The graph, not managed by pyplot, with its layer registered.

    Raises
    ------
    ValueError
        If there are no nodes.
    """
    if not nodes:
        raise ValueError("a directed graph needs at least one node")
    places = layout(nodes)
    labels = [_drawn(str(node.get("label", node["id"]))) for node in nodes]
    captions = [
        _drawn(str((node.get("attributes") or {}).get(caption, "")))  # type: ignore[union-attr]
        if caption
        else ""
        for node in nodes
    ]
    longest = max(len(text) for text in labels + captions)
    box_width = max(_MIN_BOX_WIDTH, longest * _CHAR_WIDTH + 0.3)
    step = box_width + _COLUMN_GAP
    depth = max(row for row, _ in places) + 1
    widest = max(abs(column) for _, column in places)
    scope_depth = max(len(node.get("path") or []) for node in nodes)  # type: ignore[arg-type]
    pad = _MARGIN + 0.15 * scope_depth
    centers = [(column * step, -row * _ROW_GAP) for row, column in places]
    index = {node["id"]: i for i, node in enumerate(nodes)}
    routes = []
    lanes = {1: 0, -1: 0}
    for i, node in enumerate(nodes):
        for source in _inputs(node, index, i):
            between = range(places[source][0] + 1, places[i][0])
            passed = [x for (row, _), (x, _) in zip(places, centers) if row in between]
            side = 1 if centers[source][0] + centers[i][0] >= 0 else -1
            lane = 0
            if passed:
                lane, lanes[side] = lanes[side], lanes[side] + 1
            routes.append(
                _route(centers[source], centers[i], passed, side, lane, box_width, pad)
            )
    reach = max(
        [widest * step + box_width / 2 + pad]
        + [abs(x) + _MARGIN for route in routes for x, _ in route]
    )
    width = max(4.0, 2 * reach)
    height = (depth - 1) * _ROW_GAP + _BOX_HEIGHT + 2 * pad
    fig = Figure(figsize=(width, height + _TITLE_HEIGHT))
    ax = fig.add_axes((0, 0, 1, height / (height + _TITLE_HEIGHT)))
    ax.set_xlim(-width / 2, width / 2)
    ax.set_ylim(-(height - pad - _BOX_HEIGHT / 2), pad + _BOX_HEIGHT / 2)
    ax.set_axis_off()
    ax.set_title(title, fontsize=11)
    _draw_scopes(ax, nodes, centers, box_width)
    for route in routes:
        _arrow(ax, route)
    boxes = []
    for (x, y), label, text in zip(centers, labels, captions):
        box = FancyBboxPatch(
            (x - box_width / 2, y - _BOX_HEIGHT / 2),
            box_width,
            _BOX_HEIGHT,
            boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=_FILL,
            edgecolor=_EDGE,
            linewidth=1.0,
            zorder=3,
        )
        ax.add_patch(box)
        boxes.append(box)
        ax.text(
            x,
            y + (0.07 if text else 0),
            label,
            ha="center",
            va="center",
            fontsize=9,
            color=_TEXT,
            zorder=4,
        )
        if text:
            ax.text(
                x,
                y - 0.12,
                text,
                ha="center",
                va="center",
                fontsize=7.5,
                color=_CAPTION,
                zorder=4,
            )
    FigureManager.add_plot(
        DirectedGraphPlot(ax, nodes=nodes, boxes=boxes, node_label=node_label)
    )
    return fig


def _inputs(node: Mapping[str, object], index: Mapping[object, int], at: int) -> list:
    """The positions of a node's inputs that name another node, once each."""
    found = [index[i] for i in node.get("inputs") or [] if i in index]  # type: ignore[attr-defined]
    return [i for i in dict.fromkeys(found) if i != at]


def _drawn(text: str) -> str:
    """A label as it fits in a box."""
    if len(text) <= _MAX_DRAWN_CHARS:
        return text
    return text[: _MAX_DRAWN_CHARS - 1] + "…"


def _route(
    start: tuple[float, float],
    end: tuple[float, float],
    passed: list[float],
    side: int,
    lane: int,
    width: float,
    pad: float,
) -> list[tuple[float, float]]:
    """
    The corners of an edge, from the bottom of one box to the top of another.

    ``passed`` holds the centers of the boxes in the rows between: none for
    an edge to the next row, which runs straight. Any other edge would run
    through those boxes, so it leaves and enters off the middle of the box
    on its side, turns into the gap below its source row, runs
    down past the outermost of them, and any scope frame round them, on the
    ``side`` of the chart it is already on, and turns back in the gap above
    its target. Each such edge on a side has a ``lane`` of its own.
    """
    (x0, y0), (x1, y1) = start, end
    if not passed:
        return [(x0, y0 - _BOX_HEIGHT / 2), (x1, y1 + _BOX_HEIGHT / 2)]
    # Off the middle of each box, so it is not mistaken for the edges that
    # run straight between neighbouring rows.
    x0, x1 = x0 + side * width / 4, x1 + side * width / 4
    tail = (x0, y0 - _BOX_HEIGHT / 2)
    head = (x1, y1 + _BOX_HEIGHT / 2)
    outermost = max(side * x for x in passed) * side
    clear = outermost + side * (width / 2 + pad - _MARGIN + _DETOUR + lane * _LANE_GAP)
    gap = (_ROW_GAP - _BOX_HEIGHT) / 2
    return [
        tail,
        (x0, tail[1] - gap),
        (clear, tail[1] - gap),
        (clear, head[1] + gap),
        (x1, head[1] + gap),
        head,
    ]


def _arrow(ax, corners: list[tuple[float, float]]) -> None:
    """An arrow along ``corners``, its corners rounded."""
    vertices = [corners[0]]
    codes = [Path.MOVETO]
    for before, corner, after in zip(corners, corners[1:], corners[2:]):
        into, out = _toward(corner, before), _toward(corner, after)
        if into is None or out is None:
            continue
        vertices += [into, corner, out]
        codes += [Path.LINETO, Path.CURVE3, Path.CURVE3]
    vertices.append(corners[-1])
    codes.append(Path.LINETO)
    ax.add_patch(
        FancyArrowPatch(
            path=Path(vertices, codes),
            arrowstyle="-|>",
            mutation_scale=10,
            color=_ARROW,
            linewidth=1.0,
            zorder=2,
        )
    )


def _toward(
    corner: tuple[float, float], other: tuple[float, float]
) -> tuple[float, float] | None:
    """Where a rounded corner meets the side toward ``other``; ``None`` if flat."""
    dx, dy = other[0] - corner[0], other[1] - corner[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return None
    radius = min(_CORNER, length / 2)
    return corner[0] + dx / length * radius, corner[1] + dy / length * radius


def _draw_scopes(
    ax,
    nodes: Sequence[Mapping[str, object]],
    centers: list[tuple[float, float]],
    box_width: float,
) -> None:
    """A dashed frame round the nodes of each scope, named at its corner."""
    scopes: dict[tuple, list[int]] = {}
    for i, node in enumerate(nodes):
        path = tuple(node.get("path") or [])  # type: ignore[arg-type]
        for level in range(1, len(path) + 1):
            scopes.setdefault(path[:level], []).append(i)
    for scope, members in scopes.items():
        inner = max(len(nodes[i].get("path") or []) for i in members) - len(scope)  # type: ignore[arg-type]
        pad = 0.12 + 0.15 * inner
        xs = [centers[i][0] for i in members]
        ys = [centers[i][1] for i in members]
        left = min(xs) - box_width / 2 - pad
        bottom = min(ys) - _BOX_HEIGHT / 2 - pad
        right = max(xs) + box_width / 2 + pad
        top = max(ys) + _BOX_HEIGHT / 2 + pad + 0.12
        ax.add_patch(
            FancyBboxPatch(
                (left, bottom),
                right - left,
                top - bottom,
                boxstyle="round,pad=0,rounding_size=0.1",
                facecolor="none",
                edgecolor=_SCOPE,
                linestyle="--",
                linewidth=0.9,
                zorder=1,
            )
        )
        ax.text(
            left + 0.08,
            top - 0.04,
            str(scope[-1]),
            ha="left",
            va="top",
            fontsize=7.5,
            color=_SCOPE,
            style="italic",
            # Over any edge that crosses the frame's top, so the name reads.
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5},
            zorder=2.5,
        )

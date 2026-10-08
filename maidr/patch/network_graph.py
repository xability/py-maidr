"""A networkx drawing of a directed graph reads as the graph, not its node positions.

``networkx.draw`` and ``networkx.draw_networkx`` draw a graph on matplotlib:
every node as one point of a single ``ax.scatter`` collection, every edge as
an arrow patch, every label as text. Left alone, the ``Axes.scatter`` patch
registers a *point* layer of the nodes' layout coordinates -- numbers the
layout algorithm chose, which say nothing about the graph -- and the edges,
the whole content of a graph, are not read at all.

A directed graph is read instead as the ``directed_graph`` layer
``maidr.keras.plot_model`` emits: one node per drawn node, each naming the
nodes whose edges arrive at it, so maidr.js walks it by its edges -- what
feeds a node, what it feeds, where the graph branches and merges. An
undirected graph is left as it was; ``directed_graph`` reads direction, and
an undirected edge has none.
"""

from __future__ import annotations

import math
import uuid
from numbers import Integral, Real
from typing import Any

import wrapt
from matplotlib.collections import PathCollection

from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.directed_graph import DirectedGraphPlot
from maidr.patch.common import _draw_quietly

#: What a networkx node is called in announcements.
NODE_LABEL = "Node"


def draw_networkx(wrapped, instance, args, kwargs) -> Any:
    """
    Draw a patched ``draw_networkx`` and register a directed graph's nodes.

    Drawn inside the internal context, so the scatter patch does not register
    the nodes' positions as a point layer; then the graph handed in is read:
    the nodes drawn (``nodelist``, or every node), the edges drawn
    (``edgelist``, or every edge) and the labels shown.

    Parameters
    ----------
    wrapped : Callable
        ``networkx.draw_networkx``.
    instance : Any
        Unused; a module-level function.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Any
        Whatever ``draw_networkx`` returned.
    """
    graph = args[0] if args else kwargs.get("G")
    if ContextManager.is_internal_context() or not _is_directed(graph):
        return wrapped(*args, **kwargs)

    nodes = _nodes_of(graph, kwargs)
    if nodes is None:
        return wrapped(*args, **kwargs)

    ax = kwargs.get("ax")
    before = set(map(id, ax.collections)) if ax is not None else None
    with ContextManager.set_internal_context():
        result = _draw_quietly(wrapped, args, kwargs)

    drawn = _node_collection(ax, before)
    if drawn is None or len(drawn.get_offsets()) != len(nodes):
        return result

    if drawn.get_gid() is None:
        drawn.set_gid(f"maidr-{uuid.uuid4()}")
    gid = drawn.get_gid()
    FigureManager.add_plot(
        DirectedGraphPlot(
            drawn.axes,
            nodes=nodes,
            boxes=(),
            node_label=NODE_LABEL,
            selectors=[_node_selector(gid, i) for i in range(len(nodes))],
        )
    )
    return result


def _is_directed(graph: Any) -> bool:
    """Whether ``graph`` is a networkx graph whose edges have a direction."""
    is_directed = getattr(graph, "is_directed", None)
    return callable(is_directed) and bool(is_directed())


def _nodes_of(graph: Any, kwargs: dict) -> list[dict] | None:
    """
    The drawn nodes as the layer declares them, or None when they cannot be.

    A networkx node is any hashable; the layer's ids are strings, so two
    nodes that print alike (``1`` and ``"1"``) cannot both be named, and the
    graph is then left to the reading it had.

    Parameters
    ----------
    graph : networkx.DiGraph
        The graph being drawn.
    kwargs : dict
        The caller's keyword arguments, for ``nodelist``, ``edgelist``,
        ``labels`` and ``with_labels``.

    Returns
    -------
    list of dict or None
        One node per drawn node, in drawing order.
    """
    try:
        nodelist = list(kwargs.get("nodelist") or graph.nodes())
        edgelist = kwargs.get("edgelist")
        edges = list(edgelist) if edgelist is not None else list(graph.edges())
    except (TypeError, AttributeError):
        return None
    if not nodelist:
        return None

    ids = {node: str(node) for node in nodelist}
    if len(set(ids.values())) != len(ids):
        return None

    feeds: dict = {node: [] for node in nodelist}
    for edge in edges:
        if len(edge) < 2:
            continue
        source, target = edge[0], edge[1]
        if source in ids and target in feeds and ids[source] not in feeds[target]:
            feeds[target].append(ids[source])

    labels = kwargs.get("labels")
    if not isinstance(labels, dict):
        labels = {}

    nodes = []
    for node in nodelist:
        declared = {
            "id": ids[node],
            "label": str(labels.get(node, node)),
            "inputs": feeds[node],
        }
        attributes = _attributes(graph.nodes[node]) if node in graph else {}
        if attributes:
            declared["attributes"] = attributes
        nodes.append(declared)
    return nodes


def _attributes(data: Any) -> dict:
    """A node's data the trace can announce: its strings, numbers and flags."""
    if not isinstance(data, dict):
        return {}
    plain: dict = {}
    for key, value in data.items():
        if isinstance(value, bool) or isinstance(value, str):
            plain[str(key)] = value
        elif isinstance(value, Integral):
            plain[str(key)] = int(value)
        elif isinstance(value, Real) and math.isfinite(float(value)):
            plain[str(key)] = float(value)
    return plain


def _node_collection(ax: Any, before: set | None) -> PathCollection | None:
    """
    The collection ``draw_networkx`` drew the nodes as.

    The nodes are the one ``PathCollection`` the call added: edges are arrow
    patches on a directed graph, and labels are text. Without the axes in
    hand -- ``draw_networkx`` drawing on the current one -- it is the current
    axes' newest collection.
    """
    if ax is None:
        import matplotlib.pyplot as plt

        ax = plt.gca()
        before = None
    added = [
        collection
        for collection in ax.collections
        if isinstance(collection, PathCollection)
        and (before is None or id(collection) not in before)
    ]
    if before is None:
        return added[-1] if added else None
    return added[0] if len(added) == 1 else None


def _node_selector(gid: str, index: int) -> str:
    """
    The selector of one node, whichever form matplotlib wrote the collection in.

    A collection of identical markers is one ``<g>`` holding a ``<use>`` per
    point; one colored point by point (``node_color`` a list) is a ``<g>``
    per point holding one ``<use>``; one whose marker varies per point is an
    inline ``<path>`` per point. ``nth-of-type`` counts only elements of the
    same kind, so the marker written into a ``<defs>`` sibling shifts none of
    them -- the reasoning ``ScatterPlot._get_selector`` gives. The three are
    joined, since only one occurs in a given drawing.
    """
    n = index + 1
    root = f"g[id='{gid}']"
    return (
        f"{root} > g:only-of-type > use:nth-of-type({n}), "
        f"{root} > g:nth-of-type({n}) > use:only-child, "
        f"{root} > path:nth-of-type({n})"
    )


@wrapt.when_imported("networkx")
def _patch_networkx(module: Any) -> None:
    """
    Wrap networkx's ``draw_networkx`` once networkx is imported.

    Two bindings: the drawing module's own, which ``networkx.draw`` and its
    layout variants (``draw_circular``, ``draw_spring``, ...) call, and the
    one networkx re-exports at its top level, which a caller of
    ``nx.draw_networkx`` reaches. Each call passes through exactly one.
    """
    drawing = getattr(getattr(module, "drawing", None), "nx_pylab", None)
    if drawing is not None and hasattr(drawing, "draw_networkx"):
        wrapt.wrap_function_wrapper(drawing, "draw_networkx", draw_networkx)
    if hasattr(module, "draw_networkx"):
        wrapt.wrap_function_wrapper(module, "draw_networkx", draw_networkx)

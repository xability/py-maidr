"""Read a Bokeh graph drawn from a directed networkx graph as a directed graph.

``bokeh.plotting.from_networkx`` turns a networkx graph into a
``GraphRenderer``: a node renderer whose source lists each node (``index``)
and its attributes, and an edge renderer whose source lists each edge as
``start`` and ``end``. The renderer keeps no trace of whether the graph was
directed -- an undirected edge is listed one way round like any other -- so
the patch below records the renderers ``from_networkx`` made from a directed
graph, and only those are read: an undirected graph read as directed would
announce a direction no edge has.

The layer is the ``directed_graph`` one ``maidr.keras.plot_model`` emits,
one node per row of the node renderer's source, in source order. Bokeh draws
to a canvas, so the highlight answers maidr.js's ``onNavigate``, which
reports the node being read as its index into the layer's ``data``
(``pointIndices``), and the page selects that node's row.
"""

from __future__ import annotations

import math
import weakref
from numbers import Integral, Real
from typing import Any

import wrapt

#: What a node of a Bokeh graph is called in announcements.
NODE_LABEL = "Node"

#: The ``GraphRenderer`` objects ``from_networkx`` made from a directed graph.
#: Weak, so a renderer the caller drops is not kept alive by maidr.
_DIRECTED: weakref.WeakSet = weakref.WeakSet()


def is_directed(renderer: Any) -> bool:
    """Whether ``renderer`` was made by ``from_networkx`` from a directed graph."""
    try:
        return renderer in _DIRECTED
    except TypeError:
        return False


def read_graph(renderer: Any) -> tuple[list[dict], list[list]] | None:
    """
    The nodes of a directed graph renderer and where each is drawn.

    Parameters
    ----------
    renderer : bokeh.models.GraphRenderer
        A renderer :func:`is_directed` holds.

    Returns
    -------
    tuple of (list of dict, list of list) or None
        The nodes in source order, each ``{id, label, inputs, attributes}``,
        and per node the ``[node renderer id, source row]`` to select; None
        when the sources cannot be read as a graph.
    """
    nodes_source = getattr(renderer.node_renderer, "data_source", None)
    edges_source = getattr(renderer.edge_renderer, "data_source", None)
    if nodes_source is None or edges_source is None:
        return None
    nodes = dict(nodes_source.data)
    edges = dict(edges_source.data)
    index = list(nodes.get("index", []))
    if not index:
        return None
    ids = [str(node) for node in index]
    if len(set(ids)) != len(ids):
        return None
    row_of = {node: row for row, node in enumerate(index)}

    starts, ends = list(edges.get("start", [])), list(edges.get("end", []))
    inputs: list[list[str]] = [[] for _ in index]
    for start, end in zip(starts, ends):
        if start not in row_of or end not in row_of:
            continue
        source, target = row_of[start], row_of[end]
        if ids[source] not in inputs[target]:
            inputs[target].append(ids[source])

    attributes = {
        key: list(values)
        for key, values in nodes.items()
        if key != "index" and len(values) == len(index)
    }

    declared = []
    for row, node_id in enumerate(ids):
        node = {"id": node_id, "label": node_id, "inputs": inputs[row]}
        scalars = {
            key: plain
            for key, values in attributes.items()
            if (plain := _plain(values[row])) is not None
        }
        if scalars:
            node["attributes"] = scalars
        declared.append(node)
    return declared, [[renderer.node_renderer.id, row] for row in range(len(ids))]


def _plain(value: Any) -> str | int | float | bool | None:
    """A node attribute the trace can announce, or None to leave it out."""
    if isinstance(value, (bool, str)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real) and math.isfinite(float(value)):
        return float(value)
    return None


def _record_directed(wrapped, instance, args, kwargs) -> Any:
    """Make the renderer, and remember it when its graph was directed."""
    renderer = wrapped(*args, **kwargs)
    graph = args[0] if args else kwargs.get("graph")
    is_directed_graph = getattr(graph, "is_directed", None)
    if callable(is_directed_graph) and is_directed_graph():
        try:
            _DIRECTED.add(renderer)
        except TypeError:
            pass
    return renderer


@wrapt.when_imported("bokeh.plotting")
def _patch_from_networkx(module: Any) -> None:
    """
    Wrap ``from_networkx`` where Bokeh defines it and where it re-exports it.

    The two bindings are one function reached two ways; each call passes
    through exactly one of them.
    """
    graph_module = getattr(module, "graph", None)
    for owner in (graph_module, module):
        if owner is not None and hasattr(owner, "from_networkx"):
            wrapt.wrap_function_wrapper(owner, "from_networkx", _record_directed)

"""A directed graph layer, built from the nodes a reader drew rather than read off.

matplotlib has no graph call: a model's graph is drawn as one box per node
and an arrow per edge. A reader that draws one -- such as
:func:`maidr.keras.plot_model` -- knows each node and what feeds it before it
draws them, so it builds this layer from that node list and registers it
with :meth:`~maidr.core.figure_manager.FigureManager.add_plot`. Where a box
was drawn is presentation and is never part of the layer: maidr.js walks the
graph by its edges and scopes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from matplotlib.artist import Artist
from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot


class DirectedGraphPlot(MaidrPlot):
    """
    One node per box, each naming the nodes that feed it.

    Parameters
    ----------
    ax : Axes
        The axes the graph is drawn on.
    nodes : sequence of mapping
        Each node, in the order the layer declares them: ``id`` (a string or
        number, unique in the layer), and optionally ``label`` (what is
        announced, the id by default), ``path`` (the enclosing scopes,
        outermost first), ``inputs`` (the ids of the nodes feeding it) and
        ``attributes`` (a mapping of names to strings, numbers or booleans).
    boxes : sequence of Artist
        The artist drawing each node, in the same order as ``nodes``; each is
        named in the SVG by its gid and highlights its node.
    node_label : str
        What a node is, such as ``"Layer"``: the trace announces it as the
        node noun.
    selectors : sequence of str, optional
        One selector per node, in the same order as ``nodes``, for a drawing
        whose nodes are not each an artist of their own -- networkx draws
        every node as one point of a single collection. Given, ``boxes`` is
        ignored.

    Raises
    ------
    ValueError
        If ``nodes`` and ``boxes`` (or ``selectors``) differ in length, or
        two nodes share an id.
    """

    def __init__(
        self,
        ax: Axes,
        *,
        nodes: Sequence[Mapping[str, object]],
        boxes: Sequence[Artist],
        node_label: str,
        selectors: Sequence[str] | None = None,
    ) -> None:
        super().__init__(ax, PlotType.DIRECTED_GRAPH)
        if selectors is not None:
            if len(nodes) != len(selectors):
                raise ValueError("a directed graph needs one selector per node")
            boxes = ()
        elif len(nodes) != len(boxes):
            raise ValueError("a directed graph needs one box per node")
        self._selectors = list(selectors) if selectors is not None else None
        self._nodes = [_node(node) for node in nodes]
        ids = [node["id"] for node in self._nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("each node of a directed graph needs its own id")
        self._gids = []
        for box in boxes:
            if box.get_gid() is None:
                box.set_gid(f"maidr-{uuid.uuid4()}")
            self._gids.append(str(box.get_gid()))
        self._node_label = node_label

    def _extract_axes_data(self) -> dict:
        """
        The node noun, the one axis label the directed graph trace reads.

        Returns
        -------
        dict
            ``x`` labelled with what a node is, such as ``"Layer"``.
        """
        return {MaidrKey.X: self._axis_config(label=self._node_label)}

    def _extract_plot_data(self) -> list[dict]:
        """
        Each node, in declared order.

        Returns
        -------
        list of dict
            ``{"id", "label", "inputs", "attributes"}`` per node, with
            ``"path"`` when the node sits in a scope.
        """
        return [dict(node) for node in self._nodes]

    def _get_selector(self) -> list[str]:  # type: ignore[override]
        """One selector per node, in declared order, each naming its box."""
        if self._selectors is not None:
            return list(self._selectors)
        return [f"g[id='{gid}'] > path" for gid in self._gids]


def _node(node: Mapping[str, object]) -> dict:
    """A node as JSON carries it: plain lists, and only the keys it has."""
    plain: dict = {"id": node["id"], "label": node.get("label", node["id"])}
    path = list(node.get("path") or [])  # type: ignore[call-overload]
    if path:
        plain["path"] = path
    plain["inputs"] = list(node.get("inputs") or [])  # type: ignore[call-overload]
    plain["attributes"] = dict(node.get("attributes") or {})  # type: ignore[call-overload]
    return plain

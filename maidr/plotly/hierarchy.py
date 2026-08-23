from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

#: Plotly's three hierarchy traces and the MAIDR type each one is.
#:
#: One class serves all three because they differ only in how the same tree
#: is painted -- nested rectangles, concentric rings, stacked bands -- and
#: not at all in what they are handed or in how a reader walks them. The
#: grammar keeps them apart for the same reason it keeps a lollipop apart
#: from a bar: the chart type is announced, and a reader told "treemap"
#: about a sunburst has been told something false about the picture beside
#: them.
HIERARCHY_TYPES: dict[str, PlotType] = {
    "treemap": PlotType.TREEMAP,
    "sunburst": PlotType.SUNBURST,
    "icicle": PlotType.ICICLE,
}


def is_hierarchy_trace(trace: dict) -> bool:
    """Report whether this trace is one of plotly's three hierarchy paintings."""
    return trace.get("type") in HIERARCHY_TYPES


def has_one_root(trace: dict) -> bool:
    """Report whether the tree the trace states has a single root.

    Plotly accepts several top-level nodes and **invents a parent** for
    them. Measured against ``gd.calcdata``: ``labels=[r1, r2, a]`` with
    ``parents=["", "", "r1"]`` came back as four nodes, the first one an
    id plotly made up (``c02ba4``) with an empty label, and four slices were
    drawn for the three the author wrote.

    That node is not in the data and has no name. Emitting it would announce
    a nameless root the author never wrote, and omitting it would leave the
    positional selector one place out for every node -- so a many-rooted
    hierarchy is declined rather than guessed at.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True when exactly one node names no parent.
    """
    parents = as_list(trace.get("parents"))
    if not parents:
        return False
    return sum(1 for parent in parents if not str(parent or "")) == 1


class PlotlyHierarchyPlot(PlotlyPlot):
    """Extract data from a Plotly treemap, sunburst or icicle trace.

    The three state one tree the same way -- ``labels``, ``parents`` and an
    optional ``values`` -- and `TreemapPoint` wants that tree flattened: one
    point per node, carrying its name, its declared value and the chain of
    ancestors above it.

    The emitted order is the trace's own. Measured against ``gd.calcdata``
    with an input deliberately in neither depth-first nor breadth-first
    order (``r, a1, b, a, b1``), plotly kept it exactly:
    ``['r', 'a1', 'b', 'a', 'b1']``. ``sort`` changes the drawn layout, not
    that order, and a four-deep chain came back in input order too. This
    matters because the selector is positional -- one element per node -- so
    a reordering here would land every later node on another slice.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        hierarchy_position: int = 0,
        **kwargs: str,
    ) -> None:
        kind = str(trace.get("type"))
        super().__init__(trace, layout, HIERARCHY_TYPES[kind], **kwargs)
        self._kind = kind
        self._hierarchy_position = hierarchy_position

    def _get_selector(self) -> str:
        """Address this trace's nodes inside its own figure-level layer.

        Each painting has its own layer -- ``treemaplayer``,
        ``sunburstlayer``, ``iciclelayer`` -- sitting directly under
        ``main-svg`` rather than inside a ``.subplot.xy`` group, so the
        position among that layer's trace groups stands in for the subplot
        prefix, as it does for a pie.

        Measured on all three: ``{kind}layer > .trace:nth-child(1) .slice
        path.surface`` resolved to one element per node.
        """
        return (
            f".{self._kind}layer > "
            f".trace:nth-child({self._hierarchy_position + 1}) "
            f".slice > path.surface"
        )

    def _extract_axes_data(self) -> dict:
        """Name the two dimensions a hierarchy carries.

        A hierarchy draws no axes. The core announces a node as its name
        paired with its magnitude, so the generic pair says what those two
        are -- the same stand-in a pie takes, in this chart's own words.
        """
        return {
            MaidrKey.X: self._axis_config(label="Node"),
            MaidrKey.Y: self._axis_config(label="Value"),
        }

    def _extract_plot_data(self) -> list[dict]:
        """One point per node, in the trace's own order.

        ``ids`` is honoured where the author gives it: plotly then reads
        ``parents`` as *ids* rather than as labels, which is how a tree with
        two nodes of the same name is written at all. The path is resolved
        through those ids and then spelled in labels, because
        `TreemapPoint.x` is the node's name and its `path` has to be in the
        same vocabulary for a reader to follow it.

        ``y`` is emitted only when the author declared values. Without them
        plotly counts leaves, and ``calcdata`` reports ``None`` for every
        node -- there is no declared magnitude to pass on, and
        `TreemapPoint.y` is optional precisely for that case.
        """
        labels = [self._to_native(label) for label in as_list(self._trace.get("labels"))]
        parents = [str(parent or "") for parent in as_list(self._trace.get("parents"))]
        raw_ids = as_list(self._trace.get("ids"))
        ids = (
            [str(node_id) for node_id in raw_ids]
            if len(raw_ids) == len(labels)
            else [str(label) for label in labels]
        )

        # No `has_values` flag beside this. `as_list(None)` is `[]`, so the
        # length check below already answers "did the author declare
        # values" -- a mutation removing the flag changed no test, which is
        # what a redundant guard looks like.
        values = as_list(self._trace.get("values"))

        parent_of = dict(zip(ids, parents))
        label_of = dict(zip(ids, labels))

        points: list[dict] = []
        for index, node_id in enumerate(ids):
            if index >= len(labels):
                break
            point: dict = {MaidrKey.X: labels[index]}

            if index < len(values):
                number = _number(values[index])
                if number is not None:
                    point[MaidrKey.Y] = number

            path = self._ancestors(node_id, parent_of, label_of)
            if path:
                point[MaidrKey.PATH] = path
            points.append(point)

        return points

    @staticmethod
    def _ancestors(
        node_id: str, parent_of: dict[str, str], label_of: dict[str, Any]
    ) -> list[Any]:
        """Return a node's ancestors, root first, excluding the node itself.

        Walks by id and spells the answer in labels. Guarded against a cycle
        -- ``parents`` is author-supplied and nothing upstream checks it --
        by refusing to visit an id twice; a cycle then yields the chain up to
        the repeat rather than looping forever.
        """
        chain: list[Any] = []
        seen = {node_id}
        current = parent_of.get(node_id, "")
        while current and current not in seen:
            seen.add(current)
            chain.append(label_of.get(current, current))
            current = parent_of.get(current, "")
        chain.reverse()
        return chain


def _number(value: Any) -> float | None:
    """Coerce one of plotly's numbers, or None when it is not one."""
    value = PlotlyPlot._to_native(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None

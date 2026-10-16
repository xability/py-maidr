"""
``seaborn.clustermap``: a heatmap in clustered order, and the trees that order it.

A clustermap is four things on one figure: the heatmap, its row and column
dendrograms, and its colorbar -- with, optionally, a strip of row or column
colors between a dendrogram and the heatmap. The heatmap is drawn through
``seaborn.heatmap``, so the heatmap patch already reads it, in the clustered
order and with the values of ``ClusterGrid.data2d``. Two things were missing:

* **The color strips were read as heatmaps.** ``ClusterGrid.plot_colors``
  draws each strip with ``seaborn.heatmap`` over the *indices* of a color
  list, so a reader met a second and third heatmap whose cells were ``0``,
  ``1`` and ``2`` and whose rows were named ``0.5``, ``1.5`` ... Nothing in
  them is data the caller gave: the colors are the data, and they are not
  named anywhere. They are drawn quietly here, so they register nothing.

* **The dendrograms were not read at all.** They are one ``LineCollection``
  each, which no patch reads, so the clustering -- the whole reason to draw a
  clustermap instead of a heatmap -- reached the reader only as an unexplained
  row order. Each is registered here as a ``tree`` layer built from the
  linkage seaborn clustered with, the hierarchy maidr.js navigates by parent,
  child and sibling.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.heatmap import HeatPlot
from maidr.core.plot.prebuilt import PrebuiltPlot
from maidr.patch.common import _draw_quietly
from maidr.util.panel_title import remember_panel_title

#: The generated titles. A caller's own ``set_title`` wins over them, as it
#: does over every generated panel title -- see :mod:`maidr.util.panel_title`.
HEATMAP_TITLE = "Clustered heatmap"
ROW_TREE_TITLE = "Row dendrogram"
COLUMN_TREE_TITLE = "Column dendrogram"


def _label(value: Any) -> str:
    """
    One index entry as seaborn writes it on a tick.

    Parameters
    ----------
    value : Any
        An entry of a pandas index; a tuple for a ``MultiIndex``.

    Returns
    -------
    str
        The entry, a ``MultiIndex`` tuple joined with ``-`` as seaborn's
        ``_index_to_ticklabels`` joins it.
    """
    if isinstance(value, tuple):
        return "-".join(map(str, value))
    return str(value)


def _leaf_names(ax: Axes, axis: int, index: Sequence[Any]) -> list[str]:
    """
    What each row or column of the clustered heatmap is called, in its order.

    The heatmap's own tick labels when they name every cell, so a leaf of the
    tree is announced as the heatmap row it is; otherwise -- seaborn thins the
    labels of a large heatmap -- the index of the reordered data.

    Parameters
    ----------
    ax : Axes
        The heatmap axes.
    axis : int
        ``0`` for the rows, ``1`` for the columns.
    index : sequence
        ``ClusterGrid.data2d``'s index (rows) or columns, already reordered.

    Returns
    -------
    list of str
        One name per row or column, top to bottom or left to right.
    """
    ticks = ax.get_yticklabels() if axis == 0 else ax.get_xticklabels()
    texts = [tick.get_text() for tick in ticks]
    if len(texts) == len(index) and all(texts):
        return texts
    return [_label(value) for value in index]


def _distance(height: float) -> str:
    """
    A merge height to three significant figures, positionally.

    Parameters
    ----------
    height : float
        The linkage distance at which two clusters merged.

    Returns
    -------
    str
        ``1.42``, ``0.00123`` or ``1230`` -- never an exponent.
    """
    return np.format_float_positional(
        height, precision=3, unique=True, fractional=False, trim="-"
    )


def dendrogram_nodes(
    linkage: Any, leaves: Sequence[int], names: Sequence[str]
) -> list[dict[str, Any]]:
    """
    A dendrogram as the ``tree`` trace reads it: each node and its ancestors.

    Each node is named by what it holds, so a reader knows where in the
    heatmap a cluster lies without counting: a leaf by its row or column, and
    a cluster by the first and last leaf it spans in the drawn order and the
    distance at which its two halves merged -- ``"d to a (distance 1.42)"``.
    A cluster's leaves are contiguous in that order, so two sibling clusters
    never share a name; two leaves with the same label do, and the second is
    numbered.

    No magnitude is declared. A leaf has no size, and a merge distance is not
    a share of its parent, which is what the trace makes of a magnitude.

    Parameters
    ----------
    linkage : array-like
        The ``(n - 1, 4)`` linkage matrix, as ``scipy.cluster.hierarchy``
        returns it: row ``i`` merges nodes ``Z[i, 0]`` and ``Z[i, 1]`` at
        distance ``Z[i, 2]`` into node ``n + i``.
    leaves : sequence of int
        The original index of each leaf, in the order the dendrogram drew
        them -- ``reordered_ind``.
    names : sequence of str
        What each leaf is called, in that same drawn order.

    Returns
    -------
    list of dict
        Every node, root first and depth first, children in drawn order:
        ``{"x": name}``, with ``"path"`` (its ancestors' names, root first)
        on every node but the root. Empty when nothing was merged.
    """
    merges = np.asarray(linkage, dtype=float)
    if not len(merges):
        return []
    count = len(leaves)
    position = {int(leaf): at for at, leaf in enumerate(leaves)}

    # Each node's children, merge distance, and the span of drawn positions
    # it covers. A merge only names nodes made before it, so one pass in
    # order has every child's span ready when its parent needs it.
    children: dict[int, tuple[int, int]] = {}
    heights: dict[int, float] = {}
    spans: dict[int, tuple[int, int]] = {
        leaf: (at, at) for leaf, at in position.items()
    }
    for row, (left, right, height, _size) in enumerate(merges):
        node = count + row
        pair = sorted((int(left), int(right)), key=lambda child: spans[child][0])
        children[node] = (pair[0], pair[1])
        heights[node] = float(height)
        spans[node] = (spans[pair[0]][0], spans[pair[1]][1])

    def name(node: int) -> str:
        first, last = spans[node]
        if node in children:
            return (
                f"{names[first]} to {names[last]} (distance {_distance(heights[node])})"
            )
        return names[first]

    root = count + len(merges) - 1

    nodes: list[dict[str, Any]] = []
    stack: list[tuple[int, str, list[str]]] = [(root, name(root), [])]
    while stack:
        node, own, path = stack.pop()
        nodes.append({"x": own, "path": path} if path else {"x": own})
        if node not in children:
            continue
        taken: set[str] = set()
        named = []
        for child in children[node]:
            label, suffix = name(child), 2
            while label in taken:
                label, suffix = f"{name(child)} ({suffix})", suffix + 1
            taken.add(label)
            named.append((child, label))
        # Pushed last-first, so the first child in drawn order is popped first.
        for child, label in reversed(named):
            stack.append((child, label, [*path, own]))
    return nodes


def _register_tree(
    ax: Axes | None, dendrogram: Any, names: list[str], noun: str, title: str
) -> None:
    """
    Register one dendrogram as a ``tree`` layer on the axes it is drawn on.

    Parameters
    ----------
    ax : Axes or None
        The dendrogram's axes.
    dendrogram : Any
        seaborn's ``_DendrogramPlotter``, or ``None`` when that side was not
        clustered.
    names : list of str
        What each leaf is called, in drawn order.
    noun : str
        What a node is, such as ``"Row"`` -- the tree's ``x`` axis label.
    title : str
        The layer's title, when the caller gave the axes none.
    """
    linkage = getattr(dendrogram, "linkage", None)
    leaves = getattr(dendrogram, "reordered_ind", None)
    if ax is None or linkage is None or leaves is None or len(leaves) != len(names):
        return
    nodes = dendrogram_nodes(linkage, list(leaves), names)
    if not nodes:
        return
    remember_panel_title(ax, title)
    FigureManager.add_plot(
        PrebuiltPlot(
            ax,
            PlotType.TREE,
            labels={"x": noun},
            data=nodes,
            # Nothing drawn answers to a node one for one: the collection draws
            # one link per merge and nothing at a leaf, and the trace drops a
            # highlight whose count does not match rather than misplace it.
            selectors=None,
        )
    )


def _name_heatmap_cells(ax: Axes, columns: list[str], rows: list[str]) -> None:
    """
    Name every row and column of the heatmap layer the clustermap drew.

    seaborn labels only every other row of a large heatmap, and the heatmap
    layer then names its rows by their centers -- see
    :meth:`~maidr.core.plot.heatmap.HeatPlot.name_cells`. The clustermap
    knows every name, in the clustered order, so it hands them over.

    Parameters
    ----------
    ax : Axes
        The heatmap axes.
    columns : list of str
        One name per column, left to right.
    rows : list of str
        One name per row, top to bottom.
    """
    figure = ax.get_figure()
    maidr = FigureManager.figs.get(figure) if figure is not None else None
    for layer in getattr(maidr, "plots", ()):
        if layer.ax is ax and isinstance(layer, HeatPlot):
            layer.name_cells(columns, rows)


def _axis_name(index: Any, fallback: str) -> str:
    """
    The name of a heatmap axis's variable, or a generic one.

    Parameters
    ----------
    index : Any
        ``data2d.index`` or ``data2d.columns``.
    fallback : str
        Used when the index is unnamed.

    Returns
    -------
    str
        The index's name (its levels' names joined with ``-``), or
        ``fallback``.
    """
    names = [str(level) for level in getattr(index, "names", []) if level]
    return "-".join(names) or fallback


@wrapt.when_imported("seaborn")
def _patch_seaborn(seaborn: Any) -> None:
    """Patch ``ClusterGrid`` once seaborn is imported; see ``maidr/patch``."""
    grid = seaborn.matrix.ClusterGrid

    @wrapt.patch_function_wrapper(grid, "plot_colors")
    def plot_colors(wrapped, _instance, args, kwargs) -> Any:
        """
        Draw the row and column color strips without registering them.

        Parameters
        ----------
        wrapped : Callable
            ``ClusterGrid.plot_colors``.
        _instance : ClusterGrid
            The grid. Unused here.
        args, kwargs : Any
            As passed by ``ClusterGrid.plot``.

        Returns
        -------
        Any
            Whatever ``plot_colors`` returned.

        Notes
        -----
        ``clustermap`` hands the strips the keyword arguments it hands the
        heatmap, and drawn quietly the ``seaborn.heatmap`` patch no longer
        lifts MAIDR's own ``z_label`` out of them -- so it is dropped here,
        before ``pcolormesh`` is handed a keyword it rejects.
        """
        kwargs = {key: value for key, value in kwargs.items() if key != "z_label"}
        with ContextManager.set_internal_context():
            return _draw_quietly(wrapped, args, kwargs)

    @wrapt.patch_function_wrapper(grid, "plot")
    def plot(wrapped, instance, args, kwargs) -> Any:
        """
        Draw a clustermap and register its dendrograms as trees.

        The heatmap registers itself through the ``seaborn.heatmap`` patch;
        this adds a ``tree`` layer for each side that was clustered, and a
        title on each panel that names what it is.

        Parameters
        ----------
        wrapped : Callable
            ``ClusterGrid.plot``.
        instance : ClusterGrid
            The grid being drawn.
        args, kwargs : Any
            As passed by ``seaborn.clustermap``.

        Returns
        -------
        Any
            Whatever ``ClusterGrid.plot`` returned -- the grid.
        """
        drawn = wrapped(*args, **kwargs)
        if ContextManager.is_internal_context():
            return drawn

        heatmap = instance.ax_heatmap
        data = instance.data2d
        rows = _leaf_names(heatmap, 0, data.index)
        columns = _leaf_names(heatmap, 1, data.columns)
        remember_panel_title(heatmap, HEATMAP_TITLE)
        _name_heatmap_cells(heatmap, columns, rows)
        _register_tree(
            instance.ax_row_dendrogram,
            getattr(instance, "dendrogram_row", None),
            rows,
            _axis_name(data.index, "Row"),
            ROW_TREE_TITLE,
        )
        _register_tree(
            instance.ax_col_dendrogram,
            getattr(instance, "dendrogram_col", None),
            columns,
            _axis_name(data.columns, "Column"),
            COLUMN_TREE_TITLE,
        )
        return drawn

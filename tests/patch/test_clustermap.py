"""A ``seaborn.clustermap`` reads as its heatmap and the two trees that order it.

Before this, the heatmap was read -- through the ``seaborn.heatmap`` patch,
already in the clustered order -- but beside it a row or column color strip
registered as a heatmap of color *indices*, a large heatmap's rows were named
by their centers because seaborn labels only every other one, and the
dendrograms registered nothing, so the clustering reached the reader only as
an unexplained row order. The tests pin the heatmap against
``ClusterGrid.data2d``, the strips as unread, and each dendrogram as a
``tree`` layer whose structure is the linkage seaborn clustered with, and
whose every node is highlighted by an unseen mark where seaborn drew it.
"""

from __future__ import annotations

import io
import re
from typing import Any

import matplotlib.image
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns
from matplotlib.collections import LineCollection

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.clustermap import NODE_MARK_RADIUS, dendrogram_nodes
from maidr.util.bundle_capability import bundle_trace_types


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.normal(size=(5, 4)),
        index=pd.Index(list("abcde"), name="gene"),
        columns=pd.Index(list("WXYZ"), name="sample"),
    )


def layers(grid) -> list:
    return FigureManager.get_maidr(grid.figure).plots


def layer_on(grid, ax) -> dict[str, Any]:
    (layer,) = [plot for plot in layers(grid) if plot.ax is ax]
    return layer.schema


def test_a_clustermap_is_its_heatmap_and_two_trees(frame):
    grid = sns.clustermap(frame)

    assert {(plot.type, id(plot.ax)) for plot in layers(grid)} == {
        (PlotType.HEAT, id(grid.ax_heatmap)),
        (PlotType.TREE, id(grid.ax_row_dendrogram)),
        (PlotType.TREE, id(grid.ax_col_dendrogram)),
    }


@pytest.mark.parametrize(
    "options", [{}, {"z_score": 0}, {"standard_scale": 1}, {"method": "ward"}]
)
def test_the_heatmap_is_read_in_the_clustered_order(frame, options):
    grid = sns.clustermap(frame, **options)
    data = layer_on(grid, grid.ax_heatmap)[MaidrKey.DATA]

    assert data[MaidrKey.Y] == list(grid.data2d.index)
    assert data[MaidrKey.X] == list(grid.data2d.columns)
    np.testing.assert_allclose(data[MaidrKey.POINTS], grid.data2d.to_numpy())
    # Clustered, not as given: the order is the dendrograms'.
    assert data[MaidrKey.Y] == [
        frame.index[i] for i in grid.dendrogram_row.reordered_ind
    ]


def test_the_heatmap_keeps_its_highlight_and_axis_names(frame):
    grid = sns.clustermap(frame)
    heat = layer_on(grid, grid.ax_heatmap)

    assert heat[MaidrKey.SELECTOR]
    assert heat[MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL] == "sample"
    assert heat[MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL] == "gene"
    assert heat[MaidrKey.TITLE] == "Clustered heatmap"


def test_every_row_of_a_large_clustermap_is_named():
    """seaborn labels every other row of this one; the reader hears them all."""
    rng = np.random.default_rng(1)
    names = [f"g{i}" for i in range(60)]
    grid = sns.clustermap(pd.DataFrame(rng.normal(size=(60, 8)), index=names))
    assert len(grid.ax_heatmap.get_yticklabels()) < 60

    rows = layer_on(grid, grid.ax_heatmap)[MaidrKey.DATA][MaidrKey.Y]

    assert rows == [str(name) for name in grid.data2d.index]


def test_the_color_strips_are_not_read_as_heatmaps(frame):
    grid = sns.clustermap(
        frame,
        row_colors=["r", "g", "b", "r", "g"],
        col_colors=["k", "y", "k", "y"],
    )

    assert sorted(plot.type for plot in layers(grid)) == sorted(
        [PlotType.HEAT, PlotType.TREE, PlotType.TREE]
    )
    assert all(
        plot.ax not in (grid.ax_row_colors, grid.ax_col_colors) for plot in layers(grid)
    )


def test_z_label_reaches_the_heatmap_and_not_the_strips(frame):
    """The strips are drawn with the heatmap's keywords; ``z_label`` is ours."""
    grid = sns.clustermap(frame, z_label="Expression", row_colors=list("rgbrg"))

    heat = layer_on(grid, grid.ax_heatmap)
    assert heat[MaidrKey.AXES][MaidrKey.Z][MaidrKey.LABEL] == "Expression"


def test_a_side_left_unclustered_has_no_tree(frame):
    grid = sns.clustermap(frame, row_cluster=False)

    assert [plot.ax for plot in layers(grid) if plot.type == PlotType.TREE] == [
        grid.ax_col_dendrogram
    ]
    rows = layer_on(grid, grid.ax_heatmap)[MaidrKey.DATA][MaidrKey.Y]
    assert rows == list(frame.index)


def _children(nodes: list[dict]) -> dict[tuple, list[str]]:
    """Each node's address, mapped to its children's names in order."""
    tree: dict[tuple, list[str]] = {}
    for node in nodes:
        address = (*node.get("path", []), node["x"])
        tree.setdefault(address, [])
        if node.get("path"):
            tree.setdefault(tuple(node["path"]), []).append(node["x"])
    return tree


@pytest.mark.parametrize("side", ["row", "col"])
def test_each_dendrogram_is_the_tree_seaborn_clustered_with(frame, side):
    grid = sns.clustermap(frame)
    dendrogram = getattr(grid, f"dendrogram_{side}")
    ax = getattr(grid, f"ax_{side}_dendrogram")
    tree = layer_on(grid, ax)
    nodes = tree[MaidrKey.DATA]
    index = grid.data2d.index if side == "row" else grid.data2d.columns
    heat = layer_on(grid, grid.ax_heatmap)[MaidrKey.DATA]

    assert tree[MaidrKey.TYPE] == PlotType.TREE
    assert tree[MaidrKey.TITLE] == ("Row" if side == "row" else "Column") + (
        " dendrogram"
    )
    assert tree[MaidrKey.AXES] == {MaidrKey.X: {MaidrKey.LABEL: index.name}}
    # One node per leaf and one per merge, the root first.
    leaves = len(dendrogram.reordered_ind)
    assert len(nodes) == 2 * leaves - 1
    assert "path" not in nodes[0] and all("path" in node for node in nodes[1:])
    # A leaf is the heatmap row or column it orders, in the same order.
    shape = _children(nodes)
    leaf_names = [address[-1] for address, kids in shape.items() if not kids]
    assert leaf_names == heat[MaidrKey.Y if side == "row" else MaidrKey.X]
    # Every merge has exactly two halves, and each is named by its span and
    # the distance it merged at, the root at the linkage's last.
    assert all(len(kids) == 2 for kids in shape.values() if kids)
    top = dendrogram.linkage[-1, 2]
    assert nodes[0]["x"].startswith(f"{leaf_names[0]} to {leaf_names[-1]} ")
    assert f"{top:.3g}" in nodes[0]["x"]
    # No magnitude, and one highlight per node.
    assert all("y" not in node for node in nodes)
    assert len(tree[MaidrKey.SELECTOR]) == len(nodes)


def test_a_tree_is_built_depth_first_in_drawn_order():
    # Leaves 0..3; 0+1 merge at 1, 2+3 at 2, both at 3. Drawn order 1, 0, 3, 2.
    linkage = [[0, 1, 1.0, 2], [2, 3, 2.0, 2], [4, 5, 3.0, 4]]

    nodes = dendrogram_nodes(linkage, [1, 0, 3, 2], ["b", "a", "d", "c"])

    root = "b to c (distance 3)"
    left, right = "b to a (distance 1)", "d to c (distance 2)"
    assert nodes == [
        {"x": root},
        {"x": left, "path": [root]},
        {"x": "b", "path": [root, left]},
        {"x": "a", "path": [root, left]},
        {"x": right, "path": [root]},
        {"x": "d", "path": [root, right]},
        {"x": "c", "path": [root, right]},
    ]


def test_siblings_with_one_label_are_told_apart():
    nodes = dendrogram_nodes([[0, 1, 0.5, 2]], [0, 1], ["same", "same"])

    assert [node["x"] for node in nodes[1:]] == ["same", "same (2)"]


def test_nothing_merged_is_no_tree():
    assert dendrogram_nodes(np.empty((0, 4)), [0], ["only"]) == []


def test_a_caller_title_wins(frame):
    grid = sns.clustermap(frame)
    grid.ax_heatmap.set_title("Expression")

    assert layer_on(grid, grid.ax_heatmap)[MaidrKey.TITLE] == "Expression"


def test_a_clustermap_renders_and_the_bundle_knows_its_trees(frame):
    grid = sns.clustermap(frame)

    html = str(maidr.render(grid))

    assert "Row dendrogram" in html and "Column dendrogram" in html
    assert "tree" in bundle_trace_types()


# --- Highlighting each node -------------------------------------------------
#
# maidr.js outlines one drawn element per node, and seaborn draws one link per
# merge and nothing at a leaf, so an unseen mark is drawn at every node: at
# the apex of a merge's link and at the tip of a leaf. These pin the marks to
# the nodes they name, in the layer's order, against the links seaborn drew,
# and the figure as it looked without them.


def marks(grid, ax) -> list:
    """The artist each of the tree layer's selectors names, in its order."""
    by_gid = {artist.get_gid(): artist for artist in ax.get_children()}
    selectors = layer_on(grid, ax)[MaidrKey.SELECTOR]
    return [by_gid[re.fullmatch(r"g\[id='(.+)'\] > path", s)[1]] for s in selectors]


def tree_coords(point, rotated: bool) -> tuple[float, float]:
    """A point in data coordinates as ``(along the tree, distance)``."""
    x, y = point
    return (y, x) if rotated else (x, y)


def centre(ax, mark) -> np.ndarray:
    """Where a mark is centred, in the axes' data coordinates."""
    return ax.transData.inverted().transform(mark.get_transform().transform((0, 0)))


def _clustermaps() -> list:
    rng = np.random.default_rng(3)
    tied = pd.DataFrame(
        [[0, 1], [0, 1], [1, 2], [1, 2], [5, 6], [9, 10]],
        index=list("pqrstu"),
        columns=["A", "B"],
    )
    return [
        pytest.param({}, id="default"),
        pytest.param({"method": "ward"}, id="ward"),
        pytest.param({"z_score": 0, "metric": "correlation"}, id="correlation"),
        pytest.param({"data": pd.DataFrame(rng.normal(size=(60, 8)))}, id="sixty-rows"),
        pytest.param({"data": tied}, id="tied-distances"),
    ]


@pytest.mark.parametrize("side", ["row", "col"])
@pytest.mark.parametrize("options", _clustermaps())
def test_each_node_is_marked_where_it_is_drawn(frame, side, options):
    options = dict(options)
    grid = sns.clustermap(options.pop("data", frame), **options)
    ax = getattr(grid, f"ax_{side}_dendrogram")
    rotated = side == "row"
    nodes = layer_on(grid, ax)[MaidrKey.DATA]
    leaf_names = layer_on(grid, grid.ax_heatmap)[MaidrKey.DATA][
        MaidrKey.Y if rotated else MaidrKey.X
    ]
    (lines,) = [c for c in ax.collections if isinstance(c, LineCollection)]
    links = [
        np.array([tree_coords(vertex, rotated) for vertex in segment])
        for segment in lines.get_segments()
    ]
    found = marks(grid, ax)

    # One mark per node, each a separate artist, in the layer's order.
    assert len(found) == len(nodes) == 2 * len(leaf_names) - 1
    assert len({id(mark) for mark in found}) == len(found)
    at = {
        (*node.get("path", []), node["x"]): np.array(
            tree_coords(centre(ax, mark), rotated)
        )
        for node, mark in zip(nodes, found)
    }
    children: dict[tuple, list[np.ndarray]] = {}
    for address, point in at.items():
        children.setdefault(address[:-1], []).append(point)

    leaf = 0
    for address, point in at.items():
        below = children.get(address)
        if below is None:
            # A leaf: at the tip of its row or column, on the baseline.
            assert address[-1].startswith(leaf_names[leaf])
            np.testing.assert_allclose(point, (5 + 10 * leaf, 0), atol=1e-9)
            leaf += 1
            continue
        # A merge: at the apex of the link seaborn drew down to its children.
        (link,) = [
            link
            for link in links
            if np.allclose(link[[0, 3]], below, atol=1e-9)
            and np.isclose(link[1, 1], point[1])
        ]
        np.testing.assert_allclose(
            point, ((link[1, 0] + link[2, 0]) / 2, link[1, 1]), atol=1e-9
        )
    assert leaf == len(leaf_names)


def test_the_marks_are_unseen_and_above_the_links(frame):
    grid = sns.clustermap(frame)

    for ax in (grid.ax_row_dendrogram, grid.ax_col_dendrogram):
        (lines,) = [c for c in ax.collections if isinstance(c, LineCollection)]
        for mark in marks(grid, ax):
            assert mark.get_facecolor()[3] == 0
            assert mark.get_edgecolor()[3] == 0
            assert mark.get_linewidth() == 0
            assert not mark.get_in_layout()
            assert not mark.get_clip_on()
            # Above the links: maidr.js outlines a selected panel by stroking
            # the first shape in it, and that stays the tree's links.
            assert mark.get_zorder() > lines.get_zorder()
            # Small, and the same size on screen whatever the tree's scale.
            corner = mark.get_transform().transform((1, 0))
            middle = mark.get_transform().transform((0, 0))
            radius = np.hypot(*(corner - middle)) * 72 / grid.figure.dpi
            assert radius == pytest.approx(NODE_MARK_RADIUS)


def _png(figure, **options) -> np.ndarray:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", **options)
    buffer.seek(0)
    return matplotlib.image.imread(buffer)


@pytest.mark.parametrize("options", [{}, {"bbox_inches": "tight"}])
def test_the_figure_looks_as_it_did_without_the_marks(frame, options):
    grid = sns.clustermap(frame)
    every = [
        mark
        for ax in (grid.ax_row_dendrogram, grid.ax_col_dendrogram)
        for mark in marks(grid, ax)
    ]

    drawn = _png(grid.figure, **options)
    for mark in every:
        mark.set_visible(False)
    without = _png(grid.figure, **options)

    assert drawn.shape == without.shape
    np.testing.assert_array_equal(drawn, without)


def test_a_tree_not_laid_out_as_expected_is_not_highlighted(frame, monkeypatch):
    """A link out of place would put every mark after it on the wrong node."""
    plotter = sns.matrix._DendrogramPlotter
    calculate = plotter.calculate_dendrogram

    def shifted(self):
        dendrogram = calculate(self)
        dendrogram["icoord"] = [[x + 1 for x in link] for link in dendrogram["icoord"]]
        return dendrogram

    monkeypatch.setattr(plotter, "calculate_dendrogram", shifted)
    grid = sns.clustermap(frame)

    for ax in (grid.ax_row_dendrogram, grid.ax_col_dendrogram):
        tree = layer_on(grid, ax)
        assert (
            len(tree[MaidrKey.DATA])
            == 2 * len(frame.index if ax is grid.ax_row_dendrogram else frame.columns)
            - 1
        )
        assert MaidrKey.SELECTOR not in tree
        assert not ax.patches


def test_the_rendered_page_carries_a_mark_per_selector(frame):
    grid = sns.clustermap(frame)
    selectors = [
        selector
        for ax in (grid.ax_row_dendrogram, grid.ax_col_dendrogram)
        for selector in layer_on(grid, ax)[MaidrKey.SELECTOR]
    ]

    html = str(maidr.render(grid))

    for selector in selectors:
        gid = re.fullmatch(r"g\[id='(.+)'\] > path", selector)[1]
        assert re.search(rf'<g id="{gid}"[^>]*>\s*<path ', html), gid

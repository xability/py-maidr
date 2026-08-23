"""Plotly's three hierarchy paintings produced figures with no layers.

`go.Treemap`, `go.Sunburst` and `go.Icicle` state one tree the same way --
`labels`, `parents` and an optional `values` -- and differ only in how it is
painted. `maidr/plotly/` had no handling for any of them, so each fell
through `_extract_plots` to `PlotlyPlotFactory`, which returned `None`
(#627). The core has drawn all three since xability/maidr#808.

`TreemapPoint` wants that tree flattened: one point per node carrying its
name, its declared value and the chain of ancestors above it.

Two things were measured rather than assumed, because the selector is
positional -- one element per node -- so either one being wrong lands every
later node on another slice:

  * **the order is the trace's own.** Given an input in neither depth-first
    nor breadth-first order (`r, a1, b, a, b1`), `gd.calcdata` kept it
    exactly. `sort` changes the drawn layout, not that order, and a
    four-deep chain came back in input order too.
  * **the kth element is the kth node.** Verified in Chromium against the
    `text.slicetext` sitting parallel to each slice: `['r', 'a', 'b', 'a1']`
    for all three paintings.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: A tree written in neither depth-first nor breadth-first order, so an
#: emitted order that reshuffled it could not pass by coincidence.
SHUFFLED = {
    "labels": ["r", "a1", "b", "a", "b1"],
    "parents": ["", "a", "r", "r", "b"],
    "values": [10, 1, 4, 6, 2],
}

PAINTINGS = [
    (go.Treemap, PlotType.TREEMAP, "treemaplayer"),
    (go.Sunburst, PlotType.SUNBURST, "sunburstlayer"),
    (go.Icicle, PlotType.ICICLE, "iciclelayer"),
]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


@pytest.mark.parametrize(("cls", "expected", "layer"), PAINTINGS)
def test_each_painting_is_read_as_itself(cls, expected, layer) -> None:
    """The reproduction, and the reason one class serves three types.

    They differ only in shape, but the chart type is announced -- a reader
    told "treemap" about a sunburst has been told something false about the
    picture beside them.
    """
    (emitted,) = _layers(go.Figure([cls(**SHUFFLED)]))

    assert emitted["type"] == expected
    assert f".{layer}" in emitted["selectors"]


def test_the_nodes_keep_the_order_they_were_written_in() -> None:
    """Measured against ``gd.calcdata``, which kept the input order exactly.

    The selector is positional, so a reordering here would land every later
    node on another slice -- and the reading would still look plausible,
    which is what makes it worth pinning.
    """
    (layer,) = _layers(go.Figure([go.Treemap(**SHUFFLED)]))

    assert [point["x"] for point in layer["data"]] == SHUFFLED["labels"]


def test_each_node_carries_the_ancestors_above_it() -> None:
    """Root first, excluding the node itself; a top-level node has none."""
    (layer,) = _layers(go.Figure([go.Treemap(**SHUFFLED)]))
    paths = {point["x"]: point.get("path") for point in layer["data"]}

    assert paths == {
        "r": None,
        "a": ["r"],
        "b": ["r"],
        "a1": ["r", "a"],
        "b1": ["r", "b"],
    }


def test_declared_values_are_passed_on() -> None:
    """Every node's, including the interior ones.

    `TreemapPoint.y` keeps a declared value even where it disagrees with the
    sum of its children: a parent may carry mass no child accounts for, and
    recomputing it would be inventing data.
    """
    (layer,) = _layers(go.Figure([go.Treemap(**SHUFFLED)]))

    assert [point["y"] for point in layer["data"]] == [10.0, 1.0, 4.0, 6.0, 2.0]


def test_a_tree_with_no_values_carries_none() -> None:
    """Plotly counts leaves instead, and declares nothing.

    Measured: ``gd.calcdata`` reports ``None`` for every node. There is no
    declared magnitude to pass on, and `TreemapPoint.y` is optional exactly
    for that.
    """
    (layer,) = _layers(go.Figure([go.Treemap(labels=["r", "a"], parents=["", "r"])]))

    assert all("y" not in point for point in layer["data"])
    assert [point["x"] for point in layer["data"]] == ["r", "a"]


def test_ids_resolve_the_tree_and_labels_name_it() -> None:
    """How a tree with two nodes of the same name is written at all.

    With `ids` given, plotly reads `parents` as ids rather than as labels.
    The path is resolved through those ids and then spelled in labels,
    because `TreemapPoint.x` is the node's *name* and its `path` has to be
    in the same vocabulary for a reader to follow it.
    """
    (layer,) = _layers(
        go.Figure(
            [
                go.Treemap(
                    ids=["r", "a", "b", "a-1"],
                    labels=["root", "node", "node", "leaf"],
                    parents=["", "r", "r", "a"],
                    values=[10, 6, 4, 4],
                )
            ]
        )
    )

    assert [point["x"] for point in layer["data"]] == ["root", "node", "node", "leaf"]
    assert layer["data"][3]["path"] == ["root", "node"]


def test_a_many_rooted_hierarchy_is_declined() -> None:
    """Plotly invents a parent for it.

    Measured: `labels=[r1, r2, a]` with `parents=["", "", "r1"]` came back
    as **four** nodes, the first an id plotly made up with an empty label,
    and four slices were drawn for three authored nodes. Emitting that node
    would announce a nameless root the author never wrote; omitting it would
    leave the positional selector one place out for every node.
    """
    figure = go.Figure(
        [go.Treemap(labels=["r1", "r2", "a"], parents=["", "", "r1"], values=[5, 3, 2])]
    )

    assert _layers(figure) == []


def test_a_declined_hierarchy_does_not_take_a_grid_cell() -> None:
    """It renders nothing, so it reserves nothing.

    The same rule `TestPlotlyUnrenderedDomainTraces` holds for a
    `go.Table`: a domain trace maidr draws no layer for occupies no cell,
    because reserving one would shift every renderable subplot beside it.
    """
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
    )
    figure.add_trace(
        go.Treemap(labels=["r1", "r2"], parents=["", ""], values=[5, 3]), row=1, col=1
    )
    figure.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

    cells = [(plot.row_index, plot.col_index) for plot in PlotlyMaidr(figure)._plots]

    assert cells == [(0, 0)]


def test_each_painting_numbers_among_its_own_kind() -> None:
    """Each has its own figure-level layer, so they do not shift each other.

    A treemap beside a sunburst beside an icicle: all three are the first
    trace group of their own layer.
    """
    layers = _layers(
        go.Figure(
            [
                go.Treemap(**SHUFFLED, domain={"x": [0, 0.3]}),
                go.Sunburst(**SHUFFLED, domain={"x": [0.35, 0.65]}),
                go.Icicle(**SHUFFLED, domain={"x": [0.7, 1]}),
            ]
        )
    )

    assert len(layers) == 3
    assert all("nth-child(1)" in layer["selectors"] for layer in layers)


def test_two_treemaps_address_their_own_slices() -> None:
    """The position stands in for a subplot prefix, as it does for a pie."""
    first, second = _layers(
        go.Figure(
            [
                go.Treemap(**SHUFFLED, domain={"x": [0, 0.45]}),
                go.Treemap(
                    labels=["r", "a"], parents=["", "r"], domain={"x": [0.55, 1]}
                ),
            ]
        )
    )

    assert "nth-child(1)" in first["selectors"]
    assert "nth-child(2)" in second["selectors"]


def test_a_hierarchy_names_its_two_dimensions() -> None:
    """It draws no axes, so the generic pair says what the two are."""
    (layer,) = _layers(go.Figure([go.Treemap(**SHUFFLED)]))

    assert layer["axes"]["x"]["label"] == "Node"
    assert layer["axes"]["y"]["label"] == "Value"


def test_a_cycle_in_parents_does_not_hang() -> None:
    """`parents` is author-supplied and nothing upstream checks it.

    The walk refuses to visit an id twice, so a cycle yields the chain up to
    the repeat rather than looping forever.
    """
    (layer,) = _layers(
        go.Figure([go.Treemap(labels=["r", "a", "b"], parents=["", "b", "a"])])
    )

    assert [point["x"] for point in layer["data"]] == ["r", "a", "b"]

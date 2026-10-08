"""A networkx drawing of a directed graph reads as the graph.

``nx.draw`` and ``nx.draw_networkx`` draw every node as one point of an
``ax.scatter`` collection, so before this a drawn graph registered a *point*
layer of its nodes' layout coordinates and nothing of its edges. A directed
graph is now a ``directed_graph`` layer: one node per drawn node, each naming
what feeds it. The tests are about what the reading carries (the nodes, their
inputs, labels and attributes), what it follows (``nodelist``, ``edgelist``),
what it leaves as it was (an undirected graph), and that each node is
addressed on its own.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager

nx = pytest.importorskip("networkx")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def pipeline():
    graph = nx.DiGraph()
    graph.add_edges_from(
        [
            ("load", "clean"),
            ("clean", "features"),
            ("clean", "labels"),
            ("features", "train"),
            ("labels", "train"),
            ("train", "evaluate"),
        ]
    )
    return graph


def layers(fig):
    return FigureManager.get_maidr(fig).plots


def schema(fig):
    (layer,) = layers(fig)
    return layer.schema


def test_a_directed_graph_is_read_as_one_rather_than_as_points():
    fig, ax = plt.subplots()
    nx.draw_networkx(pipeline(), ax=ax)

    assert [plot.type for plot in layers(fig)] == [PlotType.DIRECTED_GRAPH]


def test_each_node_names_what_feeds_it():
    fig, ax = plt.subplots()
    nx.draw_networkx(pipeline(), ax=ax)

    nodes = {node["id"]: node for node in schema(fig)["data"]}

    assert list(nodes) == ["load", "clean", "features", "labels", "train", "evaluate"]
    assert nodes["load"]["inputs"] == []
    assert nodes["clean"]["inputs"] == ["load"]
    assert nodes["train"]["inputs"] == ["features", "labels"]
    assert schema(fig)["axes"]["x"]["label"] == "Node"


def test_nx_draw_and_its_layout_variants_are_read_too():
    for draw in (nx.draw, nx.draw_circular, nx.draw_spring):
        fig, ax = plt.subplots()
        draw(pipeline(), ax=ax)

        assert [plot.type for plot in layers(fig)] == [PlotType.DIRECTED_GRAPH]


def test_one_call_registers_one_layer():
    fig, ax = plt.subplots()
    nx.draw(pipeline(), ax=ax, with_labels=True)

    assert len(layers(fig)) == 1


def test_labels_name_the_nodes_and_scalar_data_are_attributes():
    graph = pipeline()
    graph.nodes["train"]["epochs"] = 10
    graph.nodes["train"]["optimizer"] = "adam"
    graph.nodes["train"]["weights"] = [1, 2]
    fig, ax = plt.subplots()
    nx.draw_networkx(graph, ax=ax, labels={"train": "Train model"})

    train = next(node for node in schema(fig)["data"] if node["id"] == "train")

    assert train["label"] == "Train model"
    assert train["attributes"] == {"epochs": 10, "optimizer": "adam"}


def test_only_the_nodes_and_edges_drawn_are_read():
    fig, ax = plt.subplots()
    nx.draw_networkx(
        pipeline(),
        ax=ax,
        nodelist=["clean", "features", "train"],
        edgelist=[("clean", "features"), ("features", "train")],
    )

    nodes = {node["id"]: node["inputs"] for node in schema(fig)["data"]}

    assert nodes == {"clean": [], "features": ["clean"], "train": ["features"]}


def test_an_undirected_graph_keeps_the_reading_it_had():
    fig, ax = plt.subplots()
    nx.draw(nx.Graph(pipeline()), ax=ax)

    assert [plot.type for plot in layers(fig)] == [PlotType.SCATTER]


def test_nodes_that_print_alike_leave_the_graph_to_the_reading_it_had():
    graph = nx.DiGraph([(1, "1")])
    fig, ax = plt.subplots()
    nx.draw(graph, ax=ax)

    assert [plot.type for plot in layers(fig)] == [PlotType.SCATTER]


def test_each_node_has_a_selector_naming_its_own_point():
    fig, ax = plt.subplots()
    nx.draw_networkx(pipeline(), ax=ax)

    selectors = schema(fig)["selectors"]
    (collection,) = [c for c in ax.collections if c.get_gid()]

    assert len(selectors) == 6
    assert all(f"g[id='{collection.get_gid()}']" in s for s in selectors)
    assert ":nth-of-type(3)" in selectors[2]


def test_a_multigraph_names_each_input_once():
    graph = nx.MultiDiGraph([("a", "b"), ("a", "b"), ("b", "c")])
    fig, ax = plt.subplots()
    nx.draw(graph, ax=ax)

    nodes = {node["id"]: node["inputs"] for node in schema(fig)["data"]}

    assert nodes == {"a": [], "b": ["a"], "c": ["b"]}


def test_a_graph_on_the_current_axes_is_read():
    plt.figure()
    nx.draw_networkx(pipeline())

    assert [plot.type for plot in layers(plt.gcf())] == [PlotType.DIRECTED_GRAPH]


def test_generators_for_nodelist_and_edgelist_still_reach_networkx():
    fig, ax = plt.subplots()
    nx.draw_networkx(
        pipeline(),
        ax=ax,
        nodelist=(n for n in ["load", "clean", "features"]),
        edgelist=(e for e in [("load", "clean"), ("clean", "features")]),
    )

    nodes = {node["id"]: node["inputs"] for node in schema(fig)["data"]}

    assert nodes == {"load": [], "clean": ["load"], "features": ["clean"]}
    (collection,) = ax.collections
    assert len(collection.get_offsets()) == 3


def test_a_graph_drawn_without_axes_on_a_figure_of_several_is_found():
    fig, (left, right) = plt.subplots(1, 2)
    left.scatter([1, 2], [3, 4])
    plt.sca(right)
    nx.draw_networkx(pipeline())

    assert [plot.type for plot in layers(fig)] == [
        PlotType.SCATTER,
        PlotType.DIRECTED_GRAPH,
    ]
    assert layers(fig)[1].ax is right


def test_the_selector_names_each_form_matplotlib_writes_a_collection_in():
    from maidr.patch.network_graph import _node_selector

    assert _node_selector("g1", 2) == (
        "g[id='g1'] > g:only-of-type > use:nth-of-type(3), "
        "g[id='g1'] > g:nth-of-type(3) > use:only-child, "
        "g[id='g1'] > path:nth-of-type(3)"
    )

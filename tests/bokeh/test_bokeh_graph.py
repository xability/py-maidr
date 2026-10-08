"""A Bokeh graph made by ``from_networkx`` from a directed graph is a directed graph.

``from_networkx`` turns a networkx graph into a ``GraphRenderer``, which
``PlotReader`` skipped with a warning. One made from a directed graph is now
a ``directed_graph`` layer: one node per row of the node source, each naming
the nodes whose edges arrive at it, highlighted by selecting that row. The
renderer keeps no trace of direction, so the patch on ``from_networkx``
records which graphs were directed, and an undirected one is still skipped.
"""

from __future__ import annotations

import pytest

pytest.importorskip("bokeh")
nx = pytest.importorskip("networkx")

from bokeh.plotting import figure, from_networkx  # noqa: E402

from maidr.bokeh.layers import PlotReader  # noqa: E402


def pipeline():
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("load", "clean"), ("clean", "features"), ("clean", "labels")]
    )
    graph.add_edge("features", "train")
    graph.add_edge("labels", "train")
    graph.nodes["train"]["epochs"] = 10
    graph.nodes["train"]["weights"] = None
    return graph


def read(graph):
    p = figure(title="Pipeline")
    renderer = from_networkx(graph, nx.circular_layout)
    p.renderers.append(renderer)
    return renderer, PlotReader(p).layers()


def test_a_directed_graph_is_one_directed_graph_layer():
    _, layers = read(pipeline())

    assert [layer.schema["type"] for layer in layers] == ["directed_graph"]
    assert layers[0].schema["title"] == "Pipeline"
    assert layers[0].schema["axes"] == {"x": {"label": "Node"}}


def test_each_node_names_what_feeds_it_and_its_scalar_data():
    _, (layer,) = read(pipeline())
    nodes = {node["id"]: node for node in layer.schema["data"]}

    assert list(nodes) == ["load", "clean", "features", "labels", "train"]
    assert nodes["load"]["inputs"] == []
    assert nodes["train"]["inputs"] == ["features", "labels"]
    assert nodes["train"]["attributes"] == {"epochs": 10}
    assert "attributes" not in nodes["load"]


def test_each_node_is_highlighted_by_its_row_of_the_node_source():
    renderer, (layer,) = read(pipeline())

    assert layer.highlight == {
        "kind": "points",
        "points": [[renderer.node_renderer.id, row] for row in range(5)],
    }
    assert layer.renderers == [renderer.node_renderer]


def test_an_undirected_graph_is_still_skipped():
    with pytest.warns(UserWarning, match="GraphRenderer"):
        _, layers = read(nx.Graph(pipeline()))

    assert layers == []


def test_a_graph_renderer_built_by_hand_is_still_skipped():
    from bokeh.models import GraphRenderer

    p = figure()
    p.renderers.append(GraphRenderer())
    with pytest.warns(UserWarning, match="GraphRenderer"):
        assert PlotReader(p).layers() == []


def test_nodes_that_print_alike_leave_the_graph_unread():
    with pytest.warns(UserWarning, match="GraphRenderer"):
        _, layers = read(nx.DiGraph([(1, "1")]))

    assert layers == []

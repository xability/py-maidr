"""A Keras model's graph, drawn by ``maidr.keras.plot_model`` as a directed graph.

The graph is read from the model's config, so these need no Keras: the
configs are the ones Keras 3 and Keras 2 (``tf_keras``) wrote for the same
model, checked in by ``tests/tensorboard/fixtures/make_fixtures.py``, and a
few written out by hand. ``test_a_built_model_adds_shapes_and_parameters``
runs wherever Keras is installed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from lxml import etree
from lxml.cssselect import CSSSelector
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

import maidr
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.directed_graph import DirectedGraphPlot
from maidr.keras import plot_model
from maidr.util.graph_drawing import layout
from maidr.util.keras_config import keras_graph

FIXTURES = Path(__file__).parents[1] / "tensorboard" / "fixtures"
#: The same functional model -- a skip over a nested ``Sequential`` block --
#: as Keras 3 and Keras 2 write its ``model.to_json()``.
KERAS_3 = FIXTURES / "keras_graph.model.json"
KERAS_2 = FIXTURES / "tf_keras_graph.model.json"

#: Each layer of that model and the layers it is called on, block folded.
FOLDED = [
    ("features", []),
    ("dense_in", ["features"]),
    ("residual_block", ["dense_in"]),
    ("skip", ["dense_in", "residual_block"]),
    ("output", ["skip"]),
]
#: The same with the block opened into a scope.
EXPANDED = [
    ("features", []),
    ("dense_in", ["features"]),
    ("residual_block/block_dense_1", ["dense_in"]),
    ("residual_block/block_dense_2", ["residual_block/block_dense_1"]),
    ("skip", ["dense_in", "residual_block/block_dense_2"]),
    ("output", ["skip"]),
]


def graph_layer(figure: Figure) -> dict:
    """The one layer of a figure, as the schema maidr.js receives carries it."""
    schema = json.loads(json.dumps(FigureManager.get_maidr(figure)._flatten_maidr()))
    (layer,) = [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]
    return layer


def selected(figure: Figure) -> list:
    """The SVG elements the rendered layer's selectors resolve to, in order."""
    html = str(maidr.render(figure, use_cdn=True))
    svg = etree.fromstring(
        re.search(r"<svg.*?</svg>", html, re.S).group(0).encode(),
        etree.XMLParser(recover=True),
    )
    for element in svg.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    schema = json.loads(svg.get("maidr"))
    (layer,) = [
        layer for row in schema["subplots"] for c in row for layer in c["layers"]
    ]
    selectors = layer["selectors"]
    selectors = selectors if isinstance(selectors, list) else [selectors]
    return [element for s in selectors for element in CSSSelector(s)(svg)]


def _edges(layer: dict) -> list[tuple[str, list[str]]]:
    return [(node["id"], node["inputs"]) for node in layer["data"]]


def _sequential(layers: list[dict], name: str = "stack") -> dict:
    return {"class_name": "Sequential", "config": {"name": name, "layers": layers}}


def _dense(name: str, units: int, **config) -> dict:
    return {"class_name": "Dense", "config": {"name": name, "units": units, **config}}


def _tensor(layer: str, index: int = 0) -> dict:
    """A tensor as Keras 3 writes it in an ``inbound_nodes`` entry."""
    return {
        "class_name": "__keras_tensor__",
        "config": {"shape": [None, 4], "keras_history": [layer, 0, index]},
    }


# -- The layer ----------------------------------------------------------------


def test_a_model_is_one_directed_graph_layer_with_a_node_per_layer():
    figure = plot_model(KERAS_3.read_text())
    layer = graph_layer(figure)
    assert layer["type"] == PlotType.DIRECTED_GRAPH.value == "directed_graph"
    assert layer["title"] == "residual_model"
    assert layer["axes"] == {"x": {"label": "Layer"}}
    assert _edges(layer) == FOLDED
    assert layer["data"][0] == {
        "id": "features",
        "label": "features",
        "inputs": [],
        "attributes": {"Layer type": "InputLayer", "Output shape": "(None, 8)"},
    }
    assert layer["data"][1]["attributes"] == {
        "Layer type": "Dense",
        "Units": 16,
        "Activation": "relu",
    }
    assert layer["data"][2]["attributes"] == {"Layer type": "Sequential", "Layers": 2}


def test_each_node_highlights_its_own_box_in_declared_order():
    figure = plot_model(KERAS_3.read_text(), expand_nested=True)
    layer = graph_layer(figure)
    found = selected(figure)
    assert len(found) == len(layer["data"]) == 6
    gids = [selector.split("'")[1] for selector in layer["selectors"]]
    assert [element.getparent().get("id") for element in found] == gids
    assert len(set(gids)) == 6
    maidr.close(figure)


def test_the_title_given_wins_over_the_model_name():
    layer = graph_layer(plot_model(KERAS_3.read_text(), title="My model"))
    assert layer["title"] == "My model"


# -- Reading the config -------------------------------------------------------


@pytest.mark.parametrize("path", [KERAS_3, KERAS_2], ids=["keras3", "keras2"])
def test_a_skip_connection_is_a_second_input(path):
    layer = graph_layer(plot_model(path.read_text()))
    assert _edges(layer) == FOLDED


@pytest.mark.parametrize("path", [KERAS_3, KERAS_2], ids=["keras3", "keras2"])
def test_a_nested_model_expanded_is_a_scope_of_its_own_layers(path):
    layer = graph_layer(plot_model(path.read_text(), expand_nested=True))
    assert _edges(layer) == EXPANDED
    inner = layer["data"][2]
    assert inner["label"] == "block_dense_1"
    assert inner["path"] == ["residual_block"]
    assert all("path" not in node for node in layer["data"] if "/" not in node["id"])


def test_json_a_dict_and_a_bare_get_config_draw_the_same_graph():
    text = KERAS_3.read_text()
    config = json.loads(text)
    drawn = [
        _edges(graph_layer(plot_model(model)))
        for model in (text, config, config["config"])
    ]
    assert drawn == [FOLDED] * 3


def test_a_sequential_model_is_a_chain_from_its_input_layer():
    model = _sequential(
        [
            {
                "class_name": "InputLayer",
                "config": {"name": "pixels", "batch_shape": [None, 28, 28]},
            },
            {"class_name": "Flatten", "config": {"name": "flatten"}},
            _dense("hidden", 64, activation="relu"),
            {"class_name": "Dropout", "config": {"name": "drop", "rate": 0.2}},
            _dense("logits", 10, activation="linear"),
        ]
    )
    layer = graph_layer(plot_model(model))
    assert _edges(layer) == [
        ("pixels", []),
        ("flatten", ["pixels"]),
        ("hidden", ["flatten"]),
        ("drop", ["hidden"]),
        ("logits", ["drop"]),
    ]
    attributes = [node["attributes"] for node in layer["data"]]
    assert attributes[0]["Output shape"] == "(None, 28, 28)"
    assert attributes[3]["Rate"] == 0.2
    # A linear activation is no activation, and is not announced as one.
    assert attributes[4] == {"Layer type": "Dense", "Units": 10}


def test_a_sequential_model_without_an_input_layer_starts_at_its_first_layer():
    layer = graph_layer(plot_model(_sequential([_dense("a", 4), _dense("b", 1)])))
    assert _edges(layer) == [("a", []), ("b", ["a"])]


def test_a_keras_1_style_sequential_config_is_a_list_of_layers():
    model = {"class_name": "Sequential", "config": [_dense("a", 4), _dense("b", 1)]}
    assert _edges(graph_layer(plot_model(model))) == [("a", []), ("b", ["a"])]


def test_a_conv_layer_summarises_its_filters_and_kernel():
    model = _sequential(
        [
            {
                "class_name": "Conv2D",
                "config": {"name": "conv", "filters": 32, "kernel_size": [3, 3]},
            }
        ]
    )
    (node,) = graph_layer(plot_model(model))["data"]
    assert node["attributes"] == {
        "Layer type": "Conv2D",
        "Filters": 32,
        "Kernel size": "3x3",
    }


def _functional(layers: list[dict], inputs, outputs, name: str = "net") -> dict:
    return {
        "class_name": "Functional",
        "config": {
            "name": name,
            "layers": layers,
            "input_layers": inputs,
            "output_layers": outputs,
        },
    }


def _input(name: str) -> dict:
    return {
        "class_name": "InputLayer",
        "name": name,
        "config": {"name": name, "batch_shape": [None, 4]},
        "inbound_nodes": [],
    }


def _call(layer: dict, *args, **kwargs) -> dict:
    """A Keras 3 layer entry called on ``args``."""
    return {
        **layer,
        "name": layer["config"]["name"],
        "inbound_nodes": [{"args": list(args), "kwargs": kwargs}],
    }


def test_a_nested_functional_model_feeds_each_input_from_its_own_tensor():
    pair = _functional(
        [
            _input("left"),
            _input("right"),
            _call(_dense("left_dense", 4), _tensor("left")),
            _call(
                {"class_name": "Concatenate", "config": {"name": "join"}},
                [_tensor("left_dense"), _tensor("right")],
            ),
        ],
        [["left", 0, 0], ["right", 0, 0]],
        [["join", 0, 0]],
        name="pair",
    )
    model = _functional(
        [
            _input("a"),
            _input("b"),
            _call(pair, _tensor("a"), _tensor("b")),
            _call(_dense("head", 1), _tensor("pair")),
        ],
        [["a", 0, 0], ["b", 0, 0]],
        [["head", 0, 0]],
    )
    assert _edges(graph_layer(plot_model(model, expand_nested=True))) == [
        ("a", []),
        ("b", []),
        ("pair/left_dense", ["a"]),
        ("pair/join", ["pair/left_dense", "b"]),
        ("head", ["pair/join"]),
    ]
    assert _edges(graph_layer(plot_model(model))) == [
        ("a", []),
        ("b", []),
        ("pair", ["a", "b"]),
        ("head", ["pair"]),
    ]


def test_scopes_nest_as_deep_as_the_models_do():
    inner = _sequential([_dense("deep", 2)], name="inner")
    outer = _sequential([_dense("first", 2), inner], name="outer")
    model = _functional(
        [_input("x"), _call(outer, _tensor("x"))], [["x", 0, 0]], [["outer", 0, 0]]
    )
    layer = graph_layer(plot_model(model, expand_nested=True))
    assert _edges(layer) == [
        ("x", []),
        ("outer/first", ["x"]),
        ("outer/inner/deep", ["outer/first"]),
    ]
    assert layer["data"][2]["path"] == ["outer", "inner"]


def test_a_layer_called_twice_is_one_node_fed_by_both_calls():
    shared = _dense("shared", 4)
    model = _functional(
        [
            _input("a"),
            _input("b"),
            {
                **shared,
                "name": "shared",
                "inbound_nodes": [
                    {"args": [_tensor("a")], "kwargs": {}},
                    {"args": [_tensor("b")], "kwargs": {}},
                ],
            },
            _call(
                {"class_name": "Add", "config": {"name": "sum"}},
                [_tensor("shared", 0), _tensor("shared", 0)],
            ),
        ],
        [["a", 0, 0], ["b", 0, 0]],
        [["sum", 0, 0]],
    )
    assert _edges(graph_layer(plot_model(model))) == [
        ("a", []),
        ("b", []),
        ("shared", ["a", "b"]),
        ("sum", ["shared"]),
    ]


def test_a_keras_2_inbound_node_lists_layer_node_and_tensor():
    model = {
        "class_name": "Model",
        "config": {
            "name": "two",
            "layers": [
                {"class_name": "InputLayer", "name": "in", "config": {"name": "in"}},
                {
                    "class_name": "Dense",
                    "name": "d",
                    "config": {"name": "d", "units": 3},
                    "inbound_nodes": [[["in", 0, 0, {}]]],
                },
                {
                    "class_name": "Add",
                    "name": "add",
                    "config": {"name": "add"},
                    "inbound_nodes": [[["in", 0, 0, {}], ["d", 0, 0, {}]]],
                },
            ],
            "input_layers": [["in", 0, 0]],
            "output_layers": [["add", 0, 0]],
        },
    }
    assert _edges(graph_layer(plot_model(model))) == [
        ("in", []),
        ("d", ["in"]),
        ("add", ["in", "d"]),
    ]


@pytest.mark.parametrize(
    "model, error, match",
    [
        (42, TypeError, "not int"),
        ("{not json", ValueError, "model's JSON"),
        ({"name": "nothing"}, ValueError, "has none"),
        (_sequential([]), ValueError, "no layers"),
    ],
)
def test_what_is_not_a_model_raises(model, error, match):
    with pytest.raises(error, match=match):
        plot_model(model)


# -- Drawing ------------------------------------------------------------------


def test_each_layer_is_drawn_a_row_below_the_deepest_layer_feeding_it():
    layer = graph_layer(plot_model(KERAS_3.read_text(), expand_nested=True))
    rows = [row for row, _ in layout(layer["data"])]
    # The skip joins below the block, not beside it, though `dense_in` feeds
    # it directly.
    assert rows == [0, 1, 2, 3, 4, 5]


def test_side_by_side_branches_share_a_row():
    nodes = [
        {"id": "in", "inputs": []},
        {"id": "left", "inputs": ["in"]},
        {"id": "right", "inputs": ["in"]},
        {"id": "join", "inputs": ["left", "right", "missing", "join"]},
    ]
    assert layout(nodes) == [(0, 0.0), (1, -0.5), (1, 0.5), (2, 0.0)]


def test_a_cycle_still_gives_every_node_a_row():
    nodes = [{"id": "a", "inputs": ["b"]}, {"id": "b", "inputs": ["a"]}]
    assert sorted(row for row, _ in layout(nodes)) == [0, 1]


def test_a_long_chain_is_laid_out_without_recursion():
    nodes = [{"id": i, "inputs": [i - 1] if i else []} for i in range(3000)]
    assert layout(nodes)[-1] == (2999, 0.0)


def test_sixty_layers_are_drawn_on_a_page_tall_enough_to_read():
    layers = [_dense(f"dense_{i}", 8) for i in range(60)]
    figure = plot_model(_sequential(layers))
    width, height = figure.get_size_inches()
    assert len(graph_layer(figure)["data"]) == 60
    assert height > 60 * 0.8
    assert width >= 4


def test_a_layer_needs_a_box_per_node_and_unique_ids():
    figure = Figure()
    ax = figure.add_subplot()
    box = ax.add_patch(Rectangle((0, 0), 1, 1))
    with pytest.raises(ValueError, match="one box per node"):
        DirectedGraphPlot(ax, nodes=[{"id": 1}, {"id": 2}], boxes=[box], node_label="")
    with pytest.raises(ValueError, match="its own id"):
        DirectedGraphPlot(
            ax, nodes=[{"id": 1}, {"id": 1}], boxes=[box, box], node_label=""
        )


# -- A built model ------------------------------------------------------------


def test_a_built_model_adds_shapes_and_parameters():
    keras = pytest.importorskip("keras")
    inputs = keras.Input((8,), name="features")
    hidden = keras.layers.Dense(4, activation="relu", name="hidden")(inputs)
    outputs = keras.layers.Dense(1, name="output")(hidden)
    model = keras.Model(inputs, outputs, name="tiny")

    layer = graph_layer(plot_model(model))

    assert _edges(layer) == [
        ("features", []),
        ("hidden", ["features"]),
        ("output", ["hidden"]),
    ]
    assert layer["data"][1]["attributes"] == {
        "Layer type": "Dense",
        "Units": 4,
        "Activation": "relu",
        "Output shape": "(None, 4)",
        "Parameters": 36,
    }


TIED = FIXTURES / "keras_tied_block.model.json"


@pytest.mark.parametrize(
    "expand, edges",
    [
        (
            False,
            [
                ("x", []),
                ("shared", ["x", "pre"]),
                ("pre", ["shared"]),
                ("add", ["shared"]),
            ],
        ),
        (
            True,
            [
                ("x", []),
                ("shared/d", ["x", "pre"]),
                ("pre", ["shared/d"]),
                ("add", ["shared/d"]),
            ],
        ),
    ],
    ids=["folded", "expanded"],
)
def test_a_block_called_again_on_a_later_layer_keeps_both_inputs(expand, edges):
    _, nodes = keras_graph(TIED.read_text(), expand_nested=expand)
    assert [(node["id"], node["inputs"]) for node in nodes] == edges
    assert len({node["id"] for node in nodes}) == len(nodes)
    # The loop the second call makes is drawn, not followed for ever.
    assert graph_layer(plot_model(TIED.read_text(), expand_nested=expand))["data"]

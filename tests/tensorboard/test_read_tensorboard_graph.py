"""A Keras model graph read out of a TensorBoard log directory, as a directed graph.

The fixtures are what Keras 3's and Keras 2's ``TensorBoard`` callback wrote
with ``write_graph=True`` while fitting the same model, with the model's own
``model.to_json()`` beside each and, in ``expected.json``, the string
TensorBoard itself read (``tests/tensorboard/fixtures/make_fixtures.py``).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

import maidr
from maidr.tensorboard import TensorBoardChart, read_tensorboard_graph
from maidr.tensorboard.events import KERAS_MODEL_PLUGIN, find_runs, read_run
from maidr.util.keras_config import keras_graph
from tests.keras.test_plot_model import EXPANDED, FOLDED, graph_layer, selected
from tests.tensorboard.test_read_tensorboard_scalars import (
    _Writer,
    _bytes,
    _int,
    _tensor_value,
)

FIXTURES = Path(__file__).parent / "fixtures"
GRAPHS = ["keras_graph", "tf_keras_graph"]


def _read(logdir, **options) -> list[TensorBoardChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_tensorboard_graph(logdir, **options)


def _edges(chart: TensorBoardChart) -> list[tuple[str, list[str]]]:
    return [(node["id"], node["inputs"]) for node in graph_layer(chart.figure)["data"]]


@pytest.mark.parametrize("name", GRAPHS)
def test_the_model_is_the_one_tensorboard_reads(name):
    (run,) = find_runs(str(FIXTURES / name)).values()
    logged = read_run(run, KERAS_MODEL_PLUGIN).values["keras"]
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text())
    ((_, _, tensorboard),) = expected["train"]["keras"]
    assert logged == tensorboard
    model = json.loads((FIXTURES / f"{name}.model.json").read_text())
    assert json.loads(logged[0]) == model


@pytest.mark.parametrize("name", GRAPHS)
def test_the_graph_is_the_one_the_model_json_gives(name):
    model = (FIXTURES / f"{name}.model.json").read_text()
    for expand in (False, True):
        (chart,) = _read(FIXTURES / name, expand_nested=expand)
        assert chart.tag == "keras"
        assert chart.runs == ("train",)
        _, nodes = keras_graph(model, expand_nested=expand)
        assert graph_layer(chart.figure)["data"] == nodes
        assert _edges(chart) == (EXPANDED if expand else FOLDED)


def test_one_directed_graph_titled_with_the_model_and_its_run():
    (chart,) = _read(FIXTURES / "keras_graph")
    layer = graph_layer(chart.figure)
    assert layer["type"] == "directed_graph"
    assert layer["title"] == "residual_model (train)"
    assert layer["axes"]["x"]["label"] == "Layer"


def test_each_layer_highlights_its_own_box():
    (chart,) = _read(FIXTURES / "keras_graph", expand_nested=True)
    assert len(selected(chart.figure)) == len(EXPANDED)
    maidr.close(chart)


def test_the_scalars_beside_the_graph_are_still_read_as_scalars():
    charts = maidr.read_tensorboard_scalars(FIXTURES / "keras_graph")
    assert [chart.tag for chart in charts] == ["epoch_learning_rate", "epoch_loss"]


def test_a_log_directory_without_a_model_warns_and_reads_nothing():
    with pytest.warns(UserWarning, match="no Keras model graph"):
        assert read_tensorboard_graph(FIXTURES / "tf_summary") == []


def test_only_the_runs_asked_for_are_read():
    with pytest.warns(UserWarning, match="no run 'validation'"):
        assert (
            read_tensorboard_graph(FIXTURES / "keras_graph", runs=["validation"]) == []
        )


def _model_value(model: dict) -> bytes:
    """A ``keras`` summary value, as Keras's callback writes it: a string tensor."""
    tensor = _int(1, 7) + _bytes(8, json.dumps(model).encode())
    return _tensor_value("keras", tensor, KERAS_MODEL_PLUGIN)


def _model(*names: str) -> dict:
    layers = [{"class_name": "Dense", "config": {"name": n}} for n in names]
    return {"class_name": "Sequential", "config": {"name": "m", "layers": layers}}


def test_a_model_logged_twice_is_drawn_from_the_last(tmp_path):
    writer = _Writer(tmp_path)
    writer.event(0, _model_value(_model("old")))
    writer.event(1, _model_value(_model("new_a", "new_b")))
    writer.close()
    (chart,) = _read(tmp_path)
    assert _edges(chart) == [("new_a", []), ("new_b", ["new_a"])]
    assert graph_layer(chart.figure)["title"] == "m"


def test_a_model_that_cannot_be_read_is_left_out_with_a_warning(tmp_path):
    tensor = _int(1, 7) + _bytes(8, b"{oops")
    writer = _Writer(tmp_path)
    writer.event(0, _tensor_value("keras", tensor, KERAS_MODEL_PLUGIN))
    writer.close()
    with pytest.warns(UserWarning, match="could not read the model logged as 'keras'"):
        assert read_tensorboard_graph(tmp_path) == []


def test_a_model_with_no_layers_is_left_out_with_a_warning(tmp_path):
    writer = _Writer(tmp_path)
    writer.event(0, _model_value({"class_name": "Sequential", "config": {}}))
    writer.close()
    with pytest.warns(UserWarning, match="has no layers"):
        assert read_tensorboard_graph(tmp_path) == []

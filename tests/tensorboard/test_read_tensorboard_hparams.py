"""A hyperparameter sweep read out of a TensorBoard log directory.

``fixtures/hparams_sweep`` was written by the HParams plugin's own API --
``hp.hparams_config`` declaring four hyperparameters and two metrics, one in a
``validation`` group, then ``hp.hparams`` and the metric scalars in a run per
session -- and ``hparams_sweep.expected.json`` records what was written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import load_hparams, read_tensorboard_hparams

FIXTURES = Path(__file__).parent / "fixtures"
SWEEP = FIXTURES / "hparams_sweep"


def _schema(chart) -> dict:
    return json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )


def _layers(chart) -> list[dict]:
    return [
        layer
        for row in _schema(chart)["subplots"]
        for cell in row
        for layer in cell["layers"]
    ]


def test_each_session_is_read_with_its_hyperparameters_and_final_metrics():
    expected = json.loads((FIXTURES / "hparams_sweep.expected.json").read_text())
    sessions = load_hparams(SWEEP)
    assert [session.name for session in sessions] == list(expected)
    for session in sessions:
        want = expected[session.name]
        assert session.hparams == want["hparams"]
        assert list(session.hparams) == [
            "learning_rate",
            "optimizer",
            "units",
            "dropout",
        ]
        assert session.metrics == pytest.approx(want["metrics"], rel=1e-6)
        assert list(session.metrics) == ["accuracy", "validation/loss"]


def test_the_parallel_coordinates_carry_the_values_not_the_drawn_positions():
    parallel, _ = read_tensorboard_hparams(SWEEP)
    assert parallel.tag == "hparams"
    assert parallel.runs == ("session_0", "session_1", "session_2", "session_3")
    (layer,) = _layers(parallel)
    assert layer["type"] == "parallel_coordinates"
    assert len(layer["data"]) == len(layer["selectors"]) == 4
    first = {point["x"]: point["y"] for point in layer["data"][0]}
    assert {point["z"] for point in layer["data"][0]} == {"session_0"}
    assert first["learning_rate"] == 0.1
    assert first["units"] == 8
    assert first["optimizer (0 adam, 1 sgd)"] == 1
    assert first["dropout (0 False, 1 True)"] == 1
    assert first["accuracy"] == pytest.approx(0.56)
    assert first["validation/loss"] == pytest.approx(0.44)
    assert [point["x"] for point in layer["data"][0]] == [
        "learning_rate",
        "optimizer (0 adam, 1 sgd)",
        "units",
        "dropout (0 False, 1 True)",
        "accuracy",
        "validation/loss",
    ]


def test_the_scatter_matrix_is_a_row_per_metric_and_a_column_per_hyperparameter():
    _, matrix = read_tensorboard_hparams(SWEEP)
    schema = _schema(matrix)
    assert len(schema["subplots"]) == 2
    assert {len(row) for row in schema["subplots"]} == {4}
    cell = schema["subplots"][1][2]["layers"][0]
    assert cell["type"] == "point"
    assert cell["axes"]["x"]["label"] == "units"
    assert cell["axes"]["y"]["label"] == "validation/loss"
    assert sorted(point["x"] for point in cell["data"]) == [8, 16, 32, 32]


def test_without_an_experiment_every_scalar_of_a_session_is_a_metric(tmp_path):
    import shutil

    shutil.copytree(SWEEP, tmp_path / "sweep")
    for event in (tmp_path / "sweep").glob("events.out.tfevents.*"):
        event.unlink()
    sessions = load_hparams(tmp_path / "sweep")
    assert list(sessions[0].metrics) == ["accuracy", "validation/loss"]
    assert list(sessions[0].hparams) == [
        "dropout",
        "learning_rate",
        "optimizer",
        "units",
    ]


def test_a_directory_with_no_sweep_warns_and_reads_nothing(tmp_path):
    with pytest.warns(UserWarning, match="no hyperparameter sweep"):
        assert read_tensorboard_hparams(tmp_path) == []
    with pytest.raises(FileNotFoundError):
        load_hparams(tmp_path / "nowhere")


def test_a_metric_that_diverged_is_left_off_its_axis():
    from maidr.tensorboard.hparams import _column

    column = _column("loss", [0.5, float("nan"), float("inf"), None, 0.25])
    assert column.values == [0.5, None, None, None, 0.25]
    assert json.loads(json.dumps(column.values)) == column.values


def test_sessions_are_in_the_order_they_are_numbered():
    from maidr.tensorboard.hparams import _natural

    names = ["session_10", "session_2", "session_1"]
    assert sorted(names, key=_natural) == ["session_1", "session_2", "session_10"]


def test_a_tick_keeps_a_numeric_name_that_has_brackets():
    from maidr.tensorboard.hparams import _column

    assert _column("lr (log)", [0.1, 0.01]).short == "lr (log)"
    categorical = _column("optimizer", ["sgd", "adam"])
    assert categorical.short == "optimizer"
    assert categorical.name == "optimizer (0 adam, 1 sgd)"

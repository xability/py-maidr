"""PR curves read out of a TensorBoard log directory.

``fixtures/torch_pr_curves`` was written by PyTorch's ``add_pr_curve`` for a
good and a poor classifier at steps 0 and 10, and ``*.expected.json`` records
what TensorBoard itself read from it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import load_pr_curves, read_tensorboard_pr_curves
from maidr.tensorboard.pr_curves import average_precision, plot_pr_curves

FIXTURES = Path(__file__).parent / "fixtures"
TORCH = FIXTURES / "torch_pr_curves"


def _layer(figure) -> dict:
    schema = json.loads(json.dumps(FigureManager.get_maidr(figure)._flatten_maidr()))
    (layer,) = schema["subplots"][0][0]["layers"]
    return layer


def test_the_curves_are_the_ones_tensorboard_reads():
    expected = json.loads((FIXTURES / "torch_pr_curves.expected.json").read_text())
    read = load_pr_curves(TORCH)
    for run, tags in expected.items():
        for tag, events in tags.items():
            series = read[tag][run]
            assert series.steps.tolist() == [step for step, _, _ in events]
            for curve, (_, _, want) in zip(series.curves, events):
                np.testing.assert_allclose(curve, want)


def test_one_chart_per_tag_a_line_per_run_named_with_ap_and_chance():
    (chart,) = read_tensorboard_pr_curves(TORCH)
    layer = _layer(chart.figure)
    assert layer["type"] == "line"
    assert layer["title"] == "positive (step 10)"
    assert layer["axes"]["x"]["label"] == "Recall"
    assert layer["axes"]["y"]["label"] == "Precision"
    good, poor = (line[0]["z"] for line in layer["data"])
    assert good.startswith("good (AP 0.") and "chance 0.32" in good
    assert poor.startswith("poor (AP 0.") and "chance 0.32" in poor
    ap = {name.split()[0]: float(name.split("AP ")[1][:4]) for name in (good, poor)}
    assert ap["good"] > ap["poor"] > 0.32


def test_recall_rises_along_each_line_and_undefined_precision_is_left_out():
    (chart,) = read_tensorboard_pr_curves(TORCH)
    for line in _layer(chart.figure)["data"]:
        recall = [point["x"] for point in line]
        assert recall == sorted(recall)
        assert all(point["y"] > 0 for point in line)


def test_an_earlier_step_is_read_at_or_before_it():
    (chart,) = read_tensorboard_pr_curves(TORCH, step=5)
    assert _layer(chart.figure)["title"] == "positive (step 0)"
    with pytest.warns(UserWarning, match="no PR curve at or before step -1"):
        assert read_tensorboard_pr_curves(TORCH, step=-1) == []


def test_average_precision_is_the_stepwise_area():
    assert average_precision(np.array([1.0, 0.5]), np.array([0.5, 1.0])) == 0.75


def test_a_curve_from_labels_and_scores():
    truth = np.array([1, 1, 0, 0, 1, 0])
    figure = plot_pr_curves(truth, {"model": [0.9, 0.8, 0.7, 0.2, 0.6, 0.1]})
    (line,) = _layer(figure)["data"]
    assert line[0]["z"].startswith("model (AP ") and "chance 0.50" in line[0]["z"]
    assert line[-1]["x"] == 1.0
    with pytest.raises(ValueError, match="positive"):
        plot_pr_curves([0, 0], [0.1, 0.2])
    with pytest.raises(ValueError, match="scores 1 samples"):
        plot_pr_curves([1, 0], [0.1])


def test_no_pr_curves_warns_and_reads_nothing(tmp_path):
    with pytest.warns(UserWarning, match="no PR curves"):
        assert read_tensorboard_pr_curves(tmp_path) == []


def test_plot_pr_curves_is_exported_from_the_package():
    from maidr.tensorboard import plot_pr_curves as exported

    assert exported is plot_pr_curves


def test_a_nan_score_is_refused():
    with pytest.raises(ValueError, match="NaN or infinite"):
        plot_pr_curves([1, 0, 1], [0.9, float("nan"), 0.4])


def test_a_run_that_never_predicted_positive_is_left_out(monkeypatch):
    import maidr.tensorboard.pr_curves as module

    thresholds = 5
    empty = np.zeros((6, thresholds))
    empty[3] = 4  # every positive missed: tp + fp is 0 at every threshold
    empty[2] = 6
    good = module.load_pr_curves(TORCH)["positive"]["good"]
    series = {
        "positive": {
            "empty": module.PRCurveSeries(np.array([0]), np.array([0.0]), [empty]),
            "good": good,
        }
    }
    monkeypatch.setattr(module, "load_pr_curves", lambda *a, **k: series)
    with pytest.warns(UserWarning, match="predicted nothing positive"):
        (chart,) = read_tensorboard_pr_curves(TORCH)
    assert [run.split(" (")[0] for run in chart.runs] == ["good"]


def test_scores_are_counted_as_a_threshold_matrix_would_count_them(monkeypatch):
    from maidr.tensorboard import pr_curves as module

    rng = np.random.default_rng(1)
    truth = rng.random(500) < 0.4
    scores = np.round(rng.random(500), 2)  # ties, as rounded sigmoids have
    seen = []
    original = module._curve

    def recording(name, data, thresholds=None):
        seen.append((data, thresholds))
        return original(name, data, thresholds)

    monkeypatch.setattr(module, "_curve", recording)
    plot_pr_curves(truth, scores)
    ((data, thresholds),) = seen
    expected = np.unique(scores)[::-1]
    predicted = scores[None, :] >= expected[:, None]
    np.testing.assert_array_equal(thresholds, expected)
    np.testing.assert_array_equal(data[0], (predicted & truth).sum(axis=1))
    np.testing.assert_array_equal(data[1], (predicted & ~truth).sum(axis=1))


def test_a_large_set_of_scores_is_drawn_without_a_quadratic_matrix():
    rng = np.random.default_rng(2)
    truth = rng.random(200_000) < 0.3
    scores = np.clip(truth * 0.5 + rng.normal(0.3, 0.2, size=truth.size), 0, 1)
    figure = plot_pr_curves(truth, scores)  # 200k x 200k booleans would be 40 GB
    assert _layer(figure)["type"] == "line"

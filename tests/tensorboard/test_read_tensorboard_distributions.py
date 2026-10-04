"""Distributions read out of a TensorBoard log directory.

``*.distributions.json`` beside each histogram fixture records what
TensorBoard's own compressor makes of the histograms it read, which is what
its Distributions dashboard draws, so the nine values at each step are held
to TensorBoard's.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import load_histograms, read_tensorboard_distributions
from maidr.tensorboard.distributions import BASIS_POINTS, percentiles

FIXTURES = Path(__file__).parent / "fixtures"


def _layers(chart) -> list[dict]:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


@pytest.mark.parametrize(
    "name", ["tf_histograms", "keras_histograms", "torch_histograms"]
)
def test_the_nine_values_are_the_ones_tensorboard_draws(name):
    expected = json.loads((FIXTURES / f"{name}.distributions.json").read_text())
    read = load_histograms(FIXTURES / name)
    for run, tags in expected.items():
        for tag, events in tags.items():
            series = read[tag][run]
            assert len(series.buckets) == len(events)
            for buckets, (_, want) in zip(series.buckets, events):
                np.testing.assert_allclose(percentiles(buckets), want, atol=1e-12)


def test_one_line_layer_of_nine_lines_named_for_the_share_below():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        charts = read_tensorboard_distributions(FIXTURES / "tf_histograms")
    assert [chart.tag for chart in charts] == ["activations", "constant"]
    (layer,) = _layers(charts[0])
    assert layer["type"] == "line"
    assert layer["title"] == "activations (run)"
    assert layer["axes"]["x"]["label"] == "Step"
    assert layer["axes"]["y"]["label"] == "activations"
    assert layer["axes"]["z"]["label"] == "Share below"
    names = [line[0]["z"] for line in layer["data"]]
    assert names == [
        "min",
        "6.7%",
        "15.9%",
        "30.9%",
        "median",
        "69.1%",
        "84.1%",
        "93.3%",
        "max",
    ]
    assert len(BASIS_POINTS) == len(names)
    assert [p["x"] for p in layer["data"][0]] == list(range(0, 40, 4))


def test_the_lines_are_in_value_order_at_every_step():
    (chart, _) = read_tensorboard_distributions(FIXTURES / "tf_histograms")
    (layer,) = _layers(chart)
    values = np.array([[p["y"] for p in line] for line in layer["data"]])
    assert np.all(np.diff(values, axis=0) >= 0)


def test_a_widening_distribution_widens_between_its_outer_lines():
    (chart, _) = read_tensorboard_distributions(FIXTURES / "tf_histograms")
    (layer,) = _layers(chart)
    low, high = layer["data"][1], layer["data"][-2]
    spread = [h["y"] - lo["y"] for lo, h in zip(low, high)]
    assert spread[-1] > spread[0] * 1.4


def test_percentiles_of_an_empty_histogram_are_zero():
    assert percentiles(np.zeros((0, 3))).tolist() == [0.0] * 9


def test_percentiles_of_one_bucket_run_from_its_left_to_its_right_edge():
    values = percentiles(np.array([[0.0, 10.0, 100.0]]))
    np.testing.assert_allclose(values, np.array(BASIS_POINTS) / 1000)


def test_steps_are_thinned_and_max_points_is_checked():
    (chart, _) = read_tensorboard_distributions(
        FIXTURES / "tf_histograms", max_points=3
    )
    (layer,) = _layers(chart)
    assert [p["x"] for p in layer["data"][0]] == [0, 16, 36]
    with pytest.raises(ValueError, match="max_points"):
        read_tensorboard_distributions(FIXTURES / "tf_histograms", max_points=1)


def test_no_histograms_warns_and_reads_nothing(tmp_path):
    with pytest.warns(UserWarning, match="no histograms"):
        assert read_tensorboard_distributions(tmp_path) == []

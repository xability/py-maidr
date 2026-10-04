"""Histograms read out of a TensorBoard log directory, as ridgelines.

As for the scalars, the log directories under ``fixtures/`` were written by
real writers -- ``tf.summary.histogram``, Keras's ``TensorBoard`` callback with
``histogram_freq=1``, and PyTorch's ``add_histogram``, which writes the legacy
``histo`` field -- and ``*.expected.json`` records what TensorBoard itself read
from them, so the reader is held to TensorBoard's conversion of both encodings.
"""

from __future__ import annotations

import json
import struct
import warnings
from pathlib import Path

import numpy as np
import pytest

import maidr
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import (
    TensorBoardChart,
    load_histograms,
    read_tensorboard_histograms,
)
from maidr.tensorboard.histograms import rebin
from tests.tensorboard.test_read_tensorboard_scalars import (
    _bytes,
    _int,
    _key,
    _Writer,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(logdir, **options) -> list[TensorBoardChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_tensorboard_histograms(logdir, **options)


def _layer(chart: TensorBoardChart) -> dict:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    (layer,) = [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]
    return layer


# -- What TensorBoard reads ---------------------------------------------------


@pytest.mark.parametrize(
    "name", ["tf_histograms", "keras_histograms", "torch_histograms"]
)
def test_the_buckets_are_the_ones_tensorboard_reads(name):
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text())
    read = load_histograms(FIXTURES / name)
    assert {run for by_run in read.values() for run in by_run} == set(expected)
    for run, tags in expected.items():
        assert {tag for tag in read if run in read[tag]} == set(tags)
        for tag, events in tags.items():
            series = read[tag][run]
            assert series.steps.tolist() == [step for step, _, _ in events]
            assert series.wall_times.tolist() == [time for _, time, _ in events]
            for buckets, (_, _, want) in zip(series.buckets, events):
                assert buckets.shape == (len(want), 3)
                np.testing.assert_allclose(buckets, np.array(want).reshape(-1, 3))


def test_histograms_are_not_read_as_scalars_or_scalars_as_histograms():
    assert load_histograms(FIXTURES / "keras") == {}
    assert maidr.tensorboard.load_scalars(FIXTURES / "tf_histograms") == {}


# -- The ridgeline ------------------------------------------------------------


def test_one_ridgeline_per_tag_and_run_with_a_ridge_per_step():
    charts = _read(FIXTURES / "keras_histograms")
    assert [chart.tag for chart in charts] == [
        "sequential/dense/bias/histogram",
        "sequential/dense/kernel/histogram",
        "sequential/dense_1/bias/histogram",
        "sequential/dense_1/kernel/histogram",
    ]
    assert {chart.runs for chart in charts} == {("train",)}
    layer = _layer(charts[1])
    assert layer["type"] == PlotType.RIDGELINE.value == "ridgeline"
    assert layer["title"] == "sequential/dense/kernel/histogram (train)"
    assert layer["axes"]["x"]["label"] == "sequential/dense/kernel/histogram"
    assert layer["axes"]["y"]["label"] == "Step"
    assert layer["axes"]["z"]["label"] == "Count"
    assert [curve[0]["x"] for curve in layer["data"]] == [f"Step {i}" for i in range(6)]
    assert {len(curve) for curve in layer["data"]} == {30}


def test_every_step_is_counted_on_the_same_bins():
    (chart,) = _read(FIXTURES / "torch_histograms")
    layer = _layer(chart)
    positions = [[point["y"] for point in curve] for curve in layer["data"]]
    assert all(row == positions[0] for row in positions)
    # PyTorch logs 300 values a step, in hundreds of uneven buckets.
    for curve in layer["data"]:
        assert sum(point["density"] for point in curve) == pytest.approx(300, abs=0.2)


def test_a_distribution_that_widens_is_heard_widening():
    (activations, _) = _read(FIXTURES / "tf_histograms")
    layer = _layer(activations)
    first, last = layer["data"][0], layer["data"][-1]

    def spread(curve):
        values = np.array([p["y"] for p in curve])
        weights = np.array([p["density"] for p in curve])
        mean = np.average(values, weights=weights)
        return np.sqrt(np.average((values - mean) ** 2, weights=weights))

    assert spread(last) > spread(first) * 1.4


def test_each_step_highlights_its_own_ridge(tmp_path):
    (chart,) = _read(FIXTURES / "torch_histograms")
    layer = _layer(chart)
    selectors = layer["selectors"]
    assert len(selectors) == len(layer["data"]) == 5
    out = tmp_path / "weights.html"
    maidr.save_html(chart, str(out), use_cdn=False)
    page = out.read_text()
    for selector in selectors:
        gid = selector.split("'")[1]
        assert f'id="{gid}"' in page
    maidr.close(chart)


def test_steps_are_thinned_keeping_the_first_and_last(tmp_path):
    writer = _Writer(tmp_path / "run")
    for step in range(20):
        writer.event(step, _histogram_value("w", [(0.0, 1.0, 5.0), (1.0, 2.0, step)]))
    writer.close()
    (chart,) = _read(tmp_path, max_steps=4)
    assert [curve[0]["x"] for curve in _layer(chart)["data"]] == [
        "Step 0",
        "Step 6",
        "Step 13",
        "Step 19",
    ]
    (every,) = _read(tmp_path, max_steps=None)
    assert len(_layer(every)["data"]) == 20


# -- Rebinning ----------------------------------------------------------------


def test_a_bucket_is_shared_among_the_bins_it_overlaps():
    edges, counts = rebin([np.array([[0.0, 1.0, 4.0], [1.0, 4.0, 6.0]])], 4)
    assert edges.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert counts.tolist() == [[4.0, 2.0, 2.0, 2.0]]


def test_the_bins_span_every_step():
    edges, counts = rebin([np.array([[0.0, 1.0, 1.0]]), np.array([[3.0, 4.0, 1.0]])], 4)
    assert (edges[0], edges[-1]) == (0.0, 4.0)
    assert counts.tolist() == [[1, 0, 0, 0], [0, 0, 0, 1]]


def test_one_repeated_value_is_counted_in_a_unit_around_it():
    edges, counts = rebin([np.array([[0.5, 0.5, 50.0]])], 3)
    assert edges[0] == 0.0 and edges[-1] == 1.0
    assert counts.tolist() == [[0, 50, 0]]


def test_a_bucket_that_is_not_finite_is_left_out():
    edges, counts = rebin(
        [np.array([[0.0, 1.0, 2.0], [1.0, np.inf, 5.0], [np.nan, 2.0, 1.0]])], 2
    )
    assert edges.tolist() == [0.0, 0.5, 1.0]
    assert counts.tolist() == [[1.0, 1.0]]


def test_empty_buckets_do_not_stretch_the_bins():
    edges, _ = rebin([np.array([[-100.0, 0.0, 0.0], [0.0, 1.0, 3.0]])], 2)
    assert edges.tolist() == [0.0, 0.5, 1.0]


# -- Encodings ----------------------------------------------------------------


def test_a_legacy_histogram_drops_its_empty_ends_and_uses_min_and_max(tmp_path):
    # Bucket i holds the values up to bucket_limit[i]: here (-1e300, -0.5]
    # and (-0.5, 0], between a smallest value of -0.7 and a largest of -0.1.
    writer = _Writer(tmp_path / "run")
    histo = (
        _key(1, 1)
        + struct.pack("<d", -0.7)  # min
        + _key(2, 1)
        + struct.pack("<d", -0.1)  # max
        + _bytes(6, struct.pack("<5d", -1e300, -0.5, 0.0, 1.0, 1e300))
        + _bytes(7, struct.pack("<5d", 0, 2, 3, 0, 0))
    )
    writer.event(0, _bytes(1, _bytes(1, b"w") + _bytes(5, histo)))
    writer.close()
    (series,) = load_histograms(tmp_path)["w"].values()
    np.testing.assert_allclose(
        series.buckets[0], [[-0.7, -0.5, 2.0], [-0.5, -0.1, 3.0]], rtol=1e-6
    )


def test_an_empty_histogram_is_warned_about_and_left_out(tmp_path):
    writer = _Writer(tmp_path / "run")
    writer.event(0, _histogram_value("w", []))
    writer.close()
    with pytest.warns(UserWarning, match="'w' in run 'run' is empty"):
        assert read_tensorboard_histograms(tmp_path) == []


def test_a_tensor_of_another_plugin_is_not_a_histogram(tmp_path):
    writer = _Writer(tmp_path / "run")
    writer.event(0, _histogram_value("w", [(0.0, 1.0, 1.0)], plugin="images"))
    writer.close()
    assert load_histograms(tmp_path) == {}


# -- Bad input ----------------------------------------------------------------


def test_no_histograms_warns_and_reads_nothing(tmp_path):
    with pytest.warns(UserWarning, match="no histograms"):
        assert read_tensorboard_histograms(tmp_path) == []


@pytest.mark.parametrize("options", [{"bins": 0}, {"max_steps": 1}])
def test_bins_and_max_steps_are_checked(options):
    with pytest.raises(ValueError):
        read_tensorboard_histograms(FIXTURES / "tf_histograms", **options)


def _histogram_value(
    tag: str, buckets: list[tuple[float, float, float]], plugin: str = "histograms"
) -> bytes:
    """A TensorFlow 2 histogram summary: a float64 tensor of shape (k, 3)."""
    shape = _bytes(2, _int(1, len(buckets))) + _bytes(2, _int(1, 3))
    content = np.array(buckets, dtype="<f8").reshape(-1).tobytes()
    tensor = _int(1, 2) + _bytes(2, shape) + _bytes(4, content)
    metadata = _bytes(1, _bytes(1, plugin.encode()))
    return _bytes(1, _bytes(1, tag.encode()) + _bytes(8, tensor) + _bytes(9, metadata))

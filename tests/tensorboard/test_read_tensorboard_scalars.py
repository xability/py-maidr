"""Scalars read out of a TensorBoard log directory with ``maidr.read_tensorboard_scalars``.

The checked-in log directories under ``fixtures/`` were written by Keras's
``TensorBoard`` callback, ``tf.summary.scalar`` and PyTorch's
``SummaryWriter``, and each ``*.expected.json`` beside them is what
TensorBoard's own reader read from them (``fixtures/make_fixtures.py``), so the
reader is tested against TensorBoard rather than against itself. What those
writers do not write on demand -- a restarted run, a damaged file, the rarer
tensor types -- is written here, record by record, by ``_Writer``.
"""

from __future__ import annotations

import json
import math
import struct
import warnings
from pathlib import Path

import numpy as np
import pytest

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import (
    TensorBoardChart,
    load_scalars,
    read_tensorboard_scalars,
    smooth,
)
from maidr.tensorboard.events import _masked_crc32c

FIXTURES = Path(__file__).parent / "fixtures"


def _read(logdir, **options) -> list[TensorBoardChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_tensorboard_scalars(logdir, **options)


def _layers(chart: TensorBoardChart) -> list[dict]:
    """Every layer of the chart, as the schema maidr.js receives carries it."""
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def _series(chart: TensorBoardChart) -> dict[str, list[dict]]:
    (layer,) = _layers(chart)
    assert layer["type"] == "line"
    return {line[0]["z"]: line for line in layer["data"]}


# -- What TensorBoard reads ---------------------------------------------------


@pytest.mark.parametrize("name", ["keras", "tf_summary", "torch"])
def test_the_values_are_the_ones_tensorboard_reads(name):
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text())
    read: dict = {}
    for tag, runs in load_scalars(FIXTURES / name).items():
        for run, series in runs.items():
            read.setdefault(run, {})[tag] = [
                [int(step), float(time), "nan" if math.isnan(value) else float(value)]
                for step, time, value in zip(
                    series.steps, series.wall_times, series.values
                )
            ]
    assert read == expected


def test_keras_train_and_validation_are_two_lines_of_one_chart():
    charts = _read(FIXTURES / "keras", smoothing=0)
    assert [chart.tag for chart in charts] == [
        "epoch_accuracy",
        "epoch_learning_rate",
        "epoch_loss",
        "evaluation_accuracy_vs_iterations",
        "evaluation_loss_vs_iterations",
    ]
    loss = charts[2]
    assert loss.runs == ("train", "validation")
    (layer,) = _layers(loss)
    assert layer["title"] == "epoch_loss"
    assert layer["axes"]["x"]["label"] == "Step"
    assert layer["axes"]["y"]["label"] == "epoch_loss"
    lines = _series(loss)
    assert list(lines) == ["train", "validation"]
    assert [point["x"] for point in lines["train"]] == list(range(12))


def test_pytorch_logged_into_the_log_directory_itself_is_the_run_named_dot():
    (test, train) = _read(FIXTURES / "torch", smoothing=0)
    assert (test.tag, train.tag) == ("Loss/test", "Loss/train")
    assert train.runs == (".",)
    assert _series(train)["."][3]["y"] == pytest.approx(1 / 4)


def test_a_nan_loss_is_a_gap_in_the_line():
    (loss,) = _read(FIXTURES / "tf_summary", tags=["loss"], runs=["lr_0.01"])
    lines = _series(loss)
    at_30 = [p["y"] for p in lines["lr_0.01"] if p["x"] == 30]
    assert at_30 == [None]
    smoothed = [p["y"] for p in lines["lr_0.01 (smoothed)"] if p["x"] == 30]
    assert smoothed == [None]
    after = [p["y"] for p in lines["lr_0.01 (smoothed)"] if p["x"] == 33]
    assert after[0] is not None


# -- Smoothing and thinning ---------------------------------------------------


def test_smoothing_is_tensorboards_debiased_moving_average():
    assert smooth(np.array([1.0, 2.0, 3.0]), 0.5) == pytest.approx(
        [1.0, 1.25 / 0.75, 2.125 / 0.875]
    )
    # A constant stays constant: the bias correction is what makes it so.
    assert smooth(np.full(5, 4.0), 0.9) == pytest.approx(np.full(5, 4.0))


def test_smoothing_steps_over_a_value_that_is_not_finite():
    values = np.array([1.0, np.nan, 2.0, np.inf, 3.0])
    smoothed = smooth(values, 0.5)
    assert np.isnan(smoothed[1]) and np.isinf(smoothed[3])
    expected = smooth(np.array([1.0, 2.0, 3.0]), 0.5)
    assert smoothed[[0, 2, 4]] == pytest.approx(expected)


def test_smoothing_draws_each_run_twice_and_zero_draws_it_once():
    (smoothed,) = _read(FIXTURES / "keras", tags=["epoch_loss"])
    assert list(_series(smoothed)) == [
        "train",
        "train (smoothed)",
        "validation",
        "validation (smoothed)",
    ]
    (raw,) = _read(FIXTURES / "keras", tags=["epoch_loss"], smoothing=0)
    assert list(_series(raw)) == ["train", "validation"]


def test_smoothing_is_computed_over_every_value_before_thinning(tmp_path):
    values = [float(v % 7) for v in range(50)]
    _Writer(tmp_path / "run").scalars("loss", enumerate(values)).close()
    (chart,) = _read(tmp_path, max_points=5)
    lines = _series(chart)
    assert [p["x"] for p in lines["run"]] == [0, 12, 24, 37, 49]
    full = smooth(np.array(values), 0.6)
    assert [p["y"] for p in lines["run (smoothed)"]] == pytest.approx(
        full[[0, 12, 24, 37, 49]].tolist()
    )


def test_the_order_of_tags_asked_for_is_kept():
    charts = _read(FIXTURES / "keras", tags=["epoch_loss", "epoch_accuracy"])
    assert [chart.tag for chart in charts] == ["epoch_loss", "epoch_accuracy"]


def test_a_warning_names_the_line_that_called_maidr():
    with pytest.warns(UserWarning, match="no run") as caught:
        read_tensorboard_scalars(FIXTURES / "keras", runs=["test"])
    assert {Path(w.filename).name for w in caught} == {Path(__file__).name}


def test_an_unknown_tag_or_run_is_warned_about_by_name():
    with pytest.warns(UserWarning, match="no run 'test'.*'train', 'validation'"):
        read_tensorboard_scalars(FIXTURES / "keras", runs=["train", "test"])
    with pytest.warns(UserWarning, match="no scalars tagged 'loss'.*'epoch_loss'"):
        read_tensorboard_scalars(FIXTURES / "keras", tags=["loss"])


# -- What maidr does with a chart ---------------------------------------------


def test_a_chart_is_rendered_like_a_figure(tmp_path):
    (chart,) = _read(FIXTURES / "keras", tags=["epoch_loss"])
    out = tmp_path / "loss.html"
    maidr.save_html(chart, file=str(out), use_cdn=False)
    page = out.read_text()
    assert "epoch_loss" in page and "validation (smoothed)" in page
    maidr.close(chart)


# -- Bad input ----------------------------------------------------------------


def test_a_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="not a directory"):
        read_tensorboard_scalars(tmp_path / "nowhere")


@pytest.mark.parametrize("weight", [-0.1, 1.0, 1.5])
def test_a_smoothing_weight_outside_0_to_1_raises(weight):
    with pytest.raises(ValueError, match="smoothing"):
        read_tensorboard_scalars(FIXTURES / "keras", smoothing=weight)


def test_max_points_below_two_raises():
    with pytest.raises(ValueError, match="max_points"):
        read_tensorboard_scalars(FIXTURES / "keras", max_points=1)


def test_a_directory_with_no_scalars_warns_and_reads_nothing(tmp_path):
    with pytest.warns(UserWarning, match="no scalars"):
        assert read_tensorboard_scalars(tmp_path) == []


def test_a_damaged_record_ends_the_file_with_a_warning(tmp_path):
    writer = _Writer(tmp_path / "run").scalars("loss", [(0, 1.0), (1, 0.5)])
    writer.raw(b"\x05" * 12)
    writer.scalars("loss", [(2, 0.25)]).close()
    with pytest.warns(UserWarning, match="damaged"):
        (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.values.tolist() == [1.0, 0.5]


def test_a_record_cut_off_while_being_written_is_left_quietly(tmp_path):
    writer = _Writer(tmp_path / "run").scalars("loss", [(0, 1.0), (1, 0.5)])
    writer.raw(_record(_event(2, summary=_simple("loss", 0.25)))[:-3])
    writer.close()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.values.tolist() == [1.0, 0.5]


def test_a_length_past_the_end_of_the_file_is_never_read(tmp_path):
    writer = _Writer(tmp_path / "run").scalars("loss", [(0, 1.0)])
    length = struct.pack("<Q", 1 << 62)
    writer.raw(length + struct.pack("<I", _masked_crc32c(length)) + b"\0" * 16)
    writer.close()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.values.tolist() == [1.0]


# -- Restarted runs -----------------------------------------------------------


def test_a_restart_announced_by_a_session_start_drops_what_it_wrote_over(tmp_path):
    writer = _Writer(tmp_path / "run").session_start(0)
    writer.scalars("loss", [(0, 1.0), (1, 0.9), (2, 0.8), (3, 0.7)])
    writer.session_start(2)
    writer.scalars("loss", [(2, 0.5), (3, 0.4)]).close()
    (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.steps.tolist() == [0, 1, 2, 3]
    assert series.values.tolist() == pytest.approx([1.0, 0.9, 0.5, 0.4])


def test_steps_going_back_without_a_session_start_are_kept_as_tensorboard_keeps_them(
    tmp_path,
):
    writer = _Writer(tmp_path / "run")
    writer.scalars("loss", [(0, 1.0), (1, 0.9), (2, 0.8)])
    writer.scalars("loss", [(1, 0.6)]).close()
    (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.steps.tolist() == [0, 1, 2, 1]


def test_an_old_file_drops_a_tags_values_where_its_steps_go_back(tmp_path):
    writer = _Writer(tmp_path / "run", version="brain.Event:1")
    writer.scalars("loss", [(0, 1.0), (1, 0.9), (2, 0.8)])
    writer.scalars("acc", [(0, 0.1), (1, 0.2), (2, 0.3)])
    writer.scalars("loss", [(1, 0.6)]).close()
    read = load_scalars(tmp_path)
    assert read["loss"]["run"].steps.tolist() == [0, 1]
    assert read["loss"]["run"].values.tolist() == pytest.approx([1.0, 0.6])
    # Only the tags the out-of-order event carries are dropped.
    assert read["acc"]["run"].steps.tolist() == [0, 1, 2]


def test_the_files_of_a_run_are_read_in_the_order_they_were_opened(tmp_path):
    _Writer(tmp_path / "run", name="events.out.tfevents.200.host").scalars(
        "loss", [(2, 0.5)]
    ).close()
    _Writer(tmp_path / "run", name="events.out.tfevents.100.host").scalars(
        "loss", [(0, 1.0), (1, 0.8)]
    ).close()
    (series,) = load_scalars(tmp_path)["loss"].values()
    assert series.steps.tolist() == [0, 1, 2]


# -- Tensor encodings ---------------------------------------------------------


@pytest.mark.parametrize(
    "tensor, value",
    [
        ("float_content", 0.5),
        ("double_content", 0.125),
        ("double_val", -2.5),
        ("int64_val", -3.0),
        ("int32_val", 7.0),
        ("half_val", 1.5),
        ("half_content", -0.75),
        ("bfloat16_content", 2.0),
    ],
)
def test_every_numeric_scalar_tensor_is_read(tmp_path, tensor, value):
    writer = _Writer(tmp_path / "run")
    writer.event(0, _tensor_value("x", _TENSORS[tensor](value), plugin="scalars"))
    writer.close()
    (series,) = load_scalars(tmp_path)["x"].values()
    assert series.values.tolist() == [value]


def test_a_tensor_of_another_plugin_is_not_a_scalar(tmp_path):
    writer = _Writer(tmp_path / "run")
    writer.event(0, _tensor_value("w", _TENSORS["float_content"](1.0), "histograms"))
    writer.close()
    assert load_scalars(tmp_path) == {}


def test_metadata_on_the_first_value_names_the_plugin_of_the_rest(tmp_path):
    writer = _Writer(tmp_path / "run")
    writer.event(0, _tensor_value("x", _TENSORS["float_content"](1.0), "scalars"))
    writer.event(1, _tensor_value("x", _TENSORS["float_content"](2.0), None))
    writer.close()
    (series,) = load_scalars(tmp_path)["x"].values()
    assert series.values.tolist() == [1.0, 2.0]


# -- An event file writer, field by field ------------------------------------


def _varint(value: int) -> bytes:
    value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number: int, wire: int) -> bytes:
    return _varint(number << 3 | wire)


def _bytes(number: int, data: bytes) -> bytes:
    return _key(number, 2) + _varint(len(data)) + data


def _int(number: int, value: int) -> bytes:
    return _key(number, 0) + _varint(value)


def _simple(tag: str, value: float) -> bytes:
    return _bytes(1, _bytes(1, tag.encode()) + _key(2, 5) + struct.pack("<f", value))


def _tensor_value(tag: str, tensor: bytes, plugin: str | None) -> bytes:
    value = _bytes(1, tag.encode()) + _bytes(8, tensor)
    if plugin is not None:
        value += _bytes(9, _bytes(1, _bytes(1, plugin.encode())))
    return _bytes(1, value)


_TENSORS = {
    "float_content": lambda v: _int(1, 1) + _bytes(4, struct.pack("<f", v)),
    "double_content": lambda v: _int(1, 2) + _bytes(4, struct.pack("<d", v)),
    "double_val": lambda v: _int(1, 2) + _bytes(6, struct.pack("<d", v)),
    "int64_val": lambda v: _int(1, 9) + _int(10, int(v)),
    "int32_val": lambda v: _int(1, 3) + _bytes(7, _varint(int(v))),
    "half_val": lambda v: _int(1, 19)
    + _int(13, int(np.array([v], "<f2").view("<u2")[0])),
    "half_content": lambda v: _int(1, 19) + _bytes(4, np.array([v], "<f2").tobytes()),
    "bfloat16_content": lambda v: _int(1, 14)
    + _bytes(4, np.array([v], "<f4").tobytes()[2:]),
}


def _event(step: int, *, summary: bytes | None = None, extra: bytes = b"") -> bytes:
    out = _key(1, 1) + struct.pack("<d", 1_700_000_000.0 + step) + _int(2, step)
    if summary is not None:
        out += _bytes(5, summary)
    return out + extra


def _record(data: bytes) -> bytes:
    length = struct.pack("<Q", len(data))
    return (
        length
        + struct.pack("<I", _masked_crc32c(length))
        + data
        + struct.pack("<I", _masked_crc32c(data))
    )


class _Writer:
    """Writes one event file, the way TensorFlow lays it out."""

    def __init__(
        self,
        run: Path,
        *,
        version: str = "brain.Event:2",
        name: str = "events.out.tfevents.1.host",
    ):
        run.mkdir(parents=True, exist_ok=True)
        self._file = open(run / name, "wb")
        self.raw(_record(_event(0) + _bytes(3, version.encode())))

    def raw(self, data: bytes) -> _Writer:
        self._file.write(data)
        return self

    def event(self, step: int, summary: bytes) -> _Writer:
        return self.raw(_record(_event(step, summary=summary)))

    def scalars(self, tag: str, points) -> _Writer:
        for step, value in points:
            self.event(step, _simple(tag, value))
        return self

    def session_start(self, step: int) -> _Writer:
        return self.raw(_record(_event(step, extra=_bytes(7, _int(1, 1)))))

    def close(self) -> None:
        self._file.close()

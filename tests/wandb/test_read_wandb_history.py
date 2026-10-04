"""Training curves read out of Weights & Biases runs with ``maidr.read_wandb_history``.

The run files are written by the installed ``wandb`` itself, in offline mode,
in a subprocess, so the reader is tested against what W&B writes rather than
against a file this suite made up. A fetched run is stood in for by an object
with the one method the reader calls, ``scan_history``, since fetching one
needs a W&B server.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.util.metric_chart import MetricChart, unique_names
from maidr.wandb import load_wandb_history, read_wandb_history
from maidr.wandb.runfile import find_run_files, read_run_file


def _read(runs, **options) -> list[MetricChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_wandb_history(runs, **options)


def _layer(chart: MetricChart) -> dict:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    (layer,) = [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]
    assert layer["type"] == "line"
    return layer


def _lines(chart: MetricChart) -> dict[str, list[tuple[float, float]]]:
    """Each line the reader hears, by name, as (x, y) points."""
    return {
        line[0]["z"]: [(point["x"], point["y"]) for point in line]
        for line in _layer(chart)["data"]
    }


# -- Run files W&B wrote ------------------------------------------------------

_WRITER = """
import math, wandb
run = wandb.init(project="maidr-test", name={name!r}, mode="offline")
for step in range({steps}):
    row = {{"train/loss": {scale} / (step + 1), "epoch": step // 2}}
    if step % 2 == 0:
        row["val"] = {{"loss": {scale} * 2 / (step + 1)}}
    if step == 2:
        row["grad_norm"] = math.nan
    elif step < 4:
        row["grad_norm"] = float(step)
    if step == 1:
        row["samples"] = wandb.Histogram([1, 2, 3])
        row["k" * {long_key}] = 1.0
    wandb.log(row)
run.finish()
"""


def _write_run(directory: Path, name: str, *, steps=6, scale=1.0, long_key=1):
    """Write one offline run under ``directory/wandb`` with the real SDK."""
    pytest.importorskip("wandb")
    env = {
        **os.environ,
        "WANDB_DIR": str(directory),
        "WANDB_SILENT": "true",
        "WANDB_MODE": "offline",
        "WANDB_DISABLE_GIT": "true",
        "WANDB_CONSOLE": "off",
    }
    code = textwrap.dedent(
        _WRITER.format(name=name, steps=steps, scale=scale, long_key=long_key)
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True, timeout=120)


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> Path:
    """Two offline runs, ``baseline`` and ``lora``, in one ``wandb`` folder."""
    root = tmp_path_factory.mktemp("wandb-runs")
    _write_run(root, "baseline")
    _write_run(root, "lora", scale=0.5)
    return root / "wandb"


def test_a_run_file_reads_every_step_w_and_b_logged(runs):
    path = find_run_files(str(runs))[0]
    run = read_run_file(path)

    assert run.name == "baseline"
    assert path.endswith(f"run-{run.run_id}.wandb")
    assert [row["_step"] for row in run.rows] == list(range(6))
    assert run.rows[3]["train/loss"] == pytest.approx(0.25)
    assert run.rows[2]["val.loss"] == pytest.approx(2 / 3)
    assert math.isnan(run.rows[2]["grad_norm"])


def test_latest_run_is_not_read_twice(runs):
    # `wandb/latest-run` links to the newest run; it is the same run.
    assert (runs / "latest-run").exists()
    assert len(find_run_files(str(runs))) == 2


def test_each_metric_is_one_chart_with_a_line_per_run(runs):
    charts = _read(str(runs))

    assert [chart.metric for chart in charts] == [
        "epoch",
        "grad_norm",
        "k",
        "train/loss",
        "val.loss",
    ]
    loss = next(chart for chart in charts if chart.metric == "train/loss")
    assert loss.runs == ("baseline", "lora")
    lines = _lines(loss)
    assert lines["baseline"] == [(s, pytest.approx(1 / (s + 1))) for s in range(6)]
    assert lines["lora"][0] == (0, pytest.approx(0.5))


def test_a_metric_logged_every_other_step_is_one_unbroken_line(runs):
    (chart,) = _read(str(runs), keys=["val.loss"], x="_step")
    assert [x for x, _ in _lines(chart)["baseline"]] == [0, 2, 4]


def test_a_logged_nan_is_a_gap(runs):
    (chart,) = _read(str(runs), keys=["grad_norm"])
    line = chart.figure.axes[0].lines[0]
    assert math.isnan(line.get_ydata()[2])


def test_a_histogram_is_not_read_as_a_metric(runs):
    assert "samples" not in load_wandb_history(str(runs))


def test_the_axis_is_named_for_what_it_counts(runs):
    (by_step,) = _read(str(runs), keys=["train/loss"])
    (by_epoch,) = _read(str(runs), keys=["train/loss"], x="epoch")
    (by_time,) = _read(str(runs), keys=["train/loss"], x="_runtime")

    assert by_step.figure.axes[0].get_xlabel() == "Step"
    assert by_epoch.figure.axes[0].get_xlabel() == "epoch"
    assert by_time.figure.axes[0].get_xlabel() == "Relative time (seconds)"
    assert [x for x, _ in _lines(by_epoch)["baseline"]] == [0, 0, 1, 1, 2, 2]


def test_one_run_file_is_read_on_its_own(runs):
    path = find_run_files(str(runs))[1]
    (chart,) = _read(path, keys=["train/loss"])
    assert chart.runs == ("lora",)


def test_a_record_longer_than_a_block_is_read_whole(tmp_path):
    # A 40,000-character key cannot fit one 32 KiB block, so W&B splits
    # its record into a first, middle and last part.
    _write_run(tmp_path, "long", long_key=40_000)
    (path,) = find_run_files(str(tmp_path / "wandb"))
    rows = read_run_file(path).rows
    assert [row["_step"] for row in rows] == list(range(6))
    assert rows[1]["k" * 40_000] == 1.0


def test_a_damaged_record_ends_the_read_with_a_warning(runs, tmp_path):
    source = find_run_files(str(runs))[0]
    data = bytearray(Path(source).read_bytes())
    # The last history record's data, well inside the file.
    at = data.rfind(b"train/loss")
    data[at] ^= 0xFF
    damaged = tmp_path / "run-damaged.wandb"
    damaged.write_bytes(bytes(data))

    with pytest.warns(UserWarning, match="is damaged at byte"):
        run = read_run_file(str(damaged))
    assert 0 < len(run.rows) < 6


def test_a_run_still_writing_is_read_up_to_its_last_whole_record(runs, tmp_path):
    source = find_run_files(str(runs))[0]
    data = Path(source).read_bytes()
    cut = tmp_path / "run-writing.wandb"
    cut.write_bytes(data[: data.rfind(b"train/loss") + 3])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        run = read_run_file(str(cut))
    assert 0 < len(run.rows) < 6


def test_a_file_that_is_not_a_run_file_is_warned_about(tmp_path):
    other = tmp_path / "run-other.wandb"
    other.write_bytes(b"not a W&B file at all")
    with pytest.warns(UserWarning, match="not a W&B run file"):
        assert read_run_file(str(other)).rows == []


def test_a_directory_without_runs_is_warned_about(tmp_path):
    with pytest.warns(UserWarning, match="found no W&B run file"):
        assert read_wandb_history(str(tmp_path)) == []


def test_a_missing_run_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_wandb_history(str(tmp_path / "run-gone.wandb"))


# -- Fetched runs and saved history -------------------------------------------


class _Run:
    """What ``wandb.Api().run()`` returns, as far as the reader asks."""

    def __init__(self, name, run_id, rows):
        self.name = name
        self.id = run_id
        self._rows = rows

    def scan_history(self):
        return iter(self._rows)


class _Api:
    def __init__(self, runs):
        self._runs = runs
        self.asked: list[str] = []

    def run(self, path):
        self.asked.append(path)
        return self._runs[path]


_ROWS = [
    {"_step": 0, "_runtime": 1.5, "loss": 2.0, "lr": 1e-3},
    {"_step": 1, "_runtime": 3.0, "loss": 1.0, "lr": "NaN"},
    {"_step": 2, "_runtime": 4.5, "loss": 0.5, "eval": {"acc": 0.7}},
]


def test_a_fetched_run_is_read_from_every_row_it_logged():
    (chart,) = _read(_Run("gpt", "a1", _ROWS), keys=["loss"])
    assert _lines(chart) == {"gpt": [(0, 2.0), (1, 1.0), (2, 0.5)]}


def test_a_run_path_is_fetched_through_the_api():
    api = _Api({"team/proj/a1": _Run("gpt", "a1", _ROWS)})
    (chart,) = _read("team/proj/a1", keys=["loss"], api=api)
    assert api.asked == ["team/proj/a1"]
    assert chart.runs == ("gpt",)


def test_wandb_writes_nan_as_a_string_and_it_is_still_a_gap():
    (chart,) = _read(_Run("gpt", "a1", _ROWS), keys=["lr"])
    assert np.isnan(chart.figure.axes[0].lines[0].get_ydata()[1])


def test_a_nested_value_is_read_under_a_dotted_name():
    assert "eval.acc" in load_wandb_history(_Run("gpt", "a1", _ROWS))


def test_two_runs_sharing_a_name_are_told_apart_by_their_ids():
    charts = _read([_Run("gpt", "a1", _ROWS), _Run("gpt", "b2", _ROWS)], keys=["loss"])
    assert charts[0].runs == ("gpt (a1)", "gpt (b2)")


def test_the_same_run_twice_is_numbered_rather_than_merged():
    assert unique_names(["gpt", "gpt"], ["a1", "a1"]) == ["gpt (a1)", "gpt (a1) 2"]


def test_saved_history_is_read_by_run_name():
    frame = pd.DataFrame(_ROWS[:2])
    charts = _read({"saved": frame, "listed": _ROWS}, keys=["loss"])
    assert charts[0].runs == ("saved", "listed")


def test_a_data_frame_leaves_out_what_a_row_did_not_log():
    # `run.history()` fills a metric missing from a row with NaN; it was not
    # logged there, so it is not a gap in the line.
    frame = pd.DataFrame(
        [{"_step": 0, "loss": 1.0}, {"_step": 1}, {"_step": 2, "loss": 0.5}]
    )
    (chart,) = _read({"run": frame}, keys=["loss"])
    assert _lines(chart) == {"run": [(0, 1.0), (2, 0.5)]}


def test_a_bare_data_frame_asks_for_its_run_name():
    with pytest.raises(TypeError, match="pass it named"):
        read_wandb_history(pd.DataFrame(_ROWS))


def test_something_that_is_not_a_run_is_refused():
    with pytest.raises(TypeError):
        read_wandb_history(42)
    with pytest.raises(TypeError):
        read_wandb_history([object()])


def test_a_key_no_run_logged_is_warned_about():
    with pytest.warns(UserWarning, match="No run logged a number under 'acc'"):
        charts = read_wandb_history(_Run("gpt", "a1", _ROWS), keys=["acc", "loss"])
    assert [chart.metric for chart in charts] == ["loss"]


def test_a_metric_that_never_holds_a_number_is_left_out():
    rows = [{"_step": 0, "loss": "NaN"}, {"_step": 1, "loss": "NaN"}]
    with pytest.warns(UserWarning, match="No value logged under 'loss'"):
        assert read_wandb_history({"run": rows}) == []


def test_smoothing_draws_each_run_twice():
    (chart,) = _read(_Run("gpt", "a1", _ROWS), keys=["loss"], smoothing=0.6)
    assert list(_lines(chart)) == ["gpt", "gpt (smoothed)"]


def test_a_long_run_is_thinned():
    rows = [{"_step": step, "loss": 1 / (step + 1)} for step in range(5000)]
    (chart,) = _read({"run": rows}, max_points=100)
    xs = [x for x, _ in _lines(chart)["run"]]
    assert len(xs) == 100 and xs[0] == 0 and xs[-1] == 4999


@pytest.mark.parametrize("options", [{"smoothing": 1.0}, {"max_points": 1}])
def test_bad_options_are_refused(options):
    with pytest.raises(ValueError):
        read_wandb_history({"run": _ROWS}, **options)


def test_a_chart_renders_like_a_figure(tmp_path):
    (chart,) = _read({"run": _ROWS}, keys=["loss"])
    html = str(maidr.render(chart).get_html_string())
    assert "maidr" in html
    out = maidr.save_html(chart, str(tmp_path / "loss.html"), use_cdn=True)
    assert Path(out).exists()


def test_import_maidr_does_not_import_wandb():
    code = "import sys, maidr; print('wandb' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "MPLBACKEND": "Agg"},
        check=True,
    )
    assert result.stdout.strip() == "False"

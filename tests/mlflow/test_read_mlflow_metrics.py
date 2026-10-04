"""Training curves read out of MLflow runs with ``maidr.read_mlflow_metrics``.

The runs are logged by the installed MLflow itself, to a SQLite tracking store
in a temporary directory, the local store MLflow recommends, and read back
through the same ``MlflowClient`` the reader uses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.mlflow import (  # noqa: E402
    load_mlflow_metrics,
    log_mlflow_chart,
    read_mlflow_metrics,
)
from maidr.util.dependencies import read_bundled_js  # noqa: E402
from maidr.util.metric_chart import MetricChart  # noqa: E402


def _read(runs, **options) -> list[MetricChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_mlflow_metrics(runs, **options)


def _lines(chart: MetricChart) -> dict[str, list[tuple[float, float]]]:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    (layer,) = [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]
    assert layer["type"] == "line"
    return {
        line[0]["z"]: [(point["x"], point["y"]) for point in line]
        for line in layer["data"]
    }


class _Store:
    """A SQLite tracking store and the runs logged to it."""

    def __init__(self, root: Path) -> None:
        self.uri = f"sqlite:///{root / 'mlflow.db'}"
        self.artifacts = (root / "artifacts").as_uri()
        self.client = mlflow.MlflowClient(tracking_uri=self.uri)
        self.experiment = self.client.create_experiment(
            "llm", artifact_location=self.artifacts
        )

    def run(self, name: str, metrics: dict[str, list[tuple]], start: int = 0) -> str:
        """Log ``metrics`` as ``(step, value, timestamp)`` and end the run."""
        run = self.client.create_run(self.experiment, run_name=name, start_time=start)
        run_id = run.info.run_id
        for key, values in metrics.items():
            for step, value, timestamp in values:
                self.client.log_metric(run_id, key, value, timestamp, step)
        self.client.set_terminated(run_id)
        return run_id


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> _Store:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        store = _Store(tmp_path_factory.mktemp("mlflow"))
        store.baseline = store.run(
            "baseline",
            {
                "train_loss": [(s, 2 / (s + 1), 1_000 + 500 * s) for s in range(6)],
                "eval_acc": [(5, 0.6, 4_000)],
                "system/cpu_utilization_percentage": [(0, 12.0, 1_000)],
            },
            start=1_000,
        )
        store.lora = store.run(
            "lora",
            {"train_loss": [(s, 1 / (s + 1), 2_000 + 250 * s) for s in range(6)]},
            start=2_000,
        )
    return store


def test_each_metric_is_one_chart_with_a_line_per_run(store):
    charts = _read([store.baseline, store.lora], tracking_uri=store.uri)

    assert [chart.metric for chart in charts] == ["eval_acc", "train_loss"]
    loss = charts[1]
    assert loss.runs == ("baseline", "lora")
    assert _lines(loss)["lora"] == [(s, pytest.approx(1 / (s + 1))) for s in range(6)]
    assert charts[0].runs == ("baseline",)


def test_what_search_runs_returns_is_read(store):
    mlflow.set_tracking_uri(store.uri)
    try:
        found = mlflow.search_runs(experiment_ids=[store.experiment])
    finally:
        mlflow.set_tracking_uri(None)
    charts = _read(found, keys=["train_loss"], tracking_uri=store.uri)
    assert sorted(charts[0].runs) == ["baseline", "lora"]


def test_a_run_entity_is_read_as_it_is(store):
    run = store.client.get_run(store.lora)
    (chart,) = _read(run, keys=["train_loss"], tracking_uri=store.uri)
    assert chart.runs == ("lora",)


def test_system_metrics_are_left_out_unless_asked_for(store):
    assert "system/cpu_utilization_percentage" not in load_mlflow_metrics(
        store.baseline, tracking_uri=store.uri
    )
    asked = load_mlflow_metrics(
        store.baseline,
        keys=["system/cpu_utilization_percentage"],
        tracking_uri=store.uri,
    )
    assert list(asked) == ["system/cpu_utilization_percentage"]


def test_relative_time_counts_seconds_from_the_start_of_each_run(store):
    (chart,) = _read(
        store.lora, keys=["train_loss"], x="relative_time", tracking_uri=store.uri
    )
    assert [x for x, _ in _lines(chart)["lora"]] == [0, 0.25, 0.5, 0.75, 1, 1.25]
    assert chart.figure.axes[0].get_xlabel() == "Relative time (seconds)"


def test_two_values_at_one_step_are_both_kept_in_the_order_logged(store):
    run_id = store.run("repeat", {"loss": [(1, 0.5, 20), (0, 1.0, 5), (1, 0.4, 30)]})
    (chart,) = _read(run_id, tracking_uri=store.uri)
    assert _lines(chart)["repeat"] == [(0, 1.0), (1, 0.5), (1, 0.4)]


def test_two_runs_sharing_a_name_are_told_apart_by_their_ids(store):
    first = store.run("same", {"loss": [(0, 1.0, 1)]})
    second = store.run("same", {"loss": [(0, 2.0, 1)]})
    (chart,) = _read([first, second], tracking_uri=store.uri)
    assert chart.runs == (f"same ({first})", f"same ({second})")


def test_a_key_no_run_logged_is_warned_about(store):
    with pytest.warns(UserWarning, match="No run logged a metric 'perplexity'"):
        charts = read_mlflow_metrics(
            store.baseline, keys=["perplexity"], tracking_uri=store.uri
        )
    assert charts == []


def test_an_x_mlflow_does_not_offer_is_refused(store):
    with pytest.raises(ValueError, match="'step' or 'relative_time'"):
        read_mlflow_metrics(store.baseline, x="epoch", tracking_uri=store.uri)


def test_something_that_is_not_a_run_is_refused(store):
    with pytest.raises(TypeError):
        read_mlflow_metrics(42, tracking_uri=store.uri)
    with pytest.raises(TypeError):
        read_mlflow_metrics([object()], tracking_uri=store.uri)


# -- Logging a chart to a run -------------------------------------------------


def _artifact(store: _Store, run_id: str, path: str) -> str:
    local = store.client.download_artifacts(run_id, path)
    return Path(local).read_text(encoding="utf-8")


def test_a_logged_chart_is_a_page_that_carries_maidr_with_it(store):
    (chart,) = _read(store.baseline, keys=["train_loss"], tracking_uri=store.uri)
    log_mlflow_chart(
        chart, "charts/loss.html", run_id=store.baseline, tracking_uri=store.uri
    )
    page = _artifact(store, store.baseline, "charts/loss.html")

    assert page.startswith("<!DOCTYPE html>")
    assert "<title>train_loss</title>" in page
    # The script is inside, not next to it: the MLflow UI loads the page from
    # a blob URL, where a relative path to a bundle leads nowhere.
    assert read_bundled_js()[:200] in page


def test_a_logged_chart_can_load_maidr_from_the_cdn_instead(store):
    (chart,) = _read(store.baseline, keys=["train_loss"], tracking_uri=store.uri)
    log_mlflow_chart(
        chart,
        "charts/cdn.html",
        run_id=store.baseline,
        tracking_uri=store.uri,
        use_cdn=True,
    )
    page = _artifact(store, store.baseline, "charts/cdn.html")
    assert read_bundled_js()[:200] not in page
    assert "cdn.jsdelivr.net" in page


def test_a_chart_is_logged_to_the_active_run(store, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", store.uri)
    mlflow.set_tracking_uri(store.uri)
    try:
        with mlflow.start_run(experiment_id=store.experiment) as run:
            fig, ax = plt.subplots()
            ax.bar(["a", "b"], [1, 2])
            ax.set_title("Bars")
            log_mlflow_chart(ax, "bars.html")
            plt.close(fig)
    finally:
        mlflow.set_tracking_uri(None)
    assert "<title>Bars</title>" in _artifact(store, run.info.run_id, "bars.html")


def test_an_artifact_that_is_not_html_is_refused(store):
    with pytest.raises(ValueError, match=r"ends in \.html"):
        log_mlflow_chart(object(), "loss.txt", run_id=store.baseline)


def test_import_maidr_does_not_import_mlflow():
    code = "import sys, maidr; print('mlflow' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "MPLBACKEND": "Agg"},
        check=True,
    )
    assert result.stdout.strip() == "False"

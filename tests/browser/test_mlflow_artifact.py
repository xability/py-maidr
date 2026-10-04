"""A chart logged to an MLflow run works where the MLflow UI shows it.

The MLflow UI shows an ``.html`` artifact in an iframe loaded from a blob URL
and sandboxed with ``allow-scripts`` alone (``ShowArtifactHtmlView`` in
MLflow's frontend, read from the bundle of MLflow 3.16). That frame has an
opaque origin: no relative path resolves, and ``localStorage`` throws. This
logs a chart with :func:`maidr.log_mlflow_chart`, reads the artifact back
through MLflow, and places it in a frame made the same way, rather than
driving MLflow's own UI, whose markup is MLflow's to change.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: Places the artifact as the MLflow UI does: a blob URL, ``allow-scripts``.
_AS_MLFLOW_DOES = """
(page) => {
  const frame = document.createElement('iframe');
  frame.sandbox = 'allow-scripts';
  frame.style.width = '900px';
  frame.style.height = '700px';
  frame.src = URL.createObjectURL(new Blob([page], {type: 'text/html'}));
  document.body.appendChild(frame);
}
"""


@pytest.fixture
def artifact(tmp_path) -> str:
    mlflow = pytest.importorskip("mlflow")
    import maidr

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
        client = mlflow.MlflowClient(tracking_uri=uri)
        experiment = client.create_experiment(
            "llm", artifact_location=(tmp_path / "artifacts").as_uri()
        )
        run_id = client.create_run(experiment, run_name="baseline").info.run_id
        for step, loss in enumerate([2.0, 1.0, 0.5, 0.25]):
            client.log_metric(run_id, "train_loss", loss, step=step)
        (chart,) = maidr.read_mlflow_metrics(run_id, tracking_uri=uri)
        maidr.log_mlflow_chart(chart, "loss.html", run_id=run_id, tracking_uri=uri)
        maidr.close(chart)
        local = client.download_artifacts(run_id, "loss.html")
    return Path(local).read_text(encoding="utf-8")


def test_the_logged_chart_is_read_in_a_sandboxed_frame(browser, artifact):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.set_content("<!DOCTYPE html><title>run</title><body></body>")
        page.evaluate(_AS_MLFLOW_DOES, artifact)
        frame = None
        for _ in range(30):
            page.wait_for_timeout(1_000)
            frame = next((f for f in page.frames[1:] if f.locator(CHART).count()), None)
            if frame is not None:
                break
        assert frame is not None, "the chart never came up in the sandboxed frame"

        frame.locator(CHART).first.focus()
        spoken = []
        for key in ("ArrowRight", "ArrowRight", "b"):
            page.keyboard.press(key)
            page.wait_for_timeout(600)
            spoken.append(frame.evaluate("document.body.innerText").strip())
        assert "Step is 0" in spoken[0] and "train_loss is 2" in spoken[0], spoken
        assert "Step is 1" in spoken[1] and "train_loss is 1" in spoken[1], spoken
        assert spoken[2].endswith("Braille is on"), spoken
        # maidr reports, and survives, the storage a sandbox denies it.
        assert not errors, errors
    finally:
        page.close()

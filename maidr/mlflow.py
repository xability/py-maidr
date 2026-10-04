"""Read the training curves of MLflow runs into maidr, and log charts to them.

>>> import maidr
>>> for chart in maidr.read_mlflow_metrics("4f9d1c0b2a6e4e7f"):
...     maidr.show(chart)

Each metric a run logged with ``mlflow.log_metric`` becomes one chart, with
one line per run, drawn with matplotlib, and py-maidr reads the drawing like
any other matplotlib figure. The values are read through ``MlflowClient``, so
any tracking server MLflow itself can reach is read: a local database, a file
store, or a remote server. :func:`log_mlflow_chart` goes the other way, and
stores an accessible chart in a run, where the MLflow UI shows it.

Needs the ``mlflow`` package, which ``import maidr`` does not import:
``pip install "maidr[mlflow]"``.
"""

from __future__ import annotations

import html
import math
from typing import Any, Iterable, Literal

import numpy as np

from maidr.util.caller_warning import warn_at_caller
from maidr.util.metric_chart import (
    DEFAULT_MAX_POINTS,
    MetricChart,
    MetricSeries,
    check_options,
    draw_charts,
    unique_names,
)

__all__ = [
    "MetricChart",
    "MetricSeries",
    "load_mlflow_metrics",
    "log_mlflow_chart",
    "read_mlflow_metrics",
]

#: What MLflow's own x axes are called on its charts.
_AXIS_NAMES = {"step": "Step", "relative_time": "Relative time (seconds)"}

#: The prefix MLflow's system metrics are logged under.
_SYSTEM = "system/"


def load_mlflow_metrics(
    runs: Any,
    *,
    keys: Iterable[str] | None = None,
    x: Literal["step", "relative_time"] = "step",
    tracking_uri: str | None = None,
) -> dict[str, dict[str, MetricSeries]]:
    """
    Read the metrics MLflow runs logged.

    Parameters
    ----------
    runs : str, mlflow.entities.Run, pandas.DataFrame, or iterable of these
        The runs: a run id, a run ``MlflowClient.get_run()`` or
        ``search_runs()`` returned, the ``DataFrame`` ``mlflow.search_runs()``
        returns, or an iterable of ids and runs.
    keys : iterable of str, optional
        Only these metrics, in this order. By default every metric a run
        logged, sorted, leaving out MLflow's ``system/`` metrics. A metric
        that no run logged is warned about.
    x : {"step", "relative_time"}, default "step"
        What places a value along the x axis: the step it was logged at, or
        the seconds from the start of its run, as the MLflow UI offers.
    tracking_uri : str, optional
        The tracking server to read from. By default MLflow's own, as
        ``mlflow.set_tracking_uri`` or ``MLFLOW_TRACKING_URI`` set it.

    Returns
    -------
    dict of str to dict of str to MetricSeries
        Metric by metric, and within a metric run by run, in the order the
        runs were given. A run that logged nothing under a metric is absent.

    Raises
    ------
    ImportError
        If ``mlflow`` is not installed.
    ValueError
        If ``x`` is neither ``"step"`` nor ``"relative_time"``.
    """
    if x not in _AXIS_NAMES:
        raise ValueError(f"x is 'step' or 'relative_time', not {x!r}")
    client = _client(tracking_uri)
    found = [_run(client, run) for run in _run_list(runs)]
    names = unique_names(
        [run.info.run_name or run.info.run_id for run in found],
        [run.info.run_id for run in found],
    )
    logged = sorted({key for run in found for key in run.data.metrics})
    if keys is None:
        order = [key for key in logged if not key.startswith(_SYSTEM)]
    else:
        order = list(dict.fromkeys(keys))
        known = ", ".join(f"'{key}'" for key in logged) or "none"
        for key in order:
            if key not in logged:
                warn_at_caller(
                    f"No run logged a metric '{key}'; the metrics logged are "
                    f"{known}."
                )
    metrics: dict[str, dict[str, MetricSeries]] = {}
    for key in order:
        for name, run in zip(names, found):
            if key not in run.data.metrics:
                continue
            history = client.get_metric_history(run.info.run_id, key)
            if history:
                metrics.setdefault(key, {})[name] = _series(history, run, x)
    return metrics


def read_mlflow_metrics(
    runs: Any,
    *,
    keys: Iterable[str] | None = None,
    x: Literal["step", "relative_time"] = "step",
    smoothing: float = 0.0,
    max_points: int | None = DEFAULT_MAX_POINTS,
    tracking_uri: str | None = None,
) -> list[MetricChart]:
    """
    Read the training curves of MLflow runs.

    One chart per metric, as the MLflow UI's model metrics draw it: the step
    along the x axis, the value along the y axis, and one line per run.

    Parameters
    ----------
    runs : str, mlflow.entities.Run, pandas.DataFrame, or iterable of these
        The runs, as for :func:`load_mlflow_metrics`: a run id, a run, what
        ``mlflow.search_runs()`` returns, or a list of ids and runs.
    keys : iterable of str, optional
        Only these metrics, in this order, such as ``["train_loss"]``.
    x : {"step", "relative_time"}, default "step"
        What the x axis counts.
    smoothing : float, default 0
        A smoothing weight, from 0 up to but not including 1, applied as
        TensorBoard applies it. Above 0, each run is drawn twice: as logged,
        and smoothed, under the run's name followed by ``(smoothed)``. 0
        draws the values as logged only.
    max_points : int or None, default 1000
        At most this many points per line, evenly spaced and always keeping
        the first and last, so a long run stays quick to walk. ``None``
        keeps every point.
    tracking_uri : str, optional
        The tracking server to read from. By default MLflow's own.

    Returns
    -------
    list of maidr.mlflow.MetricChart
        One per metric. Pass one to :func:`maidr.show`, :func:`maidr.render`
        or :func:`maidr.save_html`, or store it in a run with
        :func:`log_mlflow_chart`.

    Raises
    ------
    ImportError
        If ``mlflow`` is not installed.
    ValueError
        If ``x`` is not one of the above, ``smoothing`` is not in ``[0, 1)``
        or ``max_points`` is below 2.

    Notes
    -----
    Every value of a metric is read, with ``MlflowClient.get_metric_history``,
    and placed in order of its step and then the time it was logged, so two
    values logged at one step are both kept, in the order they were logged.
    ``max_points`` then thins the line. A logged ``NaN`` is a gap in it.

    Examples
    --------
    >>> import mlflow
    >>> import maidr
    >>> runs = mlflow.search_runs(experiment_names=["llm-finetune"])
    >>> charts = maidr.read_mlflow_metrics(runs, keys=["train_loss"])
    >>> maidr.save_html(charts[0], "loss.html")
    """
    check_options(smoothing, max_points)
    metrics = load_mlflow_metrics(runs, keys=keys, x=x, tracking_uri=tracking_uri)
    if not metrics and keys is None:
        warn_at_caller("maidr found no metrics in these runs.")
    return draw_charts(
        metrics,
        smoothing=smoothing,
        max_points=max_points,
        xlabel=_AXIS_NAMES[x],
    )


def log_mlflow_chart(
    plot: Any,
    artifact_file: str,
    *,
    run_id: str | None = None,
    tracking_uri: str | None = None,
    use_cdn: bool | Literal["auto"] | None = False,
) -> None:
    """
    Store an accessible chart in an MLflow run, as an HTML artifact.

    The MLflow UI shows an ``.html`` artifact in a frame on the run's
    Artifacts tab, where the chart is read from the keyboard, as sound, as
    text and in braille like any other maidr chart.

    Parameters
    ----------
    plot : Any
        The chart: one :func:`read_mlflow_metrics` returned, or anything
        :func:`maidr.render` takes, such as a matplotlib figure or axes.
    artifact_file : str
        Where in the run's artifacts to store it, ending in ``.html``, such
        as ``"charts/loss.html"``.
    run_id : str, optional
        The run to store it in. By default the active run, as
        ``mlflow.log_text`` would.
    tracking_uri : str, optional
        The tracking server holding ``run_id``. By default MLflow's own.
        Used only with ``run_id``.
    use_cdn : bool, {"auto"}, or None, default False
        Where the chart loads ``maidr.js`` from. ``False``, the default,
        stores the script inside the artifact, about 2 MB, so the chart works
        wherever the tracking server can be reached, with no other network
        access, and keeps working as maidr.js changes. ``True`` loads it from
        the jsDelivr CDN, which keeps the artifact small. ``None`` defers to
        :func:`maidr.get_use_cdn`.

    Raises
    ------
    ImportError
        If ``mlflow`` is not installed.
    ValueError
        If ``artifact_file`` does not end in ``.html``, which the MLflow UI
        would show as text.

    Notes
    -----
    The MLflow UI loads an HTML artifact into a frame sandboxed with
    ``allow-scripts`` alone, so maidr runs in it but cannot keep its settings
    between visits, and a refreshable braille display cannot be reached from
    it.

    Examples
    --------
    >>> import mlflow
    >>> import maidr
    >>> with mlflow.start_run() as run:
    ...     for step, loss in enumerate([0.9, 0.6, 0.4]):
    ...         mlflow.log_metric("loss", loss, step=step)
    >>> chart = maidr.read_mlflow_metrics(run.info.run_id)[0]
    >>> maidr.log_mlflow_chart(chart, "charts/loss.html", run_id=run.info.run_id)
    """
    if not artifact_file.endswith(".html"):
        raise ValueError(
            f"artifact_file ends in .html for the MLflow UI to show it as a "
            f"chart, not {artifact_file!r}"
        )
    # The frame's own document, rather than a fragment: the MLflow UI loads
    # the artifact as a page of its own, which a screen reader announces by
    # its <title>.
    from maidr.widget._document import render as render_document

    fragment, title = render_document(plot, use_cdn, stacklevel=4)
    page = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html.escape(title or 'Accessible chart')}</title>\n</head>\n"
        f"<body>\n{fragment}\n</body>\n</html>\n"
    )
    if run_id is None:
        mlflow = _mlflow()
        mlflow.log_text(page, artifact_file)
    else:
        _client(tracking_uri).log_text(run_id, page, artifact_file)


def _mlflow() -> Any:
    try:
        import mlflow
    except ImportError as error:
        from maidr.widget._extras import missing_extra_error

        raise missing_extra_error(error, "mlflow", "mlflow") from error
    return mlflow


def _client(tracking_uri: str | None) -> Any:
    return _mlflow().MlflowClient(tracking_uri=tracking_uri)


def _run_list(runs: Any) -> list[Any]:
    """The runs as a list of ids and runs, whichever form they came in."""
    # Asked before ``info``: a DataFrame has an ``info`` method too.
    columns = getattr(runs, "columns", None)
    if columns is not None:
        if "run_id" not in columns:
            raise TypeError(
                "maidr reads MLflow runs from a DataFrame with a 'run_id' "
                "column, as mlflow.search_runs() returns."
            )
        return list(runs["run_id"])
    if isinstance(runs, str) or _is_run(runs):
        return [runs]
    try:
        return list(runs)
    except TypeError:
        raise TypeError(
            "maidr reads MLflow runs from a run id, a run, what "
            f"mlflow.search_runs() returns, or a list of these, not {runs!r}."
        ) from None


def _run(client: Any, run: Any) -> Any:
    """A run as ``get_run`` returns it, its metrics' latest values included."""
    if isinstance(run, str):
        return client.get_run(run)
    if _is_run(run):
        return run
    raise TypeError(f"maidr reads an MLflow run from its id or a Run, not {run!r}.")


def _is_run(run: Any) -> bool:
    """Whether ``run`` is an ``mlflow.entities.Run``, by what it holds."""
    return hasattr(getattr(run, "info", None), "run_id") and hasattr(run, "data")


def _series(history: list[Any], run: Any, x: str) -> MetricSeries:
    """A metric's history in order of step, then time, as the MLflow UI draws."""
    if x == "step":
        ordered = sorted(history, key=lambda m: (m.step, m.timestamp))
        steps = [float(m.step) for m in ordered]
    else:
        ordered = sorted(history, key=lambda m: (m.timestamp, m.step))
        start = run.info.start_time
        if start is None:
            start = ordered[0].timestamp
        steps = [(m.timestamp - start) / 1000 for m in ordered]
    values = [_value(m.value) for m in ordered]
    return MetricSeries(np.asarray(steps, dtype=float), np.asarray(values, dtype=float))


def _value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan

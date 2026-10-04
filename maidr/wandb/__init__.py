"""Read the training curves of Weights & Biases runs into maidr.

>>> import maidr
>>> for chart in maidr.read_wandb_history("my-team/my-project/abc123"):
...     maidr.show(chart)

Each metric a run logged with ``wandb.log`` becomes one chart, with one line
per run, drawn with matplotlib, and py-maidr reads the drawing like any other
matplotlib figure. A run named by its path is fetched through ``wandb.Api``,
so that needs the ``wandb`` package and an API key; a run already fetched, or
history rows saved earlier, need neither.
"""

from __future__ import annotations

import math
import os
from typing import Any, Iterable, Iterator, Mapping

import numpy as np

from maidr.util.caller_warning import warn_at_caller
from maidr.wandb.runfile import find_run_files, is_run_file, read_run_file
from maidr.util.metric_chart import (
    DEFAULT_MAX_POINTS,
    MetricChart,
    MetricSeries,
    check_options,
    draw_charts,
    unique_names,
)

__all__ = ["MetricChart", "MetricSeries", "load_wandb_history", "read_wandb_history"]

#: What W&B's own x axes are called on its charts.
_AXIS_NAMES = {
    "_step": "Step",
    "_runtime": "Relative time (seconds)",
    "_timestamp": "Wall time (seconds since 1970)",
}

#: How W&B writes a value JSON cannot hold.
_NON_FINITE = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}


def load_wandb_history(
    runs: Any,
    *,
    keys: Iterable[str] | None = None,
    x: str = "_step",
    api: Any = None,
) -> dict[str, dict[str, MetricSeries]]:
    """
    Read the metrics Weights & Biases runs logged.

    Parameters
    ----------
    runs : str, wandb.apis.public.Run, mapping, or iterable of these
        The runs: a run's path (``"entity/project/run_id"``, as its page's
        URL ends), a run ``wandb.Api().run()`` or ``.runs()`` returned, or an
        iterable of either. A mapping instead reads history saved earlier:
        run name to its rows, as a list of dicts or as the
        ``pandas.DataFrame`` that ``run.history()`` returns.
    keys : iterable of str, optional
        Only these metrics, in this order. By default every metric a run
        logged a number under, sorted, leaving out W&B's own ``_``-prefixed
        keys and ``x``. A metric that no run logged is warned about.
    x : str, default "_step"
        The key whose value places a row along the x axis: ``"_step"``,
        ``"_runtime"``, ``"_timestamp"`` or a metric you logged yourself,
        such as ``"epoch"``. A row without a number under it is left out.
    api : wandb.Api, optional
        The API that fetches a run named by its path. By default
        ``wandb.Api()``.

    Returns
    -------
    dict of str to dict of str to MetricSeries
        Metric by metric, and within a metric run by run, in the order the
        runs were given. A run that logged nothing under a metric is absent.

    Raises
    ------
    ImportError
        If a run is named by its path and ``wandb`` is not installed.
    TypeError
        If ``runs`` is none of the above.
    """
    names, ids, histories = [], [], []
    for name, run_id, rows in _runs(runs, api):
        names.append(name)
        ids.append(run_id)
        histories.append(rows)
    logged: dict[str, dict[str, tuple[list[float], list[float]]]] = {}
    for name, rows in zip(unique_names(names, ids), histories):
        for row in rows:
            step = _number(row.get(x))
            if step is None or math.isnan(step):
                continue
            for key, value in _flatten(row):
                if key == x:
                    continue
                number = _number(value)
                if number is None:
                    continue
                steps, values = logged.setdefault(key, {}).setdefault(name, ([], []))
                steps.append(step)
                values.append(number)

    if keys is None:
        order = sorted(key for key in logged if not key.startswith("_"))
    else:
        order = list(dict.fromkeys(keys))
        known = ", ".join(f"'{key}'" for key in sorted(logged)) or "none"
        for key in order:
            if key not in logged:
                warn_at_caller(
                    f"No run logged a number under '{key}'; the metrics logged "
                    f"are {known}."
                )
    return {
        key: {name: _series(steps, values) for name, (steps, values) in by_run.items()}
        for key, by_run in ((key, logged[key]) for key in order if key in logged)
    }


def read_wandb_history(
    runs: Any,
    *,
    keys: Iterable[str] | None = None,
    x: str = "_step",
    smoothing: float = 0.0,
    max_points: int | None = DEFAULT_MAX_POINTS,
    api: Any = None,
) -> list[MetricChart]:
    """
    Read the training curves of Weights & Biases runs.

    One chart per metric, as a W&B workspace draws it: the step along the x
    axis, the value along the y axis, and one line per run.

    Parameters
    ----------
    runs : str, wandb.apis.public.Run, mapping, or iterable of these
        The runs, as for :func:`load_wandb_history`: a run's path such as
        ``"my-team/my-project/abc123"``, a fetched run, a list of either, or
        a mapping of run name to saved history rows.
    keys : iterable of str, optional
        Only these metrics, in this order, such as ``["train/loss"]``.
    x : str, default "_step"
        What the x axis counts, such as ``"epoch"`` or ``"_runtime"``.
    smoothing : float, default 0
        A smoothing weight, from 0 up to but not including 1, applied as
        TensorBoard applies it (W&B's "Exponential moving average"). Above
        0, each run is drawn twice: as logged, and smoothed, under the run's
        name followed by ``(smoothed)``. 0 draws the values as logged only.
    max_points : int or None, default 1000
        At most this many points per line, evenly spaced and always keeping
        the first and last, so a long run stays quick to walk. ``None``
        keeps every point.
    api : wandb.Api, optional
        The API that fetches a run named by its path.

    Returns
    -------
    list of maidr.wandb.MetricChart
        One per metric. Pass one to :func:`maidr.show`, :func:`maidr.render`
        or :func:`maidr.save_html`.

    Raises
    ------
    ImportError
        If a run is named by its path and ``wandb`` is not installed.
    TypeError
        If ``runs`` is not a run, a path, a mapping or an iterable of these.
    ValueError
        If ``smoothing`` is not in ``[0, 1)`` or ``max_points`` is below 2.

    Notes
    -----
    A fetched run is read with ``run.scan_history()``, every row it logged,
    not the 500 evenly sampled rows ``run.history()`` returns; ``max_points``
    then thins the line. Rows are placed in order of ``x``.

    A value that is not a number -- an image, a table, a histogram -- is not
    read. A dictionary logged as a value is read as its own metrics, named
    with a dot, ``{"val": {"loss": 0.3}}`` as ``val.loss``. In rows given as
    a ``pandas.DataFrame`` a missing value and a logged ``NaN`` look the
    same, so both are left out; elsewhere a logged ``NaN`` is a gap in the
    line.

    Examples
    --------
    >>> import maidr
    >>> charts = maidr.read_wandb_history(
    ...     ["my-team/llm/abc123", "my-team/llm/def456"], keys=["train/loss"]
    ... )
    >>> maidr.save_html(charts[0], "loss.html")
    """
    check_options(smoothing, max_points)
    metrics = load_wandb_history(runs, keys=keys, x=x, api=api)
    if not metrics and keys is None:
        warn_at_caller("maidr found no numeric metrics in these runs.")
    return draw_charts(
        metrics,
        smoothing=smoothing,
        max_points=max_points,
        xlabel=_AXIS_NAMES.get(x, x),
    )


def _runs(runs: Any, api: Any) -> Iterator[tuple[str, str, Iterable[Mapping]]]:
    """Each run as its display name, its id and its history rows."""
    if isinstance(runs, Mapping):
        for name, rows in runs.items():
            yield str(name), str(name), _rows(rows)
        return
    if isinstance(runs, (str, os.PathLike)) or hasattr(runs, "scan_history"):
        runs = [runs]
    elif _is_frame(runs):
        raise TypeError(
            "maidr cannot tell which run a DataFrame of history is; pass it "
            "named, as {'run name': frame}."
        )
    try:
        items = list(runs)
    except TypeError:
        raise TypeError(
            "maidr reads W&B runs from a run path such as "
            "'entity/project/run_id', a run wandb.Api() returned, a list of "
            f"these, or a mapping of run name to history rows, not {runs!r}."
        ) from None
    for run in items:
        if isinstance(run, os.PathLike) or (
            isinstance(run, str) and (os.path.exists(run) or is_run_file(run))
        ):
            yield from _local(os.fspath(run))
            continue
        if isinstance(run, str):
            run = _api(api).run(run)
        if not hasattr(run, "scan_history"):
            raise TypeError(
                "maidr reads a W&B run from its path or from a run "
                f"wandb.Api() returned, not {run!r}."
            )
        run_id = str(getattr(run, "id", "") or getattr(run, "name", ""))
        yield str(getattr(run, "name", "") or run_id), run_id, run.scan_history()


def _local(path: str) -> Iterator[tuple[str, str, Iterable[Mapping]]]:
    """Each run a run file, or a directory of them, holds."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"maidr found no W&B run file at {path}.")
    found = find_run_files(path)
    if not found:
        warn_at_caller(f"maidr found no W&B run file (run-<id>.wandb) in {path}.")
    for run_file in found:
        run = read_run_file(run_file)
        yield run.name, run.run_id, run.rows


def _api(api: Any) -> Any:
    if api is not None:
        return api
    try:
        import wandb
    except ImportError as error:
        from maidr.widget._extras import missing_extra_error

        raise missing_extra_error(error, "wandb", "wandb") from error
    return wandb.Api()


def _is_frame(rows: Any) -> bool:
    return hasattr(rows, "columns") and hasattr(rows, "to_dict")


def _rows(rows: Any) -> Iterable[Mapping]:
    """History rows as dicts, a DataFrame's missing values dropped."""
    if _is_frame(rows):
        return (
            {
                key: value
                for key, value in record.items()
                if not (isinstance(value, float) and math.isnan(value))
            }
            for record in rows.to_dict("records")
        )
    return rows


def _flatten(row: Mapping, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """A row's values, a nested dictionary's under dotted names.

    A dictionary with a ``_type`` is a W&B media or chart value, not a group
    of metrics, and is passed on whole to be skipped.
    """
    for key, value in row.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping) and "_type" not in value:
            yield from _flatten(value, f"{name}.")
        else:
            yield name, value


def _number(value: Any) -> float | None:
    """A logged value as a float, or ``None`` when it is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, str):
        return _NON_FINITE.get(value)
    return None


def _series(steps: list[float], values: list[float]) -> MetricSeries:
    """One run's values, placed in order of their x, ties kept as logged."""
    xs = np.asarray(steps, dtype=float)
    order = np.argsort(xs, kind="stable")
    return MetricSeries(xs[order], np.asarray(values, dtype=float)[order])

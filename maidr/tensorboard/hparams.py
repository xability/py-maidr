"""Read the hyperparameter sweep of a TensorBoard log directory.

TensorBoard's HParams dashboard shows a sweep two ways: as parallel
coordinates, one line per training session across an axis for each
hyperparameter and each metric, and as a scatter plot matrix, each
hyperparameter against each metric. Both are read here from the summaries the
HParams plugin's API writes: the experiment, in the log directory's own
events, says which hyperparameters and metrics there are; each session's run
says its hyperparameters; and the session's scalars give each metric its
final value.
"""

from __future__ import annotations

import math
import os
import re
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any

from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.prebuilt import PrebuiltPlot
from maidr.tensorboard.events import (
    HPARAMS_PLUGIN,
    SCALARS_PLUGIN,
    _fields,
    find_runs,
    read_run,
)
from maidr.tensorboard.logdir import TensorBoardChart
from maidr.util.caller_warning import warn_at_caller

__all__ = ["Session", "load_hparams", "read_tensorboard_hparams"]

_SESSION_TAG = "_hparams_/session_start_info"
_EXPERIMENT_TAG = "_hparams_/experiment"
_LINES = "#1f77b4"


@dataclass(frozen=True)
class Session:
    """
    One training session of a sweep.

    Attributes
    ----------
    name : str
        The session's run, such as ``"session_3"``.
    hparams : dict
        Each hyperparameter's value: a number, a string or a bool.
    metrics : dict of str to float
        Each metric's last logged value, named ``tag`` for one logged in the
        session's own run and ``group/tag`` for one logged in a run under it,
        such as ``validation/loss``.
    """

    name: str
    hparams: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)


def load_hparams(logdir: str | os.PathLike) -> list[Session]:
    """
    Read the sessions of a hyperparameter sweep.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``), as
        the HParams plugin's ``hp.hparams_config`` and ``hp.hparams`` wrote it.

    Returns
    -------
    list of Session
        One per run that logged ``hp.hparams``, by run name. The metrics are
        the ones the experiment declares, when ``hp.hparams_config`` wrote
        one, and otherwise every scalar the session's runs logged.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    """
    path = os.fspath(logdir)
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"maidr reads a TensorBoard log directory, and {path} is not a directory."
        )
    runs = find_runs(path)
    starts: dict[str, dict[str, Any]] = {}
    declared: list[tuple[str, str]] | None = None
    order: list[str] = []
    for run, paths in runs.items():
        read = read_run(paths, HPARAMS_PLUGIN)
        for tag, contents in read.values.items():
            for content in contents:
                if not content:
                    continue
                if tag == _SESSION_TAG:
                    starts[run] = _session_start(content)
                elif tag == _EXPERIMENT_TAG and declared is None:
                    order, declared = _experiment(content)
    sessions = []
    for name in sorted(starts, key=_natural):
        last: dict[str, float] = {}
        for run, paths in runs.items():
            if run != name and not run.startswith(f"{name}/"):
                continue
            group = run[len(name) + 1 :]
            scalars = read_run(paths, SCALARS_PLUGIN)
            for tag, values in scalars.values.items():
                if scalars.plugins.get(tag) == SCALARS_PLUGIN and values:
                    last[f"{group}/{tag}" if group else tag] = float(values[-1])
        if declared is not None:
            wanted = [f"{group}/{tag}" if group else tag for group, tag in declared]
            metrics = {metric: last[metric] for metric in wanted if metric in last}
        else:
            metrics = dict(sorted(last.items()))
        hparams = starts[name]
        # A session's hyperparameters arrive as a protobuf map, in no order;
        # the experiment's declaration order is the one the dashboard shows.
        ranked = order + sorted(set(hparams) - set(order))
        hparams = {key: hparams[key] for key in ranked if key in hparams}
        sessions.append(Session(name, hparams, metrics))
    return sessions


def read_tensorboard_hparams(logdir: str | os.PathLike) -> list[TensorBoardChart]:
    """
    Read a hyperparameter sweep as its parallel coordinates and scatter matrix.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``).

    Returns
    -------
    list of TensorBoardChart
        Two charts, both tagged ``"hparams"``, whose ``runs`` are the
        sessions: first the parallel coordinates plot, one line per session
        across an axis for each hyperparameter and then each metric; then the
        scatter plot matrix, a row per metric and a column per hyperparameter.
        Empty, with a warning, when the directory holds no sweep.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.

    Notes
    -----
    Each axis of the parallel coordinates plot is pitched on its own scale,
    as it is drawn. A hyperparameter whose values are strings or bools is
    placed by the position of its value among the values the sweep tried, in
    sorted order, and the axis says which position is which, such as
    ``optimizer (0 adam, 1 sgd)``.

    Examples
    --------
    >>> import maidr
    >>> parallel, matrix = maidr.read_tensorboard_hparams("logs/hparam_tuning")
    >>> maidr.show(parallel)
    """
    sessions = load_hparams(logdir)
    if not sessions:
        warn_at_caller(f"maidr found no hyperparameter sweep in {os.fspath(logdir)}.")
        return []
    names = tuple(session.name for session in sessions)
    hparams = list(dict.fromkeys(k for s in sessions for k in s.hparams))
    metrics = list(dict.fromkeys(k for s in sessions for k in s.metrics))
    columns = [
        _column(name, [s.hparams.get(name) for s in sessions]) for name in hparams
    ]
    columns += [
        _column(name, [s.metrics.get(name) for s in sessions]) for name in metrics
    ]
    return [
        TensorBoardChart("hparams", names, _parallel(names, columns)),
        TensorBoardChart(
            "hparams",
            names,
            _matrix(columns[: len(hparams)], columns[len(hparams) :]),
        ),
    ]


@dataclass
class _Column:
    """
    One axis: its name, each session's position on it, and its tick names.

    ``short`` is the name alone, for a tick; ``name`` also lists the positions
    of a categorical axis.
    """

    name: str
    values: list[float | None]
    ticks: list[str] | None = None
    short: str = ""

    def __post_init__(self) -> None:
        if not self.short:
            self.short = self.name


def _column(name: str, raw: list[Any]) -> _Column:
    """
    Place each session's value on an axis.

    Numbers stay as they are. Strings and bools become the position of the
    value among the values seen, sorted, and the axis names the positions.
    """
    present = [value for value in raw if value is not None]
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in present
    ):
        # A diverged run's NaN or infinity has no place on an axis; it is
        # left out, as a value that was never logged is.
        return _Column(
            name,
            [None if v is None or not math.isfinite(v) else float(v) for v in raw],
        )
    levels = sorted({str(value) for value in present})
    index = {level: position for position, level in enumerate(levels)}
    label = f"{name} ({', '.join(f'{i} {level}' for i, level in enumerate(levels))})"
    return _Column(
        label,
        [None if v is None else float(index[str(v)]) for v in raw],
        ticks=levels,
        short=name,
    )


def _parallel(names: tuple[str, ...], columns: list[_Column]) -> Figure:
    """
    Draw one line per session across an axis per column, and register them.

    Each axis is scaled to its own extent, so the lines are drawn as plain
    ``Line2D`` artists, which nothing reads, and the layer carries the
    unscaled values.
    """
    count = len(columns)
    fig = Figure(figsize=(max(6.0, 1.6 * count), 4.6))
    ax = fig.add_subplot()
    extents = []
    for column in columns:
        present = [v for v in column.values if v is not None]
        low, high = (min(present), max(present)) if present else (0.0, 1.0)
        extents.append((low, high))
    for position, (column, (low, high)) in enumerate(zip(columns, extents)):
        ax.add_line(Line2D([position, position], [0, 1], color="#555555", lw=0.8))
        ax.text(position, -0.06, _tick(column, low), ha="center", va="top", fontsize=8)
        ax.text(
            position, 1.04, _tick(column, high), ha="center", va="bottom", fontsize=8
        )
    lines = []
    for row in range(len(names)):
        xs, ys = [], []
        for position, (column, (low, high)) in enumerate(zip(columns, extents)):
            value = column.values[row]
            if value is None:
                continue
            xs.append(position)
            ys.append(0.5 if high == low else (value - low) / (high - low))
        line = Line2D(xs, ys, color=_LINES, alpha=0.75, lw=1.4, marker="o", ms=3)
        line.set_gid(f"maidr-{uuid.uuid4()}")
        ax.add_line(line)
        lines.append(line)
    ax.set_xlim(-0.3, count - 0.7)
    ax.set_ylim(-0.15, 1.15)
    ax.set_xticks(range(count), [column.short for column in columns])
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_title("Hyperparameters and metrics, one line per session")
    fig.tight_layout()
    data = [
        [
            {"x": column.name, "y": column.values[row], "z": name}
            for column in columns
            if column.values[row] is not None
        ]
        for row, name in enumerate(names)
    ]
    FigureManager.add_plot(
        PrebuiltPlot(
            ax,
            PlotType.PARALLEL,
            labels={"x": "Hyperparameter or metric", "y": "Value"},
            data=data,
            selectors=[f"g[id='{line.get_gid()}'] > path" for line in lines],
        )
    )
    return fig


def _matrix(hparams: list[_Column], metrics: list[_Column]) -> Figure:
    """Draw each hyperparameter against each metric, a row per metric."""
    rows, cols = max(len(metrics), 1), max(len(hparams), 1)
    fig = Figure(figsize=(min(14.0, 2.8 * cols + 0.8), min(14.0, 2.4 * rows + 0.6)))
    grid = fig.subplots(rows, cols, squeeze=False)
    for r, metric in enumerate(metrics):
        for c, hparam in enumerate(hparams):
            ax = grid[r][c]
            pairs = [
                (x, y)
                for x, y in zip(hparam.values, metric.values)
                if x is not None and y is not None
            ]
            if pairs:
                xs, ys = zip(*pairs)
                ax.scatter(xs, ys, color=_LINES, s=24)
            if hparam.ticks is not None:
                ax.set_xticks(range(len(hparam.ticks)), hparam.ticks)
            ax.set_xlabel(hparam.short, fontsize=8)
            ax.set_ylabel(metric.name, fontsize=8)
            ax.tick_params(labelsize=7)
    fig.suptitle("Each hyperparameter against each metric")
    fig.tight_layout()
    return fig


def _tick(column: _Column, value: float) -> str:
    """A position on an axis as its tick reads: the category, or the number."""
    if column.ticks is not None:
        return column.ticks[int(round(value))]
    return f"{value:.4g}"


def _natural(name: str) -> list[Any]:
    """A sort key that puts ``session_2`` before ``session_10``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _session_start(content: bytes) -> dict[str, Any]:
    """The hyperparameters an ``HParamsPluginData.session_start_info`` holds."""
    values: dict[str, Any] = {}
    for number, wire, start in _fields(content):
        if number != 3 or wire != 2:
            continue
        for inner, inner_wire, entry in _fields(start):
            if inner != 1 or inner_wire != 2:
                continue
            key = None
            value = None
            for part, part_wire, item in _fields(entry):
                if part == 1 and part_wire == 2:
                    key = item.decode("utf-8", "replace")
                elif part == 2 and part_wire == 2:
                    value = _value(item)
            if key is not None and value is not None:
                values[key] = value
    return values


def _experiment(content: bytes) -> tuple[list[str], list[tuple[str, str]] | None]:
    """
    The hyperparameters an experiment declares, in order, and the
    ``(group, tag)`` of each metric it declares; ``None`` without one.
    """
    for number, wire, experiment in _fields(content):
        if number != 2 or wire != 2:
            continue
        hparams = []
        metrics = []
        for inner, inner_wire, info in _fields(experiment):
            if inner == 4 and inner_wire == 2:
                for part, part_wire, text in _fields(info):
                    if part == 1 and part_wire == 2:
                        hparams.append(text.decode("utf-8", "replace"))
            if inner != 5 or inner_wire != 2:
                continue
            for part, part_wire, name in _fields(info):
                if part == 1 and part_wire == 2:
                    group = tag = ""
                    for piece, piece_wire, text in _fields(name):
                        if piece == 1 and piece_wire == 2:
                            group = text.decode("utf-8", "replace")
                        elif piece == 2 and piece_wire == 2:
                            tag = text.decode("utf-8", "replace")
                    metrics.append((group, tag))
        return hparams, metrics
    return [], None


def _value(message: bytes) -> Any:
    """A ``google.protobuf.Value``: a number, a string or a bool."""
    for number, wire, value in _fields(message):
        if number == 2 and wire == 1:
            return struct.unpack("<d", value)[0]
        if number == 3 and wire == 2:
            return value.decode("utf-8", "replace")
        if number == 4 and wire == 0:
            return bool(value)
    return None

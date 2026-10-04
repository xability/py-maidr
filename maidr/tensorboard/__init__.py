"""Read the scalar charts of a TensorBoard log directory into maidr.

>>> import maidr
>>> for chart in maidr.read_tensorboard_scalars("logs/fit"):
...     maidr.show(chart)

The log directory is read from its event files, so neither TensorFlow nor
TensorBoard needs to be installed: what Keras's ``TensorBoard`` callback,
``tf.summary.scalar`` and PyTorch's ``SummaryWriter`` write are all read. Each
tag becomes one chart, with one line per run, drawn with matplotlib, and
py-maidr reads the drawing like any other matplotlib figure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from matplotlib import colormaps
from matplotlib.figure import Figure

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard.events import SCALARS_PLUGIN
from maidr.tensorboard.distributions import read_tensorboard_distributions
from maidr.tensorboard.histograms import (
    HistogramSeries,
    load_histograms,
    read_tensorboard_histograms,
)
from maidr.tensorboard.logdir import TensorBoardChart, load, thin
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "HistogramSeries",
    "ScalarSeries",
    "TensorBoardChart",
    "load_histograms",
    "load_scalars",
    "read_tensorboard_distributions",
    "read_tensorboard_histograms",
    "read_tensorboard_scalars",
    "smooth",
]

#: TensorBoard's default smoothing weight.
DEFAULT_SMOOTHING = 0.6

#: Points kept per line: as many as TensorBoard keeps for a scalar.
DEFAULT_MAX_POINTS = 1000

_WIDTH = 7.0
_HEIGHT = 4.5


@dataclass(frozen=True, eq=False)
class ScalarSeries:
    """
    The values one run logged under one tag, in the order TensorBoard keeps.

    Attributes
    ----------
    steps : numpy.ndarray
        The step of each value, as integers.
    wall_times : numpy.ndarray
        When each value was logged, in seconds since the epoch.
    values : numpy.ndarray
        The values, as floats. A ``NaN`` logged as a loss stays ``NaN``.
    """

    steps: np.ndarray = field(repr=False)
    wall_times: np.ndarray = field(repr=False)
    values: np.ndarray = field(repr=False)

    def __len__(self) -> int:
        return len(self.steps)


def load_scalars(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
) -> dict[str, dict[str, ScalarSeries]]:
    """
    Read the scalars of a TensorBoard log directory.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``). Every
        directory under it holding an event file is a run, named by its path
        from ``logdir``, and ``"."`` for ``logdir`` itself.
    tags : iterable of str, optional
        Only these tags, in this order. A tag that no run logged is warned
        about.
    runs : iterable of str, optional
        Only these runs. A run that is not in ``logdir`` is warned about.

    Returns
    -------
    dict of str to dict of str to ScalarSeries
        Tag by tag, sorted unless ``tags`` gives the order, and within a tag
        run by run, sorted.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    """
    logged = load(logdir, SCALARS_PLUGIN, tags=tags, runs=runs)
    return {
        tag: {
            run: ScalarSeries(
                np.asarray(steps, dtype=np.int64),
                np.asarray(wall_times, dtype=float),
                np.asarray(values, dtype=float),
            )
            for run, (steps, wall_times, values) in by_run.items()
        }
        for tag, by_run in logged.items()
    }


def read_tensorboard_scalars(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
    smoothing: float = DEFAULT_SMOOTHING,
    max_points: int | None = DEFAULT_MAX_POINTS,
) -> list[TensorBoardChart]:
    """
    Read the scalar charts of a TensorBoard log directory.

    One chart per tag, as TensorBoard's Scalars dashboard draws it: the step
    along the x axis, the value along the y axis, and one line per run.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``), such
        as the ``log_dir`` given to Keras's ``TensorBoard`` callback.
    tags : iterable of str, optional
        Only these tags, in this order. By default every scalar tag, sorted.
    runs : iterable of str, optional
        Only these runs, such as ``["train", "validation"]``.
    smoothing : float, default 0.6
        TensorBoard's smoothing weight, from 0 up to but not including 1. Above
        0, each run is drawn twice: as logged, and smoothed, under the run's
        name followed by ``(smoothed)``, as TensorBoard shows both. 0 draws
        the values as logged only.
    max_points : int or None, default 1000
        At most this many points per line, evenly spaced over the steps and
        always keeping the first and last, so a long run stays quick to walk.
        ``None`` keeps every point.

    Returns
    -------
    list of TensorBoardChart
        One per tag. Pass one to :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    ValueError
        If ``smoothing`` is not in ``[0, 1)`` or ``max_points`` is below 2.

    Notes
    -----
    Read: scalars written by Keras's ``TensorBoard`` callback,
    ``tf.summary.scalar`` in TensorFlow 1 and 2, PyTorch's
    ``torch.utils.tensorboard.SummaryWriter`` and tensorboardX. Histograms,
    distributions, images and the other dashboards are not read yet.

    Smoothing is TensorBoard's: an exponential moving average, corrected so
    the first values are not pulled toward zero. It is computed over every
    value logged, before ``max_points`` thins the line. A value that is not
    finite, such as a loss that became ``NaN``, is a gap in the line and is
    left out of the average, as TensorBoard leaves it out.

    A damaged event file is read up to the damage, with a warning, wherever
    the damage reaches a record's length. Damage inside a record's data is
    not detected, since checking it would mean a checksum over every image
    and histogram the log directory holds, and reads as the damaged value.

    Examples
    --------
    >>> import maidr
    >>> charts = maidr.read_tensorboard_scalars("logs/fit", tags=["epoch_loss"])
    >>> maidr.save_html(charts[0], "loss.html")
    """
    if not 0 <= smoothing < 1:
        raise ValueError(
            f"smoothing is a weight from 0 up to but not including 1, not {smoothing}"
        )
    if max_points is not None and max_points < 2:
        raise ValueError(f"max_points keeps at least 2 points, not {max_points}")
    scalars = load_scalars(logdir, tags=tags, runs=runs)
    if not scalars and tags is None:
        warn_at_caller(f"maidr found no scalars in {os.fspath(logdir)}.")
    charts = []
    for tag, series in scalars.items():
        figure = _draw(tag, series, smoothing, max_points)
        try:
            FigureManager.get_maidr(figure)
        except KeyError:
            warn_at_caller(
                f"No value logged under '{tag}' is a number; it is left out."
            )
            continue
        charts.append(TensorBoardChart(tag, tuple(series), figure))
    return charts


def smooth(values: np.ndarray, weight: float) -> np.ndarray:
    """
    Smooth values the way TensorBoard's Scalars dashboard does.

    An exponential moving average, divided by ``1 - weight ** n`` after the
    ``n``-th finite value so that it starts at the first value rather than
    near zero. A value that is not finite is kept where it is and left out of
    the average.

    Parameters
    ----------
    values : numpy.ndarray
        The values, in step order.
    weight : float
        The smoothing weight, from 0 (none) up to but not including 1.

    Returns
    -------
    numpy.ndarray
        The smoothed values, as many as ``values``.
    """
    values = np.asarray(values, dtype=float)
    smoothed = values.copy()
    finite = np.isfinite(values)
    if weight == 0 or not finite.any():
        return smoothed
    # The average over the finite values alone, as one linear filter rather
    # than a Python loop: a run can log millions of steps. Imported here, as
    # `import maidr` loads no scipy (tests/core/test_lazy_patches.py).
    from scipy.signal import lfilter

    average = lfilter([1 - weight], [1, -weight], values[finite])
    count = np.arange(1, len(average) + 1)
    smoothed[finite] = average / (1 - weight**count)
    return smoothed


def _draw(
    tag: str,
    series: dict[str, ScalarSeries],
    smoothing: float,
    max_points: int | None,
) -> Figure:
    fig = Figure(figsize=(_WIDTH, _HEIGHT))
    ax = fig.add_subplot()
    colors = _colors(len(series))
    for color, (run, data) in zip(colors, series.items()):
        keep = thin(len(data), max_points)
        steps = data.steps[keep]
        if smoothing > 0:
            ax.plot(steps, data.values[keep], color=color, alpha=0.35, label=run)
            ax.plot(
                steps,
                smooth(data.values, smoothing)[keep],
                color=color,
                label=f"{run} (smoothed)",
            )
        else:
            ax.plot(steps, data.values[keep], color=color, label=run)
    ax.set_title(tag)
    ax.set_xlabel("Step")
    ax.set_ylabel(tag)
    ax.grid(True, color="#E0E0E0", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    fig.tight_layout()
    return fig


def _colors(count: int) -> list:
    """One color per run, from matplotlib's tab10, repeating after ten."""
    palette = colormaps["tab10"]
    return [palette(i % palette.N) for i in range(count)]

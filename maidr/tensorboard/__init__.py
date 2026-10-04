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
from maidr.tensorboard.events import SCALARS_PLUGIN, find_runs, read_run
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "ScalarSeries",
    "TensorBoardChart",
    "load_scalars",
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


@dataclass(frozen=True, eq=False)
class TensorBoardChart:
    """
    One tag of a TensorBoard log directory, drawn and ready for maidr.

    Pass it to :func:`maidr.show`, :func:`maidr.render`,
    :func:`maidr.save_html` or :func:`maidr.close` as you would a matplotlib
    figure.

    Attributes
    ----------
    tag : str
        The tag the values were logged under, such as ``"epoch_loss"``.
    runs : tuple of str
        The runs drawn, one line each (two with smoothing), in legend order.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    tag: str
    runs: tuple[str, ...]
    figure: Figure = field(repr=False)


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
    found = _runs(logdir)
    wanted_runs = None if runs is None else list(runs)
    if wanted_runs is not None:
        for run in wanted_runs:
            if run not in found:
                warn_at_caller(
                    f"maidr found no run '{run}' in {os.fspath(logdir)}; "
                    f"its runs are {_names(found)}."
                )
        found = {run: found[run] for run in wanted_runs if run in found}
    scalars: dict[str, dict[str, ScalarSeries]] = {}
    for run, paths in found.items():
        read = read_run(paths)
        for tag, steps in read.steps.items():
            if read.plugins.get(tag) != SCALARS_PLUGIN or not steps:
                continue
            scalars.setdefault(tag, {})[run] = ScalarSeries(
                np.asarray(steps, dtype=np.int64),
                np.asarray(read.wall_times[tag], dtype=float),
                np.asarray(read.values[tag], dtype=float),
            )
    order = sorted(scalars)
    if tags is not None:
        order = list(dict.fromkeys(tags))
        known = _names(dict.fromkeys(sorted(scalars)))
        for tag in order:
            if tag not in scalars:
                warn_at_caller(
                    f"maidr found no scalars tagged '{tag}' in "
                    f"{os.fspath(logdir)}; its tags are {known}."
                )
    return {tag: dict(sorted(scalars[tag].items())) for tag in order if tag in scalars}


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


def _runs(logdir: str | os.PathLike) -> dict[str, list[str]]:
    path = os.fspath(logdir)
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"maidr reads a TensorBoard log directory, and {path} is not a directory."
        )
    return find_runs(path)


def _names(found: dict) -> str:
    return ", ".join(f"'{name}'" for name in found) or "none"


def _thin(count: int, max_points: int | None) -> np.ndarray:
    """Which of ``count`` points to keep: evenly spaced, first and last kept."""
    if max_points is None or count <= max_points:
        return np.arange(count)
    return np.unique(np.round(np.linspace(0, count - 1, max_points)).astype(int))


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
        keep = _thin(len(data), max_points)
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

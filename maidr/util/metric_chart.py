"""Training curves: one chart per metric, one line per run.

Shared by the readers of what a training run logs -- TensorBoard's scalars,
Weights & Biases' history and MLflow's metrics. Each hands over, metric by
metric, the values every run logged against a step, and gets back a matplotlib
figure drawn through the patched ``Axes.plot``, which py-maidr reads like any
other line chart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from matplotlib import colormaps
from matplotlib.figure import Figure

from maidr.core.figure_manager import FigureManager
from maidr.util.caller_warning import warn_at_caller

#: Points kept per line: as many as TensorBoard keeps for a scalar.
DEFAULT_MAX_POINTS = 1000

_WIDTH = 7.0
_HEIGHT = 4.5


@dataclass(frozen=True, eq=False)
class MetricChart:
    """
    One metric of one or more training runs, drawn and ready for maidr.

    Pass it to :func:`maidr.show`, :func:`maidr.render`,
    :func:`maidr.save_html` or :func:`maidr.close` as you would a matplotlib
    figure.

    Attributes
    ----------
    metric : str
        The name the values were logged under, such as ``"train/loss"``.
    runs : tuple of str
        The runs drawn, one line each (two with smoothing), in legend order.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    metric: str
    runs: tuple[str, ...]
    figure: Figure = field(repr=False)


@dataclass(frozen=True, eq=False)
class MetricSeries:
    """
    The values one run logged under one metric, in step order.

    Attributes
    ----------
    steps : numpy.ndarray
        Where each value sits along the x axis, as floats: a step, an epoch
        or a time, whichever the reader was asked for.
    values : numpy.ndarray
        The values, as floats. A ``NaN`` logged as a loss stays ``NaN``.
    """

    steps: np.ndarray = field(repr=False)
    values: np.ndarray = field(repr=False)

    def __len__(self) -> int:
        return len(self.steps)


def check_options(smoothing: float, max_points: int | None) -> None:
    """
    Refuse a smoothing weight or a point count no reader can draw.

    Raises
    ------
    ValueError
        If ``smoothing`` is not in ``[0, 1)`` or ``max_points`` is below 2.
    """
    if not 0 <= smoothing < 1:
        raise ValueError(
            f"smoothing is a weight from 0 up to but not including 1, not {smoothing}"
        )
    if max_points is not None and max_points < 2:
        raise ValueError(f"max_points keeps at least 2 points, not {max_points}")


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


def thin(count: int, keep: int | None) -> np.ndarray:
    """
    Which of ``count`` points to keep: evenly spaced, the first and last kept.

    Parameters
    ----------
    count : int
        How many points there are.
    keep : int or None
        At most this many; ``None`` keeps every one.

    Returns
    -------
    numpy.ndarray
        The indices kept, in order.
    """
    if keep is None or count <= keep:
        return np.arange(count)
    return np.unique(np.round(np.linspace(0, count - 1, keep)).astype(int))


def draw_lines(
    title: str,
    series: Mapping[str, tuple[np.ndarray, np.ndarray]],
    *,
    smoothing: float,
    max_points: int | None,
    xlabel: str,
) -> Figure:
    """
    Draw one metric: one line per run, and a smoothed one beside it.

    Parameters
    ----------
    title : str
        The metric's name, which is the chart's title and its y label.
    series : mapping of str to (numpy.ndarray, numpy.ndarray)
        Run by run, in legend order: the x values and the values.
    smoothing : float
        :func:`smooth`'s weight. Above 0, each run is drawn twice: faintly as
        logged, and smoothed under the run's name followed by ``(smoothed)``.
    max_points : int or None
        At most this many points per line, by :func:`thin`. Smoothing is
        computed over every value first.
    xlabel : str
        What the x axis counts, such as ``"Step"``.

    Returns
    -------
    matplotlib.figure.Figure
        The chart, outside pyplot.
    """
    fig = Figure(figsize=(_WIDTH, _HEIGHT))
    ax = fig.add_subplot()
    for color, (run, (steps, values)) in zip(colors(len(series)), series.items()):
        keep = thin(len(steps), max_points)
        if smoothing > 0:
            ax.plot(steps[keep], values[keep], color=color, alpha=0.35, label=run)
            ax.plot(
                steps[keep],
                smooth(values, smoothing)[keep],
                color=color,
                label=f"{run} (smoothed)",
            )
        else:
            ax.plot(steps[keep], values[keep], color=color, label=run)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(title)
    ax.grid(True, color="#E0E0E0", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    fig.tight_layout()
    return fig


def draw_charts(
    metrics: Mapping[str, Mapping[str, MetricSeries]],
    *,
    smoothing: float,
    max_points: int | None,
    xlabel: str,
) -> list[MetricChart]:
    """
    Draw each metric as a :class:`MetricChart`, in the order given.

    A metric none of whose values is a finite number -- a loss that was
    ``NaN`` from the first step -- has no point a reader could land on; it is
    left out with a warning rather than handed over as an empty chart.

    Parameters
    ----------
    metrics : mapping of str to mapping of str to MetricSeries
        Metric by metric, and within a metric run by run.
    smoothing, max_points, xlabel
        As for :func:`draw_lines`.

    Returns
    -------
    list of MetricChart
        One per metric that holds a number.
    """
    charts = []
    for metric, by_run in metrics.items():
        if not any(np.isfinite(data.values).any() for data in by_run.values()):
            warn_at_caller(
                f"No value logged under '{metric}' is a number; it is left out."
            )
            continue
        figure = draw_lines(
            metric,
            {run: (data.steps, data.values) for run, data in by_run.items()},
            smoothing=smoothing,
            max_points=max_points,
            xlabel=xlabel,
        )
        try:
            FigureManager.get_maidr(figure)
        except KeyError:
            warn_at_caller(
                f"No value logged under '{metric}' is a number; it is left out."
            )
            continue
        charts.append(MetricChart(metric, tuple(by_run), figure))
    return charts


def colors(count: int) -> list:
    """One color per run, from matplotlib's tab10, repeating after ten."""
    palette = colormaps["tab10"]
    return [palette(i % palette.N) for i in range(count)]


def unique_names(names: list[str], ids: list[str]) -> list[str]:
    """
    Run names as a legend can show them: a name two runs share gets its id.

    Parameters
    ----------
    names : list of str
        Each run's display name.
    ids : list of str
        Each run's id, which is unique.

    Returns
    -------
    list of str
        ``names``, with ``" (<id>)"`` added to every name that is not unique,
        so two lines are never read out under one name. The same run given
        twice is numbered from its second time, ``" (<id>) 2"``.
    """
    shared = {name for name in names if names.count(name) > 1}
    labels = [
        f"{name} ({run_id})" if name in shared else name
        for name, run_id in zip(names, ids)
    ]
    seen: dict[str, int] = {}
    unique = []
    for label in labels:
        seen[label] = seen.get(label, 0) + 1
        unique.append(label if seen[label] == 1 else f"{label} {seen[label]}")
    return unique

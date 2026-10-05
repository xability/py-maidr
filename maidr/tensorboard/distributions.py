"""Read the distributions of a TensorBoard log directory.

TensorBoard's Distributions dashboard draws the same histograms as its
Histograms dashboard, compressed: at each step, the value at nine points of
the distribution -- its minimum, the points a normal distribution puts at one,
two and three standard deviations either side of the middle, its median and
its maximum -- drawn as nested bands around the median line.

Each chart is read as one ``percentile_band`` layer: at each step, the nine
values as quantiles from 0 to 1. A reader enters on the median, Up and Down at
a step move through the quantiles in value order, through the spread, and
Left and Right move along the steps; each band is outlined as it is reached.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon

from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.prebuilt import PrebuiltPlot
from maidr.tensorboard.histograms import load_histograms
from maidr.tensorboard.logdir import TensorBoardChart
from maidr.util.metric_chart import thin
from maidr.util.caller_warning import warn_at_caller

__all__ = ["BASIS_POINTS", "percentiles", "read_tensorboard_distributions"]

#: The points of a distribution TensorBoard draws, in hundredths of a percent:
#: the minimum, a normal distribution's -3, -2 and -1 standard deviations, the
#: median, +1, +2 and +3, and the maximum.
BASIS_POINTS = (0, 668, 1587, 3085, 5000, 6915, 8413, 9332, 10000)

#: What each basis point's line is called.
_NAMES = ("min", "6.7%", "15.9%", "30.9%", "median", "69.1%", "84.1%", "93.3%", "max")

#: Points kept per line, as for a scalar.
DEFAULT_MAX_POINTS = 1000

_WIDTH = 7.0
_HEIGHT = 4.5
_BAND = "#F57C00"


def percentiles(buckets: np.ndarray) -> np.ndarray:
    """
    The value at each of :data:`BASIS_POINTS` of one histogram.

    The cumulative count is interpolated linearly within the bucket each point
    falls in, as TensorBoard's compressor does, so the values are the ones its
    Distributions dashboard draws.

    Parameters
    ----------
    buckets : numpy.ndarray
        The histogram's buckets, shape ``(k, 3)``: left edge, right edge and
        count.

    Returns
    -------
    numpy.ndarray
        Nine values, from the minimum to the maximum. All zero for an empty
        histogram, as TensorBoard reads one.
    """
    buckets = np.asarray(buckets, dtype=float).reshape(-1, 3)
    if not buckets.size:
        return np.zeros(len(BASIS_POINTS))
    lowest, highest = buckets[0, 0], buckets[-1, 1]
    counts = buckets[:, 2]
    rights = buckets[:, 1]
    weights = np.cumsum(counts * BASIS_POINTS[-1] / (counts.sum() or 1.0))
    values = []
    for point in BASIS_POINTS:
        i = int(np.searchsorted(weights, point, side="right"))
        while i < len(weights):
            cumulative = weights[i]
            before = weights[i - 1] if i > 0 else 0.0
            if cumulative == before:
                i += 1
                continue
            left = lowest if not i or not before else max(rights[i - 1], lowest)
            right = min(rights[i], highest)
            values.append(
                left + (point - before) / (cumulative - before) * (right - left)
            )
            break
        else:
            values.append(highest)
    return np.asarray(values, dtype=float)


def read_tensorboard_distributions(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
    max_points: int | None = DEFAULT_MAX_POINTS,
) -> list[TensorBoardChart]:
    """
    Read the distribution charts of a TensorBoard log directory.

    One chart per tag and run, as TensorBoard's Distributions dashboard draws
    them: the step along the x axis, and nine values -- the minimum, six
    percentiles, the median and the maximum of the logged values at each step
    -- drawn as the nested bands between them around the median line, and
    read as one ``percentile_band`` layer.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``).
    tags : iterable of str, optional
        Only these histogram tags, in this order.
    runs : iterable of str, optional
        Only these runs.
    max_points : int or None, default 1000
        At most this many steps per chart, evenly spaced and always keeping
        the first and last. ``None`` keeps every step.

    Returns
    -------
    list of TensorBoardChart
        One per tag and run.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    ValueError
        If ``max_points`` is below 2.

    Notes
    -----
    The distributions are the histograms the Histograms dashboard reads, so
    whatever :func:`maidr.read_tensorboard_histograms` reads is read here.
    Each value is a quantile, its level the share of values below it, such
    as 0.8413; a reader enters on the median, moves Up and Down through the
    quantiles in value order, which is the spread of the distribution at that
    step, and Left and Right along one of them over training. maidr.js names
    the band around the median, such as the middle 68%. ``percentile_band``
    is an experimental type.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_tensorboard_distributions("logs/fit"):
    ...     maidr.show(chart)
    """
    if max_points is not None and max_points < 2:
        raise ValueError(f"max_points keeps at least 2 points, not {max_points}")
    histograms = load_histograms(logdir, tags=tags, runs=runs)
    if not histograms and tags is None:
        warn_at_caller(f"maidr found no histograms in {os.fspath(logdir)}.")
    charts = []
    for tag, by_run in histograms.items():
        for run, series in by_run.items():
            keep = thin(len(series), max_points)
            steps = series.steps[keep]
            values = np.array([percentiles(series.buckets[i]) for i in keep])
            title = tag if run == "." else f"{tag} ({run})"
            charts.append(
                TensorBoardChart(tag, (run,), _draw(title, tag, steps, values))
            )
    return charts


def _draw(title: str, tag: str, steps: np.ndarray, values: np.ndarray) -> Figure:
    """
    Draw the bands and the nine lines, and register one ``percentile_band`` layer.

    The bands, outermost first, and the median line are named by their gids
    in the layer's selectors, so the band a reader is in is outlined; the
    other eight lines are for the eye. Nothing here is drawn through a
    patched call, so the chart is that one layer.
    """
    fig = Figure(figsize=(_WIDTH, _HEIGHT))
    ax = fig.add_subplot()
    middle = len(BASIS_POINTS) // 2
    marks = []
    for depth in range(middle):
        lower, upper = values[:, depth], values[:, -1 - depth]
        outline = np.column_stack(
            [
                np.concatenate([steps, steps[::-1]]),
                np.concatenate([lower, upper[::-1]]),
            ]
        )
        band = Polygon(outline, closed=True, facecolor=_BAND, alpha=0.18, linewidth=0)
        ax.add_patch(band)
        marks.append(band)
    for index, name in enumerate(_NAMES):
        is_median = index == middle
        line = Line2D(
            steps,
            values[:, index],
            color=_BAND,
            linewidth=1.6 if is_median else 0.5,
            alpha=1.0 if is_median else 0.6,
            label=name,
        )
        ax.add_line(line)
        if is_median:
            marks.append(line)
    ax.autoscale_view()
    ax.set_title(title)
    ax.set_xlabel("Step")
    ax.set_ylabel(tag)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        title="Share below",
    )
    fig.tight_layout()
    for mark in marks:
        mark.set_gid(f"maidr-{uuid.uuid4()}")
    levels = [point / BASIS_POINTS[-1] for point in BASIS_POINTS]
    FigureManager.add_plot(
        PrebuiltPlot(
            ax,
            PlotType.PERCENTILE_BAND,
            labels={"x": "Step", "y": tag},
            data=[
                {
                    "x": int(step),
                    "quantiles": [
                        {"level": level, "value": float(value)}
                        for level, value in zip(levels, row)
                    ],
                }
                for step, row in zip(steps, values)
            ],
            selectors=[f"g[id='{mark.get_gid()}'] > path" for mark in marks],
        )
    )
    return fig

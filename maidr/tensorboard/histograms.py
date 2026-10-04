"""Read the histograms of a TensorBoard log directory as ridgeline charts.

TensorBoard's Histograms dashboard draws one chart per tag and run: the
distribution of a tensor, such as a layer's weights, at each logged step,
the steps offset one behind another. That is a ridgeline, and it is read as
one: each step is a group, and moving between groups holds the place on the
value axis, so a reader hears how one value's count changes over training.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Polygon

from maidr.core.figure_manager import FigureManager
from maidr.core.plot.ridgeline import RidgelinePlot
from maidr.tensorboard.events import HISTOGRAMS_PLUGIN
from maidr.tensorboard.logdir import TensorBoardChart, load, thin
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "HistogramSeries",
    "load_histograms",
    "read_tensorboard_histograms",
    "rebin",
]

#: Bins each step is drawn with: as many as TensorFlow 2 writes.
DEFAULT_BINS = 30

#: Steps drawn per chart: as many as TensorBoard's Histograms dashboard asks
#: its backend for, the first and last among them.
DEFAULT_MAX_STEPS = 51

#: How far a ridge may rise into the ones above it, in ridge spacings.
_OVERLAP = 2.5
_WIDTH = 7.0
_FILL = "#F57C00"
_EDGE = "#8A4500"


@dataclass(frozen=True, eq=False)
class HistogramSeries:
    """
    The histograms one run logged under one tag, in the order TensorBoard keeps.

    Attributes
    ----------
    steps : numpy.ndarray
        The step of each histogram, as integers.
    wall_times : numpy.ndarray
        When each was logged, in seconds since the epoch.
    buckets : list of numpy.ndarray
        Each histogram's buckets, shape ``(k, 3)``: each row a bucket's left
        edge, right edge and count, as TensorBoard reads them.
    """

    steps: np.ndarray = field(repr=False)
    wall_times: np.ndarray = field(repr=False)
    buckets: list[np.ndarray] = field(repr=False)

    def __len__(self) -> int:
        return len(self.steps)


def load_histograms(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
) -> dict[str, dict[str, HistogramSeries]]:
    """
    Read the histograms of a TensorBoard log directory.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``).
    tags : iterable of str, optional
        Only these tags, in this order. A tag that no run logged is warned
        about.
    runs : iterable of str, optional
        Only these runs. A run that is not in ``logdir`` is warned about.

    Returns
    -------
    dict of str to dict of str to HistogramSeries
        Tag by tag, sorted unless ``tags`` gives the order, and within a tag
        run by run, sorted.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    """
    logged = load(logdir, HISTOGRAMS_PLUGIN, tags=tags, runs=runs)
    return {
        tag: {
            run: HistogramSeries(
                np.asarray(steps, dtype=np.int64),
                np.asarray(wall_times, dtype=float),
                list(values),
            )
            for run, (steps, wall_times, values) in by_run.items()
        }
        for tag, by_run in logged.items()
    }


def read_tensorboard_histograms(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
    bins: int = DEFAULT_BINS,
    max_steps: int | None = DEFAULT_MAX_STEPS,
) -> list[TensorBoardChart]:
    """
    Read the histogram charts of a TensorBoard log directory, as ridgelines.

    One chart per tag and run, as TensorBoard's Histograms dashboard draws
    them: the tensor's values along the x axis, and one ridge per logged step,
    the earliest at the bottom.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``), such
        as the ``log_dir`` of Keras's ``TensorBoard`` callback with
        ``histogram_freq=1``.
    tags : iterable of str, optional
        Only these tags, in this order. By default every histogram tag, sorted.
    runs : iterable of str, optional
        Only these runs.
    bins : int, default 30
        How many equal bins every step is counted in.
    max_steps : int or None, default 51
        At most this many steps per chart, evenly spaced and always keeping
        the first and last. ``None`` keeps every step.

    Returns
    -------
    list of TensorBoardChart
        One per tag and run. Pass one to :func:`maidr.show`,
        :func:`maidr.render` or :func:`maidr.save_html`.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.
    ValueError
        If ``bins`` is below 1 or ``max_steps`` below 2.

    Notes
    -----
    Read: histograms written by ``tf.summary.histogram`` in TensorFlow 1 and
    2, Keras's ``TensorBoard`` callback with ``histogram_freq`` set, and
    PyTorch's ``SummaryWriter.add_histogram``.

    Each writer buckets the values its own way, and a step's buckets need not
    line up with the next step's: PyTorch's default writes hundreds of
    unevenly wide ones. So every step is counted again in the same ``bins``
    equal bins, spanning every value the chart's steps logged, with a
    bucket's count shared among the bins it overlaps in proportion to the
    overlap. Moving from one step to the next then lands on the same bin, and
    the counts compare.

    Up and Down move between steps, Up to a later one, holding the bin; Left
    and Right move along one step's distribution.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_tensorboard_histograms("logs/fit"):
    ...     maidr.save_html(chart, f"{chart.tag.replace('/', '_')}.html")
    """
    if bins < 1:
        raise ValueError(f"bins is a number of bins, at least 1, not {bins}")
    if max_steps is not None and max_steps < 2:
        raise ValueError(f"max_steps keeps at least 2 steps, not {max_steps}")
    histograms = load_histograms(logdir, tags=tags, runs=runs)
    if not histograms and tags is None:
        warn_at_caller(f"maidr found no histograms in {os.fspath(logdir)}.")
    charts = []
    for tag, by_run in histograms.items():
        for run, series in by_run.items():
            keep = thin(len(series), max_steps)
            steps = series.steps[keep]
            buckets = [series.buckets[i] for i in keep]
            if not any(_counted(step) for step in buckets):
                warn_at_caller(
                    f"Every histogram of '{tag}' in run '{run}' is empty; it is "
                    "left out."
                )
                continue
            edges, counts = rebin(buckets, bins)
            title = tag if run == "." else f"{tag} ({run})"
            figure = _draw(title, tag, steps, edges, counts)
            charts.append(TensorBoardChart(tag, (run,), figure))
    return charts


def rebin(buckets: list[np.ndarray], bins: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Count every histogram again in the same equal bins.

    Parameters
    ----------
    buckets : list of numpy.ndarray
        Each histogram's buckets, shape ``(k, 3)``: left edge, right edge and
        count.
    bins : int
        How many equal bins.

    Returns
    -------
    edges : numpy.ndarray
        The ``bins + 1`` bin edges, spanning every non-empty bucket; a
        bucket with an edge or count that is not finite is left out. When
        every value is one number, the bins span a unit around it.
    counts : numpy.ndarray
        Shape ``(len(buckets), bins)``: each histogram's count in each bin. A
        bucket's count is shared among the bins it overlaps in proportion to
        the overlap; a bucket of no width counts in the bin it falls in.
    """
    # A bucket with an edge or count that is not finite has no place on the
    # value axis, and one would turn every bin edge into NaN.
    filled = [
        step[(step[:, 2] > 0) & np.isfinite(step).all(axis=1)] for step in buckets
    ]
    edges_seen = np.concatenate([step[:, :2].ravel() for step in filled])
    low, high = (edges_seen.min(), edges_seen.max()) if edges_seen.size else (0, 0)
    if high <= low:
        low, high = low - 0.5, high + 0.5
    edges = np.linspace(low, high, bins + 1)
    counts = np.zeros((len(buckets), bins))
    for row, step in enumerate(filled):
        for left, right, count in step:
            if right > left:
                overlap = np.clip(
                    np.minimum(right, edges[1:]) - np.maximum(left, edges[:-1]),
                    0,
                    None,
                )
                counts[row] += count * overlap / (right - left)
            else:
                at = np.searchsorted(edges, left, side="right") - 1
                counts[row, min(max(at, 0), bins - 1)] += count
    return edges, counts


def _counted(buckets: np.ndarray) -> bool:
    return bool(buckets.size) and bool((buckets[:, 2] > 0).any())


def _draw(
    title: str,
    tag: str,
    steps: np.ndarray,
    edges: np.ndarray,
    counts: np.ndarray,
) -> Figure:
    """
    Draw one ridge per step, the earliest at the bottom, and register them.

    Each ridge is its own polygon so that the layer can name them in step
    order while a lower ridge is drawn in front of the one above it.
    """
    centers = (edges[:-1] + edges[1:]) / 2
    groups = len(steps)
    peak = counts.max() or 1.0
    # Heights are scaled by the tallest count anywhere, as TensorBoard scales
    # them, so steps compare; a ridge may rise into the ones above it. A lone
    # step has none above, so it fills most of one spacing instead.
    rise = (_OVERLAP if groups > 1 else 0.9) / peak
    fig = Figure(figsize=(_WIDTH, min(9.0, 2.6 + 0.13 * groups)))
    ax = fig.add_subplot()
    ridges = []
    for row, step_counts in enumerate(counts):
        top = row + step_counts * rise
        outline = np.column_stack(
            [
                np.concatenate([[centers[0]], centers, [centers[-1]]]),
                np.concatenate([[row], top, [row]]),
            ]
        )
        ridge = Polygon(
            outline,
            closed=True,
            facecolor=_FILL,
            edgecolor=_EDGE,
            alpha=0.75,
            linewidth=0.7,
            zorder=2 + groups - row,
        )
        ax.add_patch(ridge)
        ridges.append(ridge)
    ax.set_xlim(edges[0], edges[-1])
    ax.set_ylim(-0.2, groups - 1 + _OVERLAP + 0.2 if groups > 1 else 1.0)
    labelled = thin(groups, 8)
    ax.set_yticks(labelled, [str(steps[i]) for i in labelled])
    ax.set_title(title)
    ax.set_xlabel(tag)
    ax.set_ylabel("Step")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    FigureManager.add_plot(
        RidgelinePlot(
            ax,
            # The group's name is spoken on its own ("Step 40"), so it says
            # what it is a step of rather than being a bare number.
            groups=[f"Step {int(step)}" for step in steps],
            values=[centers] * groups,
            # A bucket shared among bins leaves fractions no count has;
            # two decimals keep them without reading out a dozen digits.
            heights=list(np.round(counts, 2)),
            ridges=ridges,
            group_label="Step",
            height_label="Count",
        )
    )
    return fig

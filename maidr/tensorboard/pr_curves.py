"""Read the precision-recall curves of a TensorBoard log directory.

TensorBoard's PR Curves dashboard draws, per tag, each run's precision against
its recall at one step, one point per decision threshold. maidr has no
precision-recall layer yet (xability/maidr#1349), so each curve is read as a
line of a line layer, recall along x, and what a PR layer would announce is
put where a reader hears it: each line is named with the curve's average
precision and the precision a classifier guessing at random would reach, the
share of positives. That chance level is drawn as a dashed line, for the eye.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from maidr.tensorboard.events import PR_CURVES_PLUGIN
from maidr.tensorboard.logdir import TensorBoardChart, load
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "PRCurveSeries",
    "average_precision",
    "load_pr_curves",
    "plot_pr_curves",
    "read_tensorboard_pr_curves",
]


@dataclass(frozen=True, eq=False)
class PRCurveSeries:
    """
    The PR curves one run logged under one tag, step by step.

    Attributes
    ----------
    steps : numpy.ndarray
        The step of each curve.
    wall_times : numpy.ndarray
        When each was logged.
    curves : list of numpy.ndarray
        Each curve, shape ``(6, thresholds)``: true positives, false
        positives, true negatives, false negatives, precision and recall at
        each threshold, the thresholds evenly spaced from 0 to 1.
    """

    steps: np.ndarray = field(repr=False)
    wall_times: np.ndarray = field(repr=False)
    curves: list[np.ndarray] = field(repr=False)

    def __len__(self) -> int:
        return len(self.steps)


@dataclass(frozen=True)
class _Curve:
    """One curve as drawn: its points from low recall up, and what it is called."""

    name: str
    recall: np.ndarray
    precision: np.ndarray
    thresholds: np.ndarray
    prevalence: float
    average_precision: float


def load_pr_curves(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
) -> dict[str, dict[str, PRCurveSeries]]:
    """
    Read the PR curve summaries of a TensorBoard log directory.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with.
    tags, runs : iterable of str, optional
        Only these tags, in this order, and only these runs.

    Returns
    -------
    dict of str to dict of str to PRCurveSeries
        Tag by tag, then run by run.
    """
    logged = load(logdir, PR_CURVES_PLUGIN, tags=tags, runs=runs)
    return {
        tag: {
            run: PRCurveSeries(
                np.asarray(steps, dtype=np.int64),
                np.asarray(wall_times, dtype=float),
                list(values),
            )
            for run, (steps, wall_times, values) in by_run.items()
        }
        for tag, by_run in logged.items()
    }


def average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    """
    The area under a PR curve, as the step-wise sum scikit-learn reports.

    Parameters
    ----------
    recall, precision : numpy.ndarray
        The curve, in any order of threshold.

    Returns
    -------
    float
        ``sum((R[i] - R[i-1]) * P[i])`` over the points in order of rising
        recall, from a recall of 0.
    """
    order = np.argsort(recall, kind="stable")
    recall, precision = np.asarray(recall)[order], np.asarray(precision)[order]
    steps = np.diff(np.concatenate([[0.0], recall]))
    return float(np.sum(steps * precision))


def read_tensorboard_pr_curves(
    logdir: str | os.PathLike,
    *,
    tags: Iterable[str] | None = None,
    runs: Iterable[str] | None = None,
    step: int | None = None,
) -> list[TensorBoardChart]:
    """
    Read the PR curve charts of a TensorBoard log directory.

    One chart per tag, as TensorBoard's PR Curves dashboard draws it: recall
    along the x axis, precision along the y axis, one line per run.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with, such as the one
        PyTorch's ``add_pr_curve`` or TensorBoard's ``pr_curve`` summary
        wrote.
    tags, runs : iterable of str, optional
        Only these tags, in this order, and only these runs.
    step : int, optional
        The step each run's curve is read at: the last one logged at or
        before it. By default each run's last.

    Returns
    -------
    list of TensorBoardChart
        One per tag.

    Notes
    -----
    Each line is named with its run, its average precision and the share of
    positives -- the precision a random guess reaches, which a useful
    classifier stays above -- such as ``good (AP 0.91, chance 0.30)``. A
    threshold at which nothing was predicted positive has no precision, and
    is left out of the line rather than read as a precision of 0.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_tensorboard_pr_curves("runs"):
    ...     maidr.show(chart)
    """
    curves = load_pr_curves(logdir, tags=tags, runs=runs)
    if not curves and tags is None:
        warn_at_caller(f"maidr found no PR curves in {os.fspath(logdir)}.")
    charts = []
    for tag, by_run in curves.items():
        drawn = []
        steps = []
        for run, series in by_run.items():
            index = _at(series.steps, step)
            if index is None:
                warn_at_caller(
                    f"'{tag}' ({run}) logged no PR curve at or before step {step}; "
                    "left out."
                )
                continue
            curve = _curve(run, series.curves[index])
            if not curve.recall.size:
                warn_at_caller(
                    f"'{tag}' ({run}) predicted nothing positive at any threshold, "
                    "so its precision is undefined throughout; left out."
                )
                continue
            steps.append(int(series.steps[index]))
            drawn.append(curve)
        if not drawn:
            continue
        at = steps[0] if len(set(steps)) == 1 else None
        title = tag if at is None else f"{tag} (step {at})"
        figure = _draw(title, drawn)
        charts.append(TensorBoardChart(tag, tuple(c.name for c in drawn), figure))
    return charts


def plot_pr_curves(
    y_true: Iterable, scores: dict[str, Iterable] | Iterable, *, title: str = ""
) -> Figure:
    """
    Draw a classifier's precision-recall curve from its labels and scores.

    Parameters
    ----------
    y_true : array_like
        Whether each sample is positive: 1 or ``True`` for the positive class.
    scores : array_like or dict of str to array_like
        The score of each sample for the positive class, such as a sigmoid
        output, or several classifiers' scores by name, a line each.
    title : str, optional
        The chart's title.

    Returns
    -------
    matplotlib.figure.Figure
        The chart, ready for :func:`maidr.show`. Not managed by pyplot.

    Raises
    ------
    ValueError
        If the labels hold no positive, or a score array differs in length or
        holds a NaN or infinite score.
    """
    truth = np.asarray(y_true).reshape(-1).astype(bool)
    if not truth.any():
        raise ValueError("A PR curve needs at least one positive sample.")
    named = scores if isinstance(scores, dict) else {"classifier": scores}
    drawn = []
    for name, values in named.items():
        values = np.asarray(values, dtype=float).reshape(-1)
        if values.shape != truth.shape:
            raise ValueError(
                f"'{name}' scores {values.size} samples and there are {truth.size}."
            )
        if not np.isfinite(values).all():
            raise ValueError(
                f"'{name}' has {int((~np.isfinite(values)).sum())} scores that are "
                "NaN or infinite; a PR curve ranks samples by a finite score."
            )
        # Ranked from the highest score, the samples predicted positive at a
        # threshold are a prefix, so running counts at the last sample of each
        # distinct score are the counts at that threshold: O(n log n) time and
        # O(n) memory, where a thresholds-by-samples matrix would be O(n^2).
        order = np.argsort(-values, kind="stable")
        ranked, hits = values[order], truth[order]
        last = np.r_[np.nonzero(np.diff(ranked))[0], ranked.size - 1]
        thresholds = ranked[last]
        tp = np.cumsum(hits)[last].astype(float)
        fp = np.cumsum(~hits)[last].astype(float)
        fn = truth.sum() - tp
        tn = (~truth).sum() - fp
        precision = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=tp + fp > 0)
        recall = tp / (tp + fn)
        drawn.append(
            _curve(
                str(name), np.vstack([tp, fp, tn, fn, precision, recall]), thresholds
            )
        )
    return _draw(title or "Precision-recall curve", drawn)


def _at(steps: np.ndarray, step: int | None) -> int | None:
    """The index of the last curve logged at or before ``step``."""
    if step is None:
        return len(steps) - 1 if len(steps) else None
    before = np.nonzero(steps <= step)[0]
    return int(before[-1]) if before.size else None


def _curve(name: str, data: np.ndarray, thresholds: np.ndarray | None = None) -> _Curve:
    """
    One curve from a ``(6, thresholds)`` tensor, as it is drawn and read.

    Parameters
    ----------
    name : str
        The run or classifier, to which the average precision and chance
        level are added.
    data : numpy.ndarray
        True and false positives, true and false negatives, precision and
        recall at each threshold.
    thresholds : numpy.ndarray, optional
        Each column's threshold; by default evenly spaced from 0 to 1, as
        TensorBoard's writers space them.

    Returns
    -------
    _Curve
        Its points from low recall up, thresholds with no positive prediction
        left out. From TensorBoard's fixed thresholds the average precision
        approximates the one computed from the raw scores.
    """
    tp, fp, tn, fn, precision, recall = np.asarray(data, dtype=float)
    if thresholds is None:
        thresholds = np.linspace(0, 1, data.shape[1])
    # tp + fn and the total are the same at every threshold, so any column
    # gives the share of positives, whichever way the thresholds run.
    total = tp[0] + fp[0] + tn[0] + fn[0]
    prevalence = float((tp[0] + fn[0]) / total) if total else 0.0
    # No positive prediction at a threshold leaves its precision undefined;
    # writers put 0 there, which would read as a cliff the classifier never had.
    defined = (tp + fp) > 0
    recall, precision, thresholds = (
        recall[defined],
        precision[defined],
        thresholds[defined],
    )
    order = np.lexsort((-precision, recall))
    recall, precision, thresholds = recall[order], precision[order], thresholds[order]
    ap = average_precision(recall, precision)
    label = f"{name} (AP {ap:.2f}, chance {prevalence:.2f})"
    return _Curve(label, recall, precision, thresholds, prevalence, ap)


def _draw(title: str, curves: list[_Curve]) -> Figure:
    fig = Figure(figsize=(6.5, 5.0))
    ax = fig.add_subplot()
    for index, curve in enumerate(curves):
        color = f"C{index % 10}"
        ax.plot(curve.recall, curve.precision, color=color, label=curve.name)
        # The chance level, for the eye; drawn as a plain line so it is no
        # series of the layer.
        ax.add_line(
            Line2D(
                [0, 1],
                [curve.prevalence] * 2,
                color=color,
                linestyle="--",
                linewidth=0.8,
                alpha=0.6,
            )
        )
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(title)
    ax.legend(loc="lower left", frameon=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    return fig

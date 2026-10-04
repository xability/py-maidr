"""What the TensorBoard readers share: a log directory and its charts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from matplotlib.figure import Figure

from maidr.tensorboard.events import find_runs, read_run
from maidr.util.caller_warning import warn_at_caller


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
        The runs drawn: for scalars, one line each (two with smoothing), in
        legend order; for histograms and graphs, the one run the chart is of.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    tag: str
    runs: tuple[str, ...]
    figure: Figure = field(repr=False)


#: One run's values of one tag: their steps, wall times and values.
Logged = tuple[list[int], list[float], list[Any]]


def load(
    logdir: str | os.PathLike,
    plugin: str,
    *,
    tags: Iterable[str] | None,
    runs: Iterable[str] | None,
) -> dict[str, dict[str, Logged]]:
    """
    Read one plugin's summaries of a log directory, tag by tag and run by run.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with.
    plugin : str
        ``"scalars"``, ``"histograms"`` or ``"graph_keras_model"``.
    tags : iterable of str or None
        Only these tags, in this order; one no run logged is warned about.
    runs : iterable of str or None
        Only these runs; one not in ``logdir`` is warned about.

    Returns
    -------
    dict
        Tag by tag, sorted unless ``tags`` gives the order, and within a tag
        run by run, sorted. A run that logged nothing under a tag is absent.

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
    found = find_runs(path)
    if runs is not None:
        wanted = list(runs)
        for run in wanted:
            if run not in found:
                warn_at_caller(
                    f"maidr found no run '{run}' in {path}; its runs are "
                    f"{names(found)}."
                )
        found = {run: found[run] for run in wanted if run in found}
    logged: dict[str, dict[str, Logged]] = {}
    for run, paths in found.items():
        read = read_run(paths, plugin)
        for tag, steps in read.steps.items():
            if read.plugins.get(tag) != plugin or not steps:
                continue
            logged.setdefault(tag, {})[run] = (
                steps,
                read.wall_times[tag],
                read.values[tag],
            )
    order = sorted(logged)
    if tags is not None:
        order = list(dict.fromkeys(tags))
        known = names(dict.fromkeys(sorted(logged)))
        for tag in order:
            if tag not in logged:
                warn_at_caller(
                    f"maidr found no {plugin} tagged '{tag}' in {path}; its tags "
                    f"are {known}."
                )
    return {tag: dict(sorted(logged[tag].items())) for tag in order if tag in logged}


def names(found: dict) -> str:
    """The keys of ``found``, quoted, for a warning; ``none`` if there are none."""
    return ", ".join(f"'{name}'" for name in found) or "none"


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

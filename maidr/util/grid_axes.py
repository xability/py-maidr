"""The tick step a grid-navigable axis is walked in."""

from __future__ import annotations

import numpy as np


def tick_step(ticks: np.ndarray | None) -> float | None:
    """
    The interval between an axis' ticks, when they are evenly spaced.

    Grid navigation walks an axis in equal increments, so an axis whose ticks
    are not evenly spaced has no step to give and the grid is declined rather
    than built on an invented one. Fewer than two ticks name no interval at
    all.

    Shared rather than reached for across classes. ``ScatterPlot`` computes it
    for both its axes and ``RugPlot`` for the one its ticks stand on, and a
    private static borrowed from the other would couple them on something that
    is not a contract -- renamed or re-meant on one side, it breaks the other
    with no import-time signal. The same argument #599 made for the hue split,
    one caller later.

    Only the step lives here. Whether the *rest* of a grid is valid stays with
    each caller, because the two do not ask the same question: a scatter needs
    both of its axes linear and declines both together, while a rug asks only
    of the axis its observations lie along. Folding those into one helper would
    change what a scatter emits for a chart with one transformed axis, which is
    not this function's business.

    Parameters
    ----------
    ticks : numpy.ndarray, optional
        The axis' major tick positions.

    Returns
    -------
    float or None
        The interval, or ``None`` when the ticks do not name one.

    Examples
    --------
    >>> tick_step(np.array([0.0, 2.0, 4.0, 6.0]))
    2.0
    >>> tick_step(np.array([0.0, 1.0, 5.0, 10.0])) is None
    True
    >>> tick_step(np.array([1.0])) is None
    True
    """
    if ticks is None or len(ticks) < 2:
        return None
    diffs = np.diff(ticks)
    if np.allclose(diffs, diffs[0]):
        return float(diffs[0])
    return None

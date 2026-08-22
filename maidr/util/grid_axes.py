"""The tick step a grid-navigable axis is walked in."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes


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


def bounds_along(ax: Axes, along_x: bool) -> tuple[float, float, float] | None:
    """
    One axis' ``(min, max, tickStep)``, when it can carry a grid.

    Read off the axes rather than off the data: the grid the frontend builds
    is of the *chart*, and a reader feeling it is feeling the plotting area
    they would see.

    For the layers whose other axis is a strip rather than a measurement --
    a rug's ticks, an event plot's rows -- so only the axis named is asked.
    ``ScatterPlot`` keeps its own rule, deliberately: it needs **both** its
    axes and declines them together, and folding that in here would change
    what it emits for a chart with one transformed axis.

    Declined on three grounds, each of which would make the cells a reader
    feels not the cells the axis draws:

    - **A non-linear scale.** Currently a guard rather than a live branch: on
      a log axis the step check below already declines every chart measured,
      by an accident of units -- ``get_xlim`` answers in **log space** while
      ``get_xticks`` answers in **data space**, so ticks at 1, 2 and 3 give a
      step of 1.0 against a span of 0.75. This is the check that states the
      intent, and it holds if that accident ever stops.
      ``tests/core/plot/test_rugplot.py`` pins the two spaces, so the
      matplotlib release that ends it turns a test red rather than leaving
      this silently dead.
    - **Ticks that are not evenly spaced**, which name no step at all.
    - **Bounds enclosing no whole cell**, which is a grid of nothing.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.
    along_x : bool
        Whether the axis wanted is the x one.

    Returns
    -------
    tuple or None
        ``(min, max, tickStep)``, or ``None`` when the axis cannot carry a
        grid -- which leaves the layer reading exactly as it did before,
        minus the braille it could not reach either way.
    """
    if ax.get_xscale() != "linear" or ax.get_yscale() != "linear":
        return None

    low, high = ax.get_xlim() if along_x else ax.get_ylim()
    step = tick_step(ax.get_xticks() if along_x else ax.get_yticks())

    if step is None or low >= high or step <= 0 or step > (high - low):
        return None
    return float(low), float(high), float(step)


def one_row_around(position: float) -> tuple[float, float, float]:
    """
    Bounds enclosing one row, for an axis that is a strip rather than a scale.

    A rug is one row deep across its ticks and an event plot's layer is one
    row deep at its own line offset, so the grid across them wants exactly one
    cell -- and which cell is the only thing that differs. A finer step buys
    rows of zeroes: measured on a rug, halving it gives
    ``[[2, 1, 0, 1], [0, 0, 0, 0]]``, a row of the surface spent saying
    nothing.

    Parameters
    ----------
    position : float
        Where on that axis the layer's entries sit.

    Returns
    -------
    tuple
        ``(min, max, tickStep)`` for a single cell centred on ``position``.

    Examples
    --------
    >>> one_row_around(0.0)
    (-0.5, 0.5, 1.0)
    >>> one_row_around(3.0)
    (2.5, 3.5, 1.0)
    """
    return (position - 0.5, position + 0.5, 1.0)

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, wrap_seaborn

# The marker seaborn leaves on the lines it draws the intervals with. The
# estimate line carries a real one -- `"o"` by default, and the empty string
# when the caller turns it off, which is why this tests for the literal rather
# than for falsiness.
_INTERVAL_MARKER = "None"

# The most vertices one interval can have: lower cap, spine and upper cap, each
# two vertices, with a NaN between them. A polyline longer than this is not an
# interval, whatever else it is.
_MAX_INTERVAL_VERTICES = 8


def point(wrapped, instance, args, kwargs) -> Axes:
    """
    Register a ``seaborn.pointplot`` call as the layer it actually drew.

    A point plot is patched by name rather than left to the ``Axes.plot``
    wrapper it goes through, because only the name says the artists mean
    something other than what they look like. Seaborn draws the intervals as
    ordinary lines, so the generic wrapper described a four-category chart as
    five series: the estimates, and then four interval polylines whose cap
    geometry reached the reader as data, NaN coordinates and raw offsets like
    ``1.95`` among the category names.

    Sorting them out needs the estimates and the intervals told apart, and the
    split is verified rather than assumed: the estimates must pair one-to-one
    with the intervals, group by group. When they do not -- because a future
    seaborn renders this differently -- the layer falls back to describing
    every drawn line, which is what the generic wrapper did, rather than
    emitting bounds read off artists that are not intervals.

    Parameters
    ----------
    wrapped : Callable
        The original ``seaborn.pointplot``.
    instance : Any
        Unused; ``pointplot`` is a module-level function.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Axes
        Whatever the wrapped function returned, unchanged.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    existing = _lines_before(kwargs)

    # Set the internal context so the `Axes.plot` calls seaborn makes inside
    # do not register a line layer of their own.
    with ContextManager.set_internal_context():
        ax = _draw_quietly(wrapped, args, kwargs)

    if not isinstance(ax, Axes):
        return ax

    drawn = [line for line in ax.lines if line not in existing]
    estimates, intervals = _split(drawn)

    if not estimates:
        # Nothing looked like an estimate line, so the split says nothing and
        # every drawn line is described -- the same fallback the verification
        # below takes, and for the same reason. Registering no layer at all
        # would leave the chart unreadable, which is a worse answer than the
        # one the generic wrapper already gave.
        if drawn:
            FigureManager.create_maidr(ax, PlotType.LINE, lines=drawn)
        return ax

    paired = _pairs_up(estimates, intervals)
    measured = any(_is_drawn(line.get_xydata()) for line in intervals)

    if paired and measured and len(estimates) == 1:
        FigureManager.create_maidr(
            ax, PlotType.ERRORBAR, estimate=estimates[0], intervals=intervals
        )
        return ax

    # Everything else is a line chart. `errorbar=None` draws no intervals to
    # carry, a chart whose every group holds one observation has none to draw,
    # and more than one estimate means a `hue` split the chart into groups
    # while the MAIDR error bar layer carries a single series -- so those
    # intervals are dropped rather than mis-assigned. All three are still a
    # repair over describing every drawn line, since the interval polylines no
    # longer travel as series of their own.
    #
    # A chart where only *some* groups have an interval takes the branch above,
    # not this one: the undrawable lines stay in the list to hold their
    # positions, and the layer omits the bound for those groups alone.
    FigureManager.create_maidr(
        ax, PlotType.LINE, lines=estimates if paired else drawn
    )

    return ax


def _lines_before(kwargs: dict) -> list[Line2D]:
    """
    Return the lines already on the axes seaborn is about to draw on.

    Anything left over from an earlier call is not this point plot's, and
    sweeping it up would hand the layer another chart's line as an estimate.

    Parameters
    ----------
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    list of Line2D
        The lines present beforehand, empty when there is no axes yet.
    """
    ax = kwargs.get("ax")
    if isinstance(ax, Axes):
        return list(ax.lines)

    # Without `ax`, seaborn draws on the current axes. Asking for it here can
    # create one, but only in the case where the call itself is about to
    # create the same one, so nothing exists afterwards that would not have.
    if plt.get_fignums():
        return list(plt.gca().lines)

    return []


def _split(lines: list[Line2D]) -> tuple[list[Line2D], list[Line2D]]:
    """
    Sort the drawn lines into estimates and intervals.

    Parameters
    ----------
    lines : list of Line2D
        The lines this call drew, in the order it drew them.

    Returns
    -------
    tuple of list
        The estimate lines and the interval lines, each in drawing order.
    """
    estimates, intervals = [], []
    for line in lines:
        vertices = line.get_xydata()
        if vertices is None or not len(vertices):
            # The proxy artists a `hue` legend is built from carry no data.
            continue
        if line.get_marker() != _INTERVAL_MARKER:
            estimates.append(line)
        else:
            # Kept whether or not it carries a bound. The list is read against
            # the estimates *by position*, so dropping the line a group with a
            # single observation leaves behind would shift every later group's
            # interval onto the wrong estimate. `_is_drawn` decides what to do
            # with it; it does not decide whether it is there.
            intervals.append(line)

    return estimates, intervals


def _is_drawn(vertices: np.ndarray) -> bool:
    """
    Check that a candidate interval is a shape the chart actually drew.

    A group with a single observation has nothing to estimate an interval
    from, and seaborn renders that as a polyline whose value coordinates are
    all NaN -- the cap positions survive, the interval does not. Such a line
    carries no bound, and treating it as one hands the reader the cap's own
    width as the interval, which is neither a measurement nor even in the
    right units.

    Answering False does not remove the line: it stays in the list to hold its
    group's position, and the layer omits that one group's bound. What this
    decides is whether the chart draws *any* interval, and so whether it is an
    error bar chart at all.

    Tested as "two vertices finite in both coordinates", which is what it
    takes to draw a segment at all, so the check needs no view on which axis
    is which.

    Parameters
    ----------
    vertices : numpy.ndarray
        The line's vertices, as an ``(n, 2)`` array.

    Returns
    -------
    bool
        True when at least one segment of the polyline was drawable.
    """
    finite = np.isfinite(np.asarray(vertices, dtype=float)).all(axis=1)
    return bool(finite.sum() >= 2)


def _pairs_up(estimates: list[Line2D], intervals: list[Line2D]) -> bool:
    """
    Check that every estimate has one interval per group, or none has any.

    This is the guard on reading another library's rendering. Seaborn emits an
    estimate line and then one short polyline per group; if some future
    version emits a shape this does not describe, the counts stop matching and
    the caller can fall back rather than pair the wrong artists up.

    Parameters
    ----------
    estimates : list of Line2D
        The lines carrying the group estimates.
    intervals : list of Line2D
        The candidate interval lines.

    Returns
    -------
    bool
        True when the intervals can be handed over as they stand.
    """
    if not intervals:
        # `errorbar=None` draws the estimates alone, which is a point plot
        # with nothing to pair.
        return True

    groups = {len(estimate.get_xydata()) for estimate in estimates}
    if len(groups) != 1:
        return False

    if len(intervals) != len(estimates) * groups.pop():
        return False

    return all(
        len(interval.get_xydata()) <= _MAX_INTERVAL_VERTICES
        for interval in intervals
    )


# Patch seaborn function.
wrap_seaborn("pointplot", point)

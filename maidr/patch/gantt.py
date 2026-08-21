from __future__ import annotations

import threading

import wrapt

from matplotlib.axes import Axes
from matplotlib.collections import Collection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.gantt import GanttPlot
from maidr.exception import UnsupportedPlotError
from maidr.patch.common import _draw_quietly


#: Held across the whole "is there a lane already, and if not make one"
#: decision. Without it two threads drawing onto the same fresh axes -- the
#: off-event-loop render #454 is about -- can both find no lane and each call
#: `create_maidr`, which is the split-into-two-charts outcome this patch
#: exists to prevent. `FigureManager._lock` cannot serve: it is a plain
#: `Lock`, so holding it across `create_maidr` (which takes it again) would
#: deadlock.
_lanes = threading.Lock()


@wrapt.patch_function_wrapper(Axes, "broken_barh")
def gantt(wrapped, instance, args, kwargs) -> Collection:
    """
    Draw a patched ``Axes.broken_barh`` and register the lane it produced.

    ``broken_barh`` is matplotlib's gantt chart, and one call draws one lane:
    the `yrange` places it and each `(start, width)` is an interval in it. So a
    chart is as many calls as it has lanes, and every one of them registers a
    layer of its own here -- which is what lets a lane be named, and what keeps
    the lanes in the order they were drawn.

    Every call's own collection is handed to the plot rather than searched for
    on the axes: a gantt chart's second lane is a `PolyCollection` beside the
    first, and "the collection on this Axes" would find the wrong one for every
    lane after the opening call.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.broken_barh``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Collection
        Whatever ``broken_barh`` returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    ax = FigureManager.get_axes(plot)
    with _lanes:
        lane = _lane_of(ax)
        if lane is not None:
            lane.add_lane(plot)
        else:
            FigureManager.create_maidr(ax, PlotType.GANTT, collections=[plot])

    return plot


def _lane_of(ax: Axes) -> GanttPlot | None:
    """
    The gantt layer already registered for an axes, when there is one.

    Looked up rather than created afresh so that the second and later calls
    become further *lanes* of one chart -- see ``GanttPlot.add_lane``. Asked of
    the figure's registered plots rather than of the axes' artists, because
    what matters is whether MAIDR already has a layer to extend, not whether
    matplotlib has more collections.

    Parameters
    ----------
    ax : Axes
        The axes the call drew on.

    Returns
    -------
    GanttPlot or None
        The layer to extend, or None when this is the chart's first lane.
    """
    figure = ax.get_figure()
    if figure is None:
        return None
    try:
        registered = FigureManager.get_maidr(figure)
    except UnsupportedPlotError:
        # Nothing registered for this figure yet, which is the ordinary first
        # call. Reached through `get_maidr` rather than by reading
        # `FigureManager.figs` directly, because `figs` documents that a
        # direct caller must hold `_lock` even to read -- since #456 a lookup
        # updates the bookkeeping behind iteration, so `get` mutates shared
        # state rather than only observing it.
        return None
    # `type(... ) is` rather than `isinstance`, because what is being looked
    # for is not "a gantt-shaped layer" but "a layer `add_lane` can actually
    # extend" -- and those are no longer the same set. `SpanPlot` subclasses
    # `GanttPlot` to reuse its schema and its lane naming, but reads its lanes
    # from the segments the patch handed it, never from `self._collections`.
    # So an `isinstance` match here let a `broken_barh` call following an
    # `hlines` on the same axes append its `PolyCollection` to a `SpanPlot`,
    # where extraction never looks: the lane was drawn, accepted without
    # error, and appeared in no announcement. Measured on
    # `hlines(...)` then `broken_barh([(0, 3)], (10, 9))`, which read three
    # lanes for the four it drew.
    #
    # Excluded here rather than refused in `SpanPlot.add_lane`, because a
    # refusal would have to raise out of the caller's own `ax.broken_barh(...)`
    # to be heard, and a plotting call that throws is worse than two layers.
    # Left out of the merge, the `broken_barh` registers its own lane and both
    # charts read -- which is what the reverse drawing order already did.
    return next(
        (
            plot
            for plot in registered.plots
            if type(plot) is GanttPlot and plot.ax is ax
        ),
        None,
    )

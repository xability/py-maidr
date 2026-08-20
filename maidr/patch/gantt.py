from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.collections import Collection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.gantt import GanttPlot
from maidr.patch.common import _draw_quietly


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
    registered = FigureManager.figs.get(figure) if figure is not None else None
    if registered is None:
        return None
    return next(
        (
            plot
            for plot in registered.plots
            if isinstance(plot, GanttPlot) and plot.ax is ax
        ),
        None,
    )

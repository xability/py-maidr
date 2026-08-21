from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.spanplot import (
    DRAWN_SPANS,
    SPANS_ALONG_X,
    draws_a_schedule,
)
from maidr.patch.common import _draw_quietly


def _spans(wrapped, instance, args, kwargs, along_x: bool) -> LineCollection:
    """
    Draw a patched ``hlines`` or ``vlines`` and register the schedule it drew.

    Both draw one segment per row of the data, and both hand back a single
    ``LineCollection`` carrying every end exactly. That is a gantt -- an
    interval per lane -- and it registered nothing at all, so a figure made
    of them fell back to a picture whose numbers were in the call (#568).

    The reading is declined for the shapes that are not schedules, and the
    decision is made **here**, before anything is registered: a layer that
    refuses at extraction takes the whole figure with it, which is the defect
    #564 was about. A `vlines` drawing a lollipop's stems therefore registers
    nothing at all, exactly as it did before this reading existed, and the
    figure keeps whatever the rest of it says.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.hlines`` or ``Axes.vlines``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.
    along_x : bool
        True for ``hlines``, whose intervals run along x.

    Returns
    -------
    LineCollection
        Whatever the wrapped function returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    if not isinstance(drawn, LineCollection):
        return drawn

    if not draws_a_schedule(drawn, along_x):
        return drawn

    ax = FigureManager.get_axes(drawn)
    FigureManager.create_maidr(
        ax,
        PlotType.GANTT,
        **{DRAWN_SPANS: drawn, SPANS_ALONG_X: along_x},
    )
    return drawn


@wrapt.patch_function_wrapper(Axes, "hlines")
def hlines(wrapped, instance, args, kwargs) -> LineCollection:
    """Register an ``Axes.hlines`` call as a MAIDR gantt layer."""
    return _spans(wrapped, instance, args, kwargs, along_x=True)


@wrapt.patch_function_wrapper(Axes, "vlines")
def vlines(wrapped, instance, args, kwargs) -> LineCollection:
    """
    Register an ``Axes.vlines`` call as a MAIDR gantt layer.

    The same chart with the axes exchanged: the lanes run along x and the
    intervals down y. `GanttTrace` navigates lanes and intervals rather than
    x and y, so the two need no orientation to tell them apart -- only which
    axis the lanes were laid out on, which is what `SpanPlot` is told.
    """
    return _spans(wrapped, instance, args, kwargs, along_x=False)

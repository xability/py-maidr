from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.contour import ContourSet

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.contour import tag
from maidr.patch.common import _draw_quietly


def contour(wrapped, instance, args, kwargs) -> ContourSet:
    """
    Draw a patched contour call and register the field it produced.

    A contour is the one chart of its family whose value is a number rather
    than a colour: ``ContourSet.levels`` is the data, and ``get_paths()``
    gives one path per level. Nothing is inverted from a fill.

    Shared by ``Axes.contour`` and ``Axes.tricontour`` rather than copied,
    because the two differ only in where the field was sampled.
    ``tricontour`` contours values given at **scattered** points by
    triangulating them first, and hands back a ``TriContourSet`` -- measured,
    a ``ContourSet`` subclass, unfilled, one path per level, which the reader
    already read unchanged before this patched anything (#546).

    ``ax.contourf`` and ``ax.tricontourf`` are different calls and are
    deliberately not patched. They draw the bands *between* levels, so an
    outline of one runs along two different level curves and there is one
    fewer of them than there are levels; announcing one as a level's curve
    would be right for half of its points.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.contour`` or ``Axes.tricontour``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    ContourSet
        Whatever ``contour`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    # A set whose every level is out of range draws nothing. Registering it
    # would put an empty layer in the schema -- the phantom-layer shape of
    # #421 -- so the emptiness is asked of the drawing rather than assumed.
    if not any(len(path.vertices) for path in plot.get_paths()):
        return plot

    tag(plot)
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.CONTOUR, contour_set=plot)

    return plot


wrapt.wrap_function_wrapper(Axes, "contour", contour)

# The scattered-sample spelling of the same chart. Wrapped separately because
# `tricontour` is its own method rather than a branch inside `contour`, which
# is the whole of why it read as nothing (#546).
wrapt.wrap_function_wrapper(Axes, "tricontour", contour)

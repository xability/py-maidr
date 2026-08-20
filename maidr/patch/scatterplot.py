from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.scatterplot import DRAWN_POINTS, HUE_GROUP, hue_groups
from maidr.patch.common import _draw_quietly, wrap_seaborn


def _points_of(plot, ax: Axes | None) -> PathCollection | None:
    """
    The collection a call drew, if it can be had.

    Parameters
    ----------
    plot : Any
        Whatever the patched function returned. ``Axes.scatter`` returns the
        collection; ``seaborn.scatterplot`` returns the axes.
    ax : Axes or None
        The axes drawn on.

    Returns
    -------
    PathCollection or None
        The collection, or ``None`` when neither the return value nor the
        axes offers one.
    """
    if isinstance(plot, PathCollection):
        return plot
    collections = [
        artist
        for artist in (getattr(ax, "collections", ()) or ())
        if isinstance(artist, PathCollection)
    ]
    return collections[0] if collections else None


def scatter(wrapped, instance, args, kwargs) -> Axes | PathCollection:
    """
    Patch for ``Axes.scatter`` and ``seaborn.scatterplot``.

    Registers one layer per hue group when the call drew a grouped scatter,
    and one layer for the whole collection when it did not.

    The split has to happen here rather than inside the layer because a layer
    *is* one entry in the schema: seaborn draws every hue group as a single
    ``PathCollection`` with a colour per point, so one call produces one
    artist and has to produce several layers from it. That is the shape the
    plotly binding already has -- there each group arrives as its own trace --
    and the shape ``jointplot(hue=)``'s own marginals already emit, one
    ``smooth`` per level. A joint panel whose scatter was one layer and whose
    marginals were two was the inconsistency (#544).

    See :func:`maidr.core.plot.scatterplot.hue_groups` for every reason a
    grouped-looking chart is read as one layer anyway.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Hand the layer the collection this call drew. `ScatterPlot` otherwise
    # takes the *first* `PathCollection` on the axes, which is right only
    # while a layer is one collection -- and seaborn's categorical scatters
    # are one per category. Measured on a three-category `stripplot`: three
    # layers registered, all three holding category "a", and 60 of the 90
    # drawn points absent from the schema entirely (#426). Two plain
    # `ax.scatter()` calls fail the same way.
    #
    # `seaborn.scatterplot` is wrapped through this same function and returns
    # an `Axes` rather than the collection, so `_points_of` falls back to the
    # sweep -- which is correct for it, since it draws every point as a
    # single collection even under `hue`.
    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    ax = FigureManager.get_axes(plot)
    kwargs.pop("ax", None)
    points = _points_of(plot, ax)

    groups = hue_groups(ax, points) if points is not None else None
    if groups is None:
        FigureManager.create_maidr(
            ax, PlotType.SCATTER, **dict(kwargs, **{DRAWN_POINTS: plot})
        )
        return plot

    for group in groups:
        FigureManager.create_maidr(
            ax,
            PlotType.SCATTER,
            **dict(kwargs, **{DRAWN_POINTS: points, HUE_GROUP: group}),
        )

    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "scatter", scatter)

# Patch seaborn function.
wrap_seaborn("scatterplot", scatter)

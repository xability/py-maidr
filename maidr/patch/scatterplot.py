from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.scatterplot import DRAWN_POINTS, HUE_GROUP, hue_groups
from maidr.patch.common import drew_nothing, prospective_axes
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

    # How many collections the target axes held before the call, so a call
    # that adds none can be told from one that adds a collection of no
    # points. `seaborn.scatterplot` returns the *axes*, so its return value
    # says nothing about what it drew, and an empty call went on to sweep the
    # axes and find an earlier call's points -- announcing the same points
    # twice, under two layers, with nothing to say they were the same (#623).
    #
    # Guessed axes are not trusted: the count is used only when the axes
    # counted is the one the call came back with, which is exact. Anything
    # else declines to decide and registers as before.
    #
    # Which means it is only ever read for the seaborn binding, whose return
    # value is the axes. `Axes.scatter` hands its collection back and its
    # `instance` is the axes, so a count taken there could never be used --
    # and asking pyplot for a current axes to take it had one effect only:
    # `plt.gca()` on a pyplot figure with no axes creates one, so an
    # object-oriented `ax.scatter()` put an empty panel on whatever unrelated
    # pyplot figure happened to be current (#755).
    counted = None if isinstance(instance, Axes) else prospective_axes(kwargs)
    before = len(counted.collections) if counted is not None else None

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

    # A call that drew no points registers nothing -- as an empty artist for
    # the `ax.scatter` spelling, and as an unchanged collection count for the
    # seaborn one (#623).
    if drew_nothing(plot):
        return plot
    if (
        before is not None
        and counted is plot
        and len(plot.collections) == before
    ):
        return plot

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
            # One membership list, for the one collection this call drew.
            # `hue_groups` answers in the offsets of the collection it was
            # asked about; the layer takes a list of those, one per
            # collection, because a strip plot's groups span several (#586).
            **dict(kwargs, **{DRAWN_POINTS: points, HUE_GROUP: (group[0], [group[1]])}),
        )

    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "scatter", scatter)

# Patch seaborn function.
wrap_seaborn("scatterplot", scatter)

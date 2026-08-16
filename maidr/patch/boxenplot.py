from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.boxenplot import DRAWN_LADDERS
from maidr.patch.common import _draw_quietly, wrap_seaborn


def boxen(wrapped, instance, args, kwargs) -> Axes:
    """
    Register ``seaborn.boxenplot`` as one letter-value layer per axes.

    The internal context is what makes this a fix rather than an addition.
    A boxen plot is not drawn by a renderer of its own: seaborn builds each
    ladder from patches, draws the median with ``Axes.plot`` and the fliers
    with ``Axes.scatter``, both of which MAIDR already patches. Left alone,
    those two produce the reading :class:`~maidr.core.plot.boxenplot.BoxenPlot`
    exists to replace -- a line layer of medians, each announced as a
    two-sample series, and a scatter layer per category holding only the
    outliers, positioned at numeric slots rather than at the category labels.
    Suppressing them here is therefore not tidying: it removes a chart that
    claimed to be complete and was describing the scaffolding (#253).

    Written out rather than routed through :func:`maidr.patch.common.common`,
    which every other seaborn categorical patch uses. ``common`` draws inside
    the internal context and registers in one step, and this layer needs to
    know which collections were on the axes *before* the call -- see below for
    why. There is no hook for that between the two halves, and widening
    ``common`` for one caller would put a before/after snapshot in the path of
    every patch that does not need one.

    Parameters
    ----------
    wrapped : Callable
        ``seaborn.boxenplot``.
    instance : Any
        Unused; seaborn's plotting functions are module level.
    args, kwargs
        The caller's arguments, passed through untouched.

    Returns
    -------
    Axes
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Which collections were already on the axes, so the layer can describe
    # only the ones this call adds.
    #
    # Sweeping instead, and pairing each ladder with whatever collection
    # follows it, is right until something else draws on the same axes -- and
    # a strip plot over a boxen is a standard idiom, since the ladder
    # summarises the distribution the points make up. `showfliers=False` is
    # what breaks the pairing: seaborn then adds no flier collection at all,
    # so the run stops alternating and the last ladder takes the *strip plot's*
    # first cloud as its own. Measured on three categories with an overlay::
    #
    #     collections: Patch Patch Patch Path Path Path
    #     z=a low=0 up=0    z=b low=0 up=0    z=c low=7 up=7
    #
    # Fourteen outliers announced on a chart whose author asked for none, with
    # the values taken from a different layer (#253).
    #
    # Identity rather than a count, so it holds however the list is reordered,
    # and `plt.gca()` because that is the axes seaborn itself falls back to
    # when none is passed.
    #
    # `id()` is sound here because every collection counted stays referenced
    # by `ax.collections` for the whole window, so none can be freed and have
    # its address reused by one of the collections seaborn is about to add.
    target = kwargs.get("ax")
    if target is None:
        target = plt.gca()
    before = {id(collection) for collection in target.collections}

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    # Registered unconditionally, as the other seaborn categorical patches
    # do. `create_maidr` raises `ValueError("No plot found.")` on a `None`
    # axes, and an unresolvable axes is a genuine extraction failure -- worth
    # saying out loud rather than turning into a chart that quietly has no
    # boxen layer in it.
    ax = FigureManager.get_axes(plot)
    drawn = (
        [collection for collection in ax.collections if id(collection) not in before]
        if ax is not None
        else []
    )
    FigureManager.create_maidr(ax, PlotType.BOXEN, **{DRAWN_LADDERS: drawn})

    return plot


wrap_seaborn("boxenplot", boxen)

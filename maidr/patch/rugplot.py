from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.rugplot import (
    DRAWN_RUG,
    RUG_AXIS_LABEL,
    RUG_LABEL,
    read_rug,
)
from maidr.patch.common import _draw_quietly, prospective_axes, wrap_seaborn


def _collections_of(ax: Axes | None) -> list:
    """
    The collections already on an axes.

    Held as the artists themselves rather than as their ids, for the reason
    ``maidr/patch/histogram.py``'s ``_containers_of`` gives: an id compared
    after the object it named was freed can be matched by an unrelated artist
    allocated at the same address.

    Parameters
    ----------
    ax : Axes, optional
        The axes about to be drawn on, when it could be resolved.

    Returns
    -------
    list
        The collections present before the call.
    """
    return list(ax.collections) if ax is not None else []


def _drawn_by_this_call(ax: Axes | None, before: list) -> list:
    """
    The collections this call added, in the order it added them.

    Parameters
    ----------
    ax : Axes, optional
        The axes drawn on.
    before : list
        What ``_collections_of`` saw beforehand.

    Returns
    -------
    list
        The new collections.
    """
    if ax is None:
        return []
    seen = [id(collection) for collection in before]
    return [
        collection
        for collection in ax.collections
        if id(collection) not in seen
    ]


def _name_for(ax: Axes, along_x: bool) -> str:
    """
    What to announce the rug layer as.

    A rug is routinely drawn beside something else, and one call can draw two
    -- ``rugplot(x=..., y=...)`` marks both margins. So the layers need
    telling apart, which is what ``MaidrLayer.name`` is for
    (xability/maidr#828).

    Taken from the label on the axis the observations lie along, because
    seaborn sets it to the column being marked and that is the name a reader
    would use for them. Falls back to :data:`RUG_AXIS_LABEL` for a rug drawn
    from bare arrays, where the chart never learned a name.

    That holds when the rug's own call set the label, which is the ordinary
    case. It does not when something *else* labelled the axis first and the
    rug marks values of its own: measured, a `scatterplot(x="value")`
    followed by `rugplot(x=[7.0, 8.0])` names the rug "value", after the
    column the scatter drew rather than anything the rug marks. Accepted
    rather than worked around -- the artist carries no record of the column
    it came from, so the alternative is to name nothing at all, and a name
    off the shared axis is still the axis these ticks stand on. The layer's
    *data* is unaffected either way; only what it is announced as.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.
    along_x : bool
        Whether the observations lie along x.

    Returns
    -------
    str
        The layer's name.
    """
    named = ax.get_xlabel() if along_x else ax.get_ylabel()
    return named or RUG_AXIS_LABEL


def rug(wrapped, instance, args, kwargs) -> Axes:
    """
    Draw a patched ``seaborn.rugplot`` and register the margins it marked.

    A rug draws one short tick per observation against the frame. It drew a
    plain ``LineCollection`` that nothing read, so a figure whose only layer
    was a rug fell back to a picture, and a rug beside a density curve left
    the raw observations -- the one thing the curve does not state -- unread
    (#250).

    One layer per collection, not one per call: ``rugplot(x=..., y=...)``
    marks two margins and hands back one collection for each, and merging
    them would announce a single series whose positions come off two
    different axes.

    The collections are found by taking a before-and-after snapshot of the
    axes rather than by sweeping it afterwards, which is the distinction
    #426 was about -- a rug drawn over a scatter would otherwise read the
    scatter's collection as its own.

    Parameters
    ----------
    wrapped : Callable
        ``seaborn.rugplot``.
    instance : Any
        Unused; seaborn's rugplot is a module-level function.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Axes
        Whatever ``rugplot`` returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    ax = prospective_axes(kwargs)
    before = _collections_of(ax)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    if ax is None:
        ax = drawn if isinstance(drawn, Axes) else None
    if ax is None:
        return drawn

    for collection in _drawn_by_this_call(ax, before):
        if not isinstance(collection, LineCollection):
            continue
        read = read_rug(collection)
        if read is None:
            # Not a set of ticks held constant on one axis, so it marks no
            # single set of positions. Declined here, before anything is
            # registered, rather than raised at extraction -- a layer that
            # refuses while the schema is built takes the whole figure with
            # it, which is the defect #564 was about.
            continue
        FigureManager.create_maidr(
            ax,
            PlotType.SCATTER,
            **{
                DRAWN_RUG: collection,
                RUG_LABEL: _name_for(ax, read[1]),
            },
        )

    return drawn


wrap_seaborn("rugplot", rug)

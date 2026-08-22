from __future__ import annotations

import contextvars

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.rugplot import (
    DRAWN_RUG,
    RUG_AXIS_LABEL,
    RUG_GROUP,
    RUG_LABEL,
    read_rug,
)
from maidr.core.plot.scatterplot import _rgba
from maidr.patch.common import _draw_quietly, prospective_axes, wrap_seaborn
from maidr.util.legend_names import legend_of, names_for


#: What kind of hue mapping the rug being drawn was given, recorded by
#: :func:`_note_hue_map` while seaborn draws and read once the draw is done.
#:
#: A ``ContextVar`` rather than a module attribute, matching
#: ``ContextManager``: the patched method is class-wide, so every draw in the
#: process writes here, and ``asyncio.to_thread`` runs a render in a copy of
#: the context so concurrent draws keep their own view.
_HUE_MAP_TYPE: contextvars.ContextVar = contextvars.ContextVar(
    "maidr_rug_hue_map_type", default=None
)


def _note_hue_map(wrapped, instance, args, kwargs):
    """
    Record what kind of hue the rug about to be drawn was given.

    ``seaborn.rugplot`` does not pass its hue mapping to anything the
    function-level patch can see, and the drawn colours cannot answer on
    their own: a **numeric** hue is a colour *scale*, and on a small frame
    seaborn's legend samples every value, so every tick matches a swatch and
    the rug would split into one layer per observation -- which is not a
    reading of a scale. Measured on four observations with ``hue=`` a numeric
    column: four legend entries, four groups of one.

    The plotter knows outright. Wrapped only to record it; the drawing is
    left alone, and the registration is still made by :func:`rug` after the
    call returns.

    Parameters
    ----------
    wrapped : Callable
        ``_DistributionPlotter.plot_rug``.
    instance : Any
        The plotter, for its hue mapping.
    args : tuple
        Positional arguments seaborn passed.
    kwargs : dict
        Keyword arguments seaborn passed.

    Returns
    -------
    Any
        Whatever the wrapped method returned.
    """
    hue_map = getattr(instance, "_hue_map", None)
    _HUE_MAP_TYPE.set(getattr(hue_map, "map_type", None))
    return wrapped(*args, **kwargs)


def _hue_groups(ax: Axes, collection: LineCollection, ticks: int) -> list | None:
    """
    The hue groups a rug was drawn with, or ``None`` when it has none.

    ``seaborn`` draws a hue-grouped rug as **one** ``LineCollection`` carrying
    a colour per tick, not one collection per group, so the grouping survives
    only in those colours and in the legend that names them -- the shape
    ``scatterplot.hue_groups`` reads point by point, one artist type over.
    Measured on twelve observations over two levels::

        rugplot(x="v")            colour rows=1,  unique=1, legend None
        rugplot(x="v", hue="g")   colour rows=12, unique=2, legend ['p', 'q']

    Every reason to decline has a chart behind it:

    - **One colour for the whole rug.** ``get_colors()`` returns a single row
      when every tick shares a colour, which is what an ungrouped rug gives.
      A count that does not match the ticks is the same answer: nothing here
      can say which tick wore which colour.
    - **A tick no swatch names.** ``legend=False`` suppresses the legend, and
      the colours alone name nothing -- groups called "1" and "2" are not an
      improvement on one strip.
    - **Fewer than two groups.** Nothing to tell apart.
    - **A hue that is not a grouping.** A numeric ``hue=`` is a colour
      *scale*; see :func:`_note_hue_map` for why the colours cannot say so
      themselves and the plotter is asked instead.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    collection : LineCollection
        The ticks.
    ticks : int
        How many ticks ``read_rug`` found, so the colours can be checked
        against them rather than assumed to correspond.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        segments that belong to it, or ``None`` for a rug that is not
        grouped.
    """
    if _HUE_MAP_TYPE.get() != "categorical":
        return None

    colours = [_rgba(row) for row in np.asarray(collection.get_colors())]
    if len(colours) != ticks or ticks < 2:
        return None

    names = names_for(ax, colours)
    if any(name is None for name in names):
        return None

    members: dict = {}
    for index, name in enumerate(names):
        members.setdefault(name, []).append(index)
    if len(members) < 2:
        return None

    # Legend order, which is the order #502 settled a grouped layer's layers
    # on -- seaborn's draw order is not it.
    legend = legend_of(ax)
    order = [text.get_text() for text in legend.get_texts()] if legend else []
    return sorted(
        members.items(),
        key=lambda group: order.index(group[0]) if group[0] in order else len(order),
    )


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

    # Cleared before the draw and restored after it, so a rug drawn without a
    # hue is never read against the mapping of one drawn earlier.
    token = _HUE_MAP_TYPE.set(None)
    try:
        with ContextManager.set_internal_context():
            drawn = _draw_quietly(wrapped, args, kwargs)
        return _register(ax, drawn, before)
    finally:
        _HUE_MAP_TYPE.reset(token)


def _register(ax: Axes | None, drawn, before: list):
    """
    Register a layer for each rug the call drew, split by hue where it has one.

    Split out of :func:`rug` so the hue mapping it reads is reset on every
    path out, including the early returns below.

    Parameters
    ----------
    ax : Axes, optional
        The axes resolved before the draw, when there was one.
    drawn : Any
        Whatever ``seaborn.rugplot`` returned.
    before : list
        The collections the axes held beforehand.

    Returns
    -------
    Any
        ``drawn``, unchanged.
    """

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
        shared = {DRAWN_RUG: collection, RUG_LABEL: _name_for(ax, read[1])}
        groups = _hue_groups(ax, collection, len(read[0]))
        if groups is None:
            FigureManager.create_maidr(ax, PlotType.SCATTER, **shared)
            continue

        # One layer per level, each reading its own ticks. Split here rather
        # than in the layer because a layer *is* one entry in the schema, and
        # this is one artist -- the same reason `scatterplot.scatter` splits
        # a hue-grouped scatter in its patch (#544, #597).
        for group in groups:
            FigureManager.create_maidr(
                ax, PlotType.SCATTER, **dict(shared, **{RUG_GROUP: group})
            )

    return drawn


wrap_seaborn("rugplot", rug)

# And the plotter method beneath it, read for the one thing the drawn
# colours cannot say; see `_note_hue_map`. Wrapped by module path rather than
# by importing the private class, matching how `maidr/patch/boxplot.py`
# reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.distributions",
    "_DistributionPlotter.plot_rug",
    _note_hue_map,
)

"""Read the hue a categorical scatter was grouped by."""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.scatterplot import (
    DRAWN_POINTS,
    GROUP_LABEL,
    HUE_GROUP,
    _rgba,
)
from maidr.patch.common import _draw_quietly, plotter_axes


def _point_colours(collection: PathCollection) -> list:
    """
    One colour per point.

    ``get_facecolor`` answers a row per point on every collection seaborn
    colours by hue -- it assigns them in one ``set_facecolors`` call over the
    panel's rows -- and no rows at all on the empty collections a faceted grid
    leaves where a panel holds none of a category. Measured across strip,
    swarm, dodged, faceted, translucent and unfilled-marker charts: the two
    counts agree every time.

    The mismatch below is therefore not a live path but where this stops if
    that ever changes. Zipping a shorter list over the points would name each
    point after whichever colour fell opposite it, which is a grouping made
    up rather than read; answering ``None`` per point makes the caller decline
    the panel instead.
    ``test_seaborn_gives_every_point_its_own_colour`` pins the agreement, so
    the seaborn release that ends it turns a test red rather than this branch
    silently load-bearing.

    Parameters
    ----------
    collection : PathCollection
        The points.

    Returns
    -------
    list
        One rounded RGBA per drawn point, ``None`` where a row names no
        colour or where the rows do not correspond to the points at all.
    """
    rows = np.asarray(collection.get_facecolor())
    count = len(np.asarray(collection.get_offsets()))
    if len(rows) != count:
        return [None] * count
    return [_rgba(row) for row in rows]


def _hue_colours(plotter: Any) -> dict | None:
    """
    Each hue level's name against the colour seaborn drew it in.

    Read off the plotter's own ``_hue_map`` rather than off the legend, and
    that is the point of doing this here at all. The legend is the only
    source the ``Axes.scatter`` patch has, and for these charts it has two
    problems: a faceted ``catplot`` has no per-panel legend -- the grid's is
    built afterwards, at the figure -- and a panel holding only one of the
    levels could not be named from a legend anyway, since one colour matched
    against a swatch is a guess. The plotter knows the mapping outright.

    Keyed by the three colour channels, not by four. ``alpha=`` scales the
    drawn points' opacity and leaves the mapping's alone -- measured,
    ``stripplot(hue=..., alpha=.4)`` draws ``(0.12, 0.47, 0.71, 0.4)`` against
    a lookup entry of ``(0.12, 0.47, 0.71, 1.0)`` -- and what identifies a
    level is its hue rather than how transparently it was drawn. Two levels
    that differ *only* in opacity would collide, so that is the one case this
    declines on.

    Declined too when the mapping is numeric. Seaborn builds a lookup entry
    per distinct value there, so a continuous ``hue=`` on eighteen rows offers
    eighteen "levels" -- a colour *scale*, not a grouping, and one layer per
    point is not a reading of it. ``hue_groups`` declines the same chart for
    the same reason, one step further down.

    Parameters
    ----------
    plotter : Any
        The seaborn plotter the wrapped method is bound to.

    Returns
    -------
    dict or None
        RGB to level name, or ``None`` for a chart with no hue grouping to
        read.
    """
    hue_map = getattr(plotter, "_hue_map", None)
    if getattr(hue_map, "map_type", None) != "categorical":
        return None

    lookup = getattr(hue_map, "lookup_table", None) or {}
    if len(lookup) < 2:
        return None

    named: dict = {}
    for level, colour in lookup.items():
        rgba = _rgba(colour)
        if rgba is None:
            return None
        named[rgba[:3]] = str(level)
    return named if len(named) == len(lookup) else None


def _hue_levels(
    plotter: Any, drawn: list
) -> list[tuple[str, list[list[int]]]] | None:
    """
    One ``(name, members)`` group per hue level present among these points.

    ``members`` holds a list of offsets per collection, positionally paired
    with ``drawn``, which is the shape :data:`HUE_GROUP` takes: seaborn draws
    a categorical scatter as one collection per category, so a level spans
    every collection that holds a point of it.

    A level the panel does not hold is absent rather than empty -- a faceted
    ``catplot`` puts each level in whichever panels its rows fall in -- and a
    panel holding one level still gets that level named, because knowing
    which one it is is the whole of what was missing.

    Returns ``None`` the moment a point cannot be placed, which leaves the
    caller reading the chart the way it read it before there was a hue to
    find. A point no level claims means the colours are not the grouping, and
    a partly-named chart is worse than an unnamed one.

    Parameters
    ----------
    plotter : Any
        The seaborn plotter the wrapped method is bound to.
    drawn : list of PathCollection
        The collections this call added to one panel, in drawing order.

    Returns
    -------
    list of (str, list of list of int) or None
        The groups in the plotter's own level order, or ``None``.
    """
    named = _hue_colours(plotter)
    if named is None:
        return None

    members: Dict[str, list] = {}
    for part, collection in enumerate(drawn):
        for index, colour in enumerate(_point_colours(collection)):
            if colour is None:
                return None
            name = named.get(colour[:3])
            if name is None:
                return None
            members.setdefault(name, [[] for _ in drawn])[part].append(index)

    if not members:
        return None

    # The plotter's level order, which is the order seaborn's own legend is
    # written in and the order #502 settled a grouped layer's layers on.
    order = [str(level) for level in getattr(plotter._hue_map, "levels", None) or []]
    return sorted(
        members.items(),
        key=lambda group: order.index(group[0]) if group[0] in order else len(order),
    )


def _added(ax: Axes, before: set) -> list:
    """
    The collections this call put on one panel, in drawing order.

    Parameters
    ----------
    ax : Axes
        One panel.
    before : set
        ``id`` of every collection the panel already held.

    Returns
    -------
    list of PathCollection
        Possibly empty, which makes the caller skip the panel.
    """
    return [
        artist
        for artist in ax.collections
        if isinstance(artist, PathCollection) and id(artist) not in before
    ]


def sns_categorical_points(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Any:
    """
    Register the strip and swarm panels seaborn draws, hue and all.

    One registrar for both, and for ``sns.catplot`` with them: ``catplot``
    drives ``_CategoricalPlotter`` directly and imports neither public
    function, so a patch on the functions reaches two of the three ways in
    and a patch here reaches all of them -- the same reason
    ``maidr/patch/barplot.py`` wraps ``plot_bars``.

    The reading has to happen *after* the method rather than under it, and
    that is the defect this fixes (#586). ``plot_strips`` colours its points
    by hue and builds its legend as its last two acts::

        points = ax.scatter(...)
        if "hue" in self.variables:
            points.set_facecolors(self._hue_map(sub_data["hue"]))
        ...
        self._configure_legend(...)

    so the ``Axes.scatter`` patch, which registered these charts until now,
    was asked for the grouping before either existed -- measured, one uniform
    colour and no legend at every one of the three calls. It declined both
    times and the chart came out with its hue dropped: identical, point for
    point, to the same call without one.

    Drawing inside the internal context is what moves the decision here. The
    ``Axes.scatter`` calls made under it draw and register nothing, and every
    panel is registered below instead.

    The layers a panel gets:

    - **A hue level each**, spanning the categories, named by the level and
      carrying the hue variable on ``z``. That is the decomposition
      ``seaborn.scatterplot(hue=...)`` already emits for the same frame
      (#544), and a dodged bar's before it.
    - **A collection each, unnamed**, for a chart with no hue to read --
      which is one layer per category, exactly what #426 settled these charts
      on and what ``tests/core/plot/test_scatter_own_collection.py`` pins.

    Parameters
    ----------
    wrapped : Callable
        ``_CategoricalPlotter.plot_strips`` or ``.plot_swarms``.
    instance : Any
        The plotter, for its axes and its hue mapping.
    args : tuple
        Positional arguments seaborn passed.
    kwargs : dict
        Keyword arguments seaborn passed.

    Returns
    -------
    Any
        Whatever the wrapped method returned.

    Examples
    --------
    >>> # Two named layers, nine points each, categories on `xLabel`.
    >>> sns.stripplot(data=df, x="cat", y="val", hue="hue")

    >>> # Three unnamed layers, one per category, as before.
    >>> sns.swarmplot(data=df, x="cat", y="val")
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Asked once. The panels a plotter draws into are fixed before it draws
    # -- `plotter.ax` for one axes, the grid's for a faceted call -- so the
    # snapshot and the reading below are of the same list.
    panels = plotter_axes(instance)
    before = {id(artist) for ax in panels for artist in ax.collections}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax in panels:
        added = _added(ax, before)
        if not added:
            continue

        levels = _hue_levels(instance, added)
        if levels is None:
            for collection in added:
                FigureManager.create_maidr(
                    ax, PlotType.SCATTER, **{DRAWN_POINTS: collection}
                )
            continue

        # The plotter's own record of which column the hue came from. A
        # `catplot` panel has no legend to read the variable's name off --
        # the grid builds one at the figure, afterwards -- and neither has a
        # chart drawn `legend=False`.
        label = (getattr(instance, "variables", None) or {}).get("hue")

        for name, members in levels:
            FigureManager.create_maidr(
                ax,
                PlotType.SCATTER,
                **{
                    DRAWN_POINTS: added,
                    HUE_GROUP: (name, members),
                    GROUP_LABEL: label,
                },
            )

    return drawn


# The plotter methods `seaborn.stripplot`, `seaborn.swarmplot` and
# `sns.catplot(kind="strip"/"swarm")` all drive. Wrapped by module path rather
# than by importing the private class, matching how `maidr/patch/barplot.py`
# reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_strips",
    sns_categorical_points,
)
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_swarms",
    sns_categorical_points,
)

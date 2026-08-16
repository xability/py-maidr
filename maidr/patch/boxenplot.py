from __future__ import annotations

from typing import Any, Callable

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.boxenplot import DRAWN_LADDERS
from maidr.patch.common import _draw_quietly, plotter_axes, wrap_seaborn


def boxen(
    wrapped: Callable, instance: Any, args: tuple, kwargs: dict
) -> Axes:
    """
    Draw ``seaborn.boxenplot`` quietly and leave the reading to the plotter.

    Registration used to happen here and no longer does. ``sns.catplot(
    kind="boxen")`` reaches this function not at all -- it drives
    ``_CategoricalPlotter`` directly and imports nothing -- so its panel was
    seen only by the matplotlib-level patches, and what came out was the
    reading :class:`~maidr.core.plot.boxenplot.BoxenPlot` was written to
    replace (#448)::

        sns.catplot(df, x="g", y="v", kind="boxen")   line(2), point(16), point(16)
        sns.boxenplot(df, x="g", y="v", ax=ax)        boxen(2)

    The line layer is the median segments, so the chart announces itself as a
    line chart and says each median twice; the point layers are the outliers
    alone, at numeric slots rather than at the category names. Every rung of
    every ladder absent, and nothing saying so.

    :func:`sns_categorical_boxens` wraps the method that draws, which both
    interfaces reach, and registers there instead. What remains here is
    ``_draw_quietly`` over the whole seaborn call and the ``wrap_seaborn``
    that keeps both bindings of the name wrapped.

    Nothing here sets the internal context, and that is deliberate: the
    context is what makes a patch decline, so setting it here would silence
    the plotter patch below. What it used to suppress -- the median drawn
    through ``Axes.plot`` and the fliers through ``Axes.scatter``, both of
    which MAIDR patches -- is drawn *inside* ``plot_boxens``, so it is inside
    the context that patch sets. The colour probe seaborn runs before it draws
    has been handled in ``maidr/patch/seaborn_probe.py`` since #373.

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
    return _draw_quietly(wrapped, args, kwargs)


wrap_seaborn("boxenplot", boxen)


def sns_categorical_boxens(
    wrapped: Callable, instance: Any, args: tuple, kwargs: dict
) -> Any:
    """
    Register every letter-value ladder seaborn draws, per panel.

    One registrar for both interfaces. ``seaborn.boxenplot`` and
    ``sns.catplot(kind="boxen")`` share no code above this method, so a patch
    on the function reached one of them and a patch here reaches both -- the
    idiom ``maidr/patch/boxplot.py`` uses for ``plot_boxes`` and #446 used for
    ``_DistributionPlotter``.

    Which collections *this call added* is still what the layer is built from,
    and asking it per panel is what makes it work on a grid at all: every
    panel's ladders would otherwise be handed the first panel's collections.

    Sweeping the axes instead, and pairing each ladder with whatever collection
    follows it, is right until something else draws on the same axes -- and a
    strip plot over a boxen is a standard idiom, since the ladder summarises
    the distribution the points make up. ``showfliers=False`` is what breaks
    the pairing: seaborn then adds no flier collection at all, so the run stops
    alternating and the last ladder takes the *strip plot's* first cloud as its
    own. Measured on three categories with an overlay::

        collections: Patch Patch Patch Path Path Path
        z=a low=0 up=0    z=b low=0 up=0    z=c low=7 up=7

    Fourteen outliers announced on a chart whose author asked for none, with
    the values taken from a different layer (#253).

    By identity rather than by count, so it holds however the list is
    reordered, and the collections themselves rather than their ``id()``s:
    an id is only unique while its object is alive, and holding the set keeps
    every one of them alive for the comparison.

    Parameters
    ----------
    wrapped : Callable
        ``_CategoricalPlotter.plot_boxens``.
    instance : Any
        The plotter the method is bound to.
    args, kwargs
        The method's own arguments, passed through untouched.

    Returns
    -------
    Any
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    before = {id(ax): set(ax.collections) for ax in plotter_axes(instance)}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    # Registered unconditionally per panel, as the other seaborn categorical
    # patches do: a panel seaborn drew a ladder onto and MAIDR could not read
    # is worth an error rather than a chart that quietly has no boxen layer
    # in it.
    for ax in plotter_axes(instance):
        added = [
            collection
            for collection in ax.collections
            if collection not in before.get(id(ax), set())
        ]
        FigureManager.create_maidr(ax, PlotType.BOXEN, **{DRAWN_LADDERS: added})

    return drawn


# And the plotter method beneath `seaborn.boxenplot`, which is the only thing
# `catplot` drives. Wrapped by module path rather than by importing the private
# class, matching how `maidr/patch/boxplot.py` reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_boxens",
    sns_categorical_boxens,
)

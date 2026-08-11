from __future__ import annotations

import inspect
from typing import Callable

import wrapt

from matplotlib.axes import Axes
from matplotlib.collections import Collection
from matplotlib.image import AxesImage

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly


def _declares_fmt(wrapped: Callable) -> bool:
    """
    Whether a patched function takes ``fmt`` as a parameter of its own.

    ``fmt`` is seaborn's: ``seaborn.heatmap`` declares it and uses it to format
    the cell annotations. The matplotlib entry points patched here do not, and
    forwarding it to one of them does not fail cleanly -- ``Axes.pcolormesh``
    swallows the kwarg into ``**kwargs`` and passes it to the artist, which
    raises ``AttributeError: QuadMesh.set() got an unexpected keyword argument
    'fmt'`` from somewhere the caller has no way to connect back to MAIDR.

    So the test has to be for an *explicitly declared* parameter. A
    ``**kwargs``-accepting signature is exactly the case that misleads here:
    every one of these functions has one, and none of them can actually use
    the value.

    Parameters
    ----------
    wrapped : Callable
        The wrapped plotting function.

    Returns
    -------
    bool
        True when the function declares ``fmt`` and can be handed it.
    """
    try:
        return "fmt" in inspect.signature(wrapped).parameters
    except (TypeError, ValueError):
        # A callable with no introspectable signature. Assume it cannot take
        # `fmt`: dropping it costs MAIDR nothing, since the value is read out
        # for the schema either way, while forwarding one the function cannot
        # take aborts the draw.
        return False


def heat(wrapped, _, args, kwargs) -> Axes | AxesImage | Collection:
    # `seaborn.heatmap` draws through `Axes.pcolormesh`, and both are patched
    # here. Without this guard the inner call registers a second HEAT layer for
    # the same axes, so one `sns.heatmap()` would be announced as two identical
    # heatmaps the user has to navigate between. Every other patch reaches the
    # same guard through `common()`; this one does not call it, because it has
    # to pop `z_label` before the draw rather than pass it through.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Check for additional params used by MAIDR heatmap.
    optional_params = {}
    if "z_label" in kwargs:
        # Remove `z_label` because it is introduced by us.
        optional_params["z_label"] = kwargs.pop("z_label")
    if "fmt" in kwargs:
        # Read for the schema either way, but only forwarded to a function that
        # can actually take it -- see `_declares_fmt`.
        optional_params["fmt"] = kwargs["fmt"]
        if not _declares_fmt(wrapped):
            kwargs.pop("fmt")

    # Patch `ax.imshow()`, `ax.pcolormesh()`, `ax.pcolor()` and `seaborn.heatmap`.
    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    # Extract the heatmap data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HEAT, **optional_params)

    # Return to the caller.
    return plot


# Patch matplotlib functions.
#
# `imshow` is not the only way a matplotlib heatmap gets drawn, and it is not
# the most common one: `pcolormesh` is what you reach for whenever the grid is
# irregular or the axes carry real coordinates rather than array indices, which
# covers most scientific use. Until these two were patched such a figure
# registered nothing at all, and the user got silence with no indication that
# anything had been missed.
wrapt.wrap_function_wrapper(Axes, "imshow", heat)
wrapt.wrap_function_wrapper(Axes, "pcolormesh", heat)
wrapt.wrap_function_wrapper(Axes, "pcolor", heat)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "heatmap", heat)

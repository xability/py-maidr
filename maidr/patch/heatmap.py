from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.image import AxesImage

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly


def heat(wrapped, _, args, kwargs) -> Axes | AxesImage:
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
        optional_params["fmt"] = kwargs["fmt"]

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

from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.enum import PlotType
from maidr.core.plot.scatterplot import DRAWN_POINTS
from maidr.patch.common import common, wrap_seaborn


def scatter(wrapped, instance, args, kwargs) -> Axes | PathCollection:
    # Hand the layer the collection this call drew. `ScatterPlot` otherwise
    # takes the *first* `PathCollection` on the axes, which is right only
    # while a layer is one collection -- and seaborn's categorical scatters
    # are one per category. Measured on a three-category `stripplot`: three
    # layers registered, all three holding category "a", and 60 of the 90
    # drawn points absent from the schema entirely (#426). Two plain
    # `ax.scatter()` calls fail the same way.
    #
    # `seaborn.scatterplot` is wrapped through this same function and returns
    # an `Axes` rather than the collection, so it falls back to the sweep --
    # which is correct for it, since it draws every point as a single
    # collection even under `hue`.
    return common(
        PlotType.SCATTER, wrapped, instance, args, kwargs, drawn_as=DRAWN_POINTS
    )


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "scatter", scatter)

# Patch seaborn function.
wrap_seaborn("scatterplot", scatter)

from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.image import AxesImage

from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


def heat(wrapped, _, args, kwargs) -> Axes | AxesImage:
    # Check for additional params used by MAIDR heatmap.
    optional_params = {}
    if "z_label" in kwargs:
        # Remove `z_label` because it is introduced by us.
        optional_params["z_label"] = kwargs.pop("z_label")
    elif "fill_label" in kwargs:
        # Backward compatibility: support old `fill_label` parameter
        optional_params["z_label"] = kwargs.pop("fill_label")
    if "fmt" in kwargs:
        optional_params["fmt"] = kwargs["fmt"]

    # Patch `ax.imshow()` and `seaborn.heatmap`.
    plot = wrapped(*args, **kwargs)

    # Extract the heatmap data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HEAT, **optional_params)

    # Return to the caller.
    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "imshow", heat)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "heatmap", heat)

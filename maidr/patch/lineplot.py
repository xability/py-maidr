from __future__ import annotations

import inspect

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import common


def line(wrapped, instance, args, kwargs) -> Axes | list[Line2D]:
    """
    Wrapper function for line plotting functions in matplotlib and seaborn.

    Parameters
    ----------
    wrapped : callable
        The wrapped function (plot or lineplot)
    instance : object
        The object to which the wrapped function belongs
    args : tuple
        Positional arguments passed to the wrapped function
    kwargs : dict
        Keyword arguments passed to the wrapped function

    Returns
    -------
    Axes | list[Line2D]
        The result of the wrapped function after processing
    """
    plot_type = PlotType.LINE

    # Check if this is matplotlib's plot with a label (multiline)
    if "label" in kwargs:
        plot_type = PlotType.MULTILINE

    if "hue" in kwargs:
        plot_type = PlotType.MULTILINE
    # Check for multiple y columns case
    elif "data" in kwargs and "y" in kwargs:
        # If y is a list or contains multiple columns, it's a multiline plot
        y_param = kwargs.get("y")
        if isinstance(y_param, list) and len(y_param) > 1:
            plot_type = PlotType.MULTILINE
    return common(plot_type, wrapped, instance, args, kwargs)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "lineplot", line)

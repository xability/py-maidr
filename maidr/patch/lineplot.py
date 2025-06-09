from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.enum.smooth_keywords import SMOOTH_KEYWORDS


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
    result = wrapped(*args, **kwargs)
    # result can be a list of Line2D or a single Axes
    lines = result if isinstance(result, list) else [result]
    for line in lines:
        if isinstance(line, Line2D):
            label = str(line.get_label() or "")
            if any(key in label.lower() for key in SMOOTH_KEYWORDS):
                # Skip registering as LINE if it's a smooth/regression line
                return result
    # If none of the lines are smooth/regression, register as LINE
    return common(PlotType.LINE, wrapped, instance, args, kwargs)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "lineplot", line)

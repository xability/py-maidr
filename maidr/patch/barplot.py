from __future__ import annotations

from numbers import Number
from typing import Any, Callable, Dict, Tuple, Union

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import PlotType
from maidr.patch.common import common


def bar(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Union[Axes, BarContainer]:
    """
    Patch function for bar plots.

    This function patches the bar plotting functions to identify whether the
    plot should be rendered as a normal, stacked, or dodged bar plot.
    It uses the 'bottom' keyword to identify stacked bar plots. If 'bottom'
    is not provided and the x positions (first positional argument) are numeric,
    then a dodged plot is assumed.

    Parameters
    ----------
    wrapped : Callable
        The original function to be wrapped.
    instance : Any
        The instance of the class where the function is being patched.
    args : tuple
        Positional arguments passed to the original function.
        For a dodged plot, the first argument (x positions) should be numeric.
    kwargs : dict
        Keyword arguments passed to the original function.

    Returns
    -------
    Union[Axes, BarContainer]
        The axes or bar container returned by the original function.

    Examples
    --------
    >>> # For a dodged (grouped) bar plot, pass numeric x positions:
    >>> x_positions = np.arange(3)
    >>> ax.bar(x_positions, heights, width, label='Group')  # Dodged bar plot.
    """
    plot_type = PlotType.BAR
    if "bottom" in kwargs:
        bottom = kwargs.get("bottom")
        if bottom is not None:
            plot_type = PlotType.STACKED
    elif args:
        x = args[0]
        is_numeric = False
        if isinstance(x, np.ndarray) and np.issubdtype(x.dtype, np.number):
            is_numeric = True
        elif isinstance(x, (list, tuple)) and x and isinstance(x[0], Number):
            is_numeric = True
        if is_numeric:
            plot_type = PlotType.DODGED

    return common(plot_type, wrapped, instance, args, kwargs)


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrapt.wrap_function_wrapper("seaborn", "barplot", bar)
wrapt.wrap_function_wrapper("seaborn", "countplot", bar)

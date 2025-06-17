from __future__ import annotations

from typing import Any, Callable, Dict, Tuple, Union

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
    else:
        if len(args) >= 3:
            real_width = args[2]
        else:
            real_width = kwargs.get("width", 0.8)

        align = kwargs.get("align", "center")

        if (isinstance(real_width, (int, float)) and float(real_width) < 0.8) or (
            align == "edge"
        ):
            plot_type = PlotType.DODGED
    if "dodge" in kwargs:
        plot_type = PlotType.DODGED

    return common(plot_type, wrapped, instance, args, kwargs)


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrapt.wrap_function_wrapper("seaborn", "barplot", bar)
wrapt.wrap_function_wrapper("seaborn", "countplot", bar)

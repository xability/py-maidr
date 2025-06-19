import wrapt
from typing import Any, Callable, Dict, Tuple
from matplotlib.patches import Rectangle
from mplfinance import original_flavor

from maidr.core.context_manager import ContextManager
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager


def candlestick(
    wrapped: Callable[..., list[Rectangle]],
    instance: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> list[Rectangle]:
    """
    Patch function for candlestick plots.

    This function patches the candlestick plotting function to extract
    candlestick data and create MAIDR plot instances for visualization.

    Parameters
    ----------
    wrapped : Callable[..., list[Rectangle]]
        The original candlestick function to be wrapped.
    instance : Any
        The instance of the class where the function is being patched.
    args : Tuple[Any, ...]
        Positional arguments passed to the original function.
    kwargs : Dict[str, Any]
        Keyword arguments passed to the original function.

    Returns
    -------
    list[Rectangle]
        The list of Rectangle objects returned by the original candlestick function.

    Notes
    -----
    This wrapper function is used by the wrapt library to patch the mplfinance
    candlestick function. It creates MAIDR plot instances for candlestick charts
    while preserving the original functionality.
    """
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = wrapped(*args, **kwargs)

    axes = []
    for ax in plot:
        axes.append(FigureManager.get_axes(ax))
    FigureManager.create_maidr(axes, PlotType.CANDLESTICK)

    return plot


wrapt.wrap_function_wrapper(original_flavor, "_candlestick", candlestick)

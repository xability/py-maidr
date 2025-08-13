import wrapt
from typing import Any, Callable, Dict, Tuple
from matplotlib.patches import Rectangle
from mplfinance import original_flavor
import numpy as np

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

    original_data = None
    date_nums = None
    if len(args) >= 2:
        try:
            quotes = args[1]
            if quotes is not None:
                arr = np.asarray(quotes)
                if arr.ndim == 2 and arr.shape[1] >= 5 and arr.size > 0:
                    date_nums = arr[:, 0].tolist()
                    original_data = {
                        "Open": arr[:, 1].tolist(),
                        "High": arr[:, 2].tolist(),
                        "Low": arr[:, 3].tolist(),
                        "Close": arr[:, 4].tolist(),
                    }
        except Exception:
            pass

    axes = []
    for ax in plot:
        axes.append(FigureManager.get_axes(ax))

    extra_kwargs: Dict[str, Any] = {}
    if original_data is not None:
        extra_kwargs["_maidr_original_data"] = original_data
    if date_nums is not None:
        extra_kwargs["_maidr_date_nums"] = date_nums

    FigureManager.create_maidr(axes, PlotType.CANDLESTICK, **extra_kwargs)

    return plot


wrapt.wrap_function_wrapper(original_flavor, "_candlestick", candlestick)

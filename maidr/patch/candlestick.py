import wrapt
from matplotlib.patches import Rectangle
from mplfinance import original_flavor

from maidr.core.context_manager import ContextManager
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager


def candlestick(wrapped, instance, args, kwargs) -> list[Rectangle]:

    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = wrapped(*args, **kwargs)

    axes = []
    for ax in plot:
        axes.append(FigureManager.get_axes(ax))
    FigureManager.create_maidr(axes, PlotType.CANDLESTICK)

    return plot


wrapt.wrap_function_wrapper(original_flavor, "_candlestick", candlestick)

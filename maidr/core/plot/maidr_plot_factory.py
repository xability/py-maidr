from __future__ import annotations

from matplotlib.axes import Axes

from maidr.core.enum import PlotType
from maidr.core.plot.barplot import BarPlot
from maidr.core.plot.boxplot import BoxPlot
from maidr.core.plot.candlestick import CandlestickPlot
from maidr.core.plot.grouped_barplot import GroupedBarPlot
from maidr.core.plot.heatmap import HeatPlot
from maidr.core.plot.histogram import HistPlot
from maidr.core.plot.lineplot import MultiLinePlot
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.core.plot.scatterplot import ScatterPlot
from maidr.core.plot.regplot import SmoothPlot


class MaidrPlotFactory:
    """
    A factory for creating instances of ``maidr.core.maidr.MaidrPlot`` based on the
    plot type.

    Warnings
    --------
    End users will typically not have to use this class directly.

    See Also
    --------
    MaidrPlot : The base class for MAIDR plot data objects.
    PlotType : An enumeration of types of plots supported within MAIDR.
    """

    @staticmethod
    def create(ax: Axes | list[Axes], plot_type: PlotType, **kwargs) -> MaidrPlot:
        if isinstance(ax, list):
            single_ax = ax[0]
        else:
            single_ax = ax

        if plot_type == PlotType.CANDLESTICK:
            if isinstance(ax, list):
                # If ax is a list of lists, flatten it
                if ax and isinstance(ax[0], list):
                    axes = ax[0]  # Take the first inner list
                else:
                    axes = ax  # Use the list as-is
            else:
                axes = [ax]  # Wrap single axes in list
            return CandlestickPlot(axes, **kwargs)
        elif PlotType.BAR == plot_type or PlotType.COUNT == plot_type:
            return BarPlot(single_ax)
        elif PlotType.BOX == plot_type:
            return BoxPlot(single_ax, **kwargs)
        elif PlotType.HEAT == plot_type:
            return HeatPlot(single_ax, **kwargs)
        elif PlotType.HIST == plot_type:
            return HistPlot(single_ax)
        elif PlotType.LINE == plot_type:
            return MultiLinePlot(single_ax)
        elif PlotType.SCATTER == plot_type:
            return ScatterPlot(single_ax)
        elif PlotType.DODGED == plot_type or PlotType.STACKED == plot_type:
            return GroupedBarPlot(single_ax, plot_type, **kwargs)
        elif PlotType.SMOOTH == plot_type:
            return SmoothPlot(single_ax, **kwargs)
        else:
            raise TypeError(f"Unsupported plot type: {plot_type}.")

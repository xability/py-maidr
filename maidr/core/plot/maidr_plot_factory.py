from __future__ import annotations

from matplotlib.axes import Axes

from maidr.core.enum import PlotType
from maidr.core.plot.barplot import BarPlot
from maidr.core.plot.boxplot import BoxPlot
from maidr.core.plot.grouped_barplot import GroupedBarPlot
from maidr.core.plot.heatmap import HeatPlot
from maidr.core.plot.histogram import HistPlot
from maidr.core.plot.lineplot import MultiLinePlot
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.core.plot.scatterplot import ScatterPlot


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
    def create(ax: Axes, plot_type: PlotType, **kwargs) -> MaidrPlot:
        if PlotType.BAR == plot_type or PlotType.COUNT == plot_type:
            return BarPlot(ax)
        elif PlotType.BOX == plot_type:
            return BoxPlot(ax, **kwargs)
        elif PlotType.HEAT == plot_type:
            return HeatPlot(ax, **kwargs)
        elif PlotType.HIST == plot_type:
            return HistPlot(ax)
        elif PlotType.LINE == plot_type:
            return MultiLinePlot(ax)
        elif PlotType.SCATTER == plot_type:
            return ScatterPlot(ax)
        elif PlotType.DODGED == plot_type or PlotType.STACKED == plot_type:
            return GroupedBarPlot(ax, plot_type, **kwargs)
        else:
            raise TypeError(f"Unsupported plot type: {plot_type}.")

from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


class BarPlot(MaidrPlot, ContainerExtractorMixin, LevelExtractorMixin, DictMergerMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.BAR)

    def _extract_plot_data(self) -> list:
        """
        Extract plot data for bar plots.
        
        For vertical bar plots, categories are on X-axis and values on Y-axis.
        For horizontal bar plots, categories are on Y-axis and values on X-axis.
        
        Returns
        -------
        list
            List of dictionaries containing x and y data points.
        """
        plot = self.extract_container(self.ax, BarContainer, include_all=True)
        data = self._extract_bar_container_data(plot)
        
        # Extract appropriate axis labels based on bar orientation
        if plot and plot[0].orientation == "vertical":
            # For vertical bars: categories on X-axis, values on Y-axis
            levels = self.extract_level(self.ax, MaidrKey.X)
        else:
            # For horizontal bars: categories on Y-axis, values on X-axis
            levels = self.extract_level(self.ax, MaidrKey.Y)
        
        # Handle the case where levels might be None or empty
        if levels is None or data is None:
            if data is None:
                raise ExtractionError(self.type, plot)
            # If levels is None but data exists, create default labels
            levels = [f"Item {i+1}" for i in range(len(data))]
        
        formatted_data = []
        combined_data = list(
            zip(levels, data)
            if plot and plot[0].orientation == "vertical"
            else zip(data, levels)
        )
        
        if combined_data:
            for x, y in combined_data:
                formatted_data.append({"x": x, "y": y})
            return formatted_data
        
        # If no formatted data could be created, raise an error
        if len(formatted_data) == 0:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_bar_container_data(
        self, plot: list[BarContainer] | None
    ) -> list | None:
        """
        Extract bar container data with proper orientation handling.
        
        Parameters
        ----------
        plot : list[BarContainer] | None
            List of bar containers from the plot.
            
        Returns
        -------
        list | None
            List of bar heights/widths, or None if extraction fails.
        """
        if plot is None:
            return None

        # Since v0.13, Seaborn has transitioned from using `list[Patch]` to
        # `list[BarContainers] for plotting bar plots.
        # So, extract data correspondingly based on the level.
        # Flatten all the `list[BarContainer]` to `list[Patch]`.
        plot_patches = [patch for container in plot for patch in container.patches]
        
        # Extract appropriate axis labels based on bar orientation
        if plot[0].orientation == "vertical":
            # For vertical bars: categories on X-axis
            level = self.extract_level(self.ax, MaidrKey.X)
        else:
            # For horizontal bars: categories on Y-axis
            level = self.extract_level(self.ax, MaidrKey.Y)
            
        if level is None or len(level) == 0:
            level = ["" for _ in range(len(plot_patches))]

        if len(plot_patches) != len(level):
            return None

        self._elements.extend(plot_patches)

        # For horizontal bars, use width; for vertical bars, use height
        if plot[0].orientation == "horizontal":
            return [float(patch.get_width()) for patch in plot_patches]
        else:
            return [float(patch.get_height()) for patch in plot_patches]

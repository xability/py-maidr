from __future__ import annotations

from matplotlib.axes import Axes
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
import numpy as np
from maidr.core.enum.plot_type import PlotType
from maidr.core.enum.maidr_key import MaidrKey
from maidr.util.regression_line_utils import find_regression_line
from maidr.util.svg_utils import data_to_svg_coords


class SmoothPlot(MaidrPlot):
    """
    Extracts and represents a regression line as a smooth plot for MAIDR.

    Parameters
    ----------
    ax : Axes
        The matplotlib axes object containing the regression line.
    """

    def __init__(self, ax: Axes, **kwargs):
        """
        Initialize a SmoothPlot for a regression line.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes object containing the regression line.
        """
        self._violin_layer = kwargs.pop("violin_layer", None)
        super().__init__(ax, PlotType.SMOOTH, **kwargs)
        self._smooth_gid = None
        self._regression_line = kwargs.get("regression_line", None)
        self._poly_gid = kwargs.get("poly_gid", None)
        self._poly_gids = kwargs.get("poly_gids", None)  # List of unique GIDs for each violin
        self._is_polycollection = kwargs.get("is_polycollection", False)
        self._violin_kde_lines = kwargs.get("violin_kde_lines", None)
        self._poly_collections = kwargs.get("poly_collections", None)  # Store PolyCollections for GID tagging
        
        # Add PolyCollections to _elements so they get tagged with GIDs in SVG
        if self._poly_collections:
            for poly in self._poly_collections:
                self._elements.append(poly)

    def _get_selector(self):
        """
        Return the CSS selector for highlighting the regression line or PolyCollection in the SVG output.
        For violin plots with multiple violins, returns individual selectors for each violin.
        """
        # For violin KDE plots with multiple unique GIDs, return individual selectors
        if self._is_polycollection and self._poly_gids:
            # Return individual selectors for each violin
            selectors = []
            for gid in self._poly_gids:
                selectors.append(f"g[id='{gid}'] path, g[id='{gid}'] use")
            return selectors
        
        # Fallback for single poly_gid (legacy support)
        if self._is_polycollection and self._poly_gid:
            return [f"g[id='{self._poly_gid}'] path, g[id='{self._poly_gid}'] use"]
        
        if self._smooth_gid:
            return [f"g[id='{self._smooth_gid}'] path"]
        return ["g[id^='maidr-'] path"]

    def _extract_plot_data(self) -> list:
        """
        Extract XY data from the regression line for serialization, including SVG coordinates.
        For violin plots, extracts data from all KDE lines.

        Returns
        -------
        list
            A list of lists containing dictionaries with X and Y coordinates, and SVG coordinates.
            For violin plots with multiple KDE lines, each inner list represents one violin.
        """
        # Handle violin plot case: multiple KDE lines in one layer
        if self._violin_kde_lines is not None:
            all_lines_data = []
            for kde_line in self._violin_kde_lines:
                self._elements.append(kde_line)
                if self._smooth_gid is None:
                    self._smooth_gid = kde_line.get_gid()
                xydata = np.asarray(kde_line.get_xydata())
                x_data, y_data = xydata[:, 0], xydata[:, 1]
                x_svg, y_svg = data_to_svg_coords(self.ax, x_data, y_data)
                all_lines_data.append([
                    {
                        MaidrKey.X: float(x),
                        MaidrKey.Y: float(y),
                        "svg_x": float(sx),
                        "svg_y": float(sy),
                    }
                    for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg)
                ])
            return all_lines_data
        
        # Standard single regression line case
        regression_line = (
            self._regression_line
            if self._regression_line is not None
            else find_regression_line(self.ax)
        )
        if regression_line is None:
            raise ExtractionError(PlotType.SMOOTH, self.ax)
        self._elements.append(regression_line)
        self._smooth_gid = regression_line.get_gid()
        xydata = np.asarray(regression_line.get_xydata())
        x_data, y_data = xydata[:, 0], xydata[:, 1]
        x_svg, y_svg = data_to_svg_coords(self.ax, x_data, y_data)
        return [
            [
                {
                    MaidrKey.X: float(x),
                    MaidrKey.Y: float(y),
                    "svg_x": float(sx),
                    "svg_y": float(sy),
                }
                for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg)
            ]
        ]

    def render(self) -> dict:
        """
        Generate the MAIDR schema for this plot layer, including violinLayer metadata if present.
        """
        schema = super().render()
        # Include violinLayer metadata if present (for violin plots)
        if self._violin_layer is not None:
            schema["violinLayer"] = self._violin_layer
        return schema

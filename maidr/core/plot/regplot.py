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
        super().__init__(ax, PlotType.SMOOTH)
        self._smooth_gid = None
        self._regression_line = kwargs.get("regression_line", None)
        self._poly_gid = kwargs.get("poly_gid", None)
        self._is_polycollection = kwargs.get("is_polycollection", False)

    def _get_selector(self):
        """
        Return the CSS selector for highlighting the regression line or PolyCollection in the SVG output.
        """
        if self._is_polycollection and self._poly_gid:
            return [f"g[id='{self._poly_gid}'] > defs > path"]
        if self._smooth_gid:
            return [f"g[id='{self._smooth_gid}'] path"]
        return ["g[id^='maidr-'] path"]

    def _extract_plot_data(self) -> list:
        """
        Extract XY data from the regression line for serialization, including SVG coordinates.
        For violin plots (PolyCollection), also calculates density as horizontal distance 
        between points at the same y-value.

        Returns
        -------
        list
            A list of lists containing dictionaries with X and Y coordinates, and SVG coordinates.
            For violin plots, includes "density" field representing horizontal width.
        """
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
        
        # For violin plots (is_polycollection), calculate density
        is_violin = self._is_polycollection
        
        if is_violin:
            # Calculate density: for each y-value, find the horizontal distance (width)
            # The violin boundary has points going up one side and down the other
            # We need to find the width (density) at each y-level
            
            # Use a more reasonable tolerance for y-value matching
            # Violin plots can have many points, so we'll bin y-values
            y_min, y_max = y_data.min(), y_data.max()
            y_range = y_max - y_min if y_max != y_min else 1.0
            
            # Use a tolerance that's a small fraction of the y-range
            # or a minimum absolute value, whichever is larger
            y_tolerance = max(y_range * 0.001, 0.01)  # 0.1% of range or 0.01 units
            
            # Create bins for y-values to group nearby points
            # This handles cases where exact y-values don't match
            y_unique = np.unique(np.round(y_data / y_tolerance) * y_tolerance)
            
            # Create result list with density information
            result = []
            processed_indices = set()
            
            for y_bin in y_unique:
                # Find all points in this y-bin
                y_mask = np.abs(y_data - y_bin) < y_tolerance
                y_indices = np.where(y_mask)[0]
                
                if len(y_indices) == 0:
                    continue
                
                # Get x-values at this y-level
                y_x_values = x_data[y_indices]
                
                # Calculate density as the horizontal width at this y-level
                if len(y_x_values) > 1:
                    density = float(np.max(y_x_values) - np.min(y_x_values))
                else:
                    # Single point - density is 0 (edge case)
                    density = 0.0
                
                # Add all points at this y-level with density
                for idx in y_indices:
                    if idx not in processed_indices:
                        result.append({
                            MaidrKey.X: float(x_data[idx]),
                            MaidrKey.Y: float(y_data[idx]),
                            "svg_x": float(x_svg[idx]),
                            "svg_y": float(y_svg[idx]),
                            "density": density,
                        })
                        processed_indices.add(idx)
            
            return [result]
        else:
            # For regular smooth plots, return without density
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

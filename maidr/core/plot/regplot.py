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
        **kwargs
            Additional keyword arguments:
            - ``regression_line`` : matplotlib.lines.Line2D, optional
                Pre-extracted regression line. If not provided, will be
                extracted from the axes.
            - ``poly_gid`` : str, optional
                Group ID for PolyCollection elements (used for violin plots).
            - ``is_polycollection`` : bool, default False
                Whether this plot represents a PolyCollection (e.g., violin plot).
            - ``violin_fill`` : str, optional
                Category/group name for violin plots. Used as the fill value
                in the plot data.
        """
        super().__init__(ax, PlotType.SMOOTH)
        self._smooth_gid = None
        self._regression_line = kwargs.get("regression_line", None)
        self._poly_gid = kwargs.get("poly_gid", None)
        self._is_polycollection = kwargs.get("is_polycollection", False)
        self._violin_fill = kwargs.get("violin_fill", None)

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
        list of list of dict
            A list of lists containing dictionaries with coordinate data. Each inner list
            represents a series of points. Each dictionary contains:
            - ``'x'`` : float
                X coordinate in data space.
            - ``'y'`` : float
                Y coordinate in data space.
            - ``'svg_x'`` : float
                X coordinate in SVG space.
            - ``'svg_y'`` : float
                Y coordinate in SVG space.
            - ``'density'`` : float, optional
                Horizontal width at this y-value (only for violin plots).
                Represents the density distribution width.
            - ``'fill'`` : str, optional
                Category/group name (only for violin plots when ``violin_fill`` is set).

        Notes
        -----
        Density calculations are only performed when the internal attribute
        ``_is_polycollection`` is set to ``True`` (e.g., for violin plots). In this case:
        - The output dictionaries will include a ``'density'`` field representing the
          horizontal width at each y-value.
        - Points at the same y-level are grouped together, and density is calculated
          as the difference between the maximum and minimum x-values at that y-level.
        - If ``_violin_fill`` is set, the ``'fill'`` field will be included in each
          point dictionary.
        
        For regular smooth plots (regression lines), density is not calculated and
        the output contains only x, y, svg_x, and svg_y coordinates.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> from maidr.core.plot.regplot import SmoothPlot
        >>> fig, ax = plt.subplots()
        >>> # Regular smooth plot (regression line)
        >>> plot = SmoothPlot(ax)
        >>> data = plot._extract_plot_data()
        >>> data[0][0].keys()
        dict_keys(['x', 'y', 'svg_x', 'svg_y'])
        >>> 
        >>> # Violin plot (PolyCollection)
        >>> plot = SmoothPlot(ax, is_polycollection=True, violin_fill="Group A")
        >>> data = plot._extract_plot_data()
        >>> data[0][0].keys()
        dict_keys(['x', 'y', 'svg_x', 'svg_y', 'density', 'fill'])
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
                        point_data = {
                            MaidrKey.X: float(x_data[idx]),
                            MaidrKey.Y: float(y_data[idx]),
                            "svg_x": float(x_svg[idx]),
                            "svg_y": float(y_svg[idx]),
                            "density": density,
                        }
                        # Add fill (category name) if available for violin plots
                        if self._violin_fill:
                            point_data[MaidrKey.FILL.value] = self._violin_fill
                            # Also set it as "fill" directly to ensure it's accessible
                            point_data["fill"] = self._violin_fill
                        result.append(point_data)
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

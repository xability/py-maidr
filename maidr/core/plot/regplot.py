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
        self._x_levels = kwargs.get("x_levels", None)  # X axis categorical labels for violin plots
        
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
            for idx, kde_line in enumerate(self._violin_kde_lines):
                self._elements.append(kde_line)
                if self._smooth_gid is None:
                    self._smooth_gid = kde_line.get_gid()
                xydata = np.asarray(kde_line.get_xydata())
                x_data, y_data = xydata[:, 0], xydata[:, 1]
                x_svg, y_svg = data_to_svg_coords(self.ax, x_data, y_data)
                
                # Map numeric X coordinates to categorical labels if available
                # For violin plots, each row (violin) corresponds to one categorical X value
                x_categorical_label = None
                if self._x_levels and idx < len(self._x_levels):
                    x_categorical_label = self._x_levels[idx]
                
                # Interpolate Y values to a common grid (y_common) and calculate widths
                # For violin plots, we interpolate to regularly spaced Y values
                from scipy import interpolate
                
                y_unique = sorted(set(y_data))
                if len(y_unique) < 2:
                    # Not enough points for interpolation, use original data
                    all_lines_data.append([
                        {
                            MaidrKey.X: x_categorical_label if x_categorical_label is not None else float(x),
                            MaidrKey.Y: float(y),
                            "svg_x": float(sx),
                            "svg_y": float(sy),
                            "width": None,
                        }
                        for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg)
                    ])
                    continue
                
                # Create regular Y grid (y_common) - evenly spaced between min and max Y
                y_min, y_max = min(y_unique), max(y_unique)
                num_points = len(y_unique)
                y_common = np.linspace(y_min, y_max, num_points)
                
                # Separate left and right sides of violin by X position
                x_center = np.mean(x_data)
                left_points = [(x, y) for x, y in zip(x_data, y_data) if x <= x_center]
                right_points = [(x, y) for x, y in zip(x_data, y_data) if x >= x_center]
                
                # Prepare interpolated data
                interpolated_data = []
                
                if len(left_points) > 0 and len(right_points) > 0:
                    left_x, left_y = np.array([p[0] for p in left_points]), np.array([p[1] for p in left_points])
                    right_x, right_y = np.array([p[0] for p in right_points]), np.array([p[1] for p in right_points])
                    
                    try:
                        # Sort by Y for interpolation
                        left_sort_idx = np.argsort(left_y)
                        right_sort_idx = np.argsort(right_y)
                        left_y_sorted, left_x_sorted = left_y[left_sort_idx], left_x[left_sort_idx]
                        right_y_sorted, right_x_sorted = right_y[right_sort_idx], right_x[right_sort_idx]
                        
                        # Create interpolation functions
                        f_left = interpolate.interp1d(
                            left_y_sorted, left_x_sorted, 
                            kind='linear', 
                            bounds_error=False, 
                            fill_value='extrapolate',
                            assume_sorted=True
                        )
                        f_right = interpolate.interp1d(
                            right_y_sorted, right_x_sorted, 
                            kind='linear', 
                            bounds_error=False, 
                            fill_value='extrapolate',
                            assume_sorted=True
                        )
                        
                        # Interpolate to y_common grid
                        # Output both left and right points for each Y value (like user's sample data)
                        for y_val in y_common:
                            x_left = float(f_left(y_val))
                            x_right = float(f_right(y_val))
                            
                            # Check for NaN values and skip invalid points
                            if np.isnan(x_left) or np.isnan(x_right) or np.isnan(y_val):
                                continue
                            
                            width = abs(x_right - x_left)
                            
                            # Skip if width is NaN or invalid
                            if np.isnan(width) or width <= 0:
                                continue
                            
                            # Calculate SVG coordinates for left and right points
                            svg_x_left, svg_y_left = data_to_svg_coords(
                                self.ax, 
                                np.array([x_left]), 
                                np.array([y_val])
                            )
                            svg_x_right, svg_y_right = data_to_svg_coords(
                                self.ax, 
                                np.array([x_right]), 
                                np.array([y_val])
                            )
                            
                            # Add left point
                            interpolated_data.append({
                                MaidrKey.X: x_categorical_label if x_categorical_label is not None else x_left,
                                MaidrKey.Y: float(y_val),
                                "svg_x": float(svg_x_left[0]),
                                "svg_y": float(svg_y_left[0]),
                                "width": float(width),  # Ensure it's a valid float
                            })
                            
                            # Add right point
                            interpolated_data.append({
                                MaidrKey.X: x_categorical_label if x_categorical_label is not None else x_right,
                                MaidrKey.Y: float(y_val),
                                "svg_x": float(svg_x_right[0]),
                                "svg_y": float(svg_y_right[0]),
                                "width": float(width),  # Ensure it's a valid float
                            })
                        
                        all_lines_data.append(interpolated_data)
                    except (ValueError, np.linalg.LinAlgError):
                        # Fallback: use original data with grouping method for width
                        from collections import defaultdict
                        y_to_x_coords = defaultdict(list)
                        for x, y in zip(x_data, y_data):
                            if not (np.isnan(x) or np.isnan(y)):
                                y_to_x_coords[float(y)].append(float(x))
                        
                        y_to_width = {}
                        for y_val, x_coords_list in y_to_x_coords.items():
                            if len(x_coords_list) >= 2:
                                width = abs(max(x_coords_list) - min(x_coords_list))
                                if not np.isnan(width) and width > 0:
                                    y_to_width[y_val] = width
                        
                        # Build data with width only if valid
                        fallback_data = []
                        for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg):
                            if np.isnan(x) or np.isnan(y):
                                continue
                            point_data = {
                                MaidrKey.X: x_categorical_label if x_categorical_label is not None else float(x),
                                MaidrKey.Y: float(y),
                                "svg_x": float(sx),
                                "svg_y": float(sy),
                            }
                            width_val = y_to_width.get(float(y))
                            if width_val is not None and not np.isnan(width_val) and width_val > 0:
                                point_data["width"] = float(width_val)
                            fallback_data.append(point_data)
                        all_lines_data.append(fallback_data)
                else:
                    # Fallback: use original data without width
                    all_lines_data.append([
                        {
                            MaidrKey.X: x_categorical_label if x_categorical_label is not None else float(x),
                            MaidrKey.Y: float(y),
                            "svg_x": float(sx),
                            "svg_y": float(sy),
                            # Don't include width if we can't calculate it
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

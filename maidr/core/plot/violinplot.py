"""
Utility classes and functions for handling violin plot data extraction and processing.

This module provides utilities for extracting data from seaborn violinplot arguments,
computing box plot statistics, extracting violin positions, and creating synthetic
box plot artist objects. Registration with MAIDR is handled by the patch layer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, PathPatch
from matplotlib import path as mpath
from typing import Tuple, List, Dict, Any

from maidr.core.enum import MaidrKey


class ViolinDataExtractor:
    """
    Extracts raw data groups and values from seaborn violinplot arguments.

    This utility class provides a static method to parse positional and keyword arguments
    passed to seaborn's violinplot function, returning the group names and corresponding
    data arrays for each violin in the plot. It supports DataFrame inputs with optional
    grouping and ordering via `x`, `y`, and `hue` parameters.

    Examples
    --------
    >>> import pandas as pd
    >>> import numpy as np
    >>> from maidr.core.plot.violinplot import ViolinDataExtractor
    >>> df = pd.DataFrame({
    ...     "group": ["A", "A", "B", "B"],
    ...     "value": [1.2, 2.3, 3.4, 4.5]
    ... })
    >>> args = ()
    >>> kwargs = {"data": df, "x": "group", "y": "value"}
    >>> groups, values = ViolinDataExtractor.extract(args, kwargs)
    >>> print(groups)
    ['A', 'B']
    >>> print([v.tolist() for v in values])
    [[1.2, 2.3], [3.4, 4.5]]
    """

    @staticmethod
    def extract(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[List[str], List[np.ndarray]]:
        """
        Extract groups and values from seaborn.violinplot arguments.

        Parameters
        ----------
        args : Tuple[Any, ...]
            Positional arguments passed to violinplot
        kwargs : Dict[str, Any]
            Keyword arguments passed to violinplot

        Returns
        -------
        Tuple[List[str], List[np.ndarray]]
            Tuple of (groups, values) where groups is a list of group names
            and values is a list of numpy arrays containing the data for each group
        """
        df = kwargs.get("data", None)
        x = kwargs.get("x", None)
        y = kwargs.get("y", None)
        hue = kwargs.get("hue", None)

        # Case 1 — DataFrame with x & y
        if isinstance(df, pd.DataFrame) and isinstance(x, str) and isinstance(y, str):
            groups, values = [], []
            
            # Check if order parameter is specified (for x or hue)
            x_order = kwargs.get("order", None)
            hue_order = kwargs.get("hue_order", None) if hue else None
            
            if hue is None:
                # Extract groups in the specified order (if provided), otherwise use groupby order
                if x_order is not None:
                    # Respect the order parameter - extract groups in the specified order
                    for g in x_order:
                        gdf = df[df[x] == g]
                        if not gdf.empty:
                            groups.append(str(g))
                            values.append(gdf[y].dropna().values)
                else:
                    # No order specified - use groupby order
                    for g, gdf in df.groupby(x, observed=False):
                        groups.append(str(g))
                        values.append(gdf[y].dropna().values)
            else:
                # With hue - need to handle both x_order and hue_order
                if x_order is not None or hue_order is not None:
                    # Build ordered combinations
                    x_categories = x_order if x_order is not None else df[x].unique()
                    h_categories = hue_order if hue_order is not None else df[hue].unique()
                    
                    for gx in x_categories:
                        for gh in h_categories:
                            gdf = df[(df[x] == gx) & (df[hue] == gh)]
                            if not gdf.empty:
                                groups.append(f"{gx}_{gh}")
                                values.append(gdf[y].dropna().values)
                else:
                    # No order specified - use groupby order
                    for (gx, gh), gdf in df.groupby([x, hue], observed=False):
                        groups.append(f"{gx}_{gh}")
                        values.append(gdf[y].dropna().values)
            return groups, values

        # Case 2 – DataFrame, only y ⇒ single violin
        if isinstance(df, pd.DataFrame) and isinstance(y, str):
            return ["Violin"], [df[y].dropna().values]

        # Case 3 — Passing list/array directly
        if len(args) > 0:
            data = args[0]
            if isinstance(data, (list, tuple, np.ndarray)):
                if len(data) > 0 and isinstance(data[0], (list, tuple, np.ndarray)):
                    groups = [f"Group {i+1}" for i in range(len(data))]
                    values = [np.asarray(d).flatten() for d in data]
                    return groups, values
                else:
                    return ["Violin"], [np.asarray(data).flatten()]

        # Case 4 – Data passed via data= but not a DataFrame
        if "data" in kwargs and not isinstance(kwargs["data"], pd.DataFrame):
            data = kwargs["data"]
            if isinstance(data, (list, tuple)):
                groups = [f"Group {i+1}" for i in range(len(data))]
                values = [np.asarray(d).flatten() for d in data]
                return groups, values

        # Case 5 – y=array (direct array/list passed as y parameter, single violin)
        # This handles cases like sns.violinplot(y=array_data, ...)
        if y is not None and not isinstance(y, str) and isinstance(y, (list, tuple, np.ndarray)):
            return ["Violin"], [np.asarray(y).flatten()]

        # Case 6 – x=array (direct array/list passed as x parameter, single violin)
        # This handles cases like sns.violinplot(x=array_data, ...)
        if x is not None and not isinstance(x, str) and isinstance(x, (list, tuple, np.ndarray)):
            return ["Violin"], [np.asarray(x).flatten()]

        return [], []


class ViolinBoxStatsCalculator:
    """
    Utility class for computing Tukey box plot statistics from raw data.

    This class provides a static method to compute Tukey-style box plot statistics
    (Q1, median, Q3, min, max) from a given array of values. The statistics are
    returned in a dictionary using MaidrKey keys, matching matplotlib's conventions.

    Examples
    --------
    >>> import numpy as np
    >>> from maidr.core.plot.violinplot import ViolinBoxStatsCalculator
    >>> from maidr.core.enum import MaidrKey
    >>> data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
    >>> stats = ViolinBoxStatsCalculator.compute(data)
    >>> print(stats[MaidrKey.Q1.value])
    3.0
    >>> print(stats[MaidrKey.Q2.value])
    5.0
    >>> print(stats[MaidrKey.Q3.value])
    7.0
    """

    # Statistical constants for box plot calculations
    TUKEY_FENCE_MULTIPLIER = 1.5  # Standard multiplier for Tukey fence calculation (1.5 * IQR)

    @staticmethod
    def compute(values: np.ndarray) -> Dict[str, Any]:
        """
        Compute Tukey box stats matching matplotlib/seaborn's boxplot method.

        Returns box plot statistics: Q1, Q2 (median), Q3, min, max.
        Note: min == Q1 (or max == Q3) can occur when there are no outliers
        below Q1 (or above Q3) - this is correct behavior.

        Parameters
        ----------
        values : np.ndarray
            Array of values to compute statistics for

        Returns
        -------
        Dict[str, Any]
            Dictionary containing box plot statistics with MaidrKey keys
        """
        values = np.asarray(values)
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return {
                MaidrKey.MIN.value: 0.0,
                MaidrKey.Q1.value: 0.0,
                MaidrKey.Q2.value: 0.0,
                MaidrKey.Q3.value: 0.0,
                MaidrKey.MAX.value: 0.0,
                MaidrKey.MEAN.value: 0.0,
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.UPPER_OUTLIER.value: [],
            }

        # Calculate quartiles matching matplotlib/seaborn's boxplot method
        # Matplotlib uses np.percentile with interpolation='linear' (default)
        # Sort values first for clarity (numpy.percentile does this internally)
        sorted_values = np.sort(values)

        # Calculate quartiles using numpy.percentile
        # numpy.percentile uses linear interpolation by default, matching matplotlib
        # This is the standard method used by matplotlib's boxplot
        q1 = float(np.percentile(sorted_values, 25))
        q2 = float(np.percentile(sorted_values, 50))
        q3 = float(np.percentile(sorted_values, 75))
        iqr = q3 - q1

        # Calculate Tukey fences (1.5 * IQR rule - standard Tukey fence multiplier)
        lw = q1 - ViolinBoxStatsCalculator.TUKEY_FENCE_MULTIPLIER * iqr  # Lower fence
        uw = q3 + ViolinBoxStatsCalculator.TUKEY_FENCE_MULTIPLIER * iqr  # Upper fence

        # Find values within fences (non-outliers)
        clipped = values[(values >= lw) & (values <= uw)]

        if len(clipped) > 0:
            # Min/max are the extreme values within the fences
            min_val = float(clipped.min())
            max_val = float(clipped.max())
        else:
            # Fallback if all values are outliers
            min_val = float(values.min())
            max_val = float(values.max())

        # Note: min_val may equal q1 when all values are >= q1 (within fence)
        # This is correct - the cap and box edge will overlap visually
        mean_val = float(np.mean(sorted_values))
        return {
            MaidrKey.MIN.value: min_val,
            MaidrKey.Q1.value: q1,
            MaidrKey.Q2.value: q2,
            MaidrKey.Q3.value: q3,
            MaidrKey.MAX.value: max_val,
            MaidrKey.MEAN.value: mean_val,
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.UPPER_OUTLIER.value: [],
        }

    @staticmethod
    def compute_full_range(values: np.ndarray) -> Dict[str, Any]:
        """
        Compute box statistics for violin plots using full data range for min/max.

        MIN and MAX are taken from the actual data extrema (no Tukey clipping),
        while quartiles (Q1, Q2, Q3) still follow the standard percentile
        definition. This is useful for Matplotlib violin plots where we want
        the extrema to match Series.describe() style summaries.
        """
        values = np.asarray(values)
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return {
                MaidrKey.MIN.value: 0.0,
                MaidrKey.Q1.value: 0.0,
                MaidrKey.Q2.value: 0.0,
                MaidrKey.Q3.value: 0.0,
                MaidrKey.MAX.value: 0.0,
                MaidrKey.MEAN.value: 0.0,
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.UPPER_OUTLIER.value: [],
            }

        sorted_values = np.sort(values)

        q1 = float(np.percentile(sorted_values, 25))
        q2 = float(np.percentile(sorted_values, 50))
        q3 = float(np.percentile(sorted_values, 75))
        mean_val = float(np.mean(sorted_values))

        min_val = float(sorted_values[0])
        max_val = float(sorted_values[-1])

        return {
            MaidrKey.MIN.value: min_val,
            MaidrKey.Q1.value: q1,
            MaidrKey.Q2.value: q2,
            MaidrKey.Q3.value: q3,
            MaidrKey.MAX.value: max_val,
            MaidrKey.MEAN.value: mean_val,
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.UPPER_OUTLIER.value: [],
        }


class ViolinPositionExtractor:
    """
    Extracts violin plot center positions from rendered matplotlib axes.

    This utility class provides methods to determine the center positions of violins
    in a seaborn or matplotlib violin plot, given the axes, number of groups, and orientation.
    It supports both vertical and horizontal orientations and can match positions to group
    names based on tick labels.

    Methods
    -------
    extract_positions(ax, num_groups, orientation)
        Extracts the center positions of violins from the axes.
    match_to_groups(ax, groups, positions, orientation)
        Matches positions to groups based on tick labels to ensure correct ordering.
    """

    # Thresholds for detecting violin internal rectangles
    VIOLIN_RECT_MIN_WIDTH = 0.05  # Exclude very thin artifacts
    VIOLIN_RECT_MAX_WIDTH = 1.2   # Exclude wide non-violin elements

    @staticmethod
    def extract_positions(ax: Axes, num_groups: int, orientation: str) -> List[float]:
        """
        Extract seaborn's real violin center positions from Rectangle artists or PolyCollection.

        Parameters
        ----------
        ax : Axes
            Matplotlib axes object containing the rendered violin plot
        num_groups : int
            Expected number of violin groups
        orientation : str
            Orientation: "vert" for vertical, "horz" for horizontal

        Returns
        -------
        List[float]
            List of center positions for each violin
        """
        positions = []

        if orientation == "vert":
            # Try to extract from Rectangle artists first (multi-violin plots)
            for child in ax.get_children():
                if isinstance(child, Rectangle):
                    w, h = child.get_width(), child.get_height()
                    # Violin internal rectangles tend to be narrow and tall-ish
                    # Width threshold: > 0.05 to exclude very thin artifacts, < 1.2 to exclude wide elements
                    # Height threshold: > 0 to ensure valid rectangles (matplotlib sometimes creates zero-height ones)
                    if ViolinPositionExtractor.VIOLIN_RECT_MIN_WIDTH < w < ViolinPositionExtractor.VIOLIN_RECT_MAX_WIDTH and h > 0:
                        positions.append(child.get_x() + w / 2)
            # If no rectangles found, try to extract from all PolyCollections/PathPatches
            if not positions:
                for child in ax.get_children():
                    if isinstance(child, (PolyCollection, PathPatch)):
                        if isinstance(child, PolyCollection):
                            paths = child.get_paths()
                            verts = paths[0].vertices if paths else None
                        else:  # PathPatch
                            path = child.get_path()
                            verts = path.vertices if hasattr(path, "vertices") else None
                        if verts is not None and len(verts) > 0:
                            x_coords = verts[:, 0]
                            if len(x_coords) > 0:
                                center_x = (x_coords.min() + x_coords.max()) / 2
                                positions.append(float(center_x))
                # Fallback to X-axis tick positions only if no centers were found
                if not positions:
                    x_ticks = ax.get_xticks()
                    if len(x_ticks) > 0:
                        # Use first N tick positions as approximate centers
                        positions = [float(x_ticks[i]) for i in range(min(len(x_ticks), num_groups))]
                    else:
                        # Last resort: use sequential indices
                        positions = [float(i) for i in range(num_groups)]
        else:
            # Horizontal orientation (similar logic but for Y-axis)
            for child in ax.get_children():
                if isinstance(child, Rectangle):
                    w, h = child.get_width(), child.get_height()
                    # Apply same dimension thresholds as vertical orientation
                    # Height threshold: > 0.05 to exclude very thin artifacts, < 1.2 to exclude wide elements
                    # Width threshold: > 0 to ensure valid rectangles
                    if ViolinPositionExtractor.VIOLIN_RECT_MIN_WIDTH < h < ViolinPositionExtractor.VIOLIN_RECT_MAX_WIDTH and w > 0:
                        positions.append(child.get_y() + h / 2)

            if not positions:
                for child in ax.get_children():
                    if isinstance(child, (PolyCollection, PathPatch)):
                        if isinstance(child, PolyCollection):
                            paths = child.get_paths()
                            verts = paths[0].vertices if paths else None
                        else:
                            path = child.get_path()
                            verts = path.vertices if hasattr(path, "vertices") else None
                        if verts is not None and len(verts) > 0:
                            y_coords = verts[:, 1]
                            if len(y_coords) > 0:
                                center_y = (y_coords.min() + y_coords.max()) / 2
                                positions.append(float(center_y))
                if not positions:
                    y_ticks = ax.get_yticks()
                    if len(y_ticks) > 0:
                        positions = [float(y_ticks[i]) for i in range(min(len(y_ticks), num_groups))]
                    else:
                        positions = [float(i) for i in range(num_groups)]

        positions = sorted(set(positions))

        if len(positions) < num_groups:
            # fallback - use tick positions or default
            if orientation == "vert":
                x_ticks = ax.get_xticks()
                if len(x_ticks) >= num_groups:
                    return [float(x_ticks[i]) for i in range(num_groups)]
            else:
                y_ticks = ax.get_yticks()
                if len(y_ticks) >= num_groups:
                    return [float(y_ticks[i]) for i in range(num_groups)]
            return [float(i) for i in range(num_groups)]

        return positions[:num_groups]

    @staticmethod
    def match_to_groups(ax: Axes, groups: List[str], positions: List[float], orientation: str) -> List[float]:
        """
        Match positions to groups based on tick labels to ensure correct ordering.
        
        This ensures that when groups are extracted in a specific order (e.g., from the 'order'
        parameter), the positions are matched correctly to match the visual order of violins
        on the plot.

        Parameters
        ----------
        ax : Axes
            Matplotlib axes object
        groups : List[str]
            List of group names (should be in the same order as tick labels)
        positions : List[float]
            List of extracted positions (may be in different order)
        orientation : str
            Orientation: "vert" for vertical, "horz" for horizontal

        Returns
        -------
        List[float]
            List of matched positions in the order of groups, or original positions if matching fails
        """
        if orientation == "vert":
            tick_labels = [t.get_text() for t in ax.get_xticklabels()]
            tick_positions = ax.get_xticks()
        else:
            tick_labels = [t.get_text() for t in ax.get_yticklabels()]
            tick_positions = ax.get_yticks()

        # If we have the same number of groups and tick labels, match positions based on tick labels
        # tick_positions from ax.get_xticks()/get_yticks() are already in the correct visual order
        # matching the tick_labels order
        if len(tick_labels) == len(groups):
            matched = []
            for group in groups:
                try:
                    # Find the index of this group in tick_labels (which respects the 'order' parameter)
                    tick_idx = tick_labels.index(group)
                    # tick_positions are already in the correct order matching tick_labels
                    # Use tick_positions directly as they represent the actual visual positions
                    matched.append(float(tick_positions[tick_idx]))
                except ValueError:
                    # Group not found in tick labels - skip
                    pass
            
            # If we successfully matched all groups, return matched positions
            if len(matched) == len(groups):
                return matched
        
        # Fallback: if matching failed, use extracted positions as-is
        # But limit to the number of groups we have
        return positions[:len(groups)] if positions else []


class SyntheticBoxPlotBuilder:
    """
    Utility class for building synthetic box plot artist objects from statistics.

    This class provides static methods to construct synthetic box plot artists
    (such as rectangles and lines) from precomputed box plot statistics. It is
    useful for programmatically generating box plot visuals when the underlying
    data is not directly available, or when custom rendering is required.

    Methods
    -------
    build(stats_list, vert, positions)
        Build synthetic box plot artists from statistics.
    _rect_to_pathpatch(rect)
        Convert a Rectangle to a PathPatch for compatibility with set_gid.

    Examples
    --------
    >>> from maidr.core.plot.violinplot import SyntheticBoxPlotBuilder
    >>> from maidr.core.enum import MaidrKey
    >>> stats_list = [
    ...     {
    ...         MaidrKey.MIN.value: 2.0,
    ...         MaidrKey.Q1.value: 3.0,
    ...         MaidrKey.Q2.value: 5.0,
    ...         MaidrKey.Q3.value: 7.0,
    ...         MaidrKey.MAX.value: 8.0,
    ...         MaidrKey.LOWER_OUTLIER.value: [],
    ...         MaidrKey.UPPER_OUTLIER.value: [],
    ...     },
    ...     {
    ...         MaidrKey.MIN.value: 3.0,
    ...         MaidrKey.Q1.value: 4.0,
    ...         MaidrKey.Q2.value: 6.0,
    ...         MaidrKey.Q3.value: 8.0,
    ...         MaidrKey.MAX.value: 9.0,
    ...         MaidrKey.LOWER_OUTLIER.value: [],
    ...         MaidrKey.UPPER_OUTLIER.value: [],
    ...     }
    ... ]
    >>> positions = [0.0, 1.0]
    >>> artists = SyntheticBoxPlotBuilder.build(stats_list, vert=True, positions=positions)
    >>> # artists['boxes'], artists['medians'], etc. now contain matplotlib artist objects
    >>> print(list(artists.keys()))
    ['boxes', 'medians', 'whiskers', 'caps', 'fliers']
    """

    # Box plot rendering constants
    BOX_HALF_WIDTH = 0.25  # Half-width of box rectangles as fraction of inter-box distance
    CAP_WIDTH_MULTIPLIER = 0.4  # Multiplier for cap width relative to box half-width

    @staticmethod
    def _rect_to_pathpatch(rect: Rectangle) -> PathPatch:
        """
        Convert a matplotlib Rectangle to a PathPatch.

        This is useful for creating a PathPatch from a Rectangle, which allows
        additional methods such as `set_gid` to be used for identification.

        Parameters
        ----------
        rect : Rectangle
            A matplotlib.patches.Rectangle instance to convert.

        Returns
        -------
        PathPatch
            A PathPatch object representing the same rectangle.

        Examples
        --------
        >>> from matplotlib.patches import Rectangle
        >>> rect = Rectangle((0, 0), 1, 2)
        >>> patch = SyntheticBoxPlotBuilder._rect_to_pathpatch(rect)
        >>> isinstance(patch, PathPatch)
        True
        """
        x, y = rect.get_xy()
        w, h = rect.get_width(), rect.get_height()

        verts = [
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h],
            [x, y],
        ]
        codes = [
            mpath.Path.MOVETO,
            mpath.Path.LINETO,
            mpath.Path.LINETO,
            mpath.Path.LINETO,
            mpath.Path.CLOSEPOLY
        ]
        path = mpath.Path(verts, codes)
        return PathPatch(path)

    @staticmethod
    def build(stats_list: List[Dict[str, Any]], vert: bool, positions: List[float]) -> Dict[str, List]:
        """
        Build synthetic bxp_stats dictionary from computed statistics.

        Creates matplotlib artist objects (PathPatch for boxes, Line2D for medians,
        whiskers, and caps) that can be used with MAIDR's BoxPlot class.

        Parameters
        ----------
        stats_list : List[Dict[str, Any]]
            List of statistics dictionaries, each containing min, q1, q2, q3, max
        vert : bool
            Whether the plot is vertical (True) or horizontal (False)
        positions : List[float]
            List of center positions for each box

        Returns
        -------
        Dict[str, List]
            Dictionary with keys: "boxes", "medians", "whiskers", "caps", "fliers"
            matching the format expected by matplotlib's bxp_stats
        """
        boxes, medians, whiskers, caps, means = [], [], [], [], []
        halfwidth = SyntheticBoxPlotBuilder.BOX_HALF_WIDTH

        for stats, center in zip(stats_list, positions):
            # --- box rectangle ---
            if vert:
                rect = Rectangle(
                    (center - halfwidth, stats[MaidrKey.Q1.value]),
                    2 * halfwidth,
                    stats[MaidrKey.Q3.value] - stats[MaidrKey.Q1.value],
                )
            else:
                rect = Rectangle(
                    (stats[MaidrKey.Q1.value], center - halfwidth),
                    stats[MaidrKey.Q3.value] - stats[MaidrKey.Q1.value],
                    2 * halfwidth,
                )
            boxes.append(SyntheticBoxPlotBuilder._rect_to_pathpatch(rect))

            # --- median ---
            if vert:
                med = Line2D(
                    [center - halfwidth, center + halfwidth],
                    [stats[MaidrKey.Q2.value], stats[MaidrKey.Q2.value]],
                )
            else:
                med = Line2D(
                    [stats[MaidrKey.Q2.value], stats[MaidrKey.Q2.value]],
                    [center - halfwidth, center + halfwidth],
                )
            medians.append(med)

            # --- whiskers ---
            if vert:
                wmin = Line2D([center, center], [stats[MaidrKey.MIN.value], stats[MaidrKey.Q1.value]])
                wmax = Line2D([center, center], [stats[MaidrKey.Q3.value], stats[MaidrKey.MAX.value]])
            else:
                wmin = Line2D([stats[MaidrKey.MIN.value], stats[MaidrKey.Q1.value]], [center, center])
                wmax = Line2D([stats[MaidrKey.Q3.value], stats[MaidrKey.MAX.value]], [center, center])
            whiskers.extend([wmin, wmax])

            # --- caps ---
            capw = halfwidth * SyntheticBoxPlotBuilder.CAP_WIDTH_MULTIPLIER
            if vert:
                cmin = Line2D([center - capw, center + capw], [stats[MaidrKey.MIN.value], stats[MaidrKey.MIN.value]])
                cmax = Line2D([center - capw, center + capw], [stats[MaidrKey.MAX.value], stats[MaidrKey.MAX.value]])
            else:
                cmin = Line2D([stats[MaidrKey.MIN.value], stats[MaidrKey.MIN.value]], [center - capw, center + capw])
                cmax = Line2D([stats[MaidrKey.MAX.value], stats[MaidrKey.MAX.value]], [center - capw, center + capw])
            caps.extend([cmin, cmax])

            # --- mean (optional) ---
            if MaidrKey.MEAN.value in stats:
                if vert:
                    mean_line = Line2D(
                        [center - halfwidth, center + halfwidth],
                        [stats[MaidrKey.MEAN.value], stats[MaidrKey.MEAN.value]],
                    )
                else:
                    mean_line = Line2D(
                        [stats[MaidrKey.MEAN.value], stats[MaidrKey.MEAN.value]],
                        [center - halfwidth, center + halfwidth],
                    )
                means.append(mean_line)

        return {
            "boxes": boxes,
            "medians": medians,
            "whiskers": whiskers,
            "caps": caps,
            "fliers": [],
            "means": means,
        }


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
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, PathPatch
from matplotlib import path as mpath
from typing import Tuple, List, Dict, Any

from maidr.core.enum import MaidrKey


class ViolinDataExtractor:
    """Utility class for extracting raw data from seaborn violinplot arguments."""

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
    """Utility class for computing Tukey box plot statistics from raw data."""

    @staticmethod
    def compute(values: np.ndarray) -> Dict[str, Any]:
        """
        Compute Tukey box stats matching matplotlib's method.

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

        # Calculate Tukey fences (1.5 * IQR rule)
        lw = q1 - 1.5 * iqr  # Lower fence
        uw = q3 + 1.5 * iqr  # Upper fence

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
        return {
            MaidrKey.MIN.value: min_val,
            MaidrKey.Q1.value: q1,
            MaidrKey.Q2.value: q2,
            MaidrKey.Q3.value: q3,
            MaidrKey.MAX.value: max_val,
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.UPPER_OUTLIER.value: [],
        }


class ViolinPositionExtractor:
    """Utility class for extracting violin plot positions from rendered axes."""

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
                    if 0.05 < w < 1.2 and h > 0:
                        positions.append(child.get_x() + w / 2)
            
            # If no rectangles found, try to extract from PolyCollection (violin shapes)
            # or use X-axis tick positions
            if not positions:
                # For single violin plots, check PolyCollection or PathPatch
                from matplotlib.collections import PolyCollection
                from matplotlib.patches import PathPatch
                for child in ax.get_children():
                    if isinstance(child, (PolyCollection, PathPatch)):
                        # Try to get center X position from vertices/path
                        if isinstance(child, PolyCollection):
                            verts = child.get_paths()[0].vertices if child.get_paths() else None
                        else:  # PathPatch
                            verts = child.get_path().vertices if hasattr(child.get_path(), 'vertices') else None
                        
                        if verts is not None and len(verts) > 0:
                            # Get X coordinate from vertices (assume symmetric violin)
                            x_coords = verts[:, 0]
                            if len(x_coords) > 0:
                                center_x = (x_coords.min() + x_coords.max()) / 2
                                positions.append(float(center_x))
                                break
                
                # Fallback to X-axis tick positions
                if not positions:
                    x_ticks = ax.get_xticks()
                    if len(x_ticks) > 0:
                        # Use first tick position for single violin
                        positions = [float(x_ticks[0])]
                    else:
                        # Last resort: use 0 for single violin
                        positions = [0.0]
        else:
            # Horizontal orientation (similar logic but for Y-axis)
            for child in ax.get_children():
                if isinstance(child, Rectangle):
                    w, h = child.get_width(), child.get_height()
                    if 0.05 < h < 1.2 and w > 0:
                        positions.append(child.get_y() + h / 2)
            
            if not positions:
                from matplotlib.collections import PolyCollection
                from matplotlib.patches import PathPatch
                for child in ax.get_children():
                    if isinstance(child, (PolyCollection, PathPatch)):
                        if isinstance(child, PolyCollection):
                            verts = child.get_paths()[0].vertices if child.get_paths() else None
                        else:
                            verts = child.get_path().vertices if hasattr(child.get_path(), 'vertices') else None
                        
                        if verts is not None and len(verts) > 0:
                            y_coords = verts[:, 1]
                            if len(y_coords) > 0:
                                center_y = (y_coords.min() + y_coords.max()) / 2
                                positions.append(float(center_y))
                                break
                
                if not positions:
                    y_ticks = ax.get_yticks()
                    if len(y_ticks) > 0:
                        positions = [float(y_ticks[0])]
                    else:
                        positions = [0.0]

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
    """Utility class for building synthetic box plot artist objects from statistics."""

    @staticmethod
    def _rect_to_pathpatch(rect: Rectangle) -> PathPatch:
        """Convert Rectangle to PathPatch (has set_gid method)."""
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
        boxes, medians, whiskers, caps = [], [], [], []
        halfwidth = 0.25

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
            capw = halfwidth * 0.4
            if vert:
                cmin = Line2D([center - capw, center + capw], [stats[MaidrKey.MIN.value], stats[MaidrKey.MIN.value]])
                cmax = Line2D([center - capw, center + capw], [stats[MaidrKey.MAX.value], stats[MaidrKey.MAX.value]])
            else:
                cmin = Line2D([stats[MaidrKey.MIN.value], stats[MaidrKey.MIN.value]], [center - capw, center + capw])
                cmax = Line2D([stats[MaidrKey.MAX.value], stats[MaidrKey.MAX.value]], [center - capw, center + capw])
            caps.extend([cmin, cmax])

        return {
            "boxes": boxes,
            "medians": medians,
            "whiskers": whiskers,
            "caps": caps,
            "fliers": [],
        }


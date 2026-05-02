"""
Utility classes for handling violin plot data extraction and processing.

This module provides utilities for extracting data from seaborn/matplotlib
violinplot arguments, computing box plot statistics, and extracting violin
positions. Registration with MAIDR is handled by the patch layer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection
from matplotlib.patches import PathPatch, Rectangle

from maidr.core.enum import MaidrKey


class ViolinDataExtractor:
    """
    Extract raw data groups and values from seaborn violinplot arguments.

    Examples
    --------
    >>> df = pd.DataFrame({"group": ["A", "A", "B", "B"], "value": [1, 2, 3, 4]})
    >>> groups, values = ViolinDataExtractor.extract((), {"data": df, "x": "group", "y": "value"})
    >>> groups
    ['A', 'B']
    """

    @staticmethod
    def extract(
        args: Tuple[Any, ...], kwargs: Dict[str, Any]
    ) -> Tuple[List[str], List[np.ndarray]]:
        """
        Extract groups and values from seaborn.violinplot arguments.

        Parameters
        ----------
        args : tuple
            Positional arguments passed to violinplot.
        kwargs : dict
            Keyword arguments passed to violinplot.

        Returns
        -------
        tuple[list[str], list[np.ndarray]]
            ``(groups, values)`` where *groups* is a list of group names
            and *values* is a list of numpy arrays for each group.
        """
        df = kwargs.get("data", None)
        x = kwargs.get("x", None)
        y = kwargs.get("y", None)
        hue = kwargs.get("hue", None)
        orient = kwargs.get("orient", None)

        # For horizontal orientation the roles of x and y are swapped:
        # x holds the numeric values and y holds the categorical groups.
        is_horizontal = orient in ("h", "horizontal", "y")
        if is_horizontal and isinstance(x, str) and isinstance(y, str):
            cat_col, val_col = y, x
        else:
            cat_col, val_col = x, y

        # Case 1 — DataFrame with categorical & value columns
        if (
            isinstance(df, pd.DataFrame)
            and isinstance(cat_col, str)
            and isinstance(val_col, str)
        ):
            groups: list[str] = []
            values: list[np.ndarray] = []

            x_order = kwargs.get("order", None)
            hue_order = kwargs.get("hue_order", None) if hue else None

            if hue is None:
                if x_order is not None:
                    for g in x_order:
                        gdf = df[df[cat_col] == g]
                        if not gdf.empty:
                            groups.append(str(g))
                            values.append(gdf[val_col].dropna().values)
                else:
                    for g, gdf in df.groupby(cat_col, observed=False):
                        groups.append(str(g))
                        values.append(gdf[val_col].dropna().values)
            else:
                # When hue is the same column as the category, avoid
                # duplicated labels like "Fair_Fair".
                hue_is_cat = (hue == cat_col)

                if x_order is not None or hue_order is not None:
                    x_cats = (
                        x_order if x_order is not None else df[cat_col].unique()
                    )
                    h_cats = (
                        hue_order if hue_order is not None else df[hue].unique()
                    )
                    for gx in x_cats:
                        for gh in h_cats:
                            gdf = df[(df[cat_col] == gx) & (df[hue] == gh)]
                            if not gdf.empty:
                                label = str(gx) if hue_is_cat else f"{gx}_{gh}"
                                groups.append(label)
                                values.append(gdf[val_col].dropna().values)
                else:
                    for (gx, gh), gdf in df.groupby(
                        [cat_col, hue], observed=False
                    ):
                        label = str(gx) if hue_is_cat else f"{gx}_{gh}"
                        groups.append(label)
                        values.append(gdf[val_col].dropna().values)
            return groups, values

        # Case 2 — DataFrame, only value column → single violin
        if isinstance(df, pd.DataFrame) and isinstance(val_col, str):
            return ["Violin"], [df[val_col].dropna().values]

        # Case 3 — list/array as positional arg
        if len(args) > 0:
            data = args[0]
            if isinstance(data, (list, tuple, np.ndarray)):
                if len(data) > 0 and isinstance(data[0], (list, tuple, np.ndarray)):
                    return (
                        [f"Group {i + 1}" for i in range(len(data))],
                        [np.asarray(d).flatten() for d in data],
                    )
                return ["Violin"], [np.asarray(data).flatten()]

        # Case 4 — data= (non-DataFrame)
        if "data" in kwargs and not isinstance(kwargs["data"], pd.DataFrame):
            data = kwargs["data"]
            if isinstance(data, (list, tuple)):
                return (
                    [f"Group {i + 1}" for i in range(len(data))],
                    [np.asarray(d).flatten() for d in data],
                )

        # Case 5 — y=array
        if (
            y is not None
            and not isinstance(y, str)
            and isinstance(y, (list, tuple, np.ndarray))
        ):
            return ["Violin"], [np.asarray(y).flatten()]

        # Case 6 — x=array
        if (
            x is not None
            and not isinstance(x, str)
            and isinstance(x, (list, tuple, np.ndarray))
        ):
            return ["Violin"], [np.asarray(x).flatten()]

        return [], []


class ViolinBoxStatsCalculator:
    """
    Compute Tukey-style box plot statistics from raw data.

    Examples
    --------
    >>> stats = ViolinBoxStatsCalculator.compute(np.array([1, 2, 3, 4, 5, 6, 7, 8, 9]))
    >>> stats["q2"]
    5.0
    """

    TUKEY_FENCE_MULTIPLIER = 1.5

    @staticmethod
    def compute(values: np.ndarray) -> Dict[str, Any]:
        """
        Compute Tukey box stats (seaborn convention).

        Min/max are the extreme values *within* the Tukey fences.
        """
        values = np.asarray(values)
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return ViolinBoxStatsCalculator._empty_stats()

        sorted_vals = np.sort(values)
        q1 = float(np.percentile(sorted_vals, 25))
        q2 = float(np.percentile(sorted_vals, 50))
        q3 = float(np.percentile(sorted_vals, 75))
        iqr = q3 - q1

        lw = q1 - ViolinBoxStatsCalculator.TUKEY_FENCE_MULTIPLIER * iqr
        uw = q3 + ViolinBoxStatsCalculator.TUKEY_FENCE_MULTIPLIER * iqr

        clipped = values[(values >= lw) & (values <= uw)]
        if len(clipped) > 0:
            min_val = float(clipped.min())
            max_val = float(clipped.max())
        else:
            min_val = float(values.min())
            max_val = float(values.max())

        return {
            MaidrKey.MIN.value: min_val,
            MaidrKey.Q1.value: q1,
            MaidrKey.Q2.value: q2,
            MaidrKey.Q3.value: q3,
            MaidrKey.MAX.value: max_val,
            MaidrKey.MEAN.value: float(np.mean(sorted_vals)),
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.UPPER_OUTLIER.value: [],
        }

    @staticmethod
    def compute_full_range(values: np.ndarray) -> Dict[str, Any]:
        """
        Compute box stats using full data range for min/max (matplotlib convention).
        """
        values = np.asarray(values)
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return ViolinBoxStatsCalculator._empty_stats()

        sorted_vals = np.sort(values)
        return {
            MaidrKey.MIN.value: float(sorted_vals[0]),
            MaidrKey.Q1.value: float(np.percentile(sorted_vals, 25)),
            MaidrKey.Q2.value: float(np.percentile(sorted_vals, 50)),
            MaidrKey.Q3.value: float(np.percentile(sorted_vals, 75)),
            MaidrKey.MAX.value: float(sorted_vals[-1]),
            MaidrKey.MEAN.value: float(np.mean(sorted_vals)),
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.UPPER_OUTLIER.value: [],
        }

    @staticmethod
    def _empty_stats() -> Dict[str, Any]:
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


class ViolinPositionExtractor:
    """
    Extract violin plot center positions from rendered matplotlib axes.
    """

    VIOLIN_RECT_MIN_WIDTH = 0.05
    VIOLIN_RECT_MAX_WIDTH = 1.2

    @staticmethod
    def extract_positions(ax: Axes, num_groups: int, orientation: str) -> List[float]:
        """
        Extract center positions of violins from Rectangle or PolyCollection artists.

        Parameters
        ----------
        ax : Axes
            Matplotlib axes with the rendered violin plot.
        num_groups : int
            Expected number of violin groups.
        orientation : str
            ``"vert"`` or ``"horz"``.

        Returns
        -------
        list[float]
            Center positions for each violin.
        """
        positions: list[float] = []
        use_x = orientation == "vert"

        # Try Rectangle artists first.
        for child in ax.get_children():
            if isinstance(child, Rectangle):
                w, h = child.get_width(), child.get_height()
                dim = w if use_x else h
                other = h if use_x else w
                mn = ViolinPositionExtractor.VIOLIN_RECT_MIN_WIDTH
                mx = ViolinPositionExtractor.VIOLIN_RECT_MAX_WIDTH
                if mn < dim < mx and other > 0:
                    if use_x:
                        positions.append(child.get_x() + w / 2)
                    else:
                        positions.append(child.get_y() + h / 2)

        # Fallback: PolyCollection / PathPatch centres.
        if not positions:
            for child in ax.get_children():
                if isinstance(child, (PolyCollection, PathPatch)):
                    verts = ViolinPositionExtractor._get_vertices(child)
                    if verts is not None and len(verts) > 0:
                        coords = verts[:, 0] if use_x else verts[:, 1]
                        if len(coords) > 0:
                            positions.append(float((coords.min() + coords.max()) / 2))

        # Fallback: tick positions.
        if not positions:
            ticks = ax.get_xticks() if use_x else ax.get_yticks()
            if len(ticks) > 0:
                positions = [
                    float(ticks[i]) for i in range(min(len(ticks), num_groups))
                ]
            else:
                positions = [float(i) for i in range(num_groups)]

        positions = sorted(set(positions))

        if len(positions) < num_groups:
            ticks = ax.get_xticks() if use_x else ax.get_yticks()
            if len(ticks) >= num_groups:
                return [float(ticks[i]) for i in range(num_groups)]
            return [float(i) for i in range(num_groups)]

        return positions[:num_groups]

    @staticmethod
    def match_to_groups(
        ax: Axes,
        groups: List[str],
        positions: List[float],
        orientation: str,
    ) -> List[float]:
        """Match extracted positions to groups via tick labels."""
        if orientation == "vert":
            tick_labels = [t.get_text() for t in ax.get_xticklabels()]
            tick_positions = ax.get_xticks()
        else:
            tick_labels = [t.get_text() for t in ax.get_yticklabels()]
            tick_positions = ax.get_yticks()

        if len(tick_labels) == len(groups):
            matched: list[float] = []
            for group in groups:
                try:
                    idx = tick_labels.index(group)
                    matched.append(float(tick_positions[idx]))
                except ValueError:
                    pass
            if len(matched) == len(groups):
                return matched

        return positions[: len(groups)] if positions else []

    # ------------------------------------------------------------------
    @staticmethod
    def _get_vertices(child: Any) -> np.ndarray | None:
        if isinstance(child, PolyCollection):
            paths = child.get_paths()
            return paths[0].vertices if paths else None
        if isinstance(child, PathPatch):
            path = child.get_path()
            return path.vertices if hasattr(path, "vertices") else None
        return None

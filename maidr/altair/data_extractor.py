"""Extract MAIDR-format data from Vega-Lite specifications."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from maidr.core.enum import MaidrKey, PlotType
from maidr.altair.utils import (
    get_axis_title,
    get_encoding_aggregate,
    get_encoding_bin,
    get_encoding_field,
    get_encoding_stack,
    get_mark_type,
    resolve_data,
)


def extract_chart_data(spec: dict) -> dict:
    """Extract MAIDR schema data from a single Vega-Lite unit spec.

    Returns a dict with keys: type, title, axes, data, selectors.
    """
    mark = get_mark_type(spec)
    encoding = spec.get("encoding", {})
    transforms = spec.get("transform", [])
    title = spec.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")

    plot_type = _detect_plot_type(mark, encoding, transforms)
    df = resolve_data(spec)

    axes = _extract_axes(encoding, plot_type)
    data = _extract_data_for_type(plot_type, spec, df, encoding, transforms)

    schema: dict[str, Any] = {
        MaidrKey.TYPE: plot_type.value,
        MaidrKey.TITLE: title,
        MaidrKey.AXES: axes,
        MaidrKey.DATA: data,
        MaidrKey.SELECTOR: "",
    }

    # Add labels for heatmap
    if plot_type == PlotType.HEAT:
        color_title = get_axis_title(encoding, "color")
        schema[MaidrKey.LABELS] = {MaidrKey.FILL: color_title}

    # Add orientation for box plots
    if plot_type == PlotType.BOX:
        x_type = encoding.get("x", {}).get("type", "")
        if x_type == "quantitative":
            schema[MaidrKey.ORIENTATION] = "horiz"
        else:
            schema[MaidrKey.ORIENTATION] = "vert"

    return schema


def _detect_plot_type(mark: str, encoding: dict, transforms: list) -> PlotType:
    """Detect the MAIDR PlotType from mark, encoding, and transforms."""
    if mark == "boxplot":
        return PlotType.BOX

    if mark == "rect":
        return PlotType.HEAT

    if mark in ("point", "circle", "square"):
        return PlotType.SCATTER

    if mark == "line":
        # Check if this is a density/KDE transform
        for t in transforms:
            if "density" in t:
                return PlotType.SMOOTH
            if "loess" in t:
                return PlotType.SMOOTH
        return PlotType.LINE

    if mark in ("bar",):
        # Check for histogram (binned x-axis)
        x_bin = get_encoding_bin(encoding, "x")
        if x_bin:
            return PlotType.HIST

        # Check for stacked/dodged (color encoding present)
        color_field = get_encoding_field(encoding, "color")
        x_offset = get_encoding_field(encoding, "xOffset")

        if x_offset:
            return PlotType.DODGED

        if color_field:
            stack = get_encoding_stack(encoding, "y")
            if stack is False or stack == "false":
                return PlotType.DODGED
            return PlotType.STACKED

        return PlotType.BAR

    if mark == "area":
        return PlotType.LINE

    return PlotType.BAR


def _extract_axes(encoding: dict, plot_type: PlotType) -> dict:
    """Extract axis labels from encoding."""
    axes: dict[str, Any] = {}

    if plot_type == PlotType.HEAT:
        axes[MaidrKey.X] = get_axis_title(encoding, "x")
        axes[MaidrKey.Y] = get_axis_title(encoding, "y")
        axes[MaidrKey.FILL] = get_axis_title(encoding, "color")
    elif plot_type == PlotType.BOX:
        x_type = encoding.get("x", {}).get("type", "")
        if x_type == "quantitative":
            axes[MaidrKey.X] = get_axis_title(encoding, "x")
            axes[MaidrKey.Y] = get_axis_title(encoding, "y")
        else:
            axes[MaidrKey.X] = get_axis_title(encoding, "x")
            axes[MaidrKey.Y] = get_axis_title(encoding, "y")
    else:
        axes[MaidrKey.X] = get_axis_title(encoding, "x")
        axes[MaidrKey.Y] = get_axis_title(encoding, "y")

    return axes


def _extract_data_for_type(
    plot_type: PlotType,
    spec: dict,
    df: pd.DataFrame,
    encoding: dict,
    transforms: list,
) -> list | dict:
    """Route to the correct data extraction method based on plot type."""
    if plot_type == PlotType.BAR:
        return _extract_bar_data(df, encoding)
    elif plot_type == PlotType.SCATTER:
        return _extract_scatter_data(df, encoding)
    elif plot_type == PlotType.LINE:
        return _extract_line_data(df, encoding)
    elif plot_type == PlotType.HEAT:
        return _extract_heatmap_data(df, encoding)
    elif plot_type == PlotType.HIST:
        return _extract_histogram_data(df, encoding)
    elif plot_type == PlotType.BOX:
        return _extract_box_data(df, encoding)
    elif plot_type in (PlotType.STACKED, PlotType.DODGED):
        return _extract_grouped_bar_data(df, encoding)
    elif plot_type == PlotType.SMOOTH:
        return _extract_smooth_data(df, encoding, transforms)
    else:
        return _extract_bar_data(df, encoding)


def _extract_bar_data(df: pd.DataFrame, encoding: dict) -> list[dict]:
    """Extract bar chart data."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    y_agg = get_encoding_aggregate(encoding, "y")

    if df.empty:
        return []

    if y_agg == "count" or y_field is None:
        # Count plot: aggregate by x field
        if x_field and x_field in df.columns:
            counts = df[x_field].value_counts().sort_index()
            return [
                {MaidrKey.X: str(cat), MaidrKey.Y: float(count)}
                for cat, count in counts.items()
            ]
        return []

    if y_agg and y_field and x_field:
        # Aggregated bar (e.g., mean, sum)
        grouped = df.groupby(x_field, sort=False)[y_field].agg(y_agg).reset_index()
        return [
            {MaidrKey.X: str(row[x_field]), MaidrKey.Y: _to_num(row[y_field])}
            for _, row in grouped.iterrows()
        ]

    if x_field and y_field:
        return [
            {MaidrKey.X: str(row[x_field]), MaidrKey.Y: _to_num(row[y_field])}
            for _, row in df.iterrows()
        ]

    return []


def _extract_scatter_data(df: pd.DataFrame, encoding: dict) -> list[dict]:
    """Extract scatter plot data."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")

    if df.empty or not x_field or not y_field:
        return []

    return [
        {MaidrKey.X: _to_num(row[x_field]), MaidrKey.Y: _to_num(row[y_field])}
        for _, row in df.iterrows()
    ]


def _extract_line_data(df: pd.DataFrame, encoding: dict) -> list[list[dict]]:
    """Extract line chart data. Returns list of lists for multi-line support."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    color_field = get_encoding_field(encoding, "color")

    if df.empty or not x_field or not y_field:
        return [[]]

    if color_field and color_field in df.columns:
        # Multi-line: group by color field
        result = []
        for group_name, group_df in df.groupby(color_field, sort=False):
            group_df = group_df.sort_values(x_field)
            line_data = [
                {
                    MaidrKey.X: _to_str_or_num(row[x_field]),
                    MaidrKey.Y: _to_num(row[y_field]),
                    MaidrKey.FILL: str(group_name),
                }
                for _, row in group_df.iterrows()
            ]
            result.append(line_data)
        return result

    # Single line
    sorted_df = df.sort_values(x_field)
    line_data = [
        {
            MaidrKey.X: _to_str_or_num(row[x_field]),
            MaidrKey.Y: _to_num(row[y_field]),
        }
        for _, row in sorted_df.iterrows()
    ]
    return [line_data]


def _extract_heatmap_data(df: pd.DataFrame, encoding: dict) -> dict:
    """Extract heatmap data as {points, x, y}."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    color_field = get_encoding_field(encoding, "color")

    if df.empty or not x_field or not y_field or not color_field:
        return {MaidrKey.POINTS: [], MaidrKey.X: [], MaidrKey.Y: []}

    # Get unique x and y values preserving order
    x_vals = list(df[x_field].unique())
    y_vals = list(df[y_field].unique())

    # Build 2D points array
    pivot = df.pivot_table(
        index=y_field, columns=x_field, values=color_field, aggfunc="first"
    )
    # Reindex to match original order
    pivot = pivot.reindex(index=y_vals, columns=x_vals)
    points = pivot.fillna(0).values.tolist()

    return {
        MaidrKey.POINTS: points,
        MaidrKey.X: [str(v) for v in x_vals],
        MaidrKey.Y: [str(v) for v in y_vals],
    }


def _extract_histogram_data(df: pd.DataFrame, encoding: dict) -> list[dict]:
    """Extract histogram data with bin edges."""
    x_field = get_encoding_field(encoding, "x")
    x_bin = get_encoding_bin(encoding, "x")

    if df.empty or not x_field or not x_bin:
        return []

    # Determine number of bins
    maxbins = 10
    if isinstance(x_bin, dict):
        maxbins = x_bin.get("maxbins", 10)

    values = df[x_field].dropna().values
    counts, bin_edges = np.histogram(values, bins=maxbins)

    result = []
    for i, count in enumerate(counts):
        x_min = float(bin_edges[i])
        x_max = float(bin_edges[i + 1])
        x_center = (x_min + x_max) / 2
        result.append(
            {
                MaidrKey.X: round(x_center, 4),
                MaidrKey.X_MIN: round(x_min, 4),
                MaidrKey.X_MAX: round(x_max, 4),
                MaidrKey.Y: int(count),
            }
        )

    return result


def _extract_box_data(df: pd.DataFrame, encoding: dict) -> list[dict]:
    """Extract box plot statistics from raw data."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    x_type = encoding.get("x", {}).get("type", "")

    if df.empty:
        return []

    # Determine which axis is categorical and which is quantitative
    if x_type == "quantitative":
        value_field = x_field
        group_field = y_field
    else:
        value_field = y_field
        group_field = x_field

    if not value_field:
        return []

    groups = {}
    if group_field and group_field in df.columns:
        for name, group_df in df.groupby(group_field, sort=False):
            groups[str(name)] = group_df[value_field].dropna().values
    else:
        groups[""] = df[value_field].dropna().values

    result = []
    for group_name, values in groups.items():
        if len(values) == 0:
            continue

        q1 = float(np.percentile(values, 25))
        q2 = float(np.percentile(values, 50))
        q3 = float(np.percentile(values, 75))
        iqr = q3 - q1
        whisker_low = float(np.min(values[values >= q1 - 1.5 * iqr]))
        whisker_high = float(np.max(values[values <= q3 + 1.5 * iqr]))

        lower_outliers = sorted([float(v) for v in values if v < whisker_low])
        upper_outliers = sorted([float(v) for v in values if v > whisker_high])

        entry = {
            MaidrKey.LOWER_OUTLIER: lower_outliers,
            MaidrKey.MIN: round(whisker_low, 4),
            MaidrKey.Q1: round(q1, 4),
            MaidrKey.Q2: round(q2, 4),
            MaidrKey.Q3: round(q3, 4),
            MaidrKey.MAX: round(whisker_high, 4),
            MaidrKey.UPPER_OUTLIER: upper_outliers,
        }
        if group_name:
            entry[MaidrKey.FILL] = group_name

        result.append(entry)

    return result


def _extract_grouped_bar_data(df: pd.DataFrame, encoding: dict) -> list[list[dict]]:
    """Extract stacked or dodged bar data."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    color_field = get_encoding_field(encoding, "color")
    y_agg = get_encoding_aggregate(encoding, "y")

    if df.empty or not x_field:
        return [[]]

    # If there's an aggregate, apply it
    if y_agg == "count" or y_field is None:
        # Count-based grouped bar
        if color_field and color_field in df.columns:
            grouped = (
                df.groupby([x_field, color_field], sort=False)
                .size()
                .reset_index(name="_count")
            )
            y_col = "_count"
        else:
            return [[]]
    elif y_agg and y_field and color_field:
        grouped = (
            df.groupby([x_field, color_field], sort=False)[y_field]
            .agg(y_agg)
            .reset_index()
        )
        y_col = y_field
    elif y_field and color_field:
        grouped = df
        y_col = y_field
    else:
        return [[]]

    result = []
    if color_field and color_field in grouped.columns:
        for group_name, group_df in grouped.groupby(color_field, sort=False):
            group_data = [
                {
                    MaidrKey.X: str(row[x_field]),
                    MaidrKey.FILL: str(group_name),
                    MaidrKey.Y: _to_num(row[y_col]),
                }
                for _, row in group_df.iterrows()
            ]
            result.append(group_data)

    return result


def _extract_smooth_data(
    df: pd.DataFrame, encoding: dict, transforms: list
) -> list[list[dict]]:
    """Extract smooth/KDE/LOESS data by computing the transform in Python."""
    x_field = get_encoding_field(encoding, "x")
    y_field = get_encoding_field(encoding, "y")
    color_field = get_encoding_field(encoding, "color")

    for t in transforms:
        if "density" in t:
            return _compute_density(df, t, color_field)
        if "loess" in t:
            return _compute_loess(df, t)

    # Fallback: treat as line data
    if df.empty or not x_field or not y_field:
        return [[]]

    sorted_df = df.sort_values(x_field)
    line_data = [
        {MaidrKey.X: _to_num(row[x_field]), MaidrKey.Y: _to_num(row[y_field])}
        for _, row in sorted_df.iterrows()
    ]
    return [line_data]


def _compute_density(
    df: pd.DataFrame, transform: dict, color_field: str | None
) -> list[list[dict]]:
    """Compute KDE density using scipy."""
    from scipy.stats import gaussian_kde

    field = transform.get("density", "")
    groupby = transform.get("groupby", [])

    if field not in df.columns:
        return [[]]

    result = []

    if groupby and len(groupby) > 0 and groupby[0] in df.columns:
        group_col = groupby[0]
        for group_name, group_df in df.groupby(group_col, sort=False):
            values = group_df[field].dropna().values
            if len(values) < 2:
                continue
            kde = gaussian_kde(values)
            x_range = np.linspace(float(values.min()) - 1, float(values.max()) + 1, 200)
            y_range = kde(x_range)
            line_data = [
                {
                    MaidrKey.X: round(float(x), 4),
                    MaidrKey.Y: round(float(y), 6),
                    MaidrKey.FILL: str(group_name),
                }
                for x, y in zip(x_range, y_range)
            ]
            result.append(line_data)
    else:
        values = df[field].dropna().values
        if len(values) < 2:
            return [[]]
        kde = gaussian_kde(values)
        x_range = np.linspace(float(values.min()) - 1, float(values.max()) + 1, 200)
        y_range = kde(x_range)
        line_data = [
            {
                MaidrKey.X: round(float(x), 4),
                MaidrKey.Y: round(float(y), 6),
            }
            for x, y in zip(x_range, y_range)
        ]
        result.append(line_data)

    return result


def _compute_loess(df: pd.DataFrame, transform: dict) -> list[list[dict]]:
    """Compute LOESS smoothing using statsmodels."""
    x_field = transform.get("loess", transform.get("on", ""))
    y_field = transform.get("on") if "loess" in transform else ""

    # In Altair's transform_loess, args are (x_field, y_field)
    # spec: {"loess": "y_field", "on": "x_field"} or just "loess" key
    if "on" in transform:
        x_field = transform["on"]
        y_field = transform["loess"]
    else:
        return [[]]

    if x_field not in df.columns or y_field not in df.columns:
        return [[]]

    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess

        x_vals = df[x_field].dropna().values
        y_vals = df[y_field].dropna().values
        if len(x_vals) < 2:
            return [[]]
        smoothed = lowess(y_vals, x_vals, frac=0.3)
        line_data = [
            {
                MaidrKey.X: round(float(row[0]), 4),
                MaidrKey.Y: round(float(row[1]), 4),
            }
            for row in smoothed
        ]
        return [line_data]
    except ImportError:
        # Fallback: just return sorted raw data
        sorted_df = df.sort_values(x_field)
        line_data = [
            {
                MaidrKey.X: _to_num(row[x_field]),
                MaidrKey.Y: _to_num(row[y_field]),
            }
            for _, row in sorted_df.iterrows()
        ]
        return [line_data]


def _to_num(val: Any) -> float | int:
    """Convert a value to a numeric type."""
    try:
        f = float(val)
        if f == int(f) and not isinstance(val, float):
            return int(f)
        return round(f, 4)
    except (ValueError, TypeError):
        return 0


def _to_str_or_num(val: Any) -> str | float | int:
    """Convert a value to string or number, preferring number for numeric types."""
    try:
        f = float(val)
        if f == int(f):
            return int(f)
        return round(f, 4)
    except (ValueError, TypeError):
        return str(val)

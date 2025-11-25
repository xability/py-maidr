from __future__ import annotations

import wrapt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, PathPatch
from matplotlib import path as mpath

from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.core.enum import PlotType, MaidrKey

# ============================================================
# 1. BOX STATS CALCULATION (SAFE VERSION)
# ============================================================


def compute_box_stats(values: np.ndarray):
    """Compute Tukey box stats matching matplotlib's method.
    
    Returns box plot statistics: Q1, Q2 (median), Q3, min, max.
    Note: min == Q1 (or max == Q3) can occur when there are no outliers
    below Q1 (or above Q3) - this is correct behavior.
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

    # Calculate quartiles
    q1 = float(np.percentile(values, 25))
    q2 = float(np.percentile(values, 50))
    q3 = float(np.percentile(values, 75))
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


# ============================================================
# 2. DATA EXTRACTION FROM SEABORN ARGUMENTS
# ============================================================


def extract_violin_data(args, kwargs):
    df = kwargs.get("data", None)
    x = kwargs.get("x", None)
    y = kwargs.get("y", None)
    hue = kwargs.get("hue", None)

    # Case 1 — DataFrame with x & y
    if isinstance(df, pd.DataFrame) and isinstance(x, str) and isinstance(y, str):
        groups, values = [], []
        if hue is None:
            for g, gdf in df.groupby(x, observed=False):
                groups.append(str(g))
                values.append(gdf[y].dropna().values)
        else:
            for (gx, gh), gdf in df.groupby([x, hue]):
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

    return [], []


# ============================================================
# 3. EXTRACT TRUE RENDERED VIOLIN POSITIONS
# ============================================================


def extract_violin_positions(ax, num_groups, orientation):
    """Extract seaborn's real violin center positions from Rectangle artists."""
    positions = []

    if orientation == "vert":
        for child in ax.get_children():
            if isinstance(child, Rectangle):
                w, h = child.get_width(), child.get_height()
                # Violin internal rectangles tend to be narrow and tall-ish
                if 0.05 < w < 1.2 and h > 0:
                    positions.append(child.get_x() + w / 2)
    else:
        for child in ax.get_children():
            if isinstance(child, Rectangle):
                w, h = child.get_width(), child.get_height()
                if 0.05 < h < 1.2 and w > 0:
                    positions.append(child.get_y() + h / 2)

    positions = sorted(set(positions))

    if len(positions) < num_groups:
        # fallback
        return [i + 1 for i in range(num_groups)]

    return positions[:num_groups]


# ============================================================
# 4. OPTIONALLY MATCH POSITIONS USING TICK LABELS
# ============================================================


def match_positions_to_groups(ax, groups, positions, orientation):
    """Try matching positions to tick labels for safer ordering."""
    if orientation == "vert":
        tick_labels = [t.get_text() for t in ax.get_xticklabels()]
        tick_positions = ax.get_xticks()
    else:
        tick_labels = [t.get_text() for t in ax.get_yticklabels()]
        tick_positions = ax.get_yticks()

    if len(tick_labels) == len(groups):
        matched = []
        for group in groups:
            try:
                idx = tick_labels.index(group)
                matched.append(tick_positions[idx])
            except ValueError:
                pass
        if len(matched) == len(groups):
            return matched

    return positions[:len(groups)]


# ============================================================
# 5. RECTANGLE → PATH
# ============================================================


def rect_to_pathpatch(rect: Rectangle):
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


# ============================================================
# 6. BUILD SYNTHETIC bxp_stats
# ============================================================


def make_synthetic_bxp(stats_list, vert, positions):
    boxes, medians, whiskers, caps = [], [], [], []
    halfwidth = 0.25

    for stats, center in zip(stats_list, positions):
        # --- box rectangle ---
        if vert:
            rect = Rectangle(
                (center - halfwidth, stats["q1"]),
                2 * halfwidth,
                stats["q3"] - stats["q1"],
            )
        else:
            rect = Rectangle(
                (stats["q1"], center - halfwidth),
                stats["q3"] - stats["q1"],
                2 * halfwidth,
            )
        boxes.append(rect_to_pathpatch(rect))

        # --- median ---
        if vert:
            med = Line2D(
                [center - halfwidth, center + halfwidth],
                [stats["q2"], stats["q2"]],
            )
        else:
            med = Line2D(
                [stats["q2"], stats["q2"]],
                [center - halfwidth, center + halfwidth],
            )
        medians.append(med)

        # --- whiskers ---
        if vert:
            wmin = Line2D([center, center], [stats["min"], stats["q1"]])
            wmax = Line2D([center, center], [stats["q3"], stats["max"]])
        else:
            wmin = Line2D([stats["min"], stats["q1"]], [center, center])
            wmax = Line2D([stats["q3"], stats["max"]], [center, center])
        whiskers.extend([wmin, wmax])

        # --- caps ---
        capw = halfwidth * 0.4
        if vert:
            cmin = Line2D([center - capw, center + capw], [stats["min"], stats["min"]])
            cmax = Line2D([center - capw, center + capw], [stats["max"], stats["max"]])
        else:
            cmin = Line2D([stats["min"], stats["min"]], [center - capw, center + capw])
            cmax = Line2D([stats["max"], stats["max"]], [center - capw, center + capw])
        caps.extend([cmin, cmax])

    return {
        "boxes": boxes,
        "medians": medians,
        "whiskers": whiskers,
        "caps": caps,
        "fliers": [],
    }


# ============================================================
# 7. FINAL PATCH — MAIDR BOX LAYER FOR VIOLINPLOT
# ============================================================


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def patch_violinplot(wrapped, instance, args, kwargs):
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    inner = kwargs.get("inner")
    if inner not in ("box", "boxplot"):
        return wrapped(*args, **kwargs)

    # ----- Extract data BEFORE seaborn draws -----
    groups, values = extract_violin_data(args, kwargs)
    if not groups or not values:
        return wrapped(*args, **kwargs)

    stats_list = [compute_box_stats(v) for v in values]

    # filter out empty-data stats (if using None return strategy)
    valid_pairs = [
        (stats, group)
        for stats, group in zip(stats_list, groups)
        if stats is not None
    ]

    if not valid_pairs:
        return wrapped(*args, **kwargs)

    stats_list_valid, groups_valid = zip(*valid_pairs)
    stats_list_valid = list(stats_list_valid)
    groups_valid = list(groups_valid)

    # ----- Original rendering -----
    with ContextManager.set_internal_context():
        ax = wrapped(*args, **kwargs)

    plot_ax = kwargs.get("ax", ax) or ax

    # ----- Orientation -----
    orient = kwargs.get("orient", "v")
    vert = not (orient in ("h", "horizontal", "y"))
    orientation = "vert" if vert else "horz"

    # ----- Extract true violin positions -----
    positions = extract_violin_positions(plot_ax, len(groups_valid), orientation)
    positions = match_positions_to_groups(plot_ax, groups_valid, positions, orientation)

    # ----- Build synthetic bxp_stats -----
    bxp_stats = make_synthetic_bxp(stats_list_valid, vert, positions)

    # ----- Add synthetic artists to axes so they appear in SVG with GIDs -----
    # These need to be in the axes for SVG rendering. We make them transparent
    # since the violin plot already shows the box plot (when inner='box')
    # Using alpha=0 instead of visible=False ensures they're still rendered in SVG
    for box in bxp_stats["boxes"]:
        plot_ax.add_patch(box)
        box.set_alpha(0.0)  # Transparent but still in SVG
    
    for median in bxp_stats["medians"]:
        plot_ax.add_line(median)
        median.set_alpha(0.0)
    
    for whisker in bxp_stats["whiskers"]:
        plot_ax.add_line(whisker)
        whisker.set_alpha(0.0)
    
    for cap in bxp_stats["caps"]:
        plot_ax.add_line(cap)
        cap.set_alpha(0.0)

    # ----- Register with MAIDR -----
    FigureManager.create_maidr(
        plot_ax,
        PlotType.BOX,
        bxp_stats=bxp_stats,
        orientation=orientation,
    )

    return ax

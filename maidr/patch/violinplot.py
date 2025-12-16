from __future__ import annotations

import uuid
import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from matplotlib.patches import PathPatch

from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.util.mixin.extractor_mixin import LevelExtractorMixin
from maidr.core.enum.maidr_key import MaidrKey

# Import utility classes (data extraction only, no registration)
from maidr.core.plot.violinplot import (
    ViolinDataExtractor,
    ViolinBoxStatsCalculator,
    ViolinPositionExtractor,
    SyntheticBoxPlotBuilder,
)


def _register_violin_layers(
    plot_ax: Axes,
    instance,
    args,
    kwargs,
    *,
    orientation: str,
    enable_box_layer: bool,
    box_violin_layer: str | None,
    use_full_range_extrema: bool = False,
) -> None:
    """Shared logic to register KDE (SMOOTH) and box (BOX) layers for violin plots.

    Used for both seaborn.violinplot and matplotlib.axes.Axes.violinplot so we can
    reuse the same data extraction and statistics logic.
    """
    vert = orientation == "vert"

    # ===== DETECT AND REGISTER SMOOTH (KDE) LAYER =====
    kde_polys = [c for c in plot_ax.collections if isinstance(c, PolyCollection)]
    if kde_polys:
        kde_lines = []
        unique_poly_gids = []

        # Create Line2D boundaries for each PolyCollection and assign unique GID
        for poly in kde_polys:
            paths = poly.get_paths()
            if paths:
                boundary = paths[0].vertices
                boundary = np.asarray(boundary)

                kde_line = Line2D(boundary[:, 0], boundary[:, 1])
                kde_line.axes = plot_ax

                unique_gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(unique_gid)
                poly.set_gid(unique_gid)
                kde_lines.append(kde_line)
                unique_poly_gids.append(unique_gid)

        # Register KDE layer as SMOOTH
        if kde_lines:
            x_levels = LevelExtractorMixin.extract_level(plot_ax, MaidrKey.X)

            common(
                PlotType.SMOOTH,
                # For both seaborn and matplotlib we already have the axes;
                # the wrapped function simply returns it so FigureManager can use it.
                lambda *a, **k: plot_ax,
                instance,
                args,
                dict(
                    kwargs,
                    regression_line=kde_lines[0],
                    poly_gids=unique_poly_gids,
                    is_polycollection=True,
                    violin_kde_lines=kde_lines,
                    poly_collections=kde_polys,
                    violin_layer="kde",
                    x_levels=x_levels,
                ),
            )

    # ===== DETECT AND REGISTER BOX LAYER =====
    if not enable_box_layer:
        return

    # Extract data for box plot statistics
    groups, values = ViolinDataExtractor.extract(args, kwargs)

    if not (groups and values):
        return

    # Compute box plot statistics for each group
    if use_full_range_extrema:
        stats_list = [ViolinBoxStatsCalculator.compute_full_range(v) for v in values]
    else:
        stats_list = [ViolinBoxStatsCalculator.compute(v) for v in values]

    # Filter out empty-data stats
    valid_pairs = [
        (stats, group)
        for stats, group in zip(stats_list, groups)
        if stats is not None
    ]

    if not valid_pairs:
        return

    stats_list_valid, groups_valid = zip(*valid_pairs)
    stats_list_valid = list(stats_list_valid)
    groups_valid = list(groups_valid)

    # Extract true violin positions from rendered plot.
    # For Matplotlib violins, positions correspond directly to 1..N tick locations,
    # so we can rely on sequential indices to avoid subtle ordering issues.
    if box_violin_layer == "mpl_violin":
        positions = [float(i + 1) for i in range(len(groups_valid))]
    else:
        positions = ViolinPositionExtractor.extract_positions(
            plot_ax, len(groups_valid), orientation
        )
        positions = ViolinPositionExtractor.match_to_groups(
            plot_ax, groups_valid, positions, orientation
        )

    # For single violin plots, ensure we use the actual violin center position
    if len(groups_valid) == 1 and len(positions) == 1:
        for child in plot_ax.get_children():
            if isinstance(child, PolyCollection) and child.get_paths():
                verts = child.get_paths()[0].vertices
                if verts is not None and len(verts) > 0:
                    if orientation == "vert":
                        x_coords = verts[:, 0]
                        if len(x_coords) > 0:
                            center_x = (x_coords.min() + x_coords.max()) / 2
                            positions[0] = float(center_x)
                            break
                    else:  # horizontal
                        y_coords = verts[:, 1]
                        if len(y_coords) > 0:
                            center_y = (y_coords.min() + y_coords.max()) / 2
                            positions[0] = float(center_y)
                            break

        # Fallback: try PathPatch
        if positions[0] == 0.0 or (positions[0] == 1.0 and len(positions) == 1):
            for child in plot_ax.get_children():
                if isinstance(child, PathPatch):
                    path = child.get_path()
                    if hasattr(path, "vertices") and path.vertices is not None:
                        verts = path.vertices
                        if len(verts) > 0:
                            if orientation == "vert":
                                x_coords = verts[:, 0]
                                if len(x_coords) > 0:
                                    center_x = (x_coords.min() + x_coords.max()) / 2
                                    positions[0] = float(center_x)
                                    break
                            else:  # horizontal
                                y_coords = verts[:, 1]
                                if len(y_coords) > 0:
                                    center_y = (y_coords.min() + y_coords.max()) / 2
                                    positions[0] = float(center_y)
                                    break

    # Build synthetic bxp_stats
    bxp_stats = SyntheticBoxPlotBuilder.build(stats_list_valid, vert, positions)
    # Attach raw stats (including mean) so BoxPlot can use them when building schema
    bxp_stats["stats_list"] = stats_list_valid

    # Assign GIDs to synthetic artists
    for box in bxp_stats["boxes"]:
        if not box.get_gid():
            box.set_gid(f"maidr-{uuid.uuid4()}")

    for median in bxp_stats["medians"]:
        if not median.get_gid():
            median.set_gid(f"maidr-{uuid.uuid4()}")

    for whisker in bxp_stats["whiskers"]:
        if not whisker.get_gid():
            whisker.set_gid(f"maidr-{uuid.uuid4()}")

    for cap in bxp_stats["caps"]:
        if not cap.get_gid():
            cap.set_gid(f"maidr-{uuid.uuid4()}")

    # Add synthetic artists to axes (transparent for SVG rendering)
    for box in bxp_stats["boxes"]:
        plot_ax.add_patch(box)
        box.set_alpha(0.0)

    for median in bxp_stats["medians"]:
        plot_ax.add_line(median)
        median.set_alpha(0.0)

    for whisker in bxp_stats["whiskers"]:
        plot_ax.add_line(whisker)
        whisker.set_alpha(0.0)

    for cap in bxp_stats["caps"]:
        plot_ax.add_line(cap)
        cap.set_alpha(0.0)

    # Add synthetic mean lines (if present) as fully transparent artists
    for mean in bxp_stats.get("means", []):
        plot_ax.add_line(mean)
        mean.set_alpha(0.0)

    # Register box layer
    FigureManager.create_maidr(
        plot_ax,
        PlotType.BOX,
        bxp_stats=bxp_stats,
        orientation=orientation,
        violin_layer=box_violin_layer,
    )


@wrapt.patch_function_wrapper(Axes, "violinplot")
def mpl_violinplot(wrapped, instance, args, kwargs):
    """
    Patch for matplotlib.axes.Axes.violinplot to extract and register KDE and
    box statistics with MAIDR.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Render the original Matplotlib violin plot
    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)

    plot_ax: Axes = instance

    # Determine orientation from Matplotlib's 'vert' argument (default True -> vertical)
    vert = kwargs.get("vert", True)
    orientation = "vert" if vert else "horz"

    # For Matplotlib, always compute and register box statistics from the data
    _register_violin_layers(
        plot_ax,
        instance,
        args,
        kwargs,
        orientation=orientation,
        enable_box_layer=True,
        box_violin_layer="mpl_violin",
        use_full_range_extrema=True,
    )

    return plot


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def patch_violinplot(wrapped, instance, args, kwargs):
    """
    Patch for seaborn.violinplot to extract and register KDE and box plot layers with MAIDR.

    This wrapper function intercepts calls to seaborn.violinplot and automatically
    extracts and registers the KDE (kernel density estimation) and box plot layers
    with MAIDR for accessible navigation.

    Parameters
    ----------
    wrapped : Callable
        The original seaborn.violinplot function to be patched.
    instance : Any
        The bound instance if the function is a method, otherwise None.
    args : tuple
        Positional arguments passed to seaborn.violinplot.
    kwargs : dict
        Keyword arguments passed to seaborn.violinplot.

    Returns
    -------
    matplotlib.axes.Axes
        The Axes object containing the violin plot.

    Examples
    --------
    >>> import seaborn as sns
    >>> import maidr.patch.violinplot  # Patch is applied automatically
    >>> ax = sns.violinplot(data=[1, 2, 3, 4])
    >>> # The KDE and box plot layers are registered with MAIDR.

    Notes
    -----
    Detects and registers:
        - SMOOTH layer: All violin shapes (PolyCollection) as KDE layer
        - BOX layer: Box plot statistics when inner='box' or inner='boxplot'
    """
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Original rendering - always execute
    with ContextManager.set_internal_context():
        ax = wrapped(*args, **kwargs)

    plot_ax = kwargs.get("ax", ax) or ax

    # Determine orientation
    orient = kwargs.get("orient", "v")
    vert = orient not in ("h", "horizontal", "y")
    orientation = "vert" if vert else "horz"

    # For seaborn, only register box layer when inner='box' or inner='boxplot'
    inner = kwargs.get("inner", "box")
    enable_box_layer = inner in ("box", "boxplot")

    _register_violin_layers(
        plot_ax,
        instance,
        args,
        kwargs,
        orientation=orientation,
        enable_box_layer=enable_box_layer,
        box_violin_layer="sns_violin",
        use_full_range_extrema=False,
    )

    return ax

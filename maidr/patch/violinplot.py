from __future__ import annotations

import wrapt

from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.core.enum import PlotType
from maidr.core.plot.violinplot import (
    ViolinDataExtractor,
    ViolinBoxStatsCalculator,
    ViolinPositionExtractor,
    SyntheticBoxPlotBuilder,
)


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def patch_violinplot(wrapped, instance, args, kwargs):
    """
    Patch for seaborn.violinplot to extract and register the box plot layer with MAIDR.

    This wrapper only activates when inner='box' or inner='boxplot' to extract
    box plot statistics from the violin plot data and register them as a MAIDR box plot.
    """
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    inner = kwargs.get("inner")
    if inner not in ("box", "boxplot"):
        return wrapped(*args, **kwargs)

    # Extract data BEFORE seaborn draws
    groups, values = ViolinDataExtractor.extract(args, kwargs)
    if not groups or not values:
        return wrapped(*args, **kwargs)

    # Compute box plot statistics for each group
    stats_list = [ViolinBoxStatsCalculator.compute(v) for v in values]

    # Filter out empty-data stats
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

    # Original rendering
    with ContextManager.set_internal_context():
        ax = wrapped(*args, **kwargs)

    plot_ax = kwargs.get("ax", ax) or ax

    # Determine orientation
    orient = kwargs.get("orient", "v")
    vert = not (orient in ("h", "horizontal", "y"))
    orientation = "vert" if vert else "horz"

    # Extract true violin positions from rendered plot
    positions = ViolinPositionExtractor.extract_positions(
        plot_ax, len(groups_valid), orientation
    )
    positions = ViolinPositionExtractor.match_to_groups(
        plot_ax, groups_valid, positions, orientation
    )

    # Build synthetic bxp_stats with matplotlib artist objects
    bxp_stats = SyntheticBoxPlotBuilder.build(stats_list_valid, vert, positions)

    # Add synthetic artists to axes so they appear in SVG with GIDs
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

    # Register with MAIDR
    FigureManager.create_maidr(
        plot_ax,
        PlotType.BOX,
        bxp_stats=bxp_stats,
        orientation=orientation,
    )

    return ax

from __future__ import annotations

import wrapt
import uuid
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
import numpy as np

from maidr.core.context_manager import BoxplotContextManager, ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import common
from maidr.util.svg_utils import unique_lines_by_xy


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def sns_violin(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.violinplot to register BOX and SMOOTH (KDE) layers for MAIDR.
    A violin plot consists of a box plot (statistics) and KDE (density distribution).
    """
    # Track if we're in internal context to avoid recursion
    if BoxplotContextManager.is_internal_context():
        plot = wrapped(*args, **kwargs)
        return plot

    # Execute the original violinplot
    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)

    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    if ax is None:
        return plot

    # Determine orientation
    orientation = kwargs.get("orient", "v")
    if orientation == "h" or orientation == "y":
        orientation_str = "horz"
    else:
        orientation_str = "vert"

    # Get box plot statistics if inner='box' or inner='quartiles' is set
    inner = kwargs.get("inner", None)
    has_box_stats = inner in ("box", "quartiles", "quart")

    if has_box_stats:
        # Find the box plot artists (containers)
        # Box plots created by violinplot use bxp_stats internally
        box_artists = []
        for artist in ax.artists:
            if hasattr(artist, "get_gid") and artist.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                artist.set_gid(gid)
            # Look for box-like polygons
            if isinstance(artist, PolyCollection):
                box_artists.append(artist)

        # Register box plot layer if we found box elements
        if box_artists:
            FigureManager.create_maidr(ax, PlotType.BOX, orientation=orientation_str)

    # Register KDE (violin shape) as SMOOTH layer
    # Violin plots create filled polygons for the KDE distribution
    violin_polys = []
    for collection in ax.collections:
        if isinstance(collection, PolyCollection):
            # Check if it's the violin shape (not box elements)
            if hasattr(collection, "get_paths") and collection.get_paths():
                path = collection.get_paths()[0]
                vertices = path.vertices
                if len(vertices) > 10:  # Violins have many vertices, boxes have few
                    violin_polys.append(collection)

    # Register each violin shape as a SMOOTH layer
    for violin_poly in violin_polys:
        if violin_poly.get_gid() is None:
            gid = f"maidr-{uuid.uuid4()}"
            violin_poly.set_gid(gid)
            violin_poly.set_label(f"Violin {gid}")  # Set label for identification

        # Extract the boundary of the polygon
        path = violin_poly.get_paths()[0]
        boundary = np.asarray(path.vertices)

        # Create a Line2D from the boundary for the smooth layer
        kde_line = Line2D(boundary[:, 0], boundary[:, 1])

        # Register as SMOOTH layer
        common(
            PlotType.SMOOTH,
            lambda *a, **k: ax,
            instance,
            args,
            dict(
                kwargs,
                regression_line=kde_line,
                violin_poly=violin_poly,
                poly_gid=violin_poly.get_gid(),
                is_polycollection=True,
            ),
        )

    # Also check for any lines added by the violin plot (e.g., median lines, quartiles)
    lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
    for line in unique_lines_by_xy(lines):
        if line.get_gid() is None:
            gid = f"maidr-{uuid.uuid4()}"
            line.set_gid(gid)
        # Register as SMOOTH for non-box statistics lines
        if not has_box_stats or "median" not in line.get_label().lower():
            common(
                PlotType.SMOOTH,
                lambda *a, **k: ax,
                instance,
                args,
                dict(kwargs, regression_line=line),
            )

    return plot

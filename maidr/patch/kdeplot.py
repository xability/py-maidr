from __future__ import annotations

import wrapt
import uuid
import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.context_manager import ContextManager
from maidr.util.svg_utils import unique_lines_by_xy


def kde(wrapped, instance, args, kwargs) -> Axes | Line2D | PolyCollection:
    """
    Patch for seaborn.kdeplot: register all unique lines and/or filled boundaries as SMOOTH.
    """
    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)
    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    if ax is not None:
        # Register all unique Line2D objects
        lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
        for kde_line in unique_lines_by_xy(lines):
            if kde_line.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
            common(
                PlotType.SMOOTH,
                lambda *a, **k: ax,
                instance,
                args,
                dict(kwargs, regression_line=kde_line),
            )
        # Register all PolyCollection boundaries as SMOOTH
        for poly in [c for c in ax.collections if isinstance(c, PolyCollection)]:
            if poly.get_paths():
                path = poly.get_paths()[0]
                boundary = path.vertices
                # Defensive: ensure boundary is a numpy array
                boundary = np.asarray(boundary)
                kde_line = Line2D(boundary[:, 0], boundary[:, 1])
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
                poly.set_gid(gid)  # Assign gid to PolyCollection group
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: ax,
                    instance,
                    args,
                    dict(
                        kwargs,
                        regression_line=kde_line,
                        poly_gid=gid,
                        is_polycollection=True,
                    ),
                )
    return plot


# Patch seaborn kdeplot
wrapt.wrap_function_wrapper("seaborn", "kdeplot", kde)

from __future__ import annotations

import wrapt

import numpy as np
from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
import uuid

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import common


@wrapt.patch_function_wrapper(Axes, "hist")
def mpl_hist(
    wrapped, _, args, kwargs
) -> tuple[
    np.ndarray | list[np.ndarray],
    np.ndarray,
    BarContainer | Polygon | list[BarContainer | Polygon],
]:
    """
    Patch matplotlib Axes.hist to register HIST layer for MAIDR.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch `ax.hist()`.
        n, bins, plot = wrapped(*args, **kwargs)

    # Extract the histogram data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HIST)

    # Return to the caller.
    return n, bins, plot


@wrapt.patch_function_wrapper("seaborn", "histplot")
def sns_hist(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.histplot to register HIST and (if kde=True) SMOOTH layers for MAIDR.
    """
    # Register the histogram as HIST as before
    ax = common(PlotType.HIST, wrapped, instance, args, kwargs)
    # Only register KDE overlay as SMOOTH if kde=True was set
    kde_enabled = kwargs.get("kde", False)
    if kde_enabled:
        # Find the KDE line(s) and register as SMOOTH
        axes = ax if isinstance(ax, Axes) else getattr(ax, "axes", None)
        if axes is not None:
            for line in axes.get_lines():
                if isinstance(line, Line2D):
                    if line.get_gid() is None:
                        gid = f"maidr-{uuid.uuid4()}"
                        line.set_gid(gid)
                    common(
                        PlotType.SMOOTH,
                        lambda *a, **k: axes,
                        instance,
                        args,
                        dict(kwargs, regression_line=line),
                    )
    return ax

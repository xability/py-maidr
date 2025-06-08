from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from maidr.core.enum import PlotType
from maidr.patch.common import common
import numpy as np


def regplot(wrapped, instance, args, kwargs) -> Axes:
    """
    Wrapper function for seaborn.regplot.
    Only register a scatter plot and, if present, a smooth plot for the regression line.
    """
    ax = common(PlotType.SCATTER, wrapped, instance, args, kwargs)
    axes = ax if isinstance(ax, Axes) else ax.axes if hasattr(ax, "axes") else None
    if axes is not None:
        regression_line = next(
            (
                artist
                for artist in axes.get_children()
                if isinstance(artist, Line2D)
                and artist.get_label() not in (None, "", "_nolegend_")
                and artist.get_xydata() is not None
                and np.asarray(artist.get_xydata()).size > 0
            ),
            None,
        )
        if regression_line is not None:
            # Use a lambda that returns the existing axes instead of the original plotting function.
            # This avoids re-calling the plotting function and simply registers the smooth plot for accessibility.
            common(
                PlotType.SMOOTH,
                lambda *a, **k: ax,
                instance,
                args,
                dict(kwargs, regression_line=regression_line),
            )
    return ax


# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "regplot", regplot)

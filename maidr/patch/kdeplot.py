from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
import uuid

from maidr.core.enum import PlotType
from maidr.patch.common import common


def kde(wrapped, instance, args, kwargs) -> Axes | Line2D | PathCollection:
    """
    Wrapper function for kernel density estimation plotting in seaborn.

    This function patches seaborn's kdeplot to support multiple layers and
    different display modes (layer, stack, fill).

    Parameters
    ----------
    wrapped : callable
        The wrapped function (kdeplot)
    instance : object
        The object to which the wrapped function belongs
    args : tuple
        Positional arguments passed to the wrapped function
    kwargs : dict
        Keyword arguments passed to the wrapped function
        Supported parameters:
        - multiple: str, one of ["layer", "stack", "fill"]
        - hue: str or array-like, for multiple distributions
        - common_norm: bool, whether to normalize distributions together
        - common_grid: bool, whether to use same grid for all distributions

    Returns
    -------
    Axes | Line2D | PathCollection
        The result of the wrapped function after processing
    """
    plot = common(PlotType.SMOOTH, wrapped, instance, args, kwargs)

    # Set a unique gid on the first Line2D (KDE line)
    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    if ax is not None:
        lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
        if lines:
            line = lines[0]
            if not line.get_gid():
                gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(gid)
                print(f"[MAIDR DEBUG] Set gid on KDE line: {gid}")
                print(
                    f"[MAIDR DEBUG] To select in console: document.querySelector('g[id=\"{gid}\"] > path')"
                )
    return plot


# Patch seaborn function
wrapt.wrap_function_wrapper("seaborn", "kdeplot", kde)

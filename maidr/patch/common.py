from __future__ import annotations

import warnings
from typing import Any

from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager


def common(plot_type, wrapped, _, args, kwargs) -> Any:
    # Suppress warnings not to confuse screen-reader users
    warnings.filterwarnings("ignore")

    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = wrapped(*args, **kwargs)

    # Extract the data points for MAIDR from the plot.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, plot_type)

    return plot

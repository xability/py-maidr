from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager


def line(wrapped, instance, args, kwargs) -> Axes | list[Line2D]:
    """
    Wrapper for line plotting functions that creates a single MAIDR plot per axes to handle
    multiline plots (matplotlib) and single-call plots (seaborn) correctly by preventing
    multiple MAIDR layers and using internal context to avoid cyclic processing.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = wrapped(*args, **kwargs)

    # Get the axes from the plot result (works for both matplotlib and seaborn)
    ax = FigureManager.get_axes(plot)
    if ax is None:
        # If we can't get axes from plot, try from instance
        ax = instance if isinstance(instance, Axes) else getattr(instance, "axes", None)

    # Check if a MAIDR plot already exists for this axes
    if ax is not None and not hasattr(ax, "_maidr_plot_created"):
        # Create MAIDR plot only once for this axes using common()
        common(PlotType.LINE, lambda *a, **k: plot, instance, args, kwargs)
        # Mark that a MAIDR plot has been created for this axes
        setattr(ax, "_maidr_plot_created", True)

    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "lineplot", line)

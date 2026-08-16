from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import _draw_quietly, common, wrap_seaborn
from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.util.step_utils import is_step_axes


def line(wrapped, instance, args, kwargs) -> Axes | list[Line2D]:
    """
    Wrapper for line plotting functions that creates a single MAIDR plot per axes to handle
    multiline plots (matplotlib) and single-call plots (seaborn) correctly by preventing
    multiple MAIDR layers and using internal context to avoid cyclic processing.

    The layer type is decided here rather than in a separate patch because
    ``Axes.step`` is not its own renderer: it sets ``drawstyle="steps-*"`` and
    delegates to ``Axes.plot``, which this wrapper already intercepts. Choosing
    the type from the resulting artists' drawstyles therefore covers
    ``ax.step``, ``plt.step``, ``ax.plot(drawstyle="steps-post")`` and
    ``sns.lineplot(drawstyle="steps-mid")`` with one rule, and — because no
    second interception point is added — one call can never register both a
    STEP and a LINE layer for the same axes.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = _draw_quietly(wrapped, args, kwargs)

    # Get the axes from the plot result (works for both matplotlib and seaborn)
    ax = FigureManager.get_axes(plot)
    if ax is None:
        # If we can't get axes from plot, try from instance
        ax = instance if isinstance(instance, Axes) else getattr(instance, "axes", None)

    # A call that drew no points is not a layer. `seaborn.utils._default_color`
    # plots a throwaway artist to resolve a default colour and removes it
    # again -- the mechanism #373 described for area layers, which
    # `sns.residplot` reaches here. Measured on one: the returned line is in
    # data space and carries an empty `get_xydata()`.
    #
    # Registering it produces a layer with no artist of its own, so `_series()`
    # falls back to sweeping the axes and describes whatever else is there. In
    # a residual plot the only other thing is the `axhline`, so the chart
    # announced a reference line as its data (#434).
    #
    # Emptiness is the test rather than "already detached", because seaborn
    # removes the probe *after* this returns -- the line is still attached at
    # the moment the decision is made, so detachment is not observable yet.
    # It also agrees with #421: a layer with no points is a phantom, not an
    # empty reading.
    drawn = (
        [line for line in plot if isinstance(line, Line2D)]
        if isinstance(plot, list)
        else []
    )
    if drawn and all(line.get_xydata().size == 0 for line in drawn):
        return plot

    # Check if a MAIDR plot already exists for this axes
    if ax is not None and not hasattr(ax, "_maidr_plot_created"):
        # Classify from the rendered artists: an axes is a step plot only when
        # every data-bearing line on it is a step line.
        plot_type = PlotType.STEP if is_step_axes(ax) else PlotType.LINE
        # Create MAIDR plot only once for this axes using common()
        common(plot_type, lambda *a, **k: plot, instance, args, kwargs)
        # Mark that a MAIDR plot has been created for this axes
        setattr(ax, "_maidr_plot_created", True)

    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrap_seaborn("lineplot", line)

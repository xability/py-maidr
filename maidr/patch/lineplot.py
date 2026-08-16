from __future__ import annotations

import matplotlib.pyplot as plt
import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import _draw_quietly, common, wrap_seaborn
from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager
from maidr.util.step_utils import is_step_layer

#: The attribute the accumulated series live on. A layer describes the lines
#: its own calls drew; see `line()` for what sweeping the axes collected.
DRAWN_SERIES = "_maidr_line_series"


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

    # `seaborn.lineplot` returns an Axes rather than the lines it drew, so the
    # only way to know which of them are its own is to look before and after.
    # `Axes.plot` hands its lines straight back, so it needs no snapshot -- and
    # `instance` tells the two apart before the call, being the Axes for the
    # bound method and None for the module-level seaborn function.
    #
    # Worth splitting rather than snapshotting unconditionally. Measured on an
    # axes carrying 2,000 lines, `list(ax.get_lines())` costs 369 us per call
    # against roughly 600 us for the whole patched `ax.plot` -- a third of it,
    # on the path that never reads the result.
    #
    # On the seaborn side the target is resolved the way seaborn resolves it,
    # `plt.gca()` and all: the common idiom passes no `ax=` either, which left
    # the snapshot empty and made *every* line on the axes look newly drawn.
    # Measured on the pairing this whole change is about::
    #
    #     sns.boxplot(data=df, x="g", y="v")        # no ax=
    #     sns.lineplot(data=summary, x="g", y="v")  # no ax=
    #     -> line layer: 11 series, values are whisker endpoints
    #
    # `plt.gca()` creates an axes when there is none, which is not a side
    # effect worth avoiding here: seaborn is about to call it and create the
    # same one a moment later.
    before = None
    if not isinstance(instance, Axes):
        target = kwargs.get("ax")
        if target is None:
            target = plt.gca()
        before = list(target.get_lines()) if isinstance(target, Axes) else []

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
    # Which branch runs is decided by whether a snapshot was taken, not by the
    # shape of the return value. Tying them together is what keeps a surprise
    # from `Axes.plot` -- a future release returning something other than a
    # list -- from silently falling through to the sweep this change removes.
    # Drawing nothing is the safe answer there; describing the axes is not.
    if before is None:
        drawn = (
            [line for line in plot if isinstance(line, Line2D)]
            if isinstance(plot, list)
            else []
        )
    else:
        drawn = [
            line
            for line in (ax.get_lines() if ax is not None else [])
            if line not in before
        ]
    if drawn and all(line.get_xydata().size == 0 for line in drawn):
        return plot

    if ax is None:
        return plot

    # Keep the lines this layer's own calls drew, so extraction describes those
    # rather than sweeping the axes.
    #
    # A box plot, violin or boxen renders its whiskers, caps and medians as
    # `Line2D` objects in data space, so a sweep collects them too. One
    # `ax.plot()` over such a chart -- a target, a control limit, last year's
    # median -- is enough. Measured, with a single reference line:
    #
    #     ax.plot + sns.boxplot     line layer: 11 series   (should be 1)
    #     ax.plot + sns.violinplot  line layer:  7 series
    #     ax.plot + sns.boxenplot   line layer:  3 series
    #
    # Every extra series is two points long, because a whisker is a segment.
    # The reader is walked through box geometry announced exactly as data
    # would be (#440).
    #
    # The internal context already separates the two, which is what makes this
    # cheap: a companion chart draws its lines inside its own patch's context,
    # so `line()` returns above without recording them, while a user's
    # `ax.plot` reaches here. Measured on that same chart -- the user's call
    # arrives with the context clear, all twelve of the box plot's arrive with
    # it set.
    #
    # Accumulated on the axes rather than passed per call, because several
    # `ax.plot()` calls are meant to be *one* multi-series layer. The list is
    # handed over by reference and extraction is lazy, so lines added after the
    # layer is registered still reach it -- which is what the sweep provided
    # and the only part of it worth keeping.
    series = getattr(ax, DRAWN_SERIES, None)
    if series is None:
        series = []
        setattr(ax, DRAWN_SERIES, series)
    series.extend(item for item in drawn if item not in series)

    # Check if a MAIDR plot already exists for this axes
    if not hasattr(ax, "_maidr_plot_created"):
        # Classify from the rendered artists: a layer is a step plot only when
        # every data-bearing line *it owns* is a step line.
        #
        # Asked of `series` rather than the axes for the reason above. A step
        # chart drawn over a box plot saw the box's whiskers in the mix and
        # concluded the axes was not piecewise-constant, so it registered as
        # LINE -- which means `MultiLinePlot` instead of `StepPlot`, and the
        # ordinal level names go with it.
        plot_type = PlotType.STEP if is_step_layer(series) else PlotType.LINE
        # Create MAIDR plot only once for this axes using common()
        common(
            plot_type,
            lambda *a, **k: plot,
            instance,
            args,
            dict(kwargs, lines=series),
        )
        # Mark that a MAIDR plot has been created for this axes
        setattr(ax, "_maidr_plot_created", True)

    return plot


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrap_seaborn("lineplot", line)

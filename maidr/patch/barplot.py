from __future__ import annotations

from typing import Any, Callable, Dict, Tuple, Union

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.context_manager import ContextManager
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.barplot import DRAWN_BARS
from maidr.core.plot.grouped_barplot import (
    bars_are_ragged,
    bars_by_category,
    shares_a_category,
    ticks_are_categories,
)
from maidr.patch.common import (
    _argument,
    _draw_quietly,
    _resolve,
    common,
    plotter_panels,
    wrap_seaborn,
)
from maidr.util.mixin import LevelExtractorMixin


def bar(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Union[Axes, BarContainer]:
    """
    Patch function for `Axes.bar` and `Axes.barh`.

    This function patches the bar plotting functions to identify whether the
    plot should be rendered as a normal, stacked, or dodged bar plot.
    It uses the 'bottom' argument -- or 'left', which is how a horizontal bar
    spells the same thing -- to identify stacked bar plots, whether passed by
    name or by position; a baseline of zeros is not one. For dodged plots, it
    uses robust detection logic that considers both width and context to
    avoid misclassifying simple bar plots with narrow widths as dodged plots.
    Seaborn's bar plots do not come through here — they are classified from
    the bars they drew, in `sns_bar` below.

    Parameters
    ----------
    wrapped : Callable
        The original function to be wrapped.
    instance : Any
        The instance of the class where the function is being patched.
    args : tuple
        Positional arguments passed to the original function.
        For a dodged plot, the first argument (x positions) should be numeric.
    kwargs : dict
        Keyword arguments passed to the original function.

    Returns
    -------
    Union[Axes, BarContainer]
        The axes or bar container returned by the original function.

    Examples
    --------
    >>> # For a manual dodged (grouped) bar plot, pass numeric x positions:
    >>> x_positions = np.arange(3)
    >>> ax.bar(x_positions, heights, width, label='Group')  # Dodged bar plot.
    """
    plot_type = PlotType.BAR

    # A stacked bar is the one that says where its baseline is. `bottom` is
    # how a vertical bar says it and `left` is how a horizontal one does --
    # the same argument for the two orientations, and reading only the first
    # meant `ax.barh(..., left=...)` arrived as two independent bar layers.
    # The numbers were right and the layer count was plausible; what a reader
    # was not told is that the second bar sits on top of the first, which is
    # the whole content of a stacked chart (#385).
    #
    # Read by name or by position, because both spellings are matplotlib's:
    # `bottom` is the fourth parameter of `Axes.bar` and `left` the fourth of
    # `Axes.barh`, and `ax.bar(x, b, 0.8, a)` said where its baseline was just
    # as plainly as `bottom=a` -- yet arrived as a second plain bar layer, the
    # same failure one argument over (#754).
    #
    # A baseline of zeros is where a bar starts anyway, so it says nothing
    # about stacking: `bottom=0` is matplotlib's own default written out, and
    # reading it as a stack announced a plain chart as a one-group stack named
    # after its container. The first layer of a stack registers BAR either way
    # and is superseded by the STACKED layer that follows it -- see
    # `_drop_superseded_layers`, which records that idiom as the supported one.
    baseline = _argument("bottom", wrapped, args, kwargs)
    if baseline is None:
        baseline = _argument("left", wrapped, args, kwargs)
    # A name under `data=` is looked up before the zero test, so the two
    # spellings of one chart -- `bottom="b", data=df` and `bottom=df["b"]` --
    # read the same column and give the same answer.
    baseline = _resolve(baseline, kwargs.get("data"))
    if baseline is not None and not _is_zero_baseline(baseline):
        plot_type = PlotType.STACKED
    else:
        # The thickness across the bar, which is `height` on `barh` -- where
        # `width` is the bar's length, and reading it compared two calls'
        # values rather than their spacing.
        thickness = "height" if getattr(wrapped, "__name__", "") == "barh" else "width"
        real_width = _argument(thickness, wrapped, args, kwargs)
        if real_width is None:
            real_width = 0.8

        align = kwargs.get("align", "center")

        # More robust dodged plot detection: consider multiple factors
        # Only classify as DODGED if there are strong indicators of grouping
        should_be_dodged = _should_classify_as_dodged(
            instance, real_width, align, args, kwargs
        )

        if should_be_dodged:
            plot_type = PlotType.DODGED

    # Hand the layer the container this call drew. `BarPlot` otherwise sweeps
    # every `BarContainer` on the axes, so two `ax.bar()` calls each read both
    # containers' patches against one axis' worth of tick labels, fail the
    # count check and raise -- which is fatal to the whole render (#380).
    #
    # Only the matplotlib entry point can say this. seaborn draws one layer as
    # several containers, one per hue group, and registers it from `sns_bar`
    # below, where no single container is the answer -- that path keeps the
    # sweep, which is right for it.
    return common(plot_type, wrapped, instance, args, kwargs, drawn_as=DRAWN_BARS)


def _is_zero_baseline(baseline: Any) -> bool:
    """
    Whether a bar's baseline is zero everywhere, and so no baseline at all.

    Parameters
    ----------
    baseline : Any
        The ``bottom`` or ``left`` argument, a scalar or a sequence, after
        a name under ``data=`` has been resolved to its column.

    Returns
    -------
    bool
        True for a scalar zero or an all-zero sequence. Anything that cannot
        be read as numbers -- a name that resolved to nothing, in particular
        -- is False, so it keeps reading as the stack it names.
    """
    try:
        return bool(np.all(np.asarray(baseline, dtype=float) == 0))
    except (TypeError, ValueError):
        return False


def _should_classify_as_dodged(
    ax: Any, width: Any, align: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> bool:
    """
    Determine if a bar plot should be classified as dodged based on context.

    This function uses more sophisticated logic than just checking width < 0.8,
    as simple bar plots with narrow widths should not be considered dodged.

    Parameters
    ----------
    ax : Any
        The axes instance where the plot is being created.
    width : Any
        The thickness across the bar: ``width`` on ``bar``, ``height`` on
        ``barh``, whichever the caller passed.
    align : str
        The alignment parameter for the bar plot.
    args : tuple
        Positional arguments passed to the bar function.
    kwargs : dict
        Keyword arguments passed to the bar function.

    Returns
    -------
    bool
        True if the plot should be classified as DODGED, False otherwise.

    Examples
    --------
    >>> # These should be DODGED:
    >>> ax.bar([0.1, 1.1, 2.1], [1, 2, 3], width=0.4, label='Group A')
    >>> ax.bar([0.4, 1.4, 2.4], [4, 5, 6], width=0.4, label='Group B')

    >>> # These should remain BAR:
    >>> ax.bar(['A', 'B', 'C'], [1, 2, 3], width=0.6)  # Simple categorical bar plot
    """
    # If align is 'edge', it's likely a dodged plot
    if align == "edge":
        return True

    # If width is specified and very narrow (< 0.5), more likely to be dodged
    # But only if there are other indicators
    if isinstance(width, (int, float)) and float(width) < 0.5:
        # Check if x positions suggest grouping (numeric positions with fractional parts)
        if len(args) > 0:
            x_positions = args[0]
            if _has_numeric_grouping_pattern(x_positions):
                return True

    # Check if there are already multiple bar containers on the axes
    # This suggests that this might be part of a grouped bar plot
    if hasattr(ax, "containers") and len(ax.containers) > 0:
        # If there are existing containers, this might be adding to a group
        if isinstance(width, (int, float)) and float(width) < 0.8:
            return True

    # Check for explicit grouping indicators in kwargs
    if "label" in kwargs and isinstance(width, (int, float)) and float(width) < 0.8:
        # If there's a label and narrow width, it might be part of a group
        # But we need to be conservative here to avoid false positives
        if _has_numeric_grouping_pattern(args[0] if len(args) > 0 else None):
            return True

    # Default to False - prefer BAR over DODGED for ambiguous cases
    return False


def _has_numeric_grouping_pattern(x_positions: Any) -> bool:
    """
    Check if x positions suggest a grouping pattern typical of dodged plots.

    Parameters
    ----------
    x_positions : Any
        The x positions for the bar plot.

    Returns
    -------
    bool
        True if the positions suggest grouping, False otherwise.

    Examples
    --------
    >>> _has_numeric_grouping_pattern([0.1, 1.1, 2.1])  # True - fractional offsets
    >>> _has_numeric_grouping_pattern(['A', 'B', 'C'])  # False - categorical
    >>> _has_numeric_grouping_pattern([0, 1, 2])        # False - simple numeric
    """
    try:
        # Convert to list if possible (duck typing)
        try:
            positions = list(x_positions)
        except TypeError:
            return False

        # If all positions are strings, it's categorical (not dodged)
        if all(isinstance(pos, str) for pos in positions):
            return False

        # If positions are numeric, check for fractional offsets
        # that suggest manual positioning for grouping
        numeric_positions = []
        for pos in positions:
            try:
                numeric_positions.append(float(pos))
            except (ValueError, TypeError):
                return False

        if len(numeric_positions) < 2:
            return False

        # Check if positions have fractional parts that suggest manual offset
        # for grouping (e.g., [0.1, 1.1, 2.1] or [0.8, 1.8, 2.8])
        fractional_parts = [pos % 1 for pos in numeric_positions]

        # If all have the same non-zero fractional part, it suggests grouping
        if all(abs(frac - fractional_parts[0]) < 0.01 for frac in fractional_parts):
            if fractional_parts[0] > 0.01:  # Non-zero fractional part
                return True

        return False

    except Exception:
        # If anything goes wrong in analysis, default to False
        return False


def sns_bar(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Axes:
    """
    Draw `seaborn.barplot`/`countplot` quietly and leave the reading to the
    plotter.

    Registration used to happen here and no longer does; see
    `sns_categorical_bars`, which wraps the method both these functions and
    `sns.catplot` drive. Whether a hue splits the layer into groups is still
    seaborn's decision rather than the arguments' -- `dodge` defaults to
    `"auto"`, and a hue that repeats the category variable is drawn as a plain
    bar layer wearing a legend -- so the layer is still classified from the
    bars seaborn drew, one level down.

    What remains here is `_draw_quietly` over the whole seaborn call and the
    `wrap_seaborn` that keeps both bindings of each name wrapped. Nothing sets
    the internal context, which is what would silence the plotter patch; the
    `Axes.bar` calls it used to suppress are made inside `plot_bars`.

    Parameters
    ----------
    wrapped : Callable
        The original seaborn function.
    instance : Any
        Unused; seaborn's plotting functions are module level.
    args : tuple
        Positional arguments passed to the original function.
    kwargs : dict
        Keyword arguments passed to the original function.

    Returns
    -------
    Axes
        The axes seaborn drew on, which is what both functions return.

    Examples
    --------
    >>> # Grouped: one container per hue level, one bar per category.
    >>> sns.barplot(data=df, x="day", y="tip", hue="sex")

    >>> # Not grouped: the hue repeats `x`, so each container holds one bar.
    >>> sns.barplot(data=df, x="day", y="tip", hue="day")
    """
    return _draw_quietly(wrapped, args, kwargs)


def sns_categorical_bars(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Any:
    """
    Register every bar panel seaborn draws, whichever interface drew it.

    One registrar for both. ``seaborn.barplot``/``countplot`` and
    ``sns.catplot(kind="bar"/"count")`` share no code above this method --
    ``catplot`` drives ``_CategoricalPlotter`` directly and imports nothing --
    so a patch on the functions reached one of them and a patch here reaches
    both. Measured on three categories (#448)::

        sns.catplot(df, x="g", y="v", kind="bar")    dodged_bar(3), line(2)
        sns.barplot(df, x="g", y="v", ax=ax)         bar(3)

    Two things wrong, and both are the panel being read by the
    matplotlib-level patches alone. `dodged_bar` names a chart that compares
    groups side by side, which a chart with no hue is not, so a reader is
    oriented to a chart that is not there -- ``Axes.bar`` has to guess at that
    from bar widths and positions, because seaborn does not forward the
    decision to it, and here it guessed wrong. And the ``line`` layer is the
    error-bar geometry travelling as a two-sample series of its own, the
    #440 shape.

    Both fall out of registering here: the type comes from
    :func:`_seaborn_bar_type`, which asks the drawn containers rather than the
    arguments, and the error bars are drawn *inside* this method, so the
    internal context set around the draw suppresses them.

    Parameters
    ----------
    wrapped : Callable
        ``_CategoricalPlotter.plot_bars``.
    instance : Any
        The plotter the method is bound to.
    args, kwargs
        The method's own arguments, passed through untouched.

    Returns
    -------
    Any
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax, _ in plotter_panels(instance):
        FigureManager.create_maidr(ax, _seaborn_bar_type(ax))

    return drawn


def _seaborn_bar_type(ax: Axes) -> PlotType:
    """
    Classify a drawn seaborn bar layer as grouped or plain.

    A grouped layer draws one container per hue level, each holding one bar
    per category -- or short of it, where seaborn dropped a ``NaN`` cell
    before drawing (#752). Anything else — a single container, or
    containers that do not line up with the categorical axis — is a plain
    bar layer. The bars are counted against the same tick labels
    `GroupedBarPlot` pairs them with, and a short layer's bars are placed
    against the same tick positions it places them by, so the layer is only
    called grouped when it can be read as one.

    Parameters
    ----------
    ax : Axes
        The axes seaborn drew on.

    Returns
    -------
    PlotType
        `PlotType.DODGED` for a grouped layer, `PlotType.BAR` otherwise.
    """
    # Every bar container on the axes is counted, not only the ones this call
    # drew, so a second bar layer overlaid on the same axes is read as extra
    # groups. That layering is already unrenderable — the first layer re-reads
    # every container here too and raises on the count — so this does not make
    # a working figure wrong. Scoping both to one call's own containers is the
    # fix, and it belongs to whoever takes that on.
    containers = [c for c in ax.containers if isinstance(c, BarContainer)]
    if len(containers) < 2:
        return PlotType.BAR

    # The bar labels sit on y when the bars grow along x.
    level_key = MaidrKey.Y if containers[0].orientation == "horizontal" else MaidrKey.X
    levels = LevelExtractorMixin.extract_level(ax, level_key)
    if not levels:
        return PlotType.BAR

    if all(len(container.patches) == len(levels) for container in containers):
        return PlotType.DODGED

    # A container short of the axis is still a hue level when its bars sit
    # against distinct ticks -- a level that lacks a category is a bar
    # short, and `GroupedBarPlot` reads the bar it lacks as a gap (#752).
    # This used to turn every such layer back, and the plain bar layer it
    # fell to announced the bars' fractional positions, "-0.2", in place of
    # their category and hue names. Only against ticks that are categories:
    # `native_scale=True` leaves the locator to choose breaks, and a bar
    # placed against a break is a bar placed against nothing.
    if not ticks_are_categories(ax, level_key):
        return PlotType.BAR

    positions = LevelExtractorMixin.extract_level_positions(ax, level_key)
    if positions is None or len(positions) != len(levels):
        return PlotType.BAR

    horizontal = containers[0].orientation == "horizontal"
    rows = bars_by_category(containers, positions, horizontal)
    if rows is None:
        return PlotType.BAR

    # Ragged containers can only be a hue split. Equal-length ones short of
    # the axis are either that with a category missing from every level, or
    # the hue that repeats the category -- one container per bar, colouring
    # a plain chart. Side by side is what dodged means, so a category that
    # holds bars of two containers is what tells them apart.
    if not bars_are_ragged(containers) and not shares_a_category(rows):
        return PlotType.BAR

    return PlotType.DODGED


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrap_seaborn("barplot", sns_bar)
wrap_seaborn("countplot", sns_bar)

# And the plotter method beneath both of them, which is the only thing
# `catplot` drives. Wrapped by module path rather than by importing the private
# class, matching how `maidr/patch/boxplot.py` reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_bars",
    sns_categorical_bars,
)

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple, Union

import wrapt
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.barplot import DRAWN_BARS
from maidr.patch.common import common, wrap_seaborn
from maidr.util.mixin import LevelExtractorMixin


def bar(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Union[Axes, BarContainer]:
    """
    Patch function for `Axes.bar` and `Axes.barh`.

    This function patches the bar plotting functions to identify whether the
    plot should be rendered as a normal, stacked, or dodged bar plot.
    It uses the 'bottom' keyword -- or 'left', which is how a horizontal bar
    spells the same thing -- to identify stacked bar plots. For dodged
    plots, it uses robust detection logic that considers both width and
    context to avoid misclassifying simple bar plots with narrow widths as
    dodged plots. Seaborn's bar plots do not come through here — they are
    classified from the bars they drew, in `sns_bar` below.

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
    baseline = kwargs.get("bottom", kwargs.get("left"))
    if baseline is not None:
        plot_type = PlotType.STACKED
    else:
        # Extract width and align parameters
        if len(args) >= 3:
            real_width = args[2]
        else:
            real_width = kwargs.get("width", 0.8)

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
        The width parameter for the bar plot.
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
    Patch function for `seaborn.barplot` and `seaborn.countplot`.

    Whether a hue splits the layer into groups is seaborn's decision, and it
    is not one the arguments alone answer: `dodge` defaults to `"auto"`, and
    a hue that repeats the category variable is drawn as a plain bar layer
    wearing a legend. Seaborn does not forward `hue` or `dodge` to
    `Axes.bar` either — and those inner calls are suppressed as internal
    anyway — so the layer is classified from the bars seaborn drew.

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
    return common(_seaborn_bar_type, wrapped, instance, args, kwargs)


def _seaborn_bar_type(ax: Axes) -> PlotType:
    """
    Classify a drawn seaborn bar layer as grouped or plain.

    A grouped layer draws one container per hue level, each holding one bar
    per category. Anything else — a single container, or containers that do
    not line up with the categorical axis — is a plain bar layer. The bars
    are counted against the same tick labels `GroupedBarPlot` pairs them
    with, so the layer is only called grouped when it can be read as one.

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

    if any(len(container.patches) != len(levels) for container in containers):
        return PlotType.BAR

    return PlotType.DODGED


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrap_seaborn("barplot", sns_bar)
wrap_seaborn("countplot", sns_bar)

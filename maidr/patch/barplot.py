from __future__ import annotations

from typing import Any, Callable, Dict, Tuple, Union

import wrapt
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import PlotType
from maidr.patch.common import common


def bar(
    wrapped: Callable, instance: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Union[Axes, BarContainer]:
    """
    Patch function for bar plots.

    This function patches the bar plotting functions to identify whether the
    plot should be rendered as a normal, stacked, or dodged bar plot.
    It uses the 'bottom' keyword to identify stacked bar plots. For dodged plots,
    it first checks for seaborn-specific indicators (hue parameter with dodge=True),
    then uses robust detection logic that considers both width and context
    to avoid misclassifying simple bar plots with narrow widths as dodged plots.

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
        For seaborn plots, may contain 'hue' and 'dodge' parameters.

    Returns
    -------
    Union[Axes, BarContainer]
        The axes or bar container returned by the original function.

    Examples
    --------
    >>> # For a seaborn dodged (grouped) bar plot:
    >>> sns.barplot(data=df, x='category', y='value', hue='group', dodge=True)
    
    >>> # For a manual dodged (grouped) bar plot, pass numeric x positions:
    >>> x_positions = np.arange(3)
    >>> ax.bar(x_positions, heights, width, label='Group')  # Dodged bar plot.
    """
    plot_type = PlotType.BAR
    
    # Check for stacked plots first (explicit bottom parameter)
    if "bottom" in kwargs:
        bottom = kwargs.get("bottom")
        if bottom is not None:
            plot_type = PlotType.STACKED
    else:
        # Check for seaborn-specific dodged plot indicators first
        # This handles seaborn.barplot with hue and dodge=True
        if ("hue" in kwargs and kwargs.get("dodge", False)) or \
           ("hue" in kwargs and kwargs.get("dodge") is not False):
            plot_type = PlotType.DODGED
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

    return common(plot_type, wrapped, instance, args, kwargs)


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
    if hasattr(ax, 'containers') and len(ax.containers) > 0:
        # If there are existing containers, this might be adding to a group
        if isinstance(width, (int, float)) and float(width) < 0.8:
            return True
    
    # Check for explicit grouping indicators in kwargs
    if 'label' in kwargs and isinstance(width, (int, float)) and float(width) < 0.8:
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
        # Convert to list if needed
        if hasattr(x_positions, '__iter__') and not isinstance(x_positions, str):
            positions = list(x_positions)
        else:
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


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrapt.wrap_function_wrapper("seaborn", "barplot", bar)
wrapt.wrap_function_wrapper("seaborn", "countplot", bar)

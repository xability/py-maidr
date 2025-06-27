from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.context_manager import ContextManager
import uuid
from maidr.core.enum.smooth_keywords import SMOOTH_KEYWORDS
from maidr.util.regression_line_utils import find_smooth_lines_by_label


def regplot(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.regplot to register SCATTER and SMOOTH layers for MAIDR.
    """
    scatter = kwargs.get("scatter", True)
    if scatter:
        ax = common(PlotType.SCATTER, wrapped, instance, args, kwargs)
    else:
        # Prevent any MAIDR layer registration during plotting when scatter=False
        with ContextManager.set_internal_context():
            ax = wrapped(*args, **kwargs)

    axes = ax if isinstance(ax, Axes) else ax.axes if hasattr(ax, "axes") else None
    if axes is not None:
        # Find and register all smooth lines
        smooth_lines = find_smooth_lines_by_label(axes)
        for line in smooth_lines:
            # If line doesn't have a gid yet, assign one and register
            if line.get_gid() is None:
                new_gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(new_gid)
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: ax,
                    instance,
                    args,
                    dict(kwargs, regression_line=line),
                )
            else:
                # Even if it has a gid, register it as a smooth layer
                # This handles the case where patched_plot already assigned a gid
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: ax,
                    instance,
                    args,
                    dict(kwargs, regression_line=line),
                )

    return ax


def patched_plot(wrapped, instance, args, kwargs):
    """
    Patch matplotlib Axes.plot to register SMOOTH layers for MAIDR if the label matches SMOOTH_KEYWORDS.
    """
    # Call the original plot function
    lines = wrapped(*args, **kwargs)

    # Check each line for smooth keywords and register if found
    for line in lines:
        if isinstance(line, Line2D):
            label = line.get_label() or ""
            label_str = str(label)
            # Detect if this is a smooth/regression line by label
            if any(key in label_str.lower() for key in SMOOTH_KEYWORDS):
                # Assign a unique gid if not already set
                if line.get_gid() is None:
                    new_gid = f"maidr-{uuid.uuid4()}"
                    line.set_gid(new_gid)
                # Register as a smooth layer
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: instance,
                    instance,
                    args,
                    dict(kwargs, regression_line=line),
                )

    return lines


# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "regplot", regplot)
# Patch matplotlib Axes.plot for smooth line detection/registration
wrapt.wrap_function_wrapper(Axes, "plot", patched_plot)

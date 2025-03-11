from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import common


def line(wrapped, instance, args, kwargs) -> Axes | list[Line2D]:
    plot_type = PlotType.LINE
    if "label" in kwargs:
        plot_type = PlotType.MULTILINE
    return common(plot_type, wrapped, instance, args, kwargs)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "lineplot", line)

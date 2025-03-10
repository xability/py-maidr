from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import PlotType
from maidr.patch.common import common


def line(wrapped, instance, args, kwargs) -> Axes | list[Line2D]:
    optional_args = {}
    if "label" in kwargs:
        optional_args["label"] = kwargs["label"]
    return common(PlotType.LINE, wrapped, instance, args, optional_args)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "plot", line)

# Patch seaborn function.
wrapt.wrap_function_wrapper("seaborn", "lineplot", line)

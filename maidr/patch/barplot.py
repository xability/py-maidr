from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import PlotType
from maidr.patch.common import common


def bar(wrapped, instance, args, kwargs) -> Axes | BarContainer:
    return common(PlotType.BAR, wrapped, instance, args, kwargs)


# Patch matplotlib functions.
wrapt.wrap_function_wrapper(Axes, "bar", bar)
wrapt.wrap_function_wrapper(Axes, "barh", bar)

# Patch seaborn functions.
wrapt.wrap_function_wrapper("seaborn", "barplot", bar)
wrapt.wrap_function_wrapper("seaborn", "countplot", bar)

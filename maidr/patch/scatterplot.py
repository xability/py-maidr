from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.enum import PlotType
from maidr.patch.common import common, wrap_seaborn


def scatter(wrapped, instance, args, kwargs) -> Axes | PathCollection:
    return common(PlotType.SCATTER, wrapped, instance, args, kwargs)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "scatter", scatter)

# Patch seaborn function.
wrap_seaborn("scatterplot", scatter)

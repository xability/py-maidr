from __future__ import annotations

import sys
from typing import Any


def is_plotnine_plot(obj: Any) -> bool:
    """
    Whether ``obj`` is a plotnine ``ggplot``, without importing plotnine.

    A ``ggplot`` cannot exist unless the package is loaded, so ``sys.modules``
    settles the negative case for free -- the probe
    :func:`maidr.bokeh.utils.is_bokeh_model` uses, for the same reason:
    ``maidr.render`` asks this of every figure, and importing plotnine to
    answer "no" for a matplotlib one would cost every user the import.
    ``.get() is None`` also covers an import blocked with a ``None`` entry.

    Parameters
    ----------
    obj : Any
        The object to check.

    Returns
    -------
    bool
        True for a ``plotnine.ggplot``.
    """
    if sys.modules.get("plotnine") is None:
        return False
    try:
        from plotnine import ggplot
    except ImportError:
        return False
    return isinstance(obj, ggplot)

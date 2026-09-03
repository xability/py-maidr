from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.container import ErrorbarContainer

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _argument, _draw_quietly, _resolve


def errorbar(wrapped, instance, args, kwargs) -> ErrorbarContainer:
    """
    Register an ``Axes.errorbar`` call as a MAIDR error bar layer.

    The container the call returns is handed to the layer rather than looked
    up from the axes afterwards. Two ``errorbar`` calls on one axes leave two
    containers behind, and a layer that searched for "the" container would
    find the first one both times -- describing the first series twice and
    dropping the second without any error to say so.

    Parameters
    ----------
    wrapped : Callable
        The original ``Axes.errorbar``.
    instance : Any
        The Axes the method was bound to.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    ErrorbarContainer
        Whatever the wrapped function returned, unchanged.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Read the centres before drawing. `fmt="none"` renders the intervals
    # without the estimate markers, leaving the container with no data line,
    # and an asymmetric bar is not centred on its own midpoint -- so for that
    # case the arguments are the only place the estimate still exists. They
    # may be column names of `data=`, which matplotlib resolves inside the
    # call this wraps, so they are resolved the same way here.
    data = _argument("data", wrapped, args, kwargs)
    x = _resolve(_argument("x", wrapped, args, kwargs), data)
    y = _resolve(_argument("y", wrapped, args, kwargs), data)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        container = _draw_quietly(wrapped, args, kwargs)

    # Read the axes off `instance` rather than routing through
    # `FigureManager.get_axes`: that helper has no branch for an
    # `ErrorbarContainer`, which is a `Container` rather than an `Artist`, so
    # it would answer None and the failure would surface as a bare "No plot
    # found." rather than as anything to do with error bars.
    #
    # Wrapping `Axes.errorbar` means `instance` is the bound Axes on every
    # call this patch can actually receive. The `getattr` keeps the same shape
    # `lineplot.py` uses rather than asserting, so a wrapper installed on some
    # other holder of the method degrades instead of raising here.
    ax = instance if isinstance(instance, Axes) else getattr(instance, "axes", None)

    FigureManager.create_maidr(ax, PlotType.ERRORBAR, container=container, x=x, y=y)

    return container


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "errorbar", errorbar)

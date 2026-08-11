from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.plot.areaplot import AreaPlot
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly


def stackplot(wrapped, instance, args, kwargs):
    """
    Register an ``Axes.stackplot`` call as a MAIDR area layer.

    The values are taken from the call's own arguments rather than from the
    polygons it draws, and that is the right way round here even though the
    rest of this package reads geometry. ``stackplot`` is handed each series'
    values and accumulates them itself, so the arguments are exactly the
    per-series magnitudes the schema carries -- while the drawn polygon is a
    closed outline, running forward along the baseline and back along the top
    with its endpoints repeated, from which recovering them means undoing both
    the accumulation and the closure.

    Parameters
    ----------
    wrapped : Callable
        The original ``Axes.stackplot``.
    instance : Any
        The Axes the method was bound to.
    args : tuple
        Positional arguments the caller passed: the shared x, then one array
        per series.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    list
        Whatever the wrapped function returned, unchanged.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        collections = _draw_quietly(wrapped, args, kwargs)

    ax = instance if isinstance(instance, Axes) else getattr(instance, "axes", None)
    if ax is None:
        return collections

    x, series = _positions_and_series(args, kwargs)
    if x is None or not series:
        # `stackplot(y)` with no x, or a call this cannot read. Leaving it
        # unregistered is what happened before this patch existed, and is
        # better than describing a shape that was not established.
        return collections

    FigureManager.create_maidr(
        ax,
        AreaPlot.resolve_type(series),
        x=x,
        series=series,
        labels=list(kwargs.get("labels") or []),
        collections=list(collections or []),
    )

    return collections


def _positions_and_series(args: tuple, kwargs: dict):
    """
    Split a ``stackplot`` call into its shared x and its per-series values.

    ``stackplot(x, y1, y2)`` and ``stackplot(x, y)`` with a 2-D ``y`` are both
    valid and mean the same thing, so the series arrive two ways. There is no
    keyword form: ``stackplot``'s own ``**kwargs`` are forwarded to
    ``fill_between``, and a call with no positional series is rejected by
    matplotlib before it reaches here.

    Parameters
    ----------
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    tuple
        The x array and the list of per-series arrays, or ``(None, [])`` when
        the call is not one this can read.
    """
    if not args:
        return None, []

    x = args[0]
    rest = list(args[1:])

    if not rest:
        # `stackplot(x)` alone. Matplotlib rejects it before this is reached
        # on current versions, and there is nothing to describe either way.
        return None, []

    if len(rest) == 1 and _is_two_dimensional(rest[0]):
        # `stackplot(x, y)` with a 2-D y stacks its rows.
        return x, [row for row in rest[0]]

    return x, rest


def _is_two_dimensional(values) -> bool:
    """
    Check whether a series argument holds several series rather than one.

    Parameters
    ----------
    values : Any
        A positional argument after the x.

    Returns
    -------
    bool
        True when the argument is a sequence of sequences.
    """
    try:
        first = values[0]
    except (IndexError, KeyError, TypeError):
        return False

    return hasattr(first, "__len__") and not isinstance(first, (str, bytes))


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "stackplot", stackplot)

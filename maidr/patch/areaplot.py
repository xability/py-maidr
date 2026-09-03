from __future__ import annotations

import numpy as np
import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.plot.areaplot import AreaPlot
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, _resolve


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

    A third spelling names columns: ``stackplot("x", "a", "b", data=df)``
    reaches matplotlib's `_preprocess_data` with strings where the arrays go,
    and the patch sits outside that decorator, so it sees the names. They are
    resolved against ``data`` here the way matplotlib resolves them.

    Parameters
    ----------
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed. Only ``data`` is read.

    Returns
    -------
    tuple
        The x array and the list of per-series arrays, or ``(None, [])`` when
        the call is not one this can read.
    """
    if not args:
        return None, []

    data = kwargs.get("data")
    x = _resolve(args[0], data)
    rest = [_resolve(argument, data) for argument in args[1:]]

    if not rest:
        # `stackplot(x)` alone. Matplotlib rejects it before this is reached
        # on current versions, and there is nothing to describe either way.
        return None, []

    if len(rest) == 1:
        rows = _rows_of(rest[0])
        if rows is not None:
            # `stackplot(x, y)` with a 2-D y stacks its rows.
            return x, rows

    return x, rest


def _rows_of(values) -> list | None:
    """
    Split a series argument into rows, when it holds several series.

    Asks numpy rather than indexing or iterating the argument directly,
    because for a ``DataFrame`` both of those mean the columns. ``values[0]``
    is the column labelled ``0`` -- absent for named columns, and the wrong
    axis when present -- and iterating yields the labels themselves rather
    than any data. Matplotlib reads a ``DataFrame`` here as rows, so a reading
    that took it for columns would describe a chart nobody drew, and would do
    so without raising.

    Parameters
    ----------
    values : Any
        A positional argument after the x.

    Returns
    -------
    list or None
        One array per series, or None when the argument is a single series.
    """
    try:
        array = np.asarray(values)
    except ValueError:
        # Ragged input. Matplotlib rejects it too, and it has already done so
        # by the time this runs, so there is nothing here to describe.
        return None

    if array.ndim != 2:
        return None

    return list(array)


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "stackplot", stackplot)

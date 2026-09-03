from __future__ import annotations

from typing import Any

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import Collection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.patch.common import _argument, _draw_quietly, _resolve
from maidr.util.confidence_band import DRAWN_ALONG_Y


def _baseline_is_zero(wrapped, args: tuple, kwargs: dict, name: str, data: Any) -> bool:
    """
    Whether the band runs from the value axis' zero to a single curve.

    ``fill_between(x, y1)`` fills from zero up to ``y1``. That is an area
    chart, and it measures exactly what a one-series ``stackplot`` band
    measures -- a magnitude per position, from a baseline the reader can
    assume.

    Anything else is a band between two curves, which is a different claim.
    ``fill_between(x, lo, hi)`` draws the *gap*, and its content is the
    distance between the two edges rather than the height of either; read as
    an area it would announce ``hi`` as a magnitude and drop ``lo`` entirely.
    A constant second edge is the same problem in miniature: the heights are
    measured from somewhere the announcement would not mention.

    Parameters
    ----------
    wrapped : Callable
        The original ``fill_between`` or ``fill_betweenx``, used for its
        parameter order.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.
    name : str
        ``"y2"`` for ``fill_between``, ``"x2"`` for ``fill_betweenx``.
    data : Any
        The call's ``data`` argument, against which a column name is resolved.

    Returns
    -------
    bool
        True when the second edge is absent or an explicit zero.
    """
    other = _resolve(_argument(name, wrapped, args, kwargs), data)
    if other is None:
        return True
    try:
        values = np.asarray(other, dtype=float)
    except (TypeError, ValueError):
        return False
    # An array of zeros is the same chart as the default, spelled out. Only
    # a *non-zero* edge changes what the heights are measured from.
    return bool(values.size > 0 and np.all(values == 0))


def _fills_the_whole_range(wrapped, args: tuple, kwargs: dict, data: Any) -> bool:
    """
    Whether the fill covers every position, rather than a masked subset.

    ``where=`` fills only where the mask holds, leaving the chart blank
    elsewhere -- ``fill_between(x, y, where=y > 0)`` draws three separate
    bands out of an eight-point series, and matplotlib returns three paths
    for it rather than one.

    An area layer is one continuous series, so announcing the masked call as
    one would report every position as filled, gaps included: a complete,
    confident description of a chart that was not drawn. Which is the same
    thing declining the two-curve form avoids, so it is declined the same
    way.

    A mask that holds everywhere is not a mask. It draws the single band the
    default draws, and reads as one.

    Parameters
    ----------
    wrapped : Callable
        The original function, used for its parameter order.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.
    data : Any
        The call's ``data`` argument, against which a column name is resolved.

    Returns
    -------
    bool
        True when no mask was given, or the mask holds at every position.
    """
    where = _resolve(_argument("where", wrapped, args, kwargs), data)
    if where is None:
        return True
    try:
        mask = np.asarray(where, dtype=bool)
    except (TypeError, ValueError):
        return False
    return bool(mask.size > 0 and np.all(mask))


def _magnitudes(
    wrapped, args: tuple, kwargs: dict, position: str, value: str, data: Any
):
    """
    Read the positions and the one curve a filled area is drawn from.

    Taken from the call's own arguments rather than from the polygon, the
    same way ``stackplot`` reads its series and for the same reason: the drawn
    artist is a closed outline, running forward along the curve and back along
    the baseline with its endpoints repeated, so recovering the series from it
    means undoing the closure.

    Parameters
    ----------
    wrapped : Callable
        The original function, used for its parameter order.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.
    position : str
        The parameter naming the shared axis: ``"x"`` or ``"y"``.
    value : str
        The parameter naming the curve: ``"y1"`` or ``"x1"``.
    data : Any
        The call's ``data`` argument, against which a column name is resolved.

    Returns
    -------
    tuple
        The positions and the values, or ``(None, None)`` when either is
        missing or they do not line up.
    """
    positions = _resolve(_argument(position, wrapped, args, kwargs), data)
    values = _resolve(_argument(value, wrapped, args, kwargs), data)
    if positions is None or values is None:
        return None, None

    positions = np.atleast_1d(np.asarray(positions, dtype=object))
    values = np.atleast_1d(np.asarray(values))
    if len(positions) != len(values):
        # A scalar `y1` broadcast against the positions is a horizontal band,
        # not a series. Nothing here can describe it, and pairing the two
        # lists by index would silently describe a one-point chart.
        return None, None

    return positions, values


def _tagged(collection: Collection, transposed: bool) -> Collection:
    """
    Record which way a region was shaded, on the region itself.

    Asked later by :func:`maidr.util.confidence_band.band_edges_at`, which
    reads the lowest and highest vertex **at each x** and so answers for a
    vertical interval only. A region shaded the other way about has no such
    interval to read, and bracketing does not catch it: a horizontal band
    around a horizontal line surrounds that line vertically too, because it
    surrounds it. Measured, ``plot(val, pos)`` under
    ``fill_betweenx(pos, lo, hi)`` came out announcing the polygon's vertical
    extent as ``yMin``/``yMax`` -- on the axis carrying the *positions*, which
    the chart states no uncertainty about at all (#601).

    Recorded here rather than worked out there because ``fill_betweenx`` *is*
    the horizontal spelling: no inference is involved, which is the argument
    :data:`maidr.core.plot.outlined_histogram.OUTLINE_HORIZONTAL` makes for
    the same class of question.

    Set on **every** region either spelling draws, including the ones drawn
    inside another patch and the ones the declines below leave unregistered.
    A region carries no layer of its own and is still read as some line's
    band, so the tag has to outlive the decision not to register it. Setting
    it unconditionally is also what lets its absence mean one thing only:
    that this patch did not draw the region.

    Parameters
    ----------
    collection : matplotlib.collections.Collection
        The region the wrapped call drew.
    transposed : bool
        True for ``fill_betweenx``.

    Returns
    -------
    matplotlib.collections.Collection
        The same object, tagged.
    """
    setattr(collection, DRAWN_ALONG_Y, transposed)
    return collection


def _fill(
    wrapped,
    instance,
    args,
    kwargs,
    position: str,
    value: str,
    other: str,
    transposed: bool = False,
):
    """
    Draw a patched fill call and register the area it produced, when it is one.

    Only the baseline-to-curve form is registered. The two-curve form draws an
    interval, whose content is the gap rather than either edge, and MAIDR has
    no reading for it that would not invent an estimate the chart never drew
    -- so it is left unregistered and the figure keeps its static image, as it
    did before this patch existed (#339).

    Parameters
    ----------
    wrapped : Callable
        The original ``fill_between`` or ``fill_betweenx``.
    instance : Any
        The Axes the method was bound to.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.
    position : str
        The parameter naming the shared axis.
    value : str
        The parameter naming the curve.
    other : str
        The parameter naming the second edge.
    transposed : bool
        True for ``fill_betweenx``, whose positions run down the page and
        whose magnitudes run out along x. Passed through to the layer, which
        exchanges the two axis titles -- see ``AreaPlot.render``.

    Returns
    -------
    matplotlib.collections.Collection
        Whatever the wrapped function returned, unchanged.
    """
    # Don't proceed if the call is made internally by the patched function.
    #
    # `stackplot` draws its bands through here and reads them itself, but it
    # is not what this guard catches: every band it draws carries two explicit
    # edges (`fill_between(x, stack[i], stack[i + 1])`), so the baseline test
    # below declines them all anyway. Kept as the convention every patch in
    # this package follows, and because "the caller happens to pass two edges"
    # is a property of matplotlib's `stackplot` rather than a rule about
    # nested draws.
    if ContextManager.is_internal_context():
        return _tagged(_draw_quietly(wrapped, args, kwargs), transposed)

    with ContextManager.set_internal_context():
        collection = _tagged(_draw_quietly(wrapped, args, kwargs), transposed)

    # Every argument below is read off the call rather than off the polygon,
    # and `fill_between("x", "y1", data=df)` passes them as column names. Read
    # `data` once here so each reader resolves against the same frame.
    data = _argument("data", wrapped, args, kwargs)

    if not _baseline_is_zero(wrapped, args, kwargs, other, data):
        return collection

    if not _fills_the_whole_range(wrapped, args, kwargs, data):
        return collection

    positions, values = _magnitudes(wrapped, args, kwargs, position, value, data)
    if positions is None:
        return collection

    ax = instance if isinstance(instance, Axes) else getattr(instance, "axes", None)
    if ax is None:
        return collection

    from maidr.core.figure_manager import FigureManager

    FigureManager.create_maidr(
        ax,
        PlotType.AREA,
        x=positions,
        series=[values],
        labels=[kwargs["label"]] if isinstance(kwargs.get("label"), str) else [],
        collections=[collection],
        transposed=transposed,
    )

    return collection


def fill_between(wrapped, instance, args, kwargs) -> Collection:
    """Register an ``Axes.fill_between`` call as a MAIDR area layer."""
    return _fill(wrapped, instance, args, kwargs, "x", "y1", "y2")


def fill_betweenx(wrapped, instance, args, kwargs) -> Collection:
    """
    Register an ``Axes.fill_betweenx`` call as a MAIDR area layer.

    The same chart with the axes exchanged: the shared axis is ``y`` and the
    magnitude runs along ``x``. Emitted as an area either way, since what a
    band measures does not change with which way it is drawn -- but which
    axis each number is *read against* does, and ``transposed`` is what says
    so. See :meth:`maidr.core.plot.areaplot.AreaPlot.render` for what it
    moves and why that rather than the data (#566).
    """
    return _fill(wrapped, instance, args, kwargs, "y", "x1", "x2", transposed=True)


# Patch matplotlib functions. `AreaPlot` is reached through the factory, so
# both land as the same layer type a one-series `stackplot` produces.
wrapt.wrap_function_wrapper(Axes, "fill_between", fill_between)
wrapt.wrap_function_wrapper(Axes, "fill_betweenx", fill_betweenx)

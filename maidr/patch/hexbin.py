from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import Collection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _argument, _draw_quietly


def _fill_label(wrapped, args: tuple, kwargs: dict) -> str:
    """
    Name the quantity ``hexbin`` encoded as fill.

    Usually it is the count of points that fell in the bin, and usually saying
    so is the whole of it. Two of ``hexbin``'s own arguments change what the
    colour means, and neither changes anything else a reader could notice:

    * ``C`` replaces the count with ``reduce_C_function`` applied to the values
      given for the points in the bin -- a mean by default, which is not a
      count and is routinely not even an integer.
    * ``bins``, given as a number or a sequence of edges, discretises the
      counts and colours each bin by *which* interval its count landed in.
      ``get_array()` then holds an interval index. A three-point bin and a
      nine-point bin can both read 1.

    Announcing either as "count" would be wrong in the way that is hardest to
    catch: the number is plausible, the chart is otherwise sound, and nothing
    contradicts it. ``bins="log"`` is not one of these -- it only installs a
    log norm for the colouring and leaves the array as raw counts.

    Parameters
    ----------
    wrapped : Callable
        The original ``Axes.hexbin``, used for its parameter order.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    str
        The label for the ``z`` axis.
    """
    if _argument("C", wrapped, args, kwargs) is not None:
        return "value"

    bins = _argument("bins", wrapped, args, kwargs)
    if bins is not None and not (isinstance(bins, str) and bins == "log"):
        return "count bin"

    return "count"


def hexbin(wrapped, _, args, kwargs) -> Collection:
    """
    Draw a patched ``Axes.hexbin`` call and register the lattice with MAIDR.

    The drawn collection is handed to the layer rather than searched for on the
    axes: ``marginals=True`` draws two more ``PolyCollection``s, and a violin
    body or a ``fill_between`` band on the same axes is one as well, so the
    class does not identify the lattice while the return value does.

    Parameters
    ----------
    wrapped : Callable
        The original ``Axes.hexbin``.
    _ : Any
        The instance wrapt bound the patched function to. Unused, and named
        for that.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    matplotlib.collections.Collection
        Whatever the wrapped function returned, unchanged.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # MAIDR's own, and not a parameter of the function being wrapped:
    # `hexbin` forwards what it does not recognise to the collection, which
    # raises from somewhere the caller cannot connect back to MAIDR.
    z_label = kwargs.pop("z_label", None)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        collection = _draw_quietly(wrapped, args, kwargs)

    ax = FigureManager.get_axes(collection)
    FigureManager.create_maidr(
        ax,
        PlotType.HEXBIN,
        collection=collection,
        z_label=z_label or _fill_label(wrapped, args, kwargs),
    )

    return collection


# Patch matplotlib function. `seaborn.jointplot(kind="hex")` draws through
# this same entry point, so it is covered by the one patch.
wrapt.wrap_function_wrapper(Axes, "hexbin", hexbin)

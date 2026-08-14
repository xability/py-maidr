from __future__ import annotations

import numpy as np
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
      ``get_array()`` then holds an interval index. A three-point bin and a
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
    reduced = _argument("C", wrapped, args, kwargs) is not None

    # `bins` is read first because it wins. matplotlib applies it *after* the
    # count-or-reduce step and overwrites whatever that produced, so a numeric
    # `bins` alongside `C` leaves interval indices where the reduced values
    # were -- measured, not inferred: `C=` alone gives float64 spanning 79 to
    # 114, and `C=` with `bins=5` gives int64 spanning 0 to 4.
    bins = _argument("bins", wrapped, args, kwargs)
    if bins is not None and not (isinstance(bins, str) and bins == "log"):
        # Which quantity was discretised still matters. "count bin" for a
        # chart that never counted anything would be its own small lie.
        return "value bin" if reduced else "count bin"

    return "value" if reduced else "count"


def _is_readable(wrapped, args, kwargs, collection: Collection) -> bool:
    """
    Whether the drawn lattice can be described truthfully.

    Two ways it cannot, and both would otherwise produce a chart that reads
    confidently and says something false.

    **A log axis.** ``hexbin`` takes its own ``xscale``/``yscale``, and bins in
    the transformed space. On matplotlib 3.10 the offsets come back in that
    space too, so a bin centred at x = 3.4 would be announced as ``0.53``:
    right structure, right counts, wrong coordinates, and nothing in the
    output to contradict them. On 3.9 the same call returns one path per
    hexagon and a single placeholder offset, so the centres are not in
    ``get_offsets()`` at all.

    Un-transforming the 3.10 case would be an assumption about matplotlib's
    internals that the 3.9 case shows is not stable, so a log-scaled hexbin is
    declined on both. Note this reads ``hexbin``'s own arguments, not the
    axis: an axes that was *already* log-scaled makes matplotlib bin linearly,
    and those offsets are honest data coordinates.

    **A count list that does not match the bins.** They are filtered together
    by ``mincnt``, so they agree on every release this reads -- but the whole
    scheme indexes one by the other, and a silent mismatch would pair a bin
    with a stranger's count.

    Parameters
    ----------
    wrapped : Callable
        The original ``Axes.hexbin``, used for its parameter order.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.
    collection : matplotlib.collections.Collection
        The collection the call drew.

    Returns
    -------
    bool
        True when the lattice can be read.
    """
    for axis in ("xscale", "yscale"):
        if _argument(axis, wrapped, args, kwargs) == "log":
            return False

    values = collection.get_array()
    if values is None:
        return False

    offsets = np.asarray(collection.get_offsets())
    return offsets.ndim == 2 and len(offsets) > 0 and len(offsets) == len(values)


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
    # Lifted before the recursion guard, not after. `hexbin` forwards what it
    # does not recognise to the collection, so a `z_label` still in `kwargs`
    # on the internal-context path would reach matplotlib and raise from
    # somewhere the caller cannot connect back to MAIDR. There is no live path
    # that reaches this in an internal context today; popping first costs
    # nothing and means there does not have to be one.
    z_label = kwargs.pop("z_label", None)

    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        collection = _draw_quietly(wrapped, args, kwargs)

    if not _is_readable(wrapped, args, kwargs, collection):
        # Left unregistered, so the figure renders as it did before this patch
        # existed: a static image, with no layer claiming to describe it.
        # `stackplot` declines the calls it cannot read the same way, and for
        # the same reason -- saying nothing beats describing a shape that was
        # not established.
        return collection

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

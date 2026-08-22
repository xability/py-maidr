from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.patch.common import _draw_quietly


@wrapt.patch_function_wrapper(Axes, "triplot")
def triplot(wrapped, instance, args, kwargs):
    """
    Draw a patched ``Axes.triplot`` and register nothing for it.

    A triangulation mesh is not a series, and until this it was announced as
    one. ``triplot`` draws the mesh by handing the flattened edge list to
    ``Axes.plot``::

        tri_lines = ax.plot(tri_lines_x.ravel(), tri_lines_y.ravel(), ...)

    so the line patch saw an ordinary plot call and registered a LINE layer.
    Measured on eight scattered points: a line of **thirty-two** points, x
    running 0.04 -> 0.64 -> 0.04 -> 0.27, the first point appearing again as
    the third (#572).

    That is the mesh's edge traversal -- three vertices per triangle and a
    separator -- not a sequence of observations. A line trace tells a reader
    there is a trend through ordered values and offers to play it as one;
    here there is no order, points repeat, and the count bears no relation to
    the data. Worse than being unread, because nothing about it looks wrong.

    Declined rather than given a reading. The mesh states which points were
    joined, and no trace in the core carries that -- the same conclusion
    `quiver`, `barbs` and `streamplot` reach for a vector at a place. A
    `triplot` is usually drawn *under* a `tricontour`, and that half reads;
    on its own the figure falls back to a picture, which is what a chart maidr
    cannot read is supposed to do.

    Suppressed by drawing inside the internal context, so the inner ``plot``
    calls register nothing -- the decline has to happen here rather than at
    extraction, because a layer that refuses while the schema is built takes
    the whole figure with it (#564).

    Parameters
    ----------
    wrapped : Callable
        ``Axes.triplot``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    list
        Whatever ``triplot`` returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.container import StemContainer

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.lollipop import DRAWN_STEM, marks
from maidr.patch.common import _draw_quietly


@wrapt.patch_function_wrapper(Axes, "stem")
def stem(wrapped, instance, args, kwargs) -> StemContainer:
    """
    Draw a patched ``Axes.stem`` and register the lollipop chart it produced.

    The internal context is what makes this a *replacement* reading rather
    than an extra one. ``Axes.stem`` draws its marks and its baseline by
    calling ``Axes.plot`` twice, and both of those are patched: left alone,
    the chart registers a line layer whose second series is the baseline --
    a flat two-point segment at the bottom of the frame, announced as data
    (#574). Drawing quietly and registering once here is the same shape the
    triangulation patch uses to decline a mesh, applied to a chart that has
    a reading rather than none.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.stem``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    StemContainer
        Whatever ``stem`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        container = _draw_quietly(wrapped, args, kwargs)

    if not isinstance(container, StemContainer):
        return container

    # A chart with nothing drawable is not registered, rather than registered
    # empty: a layer a reader can walk into and find no points is the
    # phantom-layer shape of #421. `ax.stem([], [])` is the plain case, and
    # a series that is entirely non-finite is the one that looks drawn.
    if not marks(container):
        return container

    ax = FigureManager.get_axes(container.markerline)
    kwargs.pop("ax", None)
    FigureManager.create_maidr(
        ax,
        PlotType.LOLLIPOP,
        **dict(kwargs, **{DRAWN_STEM: container}),
    )

    return container
